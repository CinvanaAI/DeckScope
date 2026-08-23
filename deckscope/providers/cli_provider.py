"""Drive a locally installed agent CLI — no API key, uses the user's own subscription.

Works with any CLI that accepts a prompt on stdin and prints a reply to stdout.
Presets: `claude` (Claude Code), `codex`, `gemini`, `ollama`.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import List, Optional

from ..config import ProviderConfig
from .base import Completion, LLMProvider, ProviderError

PRESETS = {
    "claude": ["claude", "-p", "--output-format", "text"],
    "codex":  ["codex", "exec", "-"],
    "gemini": ["gemini", "-p"],
    "ollama": ["ollama", "run"],
}


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

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        prompt = system + "\n\n" + "\n\n".join(
            f"[{m.role}]\n{m.content}" for m in messages
        )
        try:
            proc = subprocess.run(
                self.argv, input=prompt, capture_output=True, text=True,
                timeout=self.config.timeout,
            )
        except subprocess.TimeoutExpired:
            raise ProviderError(
                f"`{self.argv[0]}` did not respond within {self.config.timeout}s."
            ) from None
        if proc.returncode != 0:
            raise ProviderError(
                f"`{self.argv[0]}` exited {proc.returncode}: {proc.stderr[:500]}"
            )
        return Completion(text=proc.stdout, model=f"cli:{self.argv[0]}")
