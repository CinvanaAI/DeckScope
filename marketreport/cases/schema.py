"""What a market report is graded against, and how.

Every market report produced before this existed was checked the same way: I
read it. That does not repeat, does not scale, and does not survive whoever
wrote it — which is why four of seven report types shipped with agents,
scoping and cross-checks and nobody able to say whether their output was any
good.

The deck side has had `deckscope eval` for months: decks with planted,
known-correct answers and a deterministic scorer. This is that, for market
reports, and it grades two things rather than one.

**Recall — did it find what is there.** The corpus is real recorded pages, so
the facts in them are facts. A report that misses the OTC rule when the FDA
page is sitting in front of it has failed at its actual job.

**Refusal — did it decline to assert what is not there.** This is the half that
matters more, and the half a conventional benchmark skips. Every case carries
*traps*: claims that are plausible, that a reader would accept, that sound like
the sort of thing these sources would say — and that none of them supports. A
report that states one has fabricated, and no amount of recall compensates,
because the reader cannot tell the invented sentence from the sourced one.

That asymmetry is deliberate and is scored as such. A report that finds half
the facts and invents nothing is more useful than one that finds all of them
and invents one, because the first can be trusted with a caveat and the second
cannot be trusted at all.

**Absences are graded too.** Some cases require the report to state positively
that something could not be established. "Nobody publishes per-manufacturer
unit share" is a finding, and a report that quietly omits it is worse than one
that says it, even though both contain the same number of true sentences.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = ["Expect", "Trap", "Case", "Result", "score", "register",
           "get", "registered"]


@dataclass(frozen=True)
class Expect:
    """A fact genuinely present in the corpus that the report should surface."""

    #: Regex, searched case-insensitively against the whole rendered report.
    matches: str
    #: Why this matters, for the failure message. Written to be read by
    #: somebody looking at a red line and deciding whether to care.
    why: str
    #: How much this one counts. Reserve weight > 1 for facts whose absence
    #: makes the report misleading rather than merely thin.
    weight: float = 1.0
    #: When set, the report must also cite a source for it — the figure being
    #: present is not enough if it arrives unattributed.
    must_cite: bool = False


@dataclass(frozen=True)
class Trap:
    """A plausible claim the corpus does not support.

    The point of the harness. Each trap is written to be the sentence a
    confident, sloppy report would produce from this material: a real figure
    moved to the wrong subject, a plausible round number, a conclusion that
    would follow if one more fact were true.
    """

    matches: str
    #: What is wrong with it, said plainly enough to go in a report.
    why: str
    #: Traps are heavier than facts by default, because asserting something
    #: false costs a reader more than omitting something true.
    weight: float = 2.0


@dataclass(frozen=True)
class Case:
    """One market report, its recorded sources, and what a good answer says."""

    id: str
    name: str
    market: str
    report: str
    #: The dimension value this report is scoped to, if any.
    measure: str = ""
    #: Recorded pages: title, url, published, snippet. Real, with dates.
    pages: Sequence[Dict[str, str]] = ()
    #: The date the pages were retrieved, for the replay note.
    retrieved: str = ""
    expect: Sequence[Expect] = ()
    traps: Sequence[Trap] = ()
    #: Phrases the report must contain because the honest answer includes
    #: saying something could not be established.
    absences: Sequence[Expect] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.pages:
            raise ValueError(
                f"case {self.id!r} has no recorded pages. A case with no "
                f"corpus grades a report against nothing and will pass "
                f"whatever it is given.")
        if not self.expect and not self.absences:
            raise ValueError(
                f"case {self.id!r} expects nothing, so it cannot fail for the "
                f"right reason. Traps alone make a case that rewards silence: "
                f"a report that says nothing at all would score perfectly.")


@dataclass
class Result:
    """How one report did."""

    case_id: str
    found: List[str] = field(default_factory=list)
    missed: List[Tuple[str, str]] = field(default_factory=list)
    fabricated: List[Tuple[str, str]] = field(default_factory=list)
    uncited: List[Tuple[str, str]] = field(default_factory=list)
    absences_stated: List[str] = field(default_factory=list)
    absences_omitted: List[Tuple[str, str]] = field(default_factory=list)
    recall: float = 0.0
    error: str = ""

    @property
    def clean(self) -> bool:
        """Nothing invented. The bar that matters most, reported separately.

        Kept apart from `recall` on purpose. A single score would let a report
        buy its way out of a fabrication by finding more facts, and no amount
        of recall makes an invented sentence acceptable — the reader cannot
        tell which sentence was the invented one.
        """
        return not self.fabricated

    @property
    def passed(self) -> bool:
        # `uncited` fails the case. It did not at first, and the very first
        # full docket run showed why that was wrong: a case PASSED with
        # "1 uncited" — a figure its own Expect marked must_cite, present but
        # unattributed, flagged in the summary and waved through the verdict.
        # The product's one-line promise is that every figure is traceable to
        # its source; a grader that treats untraceable as a footnote is
        # grading a different product.
        return self.clean and not self.error and not self.absences_omitted \
            and not self.uncited and self.recall >= 0.5

    def summary(self) -> str:
        if self.error:
            return f"ERROR  {self.case_id}: {self.error}"
        mark = "PASS" if self.passed else "FAIL"
        parts = [f"recall {self.recall:.0%}"]
        if self.fabricated:
            parts.append(f"{len(self.fabricated)} FABRICATED")
        if self.absences_omitted:
            parts.append(f"{len(self.absences_omitted)} absence(s) not stated")
        if self.uncited:
            parts.append(f"{len(self.uncited)} uncited")
        return f"{mark}  {self.case_id}: " + ", ".join(parts)


def _hit(pattern: str, text: str) -> bool:
    try:
        return bool(re.search(pattern, text, re.I | re.S))
    except re.error:          # a broken pattern is a broken case, not a pass
        return False


#: Words that turn a sentence about a claim into a denial of it.
_DENIAL = re.compile(
    r"\b(?:no|not|never|nobody|none|cannot|can ?not|could not|without|"
    r"un(?:published|available|stated|verified)|absent|lacks?|missing|"
    r"does not|do not|is not|are not|was not|were not|refus\w+|"
    r"declin\w+ to)\b", re.I)


def _asserted(pattern: str, text: str) -> bool:
    """Whether the text ASSERTS a match for `pattern`, rather than denying one.

    The first scorer checked traps with a bare `re.search`, which convicted the
    innocent in a way one case made mandatory: the growth case *requires* the
    report to state "no forecast is published" (that is its `absences` check),
    and its trap pattern contains the word "forecast" — so the honest sentence
    satisfied the absence and tripped the trap in the same breath. A perfect
    report could not pass. Demonstrated before fixing:

        HONEST report: FAIL  recall 100%, 1 FABRICATED
        matched span: "...sold to dispensers. No forecast is publishe..."

    A trap is about asserting the claim. So each match is read against its own
    sentence, from the sentence's start through the end of the match: a denial
    token in that window means the sentence is denying the claim, and the match
    does not convict. Direction is the point — negation BEFORE or INSIDE the
    matched span excuses it ("no forecast is published"), negation only AFTER
    does not ("will reach 30 million units, not 25" is still a forecast).

    The trade, stated: a fabrication buried in a sentence that happens to open
    with a negation ("there is no doubt the market will reach $30B") slips
    through. That direction is accepted deliberately. A harness that convicts
    honest reports gets ignored, and then its true convictions are ignored with
    it — this repository has already paid for that lesson once, in a linter
    that reported 3,255 problems on a clean tree.
    """
    try:
        matches = list(re.finditer(pattern, text, re.I | re.S))
    except re.error:
        return False
    for match in matches:
        sentence_start = max(text.rfind(ch, 0, match.start())
                             for ch in ".!?\n") + 1
        window = text[sentence_start:match.end()]
        if not _DENIAL.search(window):
            return True
    return False


def score(case: Case, rendered: str, *, cited: str = "") -> Result:
    """Grade one rendered report against its case.

    `rendered` is the whole report as a person would read it. `cited` is the
    part of it that carries citations, when the caller can separate the two —
    used only for `must_cite`, and falling back to the whole report when it
    cannot, which is the permissive direction.
    """
    result = Result(case_id=case.id)
    haystack = rendered or ""
    citable = cited or haystack

    for want in case.expect:
        if _hit(want.matches, haystack):
            result.found.append(want.matches)
            if want.must_cite and not _hit(want.matches, citable):
                result.uncited.append((want.matches, want.why))
        else:
            result.missed.append((want.matches, want.why))

    for trap in case.traps:
        if _asserted(trap.matches, haystack):
            result.fabricated.append((trap.matches, trap.why))

    for absence in case.absences:
        if _hit(absence.matches, haystack):
            result.absences_stated.append(absence.matches)
        else:
            result.absences_omitted.append((absence.matches, absence.why))

    total = sum(w.weight for w in case.expect) or 1.0
    got = sum(w.weight for w in case.expect
              if w.matches in set(result.found))
    result.recall = got / total
    return result


_CASES: Dict[str, Case] = {}


def register(case: Case) -> Case:
    _CASES[case.id] = case
    return case


def get(case_id: str) -> Optional[Case]:
    _load()
    return _CASES.get((case_id or "").strip().lower())


def registered() -> List[Case]:
    _load()
    return [_CASES[k] for k in sorted(_CASES)]


_LOADED = False


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from . import suite  # noqa: F401 - imported for its registrations
