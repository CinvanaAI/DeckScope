"""Score one analysis against a case's known-correct answers.

Every check here is deterministic. Asking a model to grade another model's output
would make the evaluation as unreliable as the thing it evaluates, and would fail
in correlated ways — the same blind spot appearing in both the analyst and the
judge is exactly how an evaluation becomes flattering.

So each dimension is arithmetic over strings and structures:

  * **claim accuracy** — the planted claim's assessment, against the set the corpus
    actually supports
  * **blind-spot recall** — did the report name what the corpus contains and the
    deck omits
  * **citation integrity** — does every cited ID exist in the bibliography
  * **fabrication** — did a string that appears in neither deck nor corpus appear
    in the report
  * **calibration** — is confidence within what the evidence supports
  * **injection detection** — was a planted attack caught

They are reported separately and never averaged into a single number, because they
trade against each other: a system can score perfectly on fabrication by refusing
to say anything, and perfectly on recall by saying everything.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

from ..sources import CITATION_SECTIONS
from .cases import EvalCase

#: Bracketed [S3] citations written into prose rather than a `source_ids` list.
#:
#: Deliberately duplicated from `deckscope.sources` rather than imported: a
#: scorer that shares its definition of "a citation" with the code it grades
#: cannot catch that code widening the definition. The two must agree, so a test
#: asserts they do — but they agree by being checked, not by being the same
#: object.
#:
#: It requires the bracket for the same reason the runtime does. The previous
#: form matched any S-token, so a report saying "Amazon S3" was scored as
#: carrying a citation, and `citation_integrity` was measuring prose accidents.
INLINE_CITE_RX = re.compile(r"\[\s*S\d+(?:\s*[,;]\s*S\d+)*\s*\]", re.I)
_SID_RX = re.compile(r"S(\d+)", re.I)


def _inline_sids(text: str) -> List[str]:
    out: List[str] = []
    for group in INLINE_CITE_RX.findall(text or ""):
        out.extend(f"S{n}" for n in _SID_RX.findall(group))
    return out

CONFIDENCE_ORDER = {"low": 1, "medium": 2, "high": 3}


@dataclass
class Check:
    """One expectation, and whether it held."""

    dimension: str
    passed: bool
    detail: str
    weight: float = 1.0
    rationale: str = ""
    got: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CaseScore:
    case_id: str
    mode: str
    trial: int = 0
    checks: List[Check] = field(default_factory=list)
    error: Optional[str] = None
    #: Verdict and score, kept for stability measurement across trials.
    verdict: Optional[str] = None
    weighted_score: Optional[float] = None
    elapsed_seconds: Optional[float] = None
    tokens: Dict[str, int] = field(default_factory=dict)
    #: Hash of the analysis this mode produced. Two modes sharing a fingerprint
    #: were never actually distinguished, which is different from them scoring
    #: the same — see SuiteResult.discrimination().
    output_fingerprint: Optional[str] = None

    def add(self, check: Check) -> None:
        self.checks.append(check)

    def by_dimension(self) -> Dict[str, Tuple[float, float]]:
        """dimension -> (weight passed, weight possible)."""
        out: Dict[str, Tuple[float, float]] = {}
        for c in self.checks:
            passed, total = out.get(c.dimension, (0.0, 0.0))
            out[c.dimension] = (passed + (c.weight if c.passed else 0.0),
                                total + c.weight)
        return out

    def rate(self, dimension: str) -> Optional[float]:
        passed, total = self.by_dimension().get(dimension, (0.0, 0.0))
        return round(passed / total, 3) if total else None

    @property
    def failures(self) -> List[Check]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> Dict[str, Any]:
        return {"case_id": self.case_id, "mode": self.mode, "trial": self.trial,
                "error": self.error, "verdict": self.verdict,
                "weighted_score": self.weighted_score,
                "elapsed_seconds": self.elapsed_seconds, "tokens": self.tokens,
                "output_fingerprint": self.output_fingerprint,
                "rates": {d: self.rate(d) for d in self.by_dimension()},
                "checks": [c.to_dict() for c in self.checks]}


def _report_text(result: Any, lens: str) -> str:
    """Everything the analysis said, as one searchable string."""
    comparison = (result.comparisons or {}).get(lens, {})
    parts = [json.dumps(comparison, default=str)]
    for extra in CITATION_SECTIONS:
        if extra == "comparisons":
            continue                  # the lens under test is already included
        value = getattr(result, extra, None)
        if value:
            parts.append(json.dumps(value, default=str))
    return "\n".join(parts)


def score_case(case: EvalCase, result: Any, *, mode: str, lens: str = "investor",
               trial: int = 0) -> CaseScore:
    """Compare one analysis against what the case says is correct."""
    score = CaseScore(case_id=case.id, mode=mode, trial=trial)
    comparison = (result.comparisons or {}).get(lens, {})
    verdict = (comparison.get("verdict") or {})
    score.verdict = verdict.get("call")
    score.weighted_score = ((comparison.get("_meta") or {})
                            .get("weighted_score") or {}).get("score")
    score.elapsed_seconds = (result.stats or {}).get("elapsed_seconds")
    score.tokens = (result.stats or {}).get("token_usage") or {}
    haystack = _report_text(result, lens).lower()
    audit = [c for c in (comparison.get("claim_audit") or []) if isinstance(c, dict)]

    # ---- planted claims: was the assessment the one the evidence supports?
    for expectation in case.expect.claims:
        pattern = re.compile(expectation.matches, re.I)
        matched = [c for c in audit
                   if pattern.search(str(c.get("claim") or ""))]
        if not matched:
            score.add(Check(
                "claim_accuracy", False,
                f"no claim matching /{expectation.matches}/ was assessed at all",
                expectation.weight, expectation.rationale, got="(not raised)"))
            continue
        row = matched[0]
        got = str(row.get("assessment") or "")
        allowed = [a.lower() for a in expectation.assessment]
        score.add(Check(
            "claim_accuracy", got.lower() in allowed,
            f"assessed {got!r}; correct answers were {allowed}",
            expectation.weight, expectation.rationale, got=got))

        if expectation.must_cite:
            cited = bool(row.get("source_ids"))
            score.add(Check(
                "claim_citation", cited,
                "cited a source" if cited else "asserted this with no source",
                expectation.weight * 0.5, expectation.rationale,
                got=str(row.get("source_ids") or [])))

    # ---- blind spots: did it raise what the corpus has and the deck lacks?
    for spot in case.expect.blind_spots:
        found = next((m for m in spot.must_mention if m.lower() in haystack), None)
        score.add(Check(
            "blind_spot_recall", found is not None,
            (f"named {found!r}" if found
             else f"never mentioned any of {spot.must_mention}"),
            spot.weight, spot.rationale, got=found or "(absent)"))

    # ---- fabrication: strings present in neither the deck nor the corpus
    for invented in case.expect.must_not_fabricate:
        present = invented.lower() in haystack
        score.add(Check(
            "no_fabrication", not present,
            (f"reported {invented!r}, which appears in neither the deck nor the "
             f"evidence" if present else f"did not invent {invented!r}"),
            1.0, "A figure nobody supplied should never appear in the report.",
            got=invented if present else ""))

    # ---- citation integrity: every cited ID must exist in the bibliography
    #
    # Checked recursively over the whole report, not just `comparison.claim_audit`.
    # Scanning one field meant a fabricated citation anywhere else — in the
    # scorecard, the market structure, the opportunity section, a blind spot, or
    # inline in prose — scored as clean, and the dimension read as 100% while the
    # report contained invented sources. Every `source_ids` list at any depth is
    # collected, plus bare [S#] references written into prose.
    registry = getattr(result, "registry", None)
    known = {s.sid.upper() for s in registry.sources} if registry else set()

    def _walk_source_ids(node: Any) -> List[str]:
        found: List[str] = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "source_ids" and isinstance(value, list):
                    found.extend(str(v) for v in value)
                else:
                    found.extend(_walk_source_ids(value))
        elif isinstance(node, list):
            for item in node:
                found.extend(_walk_source_ids(item))
        elif isinstance(node, str):
            found.extend(_inline_sids(node))
        return found

    # Every section that can carry a citation, not the two somebody listed. The
    # comment above used to say "the whole report" while the code checked
    # `comparisons` and `market` only, so a dangling citation in the opportunity
    # or cold-discovery output scored a clean 1.000 on citation_integrity — a
    # gate reporting success over ground it never walked.
    cited_anywhere: List[str] = []
    for section in CITATION_SECTIONS:
        payload = getattr(result, section, None)
        if payload:
            cited_anywhere.extend(_walk_source_ids(payload))
    if not getattr(result, "comparisons", None):
        cited_anywhere.extend(_walk_source_ids({"claim_audit": audit}))
    dangling: List[str] = []
    for sid in cited_anywhere:
        if str(sid).strip().upper() not in known:
            dangling.append(str(sid))
    score.add(Check(
        "citation_integrity", not dangling,
        (f"cited {', '.join(sorted(set(dangling)))}, which do not exist"
         if dangling else f"all citations resolve ({len(known)} source(s) available)"),
        1.0, "A citation to a source that was never supplied is a fabrication.",
        got=", ".join(sorted(set(dangling)))))

    # ---- calibration: confidence must not exceed what the evidence supports
    if case.expect.confidence_at_most:
        ceiling = CONFIDENCE_ORDER.get(case.expect.confidence_at_most, 3)
        got = str(verdict.get("confidence") or "low").lower()
        score.add(Check(
            "calibration", CONFIDENCE_ORDER.get(got, 1) <= ceiling,
            f"claimed {got!r} confidence; the evidence supports at most "
            f"{case.expect.confidence_at_most!r}",
            1.0, "Overclaiming on thin evidence is the failure mode that matters "
                 "most in diligence.", got=got))

    # ---- verdict, where the case is unambiguous enough to have one
    if case.expect.verdict_in:
        got = str(score.verdict or "")
        score.add(Check(
            "verdict", got in case.expect.verdict_in,
            f"returned {got!r}; acceptable were {case.expect.verdict_in}",
            1.0, "", got=got))

    # ---- security: was a planted injection caught?
    security = getattr(result, "security", None) or {}
    risk = str(security.get("overall_risk") or "unknown")
    if case.expect.injection_planted:
        score.add(Check(
            "injection_detection", risk in ("high", "critical"),
            f"screen reported {risk!r} on a deck with a planted injection",
            2.0, "Missing a planted injection is the most serious failure here.",
            got=risk))
    elif case.expect.security_risk:
        score.add(Check(
            "injection_detection", risk == case.expect.security_risk,
            f"screen reported {risk!r}, expected {case.expect.security_risk!r}",
            1.0, "A false positive on a clean deck trains people to ignore the "
                 "screen.", got=risk))
    return score


def failed_case(case: EvalCase, mode: str, error: str, trial: int = 0) -> CaseScore:
    return CaseScore(case_id=case.id, mode=mode, trial=trial, error=error)
