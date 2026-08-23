"""How aggressively DeckScope defends against content that tries to steer it."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Mode(str, Enum):
    STRICT = "strict"        # abort the run on any critical finding
    BALANCED = "balanced"    # redact hostile spans, keep going, report loudly  (default)
    PERMISSIVE = "permissive"  # flag only, change nothing
    OFF = "off"              # no scanning at all (not recommended)

    @classmethod
    def parse(cls, v: "str | Mode") -> "Mode":
        if isinstance(v, cls):
            return v
        try:
            return cls(str(v).strip().lower())
        except ValueError:
            raise ValueError(f"Unknown security mode {v!r}. "
                             f"Choose: {', '.join(m.value for m in cls)}") from None


SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class SecurityPolicy:
    """Defaults are deliberately protective. Loosen them knowingly."""

    mode: Mode = Mode.BALANCED

    # Deck forensics
    scan_deck_forensics: bool = True      # invisible text, tiny fonts, off-slide shapes
    min_font_pt: float = 4.0              # below this is not meant for a human reader
    contrast_threshold: float = 0.12      # text-vs-background luminance gap
    scan_speaker_notes: bool = True       # notes are a classic hiding place
    scan_metadata: bool = True            # PDF/PPTX metadata fields

    # Web sources
    scan_web_sources: bool = True
    block_untrusted_domains: List[str] = field(default_factory=list)
    max_source_chars: int = 6000          # truncate before a wall of text can bury a payload

    # Text-level defenses (applied to both)
    strip_invisible_chars: bool = True    # zero-width, bidi overrides
    normalize_homoglyphs: bool = True     # Cyrillic/Greek lookalikes
    redact_on: str = "high"               # minimum severity that gets redacted in BALANCED
    abort_on: str = "critical"            # minimum severity that aborts in STRICT

    def should_redact(self, severity: str) -> bool:
        if self.mode in (Mode.PERMISSIVE, Mode.OFF):
            return False
        return SEVERITY_ORDER.get(severity, 0) >= SEVERITY_ORDER.get(self.redact_on, 3)

    #: Minimum severity at which a WEB SOURCE is dropped entirely rather than
    #: cleaned. Separate from `redact_on` because the trade differs: a deck is
    #: the thing being analyzed and must survive, whereas a suspicious source is
    #: one of many and dropping it costs almost nothing.
    quarantine_on: str = "medium"

    def should_quarantine(self, severity: str) -> bool:
        """Whether a finding at this severity disqualifies a web source."""
        if self.mode in (Mode.PERMISSIVE, Mode.OFF):
            return False
        return (SEVERITY_ORDER.get(severity, 0)
                >= SEVERITY_ORDER.get(self.quarantine_on, 2))

    def should_abort(self, severity: str) -> bool:
        if self.mode is not Mode.STRICT:
            return False
        return SEVERITY_ORDER.get(severity, 0) >= SEVERITY_ORDER.get(self.abort_on, 4)

    @property
    def enabled(self) -> bool:
        return self.mode is not Mode.OFF
