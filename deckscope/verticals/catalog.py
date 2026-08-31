"""The declared verticals. Every field here is pinned to the code it
describes by coupling tests in tests/test_verticals.py — a declaration
that drifts from the engine fails the suite, not the reader.
"""
from __future__ import annotations

from . import Vertical, register

#: Pitch deck diligence — the flagship, extracted from what already ships.
#: Nothing about the deck pipeline changed when this declaration was
#: written; it DESCRIBES the existing system, and the coupling tests hold
#: it to that.
DECK = register(Vertical(
    name="deck",
    label="Pitch deck diligence",
    document="a startup's fundraising deck (or raw founder notes)",
    cues=("pitch deck", "seed round", "series a", "series b", "term sheet",
          "raising $", "pre-money", "post-money", "cap table", "our ask",
          "tam", "sam", "som", "total addressable market", "traction",
          "burn rate", "runway", "arr ", "mrr ", "churn",
          "use of funds", "go-to-market"),
    claim_types=("market-size", "growth", "competition", "traction",
                 "technology", "team", "financial", "regulatory"),
    publicly_checkable=("market-size", "growth", "competition",
                        "regulatory"),
    lenses=("investor", "founder", "neutral"),
    evidence_homes=("search", "census", "edgar"),
    report_types=("market-size", "market-share", "competitive-landscape",
                  "regulation"),
    runner="deck_pipeline",
    #: The deck evaluation harness (deckscope eval) holds known-correct
    #: cases with planted answers and traps.
    graded=True,
    intake=True,
))

#: Scoped market reports — question-driven, not a document intake. It is
#: declared for completeness (it IS a vertical of the engine) and opts
#: out of document classification.
MARKET = register(Vertical(
    name="market",
    label="Scoped market reports",
    document="a market question ('market share of cell phones'), not a file",
    cues=(),
    claim_types=(),
    publicly_checkable=(),
    lenses=(),
    evidence_homes=("census", "search", "edgar"),
    report_types=("market-size", "market-share", "competitive-landscape",
                  "regulation", "demographics"),
    runner="question",
    #: marketreport/cases holds graded cases (2 of 6 pass under the mock,
    #: 6 of 6 invent nothing — the split is reported by `deckscope check`).
    graded=True,
    intake=False,
))


# Verticals that live in their own modules register on import.
from . import grants  # noqa: E402,F401 - imported for its registration
from . import nonprofits  # noqa: E402,F401 - imported for its registration
