"""Drive a locally installed agent CLI — no API key, uses the user's own subscription.

Works with any CLI that accepts a prompt on stdin and prints a reply to stdout.
Presets: `claude` (Claude Code), `codex`, `gemini`, `ollama`.

A caution specific to this backend. The other providers send text to an API and
get text back; the worst an injected instruction can do is bias the analysis. An
agent CLI is different: depending on how it is configured it may be able to read
files, write files, run shell commands, and reach the network. Deck content
reaching one of those is no longer only an analysis-quality problem.

So this provider:

  * passes no-tool / non-interactive flags where the CLI supports them
  * runs in a fresh empty temporary directory, never the user's project folder,
    so a relative path in an injected instruction has nothing to reach
  * clears the environment down to a minimal set, so credentials in the parent
    environment are not inherited by the child
  * hard-caps the runtime

These reduce the blast radius; they do not eliminate it, because DeckScope does
not control the CLI's own configuration. `sandbox=False` disables them for anyone
who has read this and decided otherwise.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import List, Optional

from ..config import ProviderConfig
from .base import Completion, LLMProvider, ProviderError

#: Flags that turn each CLI into a plain text-in/text-out completer.
#:
#: This matters more than it looks. Every other provider sends text to an API and
#: gets text back, so the worst an injection can do is bias the analysis. An agent
#: CLI may hold filesystem, shell and network tools, and deck content reaching one
#: of those is no longer only an analysis problem. Where the CLI exposes controls,
#: they are used; where it does not, `sandbox` refuses to run it against untrusted
#: input unless explicitly overridden.
PRESETS = {
    # --strict-mcp-config with an empty config loads no MCP servers;
    # --disallowedTools blocks the built-in filesystem and shell tools.
    "claude": ["claude", "-p", "--output-format", "text",
               "--strict-mcp-config", "--mcp-config", "{}",
               "--disallowedTools", "Bash,Edit,Write,Read,WebFetch,WebSearch,"
                                    "NotebookEdit,Glob,Grep"],
    # read-only sandbox, never prompt for approval
    "codex":  ["codex", "exec", "--sandbox", "read-only",
               "--ask-for-approval", "never", "-"],
    "gemini": ["gemini", "-p"],
    "ollama": ["ollama", "run"],
}

#: Presets DeckScope cannot verifiably restrict. Running these against a deck from
#: an untrusted source is a decision the operator has to make deliberately.
UNRESTRICTED_PRESETS = {"gemini", "ollama"}

#: Environment variables a child CLI legitimately needs. Everything else — and in
#: particular every *_API_KEY and *_TOKEN in the parent environment — is dropped.
ENV_ALLOWLIST = (
    "PATH", "HOME", "USERPROFILE", "SystemRoot", "COMSPEC", "TEMP", "TMP",
    "LANG", "LC_ALL", "TZ", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
    "PYTHONIOENCODING",
)


class CLIProvider(LLMProvider):
    """Zero-key option: shells out to an agent CLI already signed in on this machine."""

    name = "cli"
    default_model = "claude"
    catalog = [
        ("claude", "Claude Code CLI — uses your existing Claude subscription"),
        ("ollama", "Local Ollama model — free and offline"),
        ("codex", "OpenAI Codex CLI"),
        ("gemini", "Google Gemini CLI"),
    ]

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        self.sandbox = bool(self.config.extra.get("sandbox", True))
        self.allow_unrestricted = bool(
            self.config.extra.get("allow_unrestricted_cli", False))
        preset = self.config.extra.get("preset") or self.model or "claude"
        self.preset = preset
        self.argv: List[str] = list(
            self.config.extra.get("command") or PRESETS.get(preset, [preset])
        )
        if preset == "ollama" and self.config.extra.get("ollama_model"):
            self.argv.append(self.config.extra["ollama_model"])
        if (self.sandbox and preset in UNRESTRICTED_PRESETS
                and not self.config.extra.get("command")
                and not self.allow_unrestricted):
            raise ProviderError(
                f"DeckScope cannot verify that the `{preset}` CLI runs without tools, "
                f"so it will not send deck content to it by default — an injected "
                f"instruction reaching a tool-capable agent is a different class of "
                f"problem from a biased report.\n\n"
                f"Either use a preset DeckScope can restrict (`claude`, `codex`), use "
                f"an API provider, or accept the risk explicitly with:\n"
                f"  provider: {{name: cli, extra: {{preset: {preset}, "
                f"allow_unrestricted_cli: true}}}}")

        exe = self.argv[0]
        if not shutil.which(exe):
            raise ProviderError(
                f"`{exe}` is not installed or not on your PATH. Install it, or pick a "
                f"different AI connection with `deckscope setup`."
            )

    def _child_env(self) -> Optional[dict]:
        """A minimal environment, so the child does not inherit our secrets."""
        if not self.sandbox:
            return None
        import os

        env = {k: os.environ[k] for k in ENV_ALLOWLIST if k in os.environ}
        env.update(self.config.extra.get("env") or {})
        return env

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        import tempfile

        prompt = system + "\n\n" + "\n\n".join(
            f"[{m.role}]\n{m.content}" for m in messages
        )
        # A fresh empty directory per call. If an injected instruction persuades
        # the CLI to read or write a relative path, this is what it finds.
        ctx = (tempfile.TemporaryDirectory(prefix="deckscope_cli_")
               if self.sandbox else None)
        try:
            proc = subprocess.run(
                self.argv, input=prompt, capture_output=True, text=True,
                timeout=self.config.timeout,
                cwd=ctx.name if ctx else None,
                env=self._child_env(),
            )
        except subprocess.TimeoutExpired:
            raise ProviderError(
                f"`{self.argv[0]}` did not respond within {self.config.timeout}s."
            ) from None
        finally:
            if ctx:
                try:
                    ctx.cleanup()
                except Exception:  # noqa: BLE001
                    pass
        if proc.returncode != 0:
            raise ProviderError(
                f"`{self.argv[0]}` exited {proc.returncode}: {proc.stderr[:500]}"
            )
        return Completion(text=proc.stdout, model=f"cli:{self.argv[0]}")
