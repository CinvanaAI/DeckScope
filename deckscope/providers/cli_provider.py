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

PRESETS = {
    # --strict-mcp-config with no servers means no MCP tools are loaded.
    "claude": ["claude", "-p", "--output-format", "text",
               "--strict-mcp-config", "--mcp-config", "{}"],
    "codex":  ["codex", "exec", "-"],
    "gemini": ["gemini", "-p"],
    "ollama": ["ollama", "run"],
}

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
        preset = self.config.extra.get("preset") or self.model or "claude"
        self.argv: List[str] = list(
            self.config.extra.get("command") or PRESETS.get(preset, [preset])
        )
        if preset == "ollama" and self.config.extra.get("ollama_model"):
            self.argv.append(self.config.extra["ollama_model"])
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
