"""Evaluation cases: a deck, its evidence, and what a correct analysis would say.

The obstacle to evaluating a system like this is that "was the analysis good?" has
no mechanical answer for a real deck. Nobody knows the true TAM, so nobody can
score a claim about it.

The way around that is to author both sides. If the deck says $47B and the frozen
corpus says the serviceable slice is $3-5B, then "contradicted" is correct and
"supported" is wrong — not as a matter of taste, but because the evidence in front
of the model says so. Ground truth exists because it was planted.

**What this measures and does not measure.** It measures whether an analysis
correctly reads evidence that is right there: does it catch a planted
contradiction, name an incumbent the corpus mentions and the deck omits, refuse to
cite a source that does not exist, avoid repeating a figure nobody supplied, and
lower its confidence when the evidence is thin.

It does not measure real-world accuracy. These are constructed cases, and a system
tuned against them could learn the fixtures rather than the skill. Treat a high
score as "does not fail in the ways we know how to check", which is a floor rather
than a ceiling.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ClaimExpectation:
    """A planted claim whose correct assessment is known from the corpus."""

    #: Regex matched against the claim text, case-insensitively.
    matches: str
    #: Assessments that count as correct. A list because "contradicted" and
    #: "partially-supported" are often both defensible readings of the same gap.
    assessment: List[str] = field(default_factory=list)
    #: Whether a correct analysis must cite a source for this.
    must_cite: bool = False
    #: Why this is the right answer — printed when the case fails, so a failure is
    #: legible without opening the fixture.
    rationale: str = ""
    weight: float = 1.0


@dataclass
class BlindSpotExpectation:
    """Something the corpus contains, the deck omits, and the analysis should raise."""

    #: Any of these strings appearing anywhere in the report counts as found.
    must_mention: List[str] = field(default_factory=list)
    rationale: str = ""
    weight: float = 1.0


@dataclass
class Expectations:
    claims: List[ClaimExpectation] = field(default_factory=list)
    blind_spots: List[BlindSpotExpectation] = field(default_factory=list)
    #: Strings that appear in NEITHER the deck nor the corpus. If one shows up in
    #: the report, the analysis invented it.
    must_not_fabricate: List[str] = field(default_factory=list)
    #: Ceiling on confidence, for cases where the evidence does not support more.
    confidence_at_most: Optional[str] = None
    #: Expected verdicts, when the case is unambiguous enough to have one.
    verdict_in: List[str] = field(default_factory=list)
    #: Expected result of the input security screen.
    security_risk: Optional[str] = None
    #: Whether the deck contains a planted injection that must be caught.
    injection_planted: bool = False


@dataclass
class EvalCase:
    id: str
    name: str
    deck: str
    corpus: Optional[str] = None
    description: str = ""
    expect: Expectations = field(default_factory=Expectations)
    #: Cases can be skipped by tag, e.g. to run only the security ones.
    tags: List[str] = field(default_factory=list)

    def deck_path(self, root: Path) -> Path:
        return (root / self.deck).resolve()

    def corpus_path(self, root: Path) -> Optional[Path]:
        return (root / self.corpus).resolve() if self.corpus else None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_case(path: str) -> EvalCase:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    exp = raw.pop("expect", {}) or {}
    expectations = Expectations(
        claims=[ClaimExpectation(**c) for c in exp.get("claims", [])],
        blind_spots=[BlindSpotExpectation(**b) for b in exp.get("blind_spots", [])],
        must_not_fabricate=list(exp.get("must_not_fabricate", [])),
        confidence_at_most=exp.get("confidence_at_most"),
        verdict_in=list(exp.get("verdict_in", [])),
        security_risk=exp.get("security_risk"),
        injection_planted=bool(exp.get("injection_planted", False)),
    )
    known = {f for f in EvalCase.__dataclass_fields__}
    raw = {k: v for k, v in raw.items() if k in known}
    return EvalCase(expect=expectations, **raw)


def load_suite(directory: str) -> List[EvalCase]:
    """Every case in a directory, ordered by id for stable reporting."""
    root = Path(directory)
    cases = [load_case(str(p)) for p in sorted(root.glob("*.json"))]
    seen = set()
    for case in cases:
        if case.id in seen:
            raise ValueError(f"Duplicate evaluation case id: {case.id}")
        seen.add(case.id)
    return cases


def default_suite_dir() -> Path:
    """The suite that ships with DeckScope."""
    return Path(__file__).resolve().parent.parent.parent / "evals" / "cases"
