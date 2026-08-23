"""DeckScope's defense against content that tries to steer the analysis.

Both of DeckScope's inputs are attacker-controllable. A founder can hide white text
on a slide; anyone can publish a web page hoping a research agent retrieves it. This
package screens both before the model ever sees them.

    from deckscope.security import SecurityPolicy, screen_deck, screen_sources
"""
from .policy import Mode, SecurityPolicy
from .report import Finding, ScanReport, SecurityAbort
from .sanitizer import FENCE_NOTICE, fence, sanitize
from .screening import screen_deck, screen_sources
from .text_scanner import scan_text
from .forensics import scan_file

__all__ = [
    "Mode", "SecurityPolicy", "Finding", "ScanReport", "SecurityAbort",
    "fence", "sanitize", "FENCE_NOTICE", "screen_deck", "screen_sources",
    "scan_text", "scan_file",
]
