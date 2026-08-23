"""Console output that survives a default Windows terminal.

DeckScope's promoted path is "double-click the installer, then double-click the
app". On a default Windows console the encoding is CP-1252, and printing a box
character raises UnicodeEncodeError — so the advertised commands crashed, some of
them after writing their reports and some before.

Fixing the strings alone would not hold: any future contributor typing an arrow
into a print statement reintroduces it. So output goes through here instead.

  * `enable()` asks Python for UTF-8 on stdout/stderr when the stream supports
    reconfiguration, which covers modern Windows Terminal and most CI runners.
  * If that is not possible, `out()` transliterates to ASCII on the way through.
  * Either way nothing raises. A report that already exists on disk must never be
    lost to a character that cannot be printed.
"""
from __future__ import annotations

import sys
from typing import Any

#: Deliberately plain replacements. These are read aloud in logs and pasted into
#: bug reports, so clarity beats cleverness.
FALLBACKS = {
    "─": "-", "━": "=", "═": "=", "│": "|", "·": "*", "•": "*",
    "→": "->", "←": "<-", "▶": ">", "◀": "<", "◐": "*",
    "✓": "[ok]", "✗": "[x]", "✔": "[ok]", "✘": "[x]",
    "⚠": "[!]", "⏎": "<nl>", "…": "...", "—": "--", "–": "-",
    "’": "'", "‘": "'", "“": '"', "”": '"', "●": "*", "○": "o",
    "≥": ">=", "≤": "<=", "×": "x",
}

_ASCII_MODE: bool = False


def enable() -> bool:
    """Try to make stdout/stderr UTF-8. Returns True if console output is safe."""
    global _ASCII_MODE
    ok = True
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower()
        if enc.startswith("utf"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - older Python, or a redirected pipe
            ok = False
    _ASCII_MODE = not ok
    return ok


def ascii_only(text: str) -> str:
    """Transliterate to something a legacy code page can print."""
    for uni, plain in FALLBACKS.items():
        text = text.replace(uni, plain)
    return text.encode("ascii", "replace").decode("ascii")


def ascii_mode() -> bool:
    """True when output is being transliterated. Used by tests."""
    return _ASCII_MODE


def safe(text: Any) -> str:
    """The string as it can actually be written to this console."""
    text = str(text)
    if _ASCII_MODE:
        return ascii_only(text)
    return text


def out(*parts: Any, sep: str = " ", end: str = "\n", file: Any = None,
        stream: Any = None, flush: bool = True) -> None:
    """print(), but it cannot raise UnicodeEncodeError.

    Accepts print()'s keyword arguments so it is a drop-in replacement. Use this
    instead of print() for anything a user sees.
    """
    global _ASCII_MODE
    target = stream or file or sys.stdout
    text = sep.join(safe(p) for p in parts) + end
    try:
        target.write(text)
    except UnicodeEncodeError:
        # The stream lied about what it could take. Fall back permanently, so the
        # next line does not have to rediscover this.
        _ASCII_MODE = True
        try:
            target.write(ascii_only(text))
        except Exception:  # noqa: BLE001
            return
    except Exception:  # noqa: BLE001 - a closed pipe must not end the run
        return
    if flush:
        try:
            target.flush()
        except Exception:  # noqa: BLE001
            pass
