"""Copy-paste mode: works with ANY chat AI, including ones with no API at all.

Each agent step writes its prompt to a file (and to the clipboard where possible),
tells you to paste it into whatever assistant you use, then waits for you to save
the reply back. Slower, but it costs nothing beyond a subscription you already have
and it works with assistants that have no API.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from ..config import ProviderConfig
from ..console import out as _out
from .base import Completion, LLMProvider


class ManualProvider(LLMProvider):
    name = "manual"
    default_model = "human-in-the-loop"
    catalog = [("human-in-the-loop", "Paste prompts into any chat AI yourself")]

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        self.dir = Path(self.config.extra.get("exchange_dir", "./deckscope_exchange"))
        self.dir.mkdir(parents=True, exist_ok=True)
        self.step = 0
        self.poll = float(self.config.extra.get("poll_seconds", 2))

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        self.step += 1
        prompt = system + "\n\n" + "\n\n".join(
            f"[{m.role}]\n{m.content}" for m in messages
        )
        pfile = self.dir / f"step{self.step:02d}_prompt.txt"
        rfile = self.dir / f"step{self.step:02d}_response.txt"
        pfile.write_text(prompt, encoding="utf-8")
        _try_clipboard(prompt)

        _out("\n" + "=" * 70)
        _out(f"  STEP {self.step} — your turn")
        _out("=" * 70)
        _out(f"  1. The prompt is on your clipboard (and saved at {pfile}).")
        _out("  2. Paste it into ChatGPT, Claude, Gemini — whichever you use.")
        _out(f"  3. Save the FULL reply into:\n     {rfile}")
        _out("  4. Come back here and press Enter.")
        _out("=" * 70)
        try:
            input("  Waiting... press Enter once the reply file is saved: ")
        except EOFError:
            pass
        while not rfile.exists():
            _out(f"  Still don't see {rfile.name}. Waiting...")
            time.sleep(self.poll)
            try:
                input("  Press Enter to check again: ")
            except EOFError:
                break
        text = rfile.read_text(encoding="utf-8") if rfile.exists() else ""
        return Completion(text=text, model="manual")

    def health_check(self):
        return {"ok": True, "provider": self.name, "model": self.model,
                "reply": "copy-paste mode is always available"}


def _try_clipboard(text: str) -> bool:
    import shutil
    import subprocess

    for cmd in (["pbcopy"], ["clip"], ["xclip", "-selection", "clipboard"], ["wl-copy"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text, text=True, check=True)
                return True
            except Exception:  # noqa: BLE001
                continue
    return False
