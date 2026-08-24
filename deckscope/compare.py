"""Comparison, claim by claim — and the three findings that had nowhere to go.

The old synthesis stage read two summaries and wrote a report. This works
through the claim register instead: for each thing the deck asserts, gather the
findings whose questions descend from it, assess it, and *measure the gap* where
both sides carry a number. "Contradicted" is a label; "claimed $88B against an
evidence range of $6-8B, roughly twelve times" is a fact a reader can check.

Then three passes the previous schema could not express at all:

**Omission** — findings the research established that no claim addresses. The
deck is silent and the market is not.

**Contested** — where two grounded sources disagree and nothing settled it,
promoted into the report rather than resolved by picking a side.

**The ask-versus-requirement delta** — when a deck asks for $5,000 and the
evidence says the requirement is nearer $10,000, the *gap* is the finding, and
it is about the person who wrote the deck rather than the industry. Under-
pitching by half means they did not research it or hope you will not notice.
That is decision-relevant in a way no market fact is, and there was previously
no field for it anywhere in the product.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .claims import ClaimRegister
from .research.findings import Finding, FindingRegistry, parse_number
from .research.questions import CONTESTED, QuestionQueue

#: How far apart a claim and the evidence may be before the gap is worth naming.
MATERIAL_RATIO = 1.5

#: Above this multiple, a claim and a finding are treated as measuring different
#: things rather than as disagreeing. A deck overstating its market by 12x is a
#: real and common finding; a figure 5,000x from the evidence is a company's
#: revenue being compared against its industry's total size.
MISMATCH_CEILING = 100.0

#: Above this multiple, an "over-ask" is reported as a unit mismatch instead.
#: Asking for eight times the startup cost is a fundable growth plan; asking for
#: four hundred times it means the two numbers are not the same kind of thing.
OVER_ASK_CEILING = 25.0


@dataclass
class ClaimAssessment:
    claim_id: str
    claim: str
    assessment: str                    # supported | partially | contradicted | unverifiable
    because: str = ""
    #: The measured distance, when both sides carry a number.
    ratio: Optional[float] = None
    gap_text: str = ""
    finding_ids: List[str] = field(default_factory=list)
    source_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PitcherSignal:
    """A finding about whoever wrote the deck, not about the market."""

    kind: str                          # under-ask | over-ask | unsupported-precision
    statement: str
    asked: Optional[float] = None
    required: Optional[float] = None
    ratio: Optional[float] = None
    finding_ids: List[str] = field(default_factory=list)
    source_ids: List[str] = field(default_factory=list)
    why_it_matters: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def assess_claims(register: ClaimRegister,
                  findings: FindingRegistry) -> List[ClaimAssessment]:
    """One assessment per claim, with the gap measured where possible."""
    out: List[ClaimAssessment] = []
    for claim in register.claims:
        related = findings.for_claim(claim.id)
        grounded = [f for f in related if f.sourced and f.method != "absent"]
        absent = [f for f in related if f.method == "absent"]

        if not related:
            out.append(ClaimAssessment(
                claim.id, claim.text, "unverifiable",
                "no research question was answered that bears on this claim"))
            continue

        if absent and not grounded:
            out.append(ClaimAssessment(
                claim.id, claim.text, "unverifiable",
                f"research established that no source addresses it: "
                f"{absent[0].statement}",
                finding_ids=[f.id for f in absent]))
            continue

        source_text = claim.value_text or claim.text
        claimed = parse_number(source_text)
        claim_unit = unit_of(source_text)
        # Only compare like with like.
        #
        # Without this the median of every number retrieved for a question stood
        # in as "the evidence", so a claim of "$28,000 average contract value"
        # was measured against a finding of "104-112%" — a ratio of about 270,
        # duly reported as `contradicted` with a confident gap line. The
        # honest-control case exists precisely to catch a system that calls
        # everything contradicted, and it caught this. A wrong contradiction is
        # worse than a missed one: it is the product being confidently wrong in
        # exactly the way it accuses decks of being.
        measured = [f for f in grounded
                    if f.value is not None and _comparable(claim_unit, f)]
        source_ids = sorted({s for f in grounded for s in f.source_ids})

        if claimed is not None and measured:
            evidence = sorted(f.value for f in measured)[len(measured) // 2]
            ratio = (max(claimed, evidence) / min(claimed, evidence)
                     if min(claimed, evidence) else None)
            if ratio is None or ratio <= MATERIAL_RATIO:
                out.append(ClaimAssessment(
                    claim.id, claim.text, "supported",
                    "the claim sits inside what the evidence shows",
                    ratio=ratio, finding_ids=[f.id for f in measured],
                    source_ids=source_ids))
            elif ratio > MISMATCH_CEILING:
                # Past this multiple the honest reading is that the two figures
                # measure different things, not that the deck exaggerated.
                #
                # The control case produced "claimed $520k ARR; evidence
                # indicates $2.6-3.0B — roughly 5384.6x below" and called it a
                # contradiction. It was comparing a company's revenue against the
                # size of its whole market, because both are denominated in
                # dollars. Matching units is necessary and not sufficient.
                #
                # Same principle as the ask-versus-requirement ceiling, and the
                # same reason: a confident wrong contradiction is the product
                # failing in exactly the way it accuses decks of failing.
                out.append(ClaimAssessment(
                    claim.id, claim.text, "partially-supported",
                    f"the nearest evidence "
                    f"({_amount(measured[0].value_text, evidence)}) is "
                    f"{ratio:.0f}x from this claim, which is too far apart to be "
                    f"measuring the same thing — so this was not checked rather "
                    f"than judged",
                    ratio=ratio, finding_ids=[f.id for f in measured],
                    source_ids=source_ids))
            else:
                direction = "above" if claimed > evidence else "below"
                gap = (f"claimed {claim.value_text or _short(claim.text)}; evidence "
                       f"indicates {_amount(measured[0].value_text, evidence)}"
                       f" — roughly {ratio:.1f}x {direction}")
                out.append(ClaimAssessment(
                    claim.id, claim.text, "contradicted", gap, ratio=ratio,
                    gap_text=gap, finding_ids=[f.id for f in measured],
                    source_ids=source_ids))
            continue

        # No comparable magnitude. Grounded evidence exists but cannot be
        # measured against the claim, which is a weaker statement than either
        # "supported" or "contradicted" and must not be dressed up as one.
        out.append(ClaimAssessment(
            claim.id, claim.text, "partially-supported",
            "evidence bears on this but no figure could be compared directly",
            finding_ids=[f.id for f in grounded], source_ids=source_ids))
    return out


def detect_omissions(register: ClaimRegister, findings: FindingRegistry,
                     assessments: List[ClaimAssessment],
                     deck_text: str = "") -> List[Dict[str, Any]]:
    """Findings the deck never addresses, plus the sections it left out.

    An omission is about what the *deck* contains, not about which question
    happened to retrieve the finding. The first version tested `not f.claims` —
    "no claim asked about this" — which excluded every finding a claim-directed
    question turned up. A competitor named in a source retrieved while checking
    the deck's market-size claim is still a competitor the deck never mentions,
    and it was being silently dropped for having arrived by the wrong route.
    That cost most of the blind-spot recall in the first evaluation.

    With `deck_text` the test is the honest one: does the subject of this
    finding appear anywhere in the deck? Without it, fall back to comparing
    against the claims — weaker, but never silently narrower than that.
    """
    out: List[Dict[str, Any]] = []
    haystack = (deck_text or "").lower()
    if not haystack:
        haystack = " ".join(c.text for c in register.claims).lower()

    for f in findings.findings:
        if not f.sourced or f.method == "absent":
            continue
        subjects = _subjects(f.statement)
        missing = [s for s in subjects if s.lower() not in haystack]
        if subjects and missing:
            out.append({
                "kind": "unaddressed-evidence", "finding_id": f.id,
                "statement": f.statement, "beat": f.beat,
                "names": missing,
                "source_ids": list(f.source_ids),
                "why_it_matters": (
                    f"the research established this and the deck never mentions "
                    f"{', '.join(missing[:3])}")})

    for omission in register.omissions:
        out.append({
            "kind": "missing-section", "section": omission["section"],
            "statement": f"the deck contains no {omission['section']} information",
            "why_it_matters": omission["why_it_matters"], "source_ids": []})
    return out


def surface_contested(findings: FindingRegistry,
                      queue: QuestionQueue) -> List[Dict[str, Any]]:
    """Disagreements promoted into the report instead of averaged away."""
    out = []
    for a, b in findings.contested():
        question = queue.find(a.question_id) if a.question_id else None
        out.append({
            "question": question.text if question else "",
            "positions": [
                {"finding_id": a.id, "statement": a.statement,
                 "value": a.value_text, "source_ids": list(a.source_ids)},
                {"finding_id": b.id, "statement": b.statement,
                 "value": b.value_text, "source_ids": list(b.source_ids)}],
            "resolution": (question.closed_because
                           if question and question.status == CONTESTED
                           else "not settled by the research"),
            "why_it_matters": "both positions are supported by sources that "
                              "reached a model, so this is a real disagreement "
                              "rather than one side inventing something"})
    return out


def ask_versus_requirement(extraction: Dict[str, Any],
                           findings: FindingRegistry) -> List[PitcherSignal]:
    """The gap between what was asked for and what the evidence says is needed.

    A finding about the pitcher. The market does not care that somebody
    under-asked by half; the person deciding whether to fund them very much does.
    """
    ask = (extraction.get("ask") or {})
    asked = parse_number(ask.get("amount"))
    if asked is None:
        return []

    requirements = [f for f in findings.findings
                    if f.sourced and f.value is not None
                    and f.beat == "economics"
                    and _looks_like_startup_cost(f)]
    if not requirements:
        return []

    required = sorted(f.value for f in requirements)[len(requirements) // 2]
    if not required:
        return []
    ratio = max(asked, required) / min(asked, required)
    if ratio < MATERIAL_RATIO:
        return []

    under = asked < required
    if not under and ratio > OVER_ASK_CEILING:
        # A "400x more than needed" line, which is what the first run produced:
        # a $4M seed round measured against a $10,000 single-crew startup cost.
        # Past a certain multiple the honest reading is not that the founder
        # over-asked but that the two figures measure different things — a
        # funding round against an owner-operator's setup cost. Claiming
        # otherwise would be the confident-and-wrong failure this whole rebuild
        # exists to avoid, so it is reported as what it is.
        return [PitcherSignal(
            kind="unit-mismatch",
            statement=(f"the ask ({ask.get('amount')}) and the evidenced startup "
                       f"requirement ({_amount(requirements[0].value_text, required)}) "
                       f"are {ratio:.0f}x apart, which is too far to be the same "
                       f"kind of number"),
            asked=asked, required=required, ratio=ratio,
            finding_ids=[f.id for f in requirements],
            source_ids=sorted({s for f in requirements for s in f.source_ids}),
            why_it_matters="no conclusion is drawn from this gap. A funding round "
                           "and an owner-operator's setup cost are not comparable, "
                           "and the research did not find a requirement figure at "
                           "the same scale as the ask.")]

    return [PitcherSignal(
        kind="under-ask" if under else "over-ask",
        statement=(f"the deck asks for {ask.get('amount')} against an evidenced "
                   f"requirement of about "
                   f"{_amount(requirements[0].value_text, required)}"
                   f" — {ratio:.1f}x {'short' if under else 'more than needed'}"),
        asked=asked, required=required, ratio=ratio,
        finding_ids=[f.id for f in requirements],
        source_ids=sorted({s for f in requirements for s in f.source_ids}),
        why_it_matters=(
            "asking for materially less than the requirement means the founder "
            "either did not research the cost or expects the reader not to check. "
            "Either reading is about the person rather than the market, and it is "
            "the kind of thing that decides how much to give and on what "
            "conditions."
            if under else
            "asking for materially more than the requirement is not automatically "
            "wrong, but the excess should have a stated purpose and does not."))]


def build(register: ClaimRegister, findings: FindingRegistry,
          queue: QuestionQueue, extraction: Dict[str, Any],
          deck_text: str = "") -> Dict[str, Any]:
    """The whole comparison stage, as a dataset rather than a document."""
    assessments = assess_claims(register, findings)
    return {
        "claims": [a.to_dict() for a in assessments],
        "omissions": detect_omissions(register, findings, assessments,
                                      deck_text),
        "contested": surface_contested(findings, queue),
        "pitcher_signals": [s.to_dict()
                            for s in ask_versus_requirement(extraction, findings)],
        "unanswered": [
            {"question": q.text, "beat": q.beat, "because": q.closed_because}
            for q in queue.by_status("unanswerable")],
        "stats": {
            "claims_assessed": len(assessments),
            "contradicted": len([a for a in assessments
                                 if a.assessment == "contradicted"]),
            "unverifiable": len([a for a in assessments
                                 if a.assessment == "unverifiable"]),
        },
    }


def unit_of(text: str) -> str:
    """What kind of quantity a piece of text states: USD, %, count, or unknown.

    Crude and deliberately conservative — `unknown` blocks no comparison, it
    only stops the confident ones being made across incompatible kinds.
    """
    import re

    s = str(text or "")
    if re.search(r"\$|\busd\b|\bdollars?\b", s, re.I):
        return "USD"
    if "%" in s or re.search(r"\bpercent\b|\bcagr\b|\bmargin\b|\bgrowth rate\b",
                             s, re.I):
        return "%"
    if re.search(r"\b(customers?|users?|employees?|businesses|firms|companies|"
                 r"headcount|seats?|logos?)\b", s, re.I):
        return "count"
    return ""


def _comparable(claim_unit: str, finding: Finding) -> bool:
    """Whether a finding's figure measures the same kind of thing as the claim."""
    found = (finding.unit or "").strip()
    if found.lower() in ("n/a", "unknown", ""):
        found = unit_of(finding.value_text or finding.statement)
    if not claim_unit or not found:
        # One side is unclassifiable. Comparing anyway is how the unit-mismatch
        # bug happened, so the claim stays unmeasured and is reported as
        # partially-supported rather than contradicted on a guess.
        return False
    return claim_unit.lower() == found.lower()


