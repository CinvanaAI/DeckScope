"""Verticals: document types as typed declarations over one engine.

A vertical is DATA, not a subsystem. It declares what a document type's
claims look like, which of them the public evidence universe can check,
what reader postures apply, where its evidence lives, and which report
types its scoper may dispatch — and the engine executes it. This is the
inversion made structural: eight external audits showed that every
serious semantic failure came from a model inferring structure freely,
so structure is declared here and enforced by the same law everywhere.

Two hard rules:

- **A declaration must match reality.** Coupling tests pin each field to
  the code it describes (the deck vertical's lenses ARE the Lens enum,
  its claim types ARE the extraction schema's, its checkable set IS the
  scoper's). A vertical cannot drift from the engine silently.
- **Ungraded is said out loud.** ``graded`` is True only when the
  evaluation harness holds a known-correct case for this vertical. An
  inferred or newly declared vertical runs with its reports carrying an
  ungraded notice until it earns the flag.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

__all__ = ["Vertical", "register", "get", "registered", "classify_document"]


@dataclass(frozen=True)
class Vertical:
    #: Registry key: "deck", "market", "grants", "nonprofits".
    name: str
    label: str
    #: What kind of document (or request) this vertical reads.
    document: str
    #: Deterministic intake cues: phrases whose presence in a document
    #: votes for this vertical. Weighted 1 each; the classifier is
    #: transparent arithmetic, never a vibe.
    cues: Tuple[str, ...] = ()
    #: The claim vocabulary this vertical's extraction uses.
    claim_types: Tuple[str, ...] = ()
    #: Claim types checkable against evidence OUTSIDE the author. The
    #: complement is author-only: asked, never judged.
    publicly_checkable: Tuple[str, ...] = ()
    lenses: Tuple[str, ...] = ()
    #: Backend names this vertical's research prefers, in order.
    evidence_homes: Tuple[str, ...] = ()
    #: marketreport report-type keys its scoper may dispatch.
    report_types: Tuple[str, ...] = ()
    #: Which runner executes it: "deck_pipeline" (document → claims →
    #: evidence → comparison) or "question" (a market question, no file).
    runner: str = "deck_pipeline"
    #: True only when the evaluation harness holds a known-correct case.
    graded: bool = False
    #: Whether the generic `analyze` intake may classify documents into
    #: this vertical. The market vertical is question-driven and opts out.
    intake: bool = True


_REGISTRY: Dict[str, Vertical] = {}


def register(v: Vertical) -> Vertical:
    _REGISTRY[v.name] = v
    return v


def get(name: str) -> Optional[Vertical]:
    _load()
    return _REGISTRY.get((name or "").strip().lower())


def registered() -> List[Vertical]:
    _load()
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


_LOADED = False


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from . import catalog  # noqa: F401 - imported for its registrations


# ----------------------------------------------------------------- intake

@dataclass
class Classification:
    """The intake decision, with its arithmetic shown."""

    vertical: Optional[Vertical]
    scores: Dict[str, int] = field(default_factory=dict)
    #: Why the winner won, or why nothing did — reader-facing.
    because: str = ""

    @property
    def matched(self) -> bool:
        return self.vertical is not None


#: A winner needs at least this many cue hits, and strictly more than the
#: runner-up. Both thresholds exist so a two-word coincidence cannot
#: claim a document, and a tie refuses rather than guessing.
MIN_HITS = 3


def classify_document(text: str) -> Classification:
    """Deterministic-first intake: transparent cue arithmetic.

    This is the guardrail layer, not the whole Intake Analyst — the
    analyst role (model) may be consulted when this refuses, but its
    answer must still name a declared vertical, and a declared vertical
    chosen by arithmetic never needs the model at all.
    """
    _load()
    low = (text or "").lower()
    scores: Dict[str, int] = {}
    for v in registered():
        if not v.intake:
            continue
        scores[v.name] = sum(1 for cue in v.cues if cue in low)

    if not scores:
        return Classification(None, scores, "no intake-enabled verticals")
    ordered = sorted(scores.items(), key=lambda kv: -kv[1])
    top_name, top = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0
    if top >= MIN_HITS and top > second:
        v = get(top_name)
        return Classification(
            v, scores,
            f"{top} cue match(es) for {v.label}, next best {second}")
    if top == second and top >= MIN_HITS:
        tied = [n for n, s in ordered if s == top]
        return Classification(
            None, scores,
            f"tied between {', '.join(tied)} at {top} cue(s) — a tie "
            f"refuses rather than guesses")
    nearest = top_name if top > 0 else ""
    because = (f"only {top} cue match(es); the strongest candidate was "
               f"{nearest or 'none'}" if nearest else
               "no declared vertical's cues appear in this document")
    return Classification(None, scores, because)
