"""Bring-your-own-model mode: works with ANY assistant, including ones with no API.

Two ways to use it, and they are the same mechanism.

**Interactive (a person at a keyboard).** Each step writes its prompt to a file
and to the clipboard, tells you to paste it into whichever chat AI you already
pay for, and waits while you save the reply back. Slower than an API, but it
costs nothing beyond a subscription you already have.

**Non-interactive (a script or an agent at the other end).** The same spool
without the prompts to press Enter: DeckScope writes the prompt, blocks until an
answer file appears, and carries on. Anything that can watch a directory can
drive the whole pipeline this way with no API key at all.

**Answers are cached by prompt content, not by step number.** This is what makes
the mode usable rather than merely possible. A copy-paste run of the full
pipeline is a dozen exchanges; before, closing the terminal threw all of them
away, and a re-run started from step one. Now every answered prompt is stored
under the hash of the prompt text, so re-running replays what has already been
answered and stops at the first genuinely new question. Close the laptop, come
back tomorrow, run the same command: it picks up where you left it.

Hashing the prompt rather than counting steps also means an identical prompt
issued twice — which happens whenever a panel convenes several panelists on the
same deck — is asked of you once.

Both modes are strict about one thing: an unanswered prompt is an error, never an
empty completion. Returning "" would flow into the JSON repair loop and surface
three retries later as a parse failure, which describes the wrong problem.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from ..config import ProviderConfig
from ..console import out as _out
from .base import Completion, LLMProvider, ProviderError


def _env_flag(name: str) -> Optional[bool]:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() not in ("", "0", "false", "no")


class ManualProvider(LLMProvider):
    """Prompts out to a directory, answers back from the same directory."""

    name = "manual"
    default_model = "human-in-the-loop"
    catalog = [("human-in-the-loop", "Paste prompts into any chat AI yourself")]

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        extra = self.config.extra

        # The environment is consulted as well as the config because `deckscope
        # eval` builds its own ProviderConfig and has nowhere to thread `extra`
        # through. An agent driving the suite sets these and needs no code change
        # anywhere else.
        self.dir = Path(
            os.environ.get("DECKSCOPE_MANUAL_DIR")
            or extra.get("exchange_dir", "./deckscope_exchange"))
        self.asked = self.dir / "asked"
        self.answers = self.dir / "answers"
        for d in (self.dir, self.asked, self.answers):
            d.mkdir(parents=True, exist_ok=True)

        env_interactive = _env_flag("DECKSCOPE_MANUAL_INTERACTIVE")
        self.interactive = (extra.get("interactive", True)
                            if env_interactive is None else env_interactive)

        self.poll = float(os.environ.get("DECKSCOPE_MANUAL_POLL")
                          or extra.get("poll_seconds", 2))
        self.timeout = float(os.environ.get("DECKSCOPE_MANUAL_TIMEOUT")
                             or extra.get("timeout_seconds", 3600))

        # Only used to label files for a human reading the spool. Identity comes
        # from the prompt hash, so a tag collision cannot cross answers over.
        self.run_tag = (os.environ.get("DECKSCOPE_MANUAL_TAG")
                        or extra.get("run_tag") or uuid.uuid4().hex[:8])
        self.step = 0
        self.replayed = 0

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _key(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    #: How long an answer file's size must hold steady before it is read. A file
    #: exists from its first byte, and reading it half-written looks exactly like
    #: a model emitting broken JSON — which sends whoever debugs it after the
    #: wrong problem entirely. Tied to a wall-clock floor rather than to
    #: `poll_seconds`, because a fast poll would otherwise shrink the guard to
    #: nothing. It is best-effort and cannot be made airtight from this side: a
    #: writer that stalls mid-file for longer than this still defeats it. The
    #: reliable protocol is to write a temporary file and rename it into place,
    #: which is atomic and needs no guard at all.
    SETTLE_SECONDS = 0.3

    def _wait_for(self, rfile: Path, pfile: Path) -> str:
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if rfile.exists():
                settled = time.time() + self.SETTLE_SECONDS
                size = rfile.stat().st_size
                stable = True
                while time.time() < settled:
                    time.sleep(min(self.poll, 0.05))
                    if not rfile.exists() or rfile.stat().st_size != size:
                        stable = False
                        break
                if stable:
                    return rfile.read_text(encoding="utf-8")
                continue
            time.sleep(self.poll)
        raise ProviderError(
            f"No answer appeared for {pfile.name} within {self.timeout:.0f}s.\n"
            f"  prompt : {pfile}\n"
            f"  answer : {rfile}\n"
            f"Answers already given are cached, so re-running this command "
            f"resumes here rather than starting over.")

    # ----------------------------------------------------------------- protocol

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        self.step += 1
        prompt = system + "\n\n" + "\n\n".join(
            f"[{m.role}]\n{m.content}" for m in messages
        )
        key = self._key(prompt)
        rfile = self.answers / f"{key}.txt"
        pfile = self.asked / f"{key}.prompt.txt"

        if rfile.exists():
            self.replayed += 1
            return self._completion(prompt, rfile.read_text(encoding="utf-8"),
                                    cached=True)

        pfile.write_text(prompt, encoding="utf-8")
        (self.asked / f"{key}.meta.json").write_text(json.dumps({
            "run_tag": self.run_tag, "step": self.step,
            "chars": len(prompt), "answer_path": str(rfile),
        }, indent=2), encoding="utf-8")

        if self.interactive:
            _try_clipboard(prompt)
            _out("\n" + "=" * 70)
            _out(f"  STEP {self.step} — your turn")
            _out("=" * 70)
            _out(f"  1. The prompt is on your clipboard (and saved at {pfile}).")
            _out("  2. Paste it into ChatGPT, Claude, Gemini — whichever you use.")
            _out(f"  3. Save the FULL reply into:\n     {rfile}")
            _out("  4. Come back here and press Enter.")
            _out("     (Answers are kept. If you stop now, re-running resumes here.)")
            _out("=" * 70)
            try:
                input("  Waiting... press Enter once the reply file is saved: ")
            except EOFError:
                pass

        return self._completion(prompt, self._wait_for(rfile, pfile), cached=False)

    def _completion(self, prompt: str, text: str, *, cached: bool) -> Completion:
        # Character-based, and labelled as such. No tokenizer is available here,
        # and guessing precisely would be worse than admitting the estimate.
        # Comparisons between modes stay meaningful because every mode is
        # estimated the same way; nobody should quote these as billing figures.
        usage = {"input": max(1, len(prompt) // 4),
                 "output": max(1, len(text) // 4),
                 "estimated": True}
        return Completion(text=text, model=self.model or "manual", usage=usage,
                          raw={"cached": cached})

    def health_check(self):
        if self.interactive:
            return {"ok": True, "provider": self.name, "model": self.model,
                    "reply": "copy-paste mode is always available"}
        return {"ok": True, "provider": self.name, "model": self.model,
                "reply": f"spool mode; watching {self.dir}"}


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