#: Capitalised words that begin sentences or name concepts rather than entities.
#: Kept short on purpose — over-filtering here hides real competitors, which is
#: the failure that matters, and a false positive merely produces a weak line in
#: a section the reader is already scanning.
_NOT_AN_ENTITY = {
    "The", "This", "That", "These", "Those", "Their", "There", "Both", "Its",
    "Independent", "Estimates", "Analysts", "Roughly", "About", "Most", "Many",
    "Several", "Some", "Market", "Revenue", "Growth", "Adoption", "Startup",
    "Customer", "Customers", "Public", "Private", "Companies", "Firms",
    "Vendors", "Buyers", "Net", "Per", "Open", "Small", "Wider", "Category",
    "Support", "Standalone", "Finance", "Reconciliation", "No", "Half", "One",
    "Two", "Three", "Four", "Five",
}


def _subjects(statement: str) -> List[str]:
    """Named entities a finding is about — the things a deck could have named.

    Deliberately crude capitalisation matching, and deliberately the same rule
    the rest of the product uses, so no stage is advantaged by a cleverer
    extractor than its neighbour.
    """
    import re

    out, seen = [], set()
    for m in re.finditer(r"\b([A-Z][a-z][A-Za-z0-9.]*(?:\.com)?)\b",
                         statement or ""):
        name = m.group(1)
        if name in _NOT_AN_ENTITY or len(name) < 3 or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    return out


def _amount(value_text: str, number: float) -> str:
    """Prefer the source's own wording; fall back to the parsed number.

    Written out because the obvious one-liner — `{value_text or number:,}` —
    applies the thousands separator to whichever side wins, and a string with a
    `,` format spec raises. It looked right and blew up on the first real run.
    """
    text = (value_text or "").strip()
    return text if text else f"{number:,.0f}"


def _short(text: str, n: int = 48) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[:n - 1] + "…"


def _looks_like_startup_cost(f: Finding) -> bool:
    words = (f.statement or "").lower()
    return any(k in words for k in
               ("start", "startup", "start-up", "capital", "equipment",
                "upfront", "initial", "to open", "to launch", "requirement"))
