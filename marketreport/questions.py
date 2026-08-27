"""The standing questions a market report answers.

A report is not a document with sections. It is a set of questions with their
answers, their sources, and an honest record of the ones nobody could answer —
and the document is a view over that set.

**A reader who finishes this report with questions has been failed by it.** That
is the standard, and it is not rhetorical. Nobody commissions a quarterly review
so they can ask more questions afterwards; they commission it so the questions
are already answered. So the standing set below is not a starting position for a
conversation — it is a claim about completeness, and any question a section
raises without answering is a defect in the report rather than an invitation to
the reader.

Which is what `raises` is for. A section that raises a question must have that
question answered before the report is finished, and `closure()` is the check.
An unanswered follow-up is reported as a hole, not as further reading.

These eleven come from the intersection of two independent professional formats:
the industry sections of filed S-1s (see `market-corpus/SCHEMA.md`) and the
IBISWorld report structure (see `RESEARCH_NOTES.md`). Where two formats built by
different professions for different buyers agree on a question, that question is
load-bearing. Where only one has it, it is noted as such.

Two of them are deliberately the same question asked twice. The profession's own
advice on market sizing is to run top-down and bottom-up independently and treat
convergence as a reliability signal — so Q2 and Q3 are separate agents that
never see each other's work, and their disagreement is a reported finding.

Q11 is ours. Neither profession writes it, for the same reason: both are paid to
produce an answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

#: How an answer is arrived at. `computed` is the important one: everything the
#: profession works out with a formula, we work out with a formula rather than
#: asking a model to consider it.
RETRIEVED = "retrieved"      # read out of a published source
COMPUTED = "computed"        # arithmetic over other answers
DERIVED = "derived"          # reasoned over other ANSWERS, never raw evidence
SUPPLIED = "supplied"        # the user told us
KINDS = (RETRIEVED, COMPUTED, DERIVED, SUPPLIED)


@dataclass(frozen=True)
class StandingQuestion:
    """One question every market report answers, and how it gets answered."""

    id: str
    text: str
    #: The report section this answer becomes.
    section: str
    kind: str = RETRIEVED
    #: Which agent owns it. Agents are questions, not roles — see AGENTS.md.
    agent: str = ""
    #: Answers this question needs first. A data dependency, not an ordering
    #: preference: you cannot grade barriers to entry before knowing the
    #: concentration and the cost of operating.
    needs: Tuple[str, ...] = ()
    #: What this agent must NOT see. Specialization is only real if the context
    #: differs, and the denials do more work than the grants.
    denied: str = ""
    #: Questions a reader will have the moment they read this answer. They are
    #: part of the deliverable, not further reading — see the module docstring.
    raises: Tuple[str, ...] = ()
    #: Which professional format has this section. Both means load-bearing.
    seen_in: Tuple[str, ...] = ("s-1", "ibisworld")
    why: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


STANDING: Tuple[StandingQuestion, ...] = (
    StandingQuestion(
        "Q1", "What market is this, exactly — which activity, which customers, "
        "which geography?", section="definition", kind=SUPPLIED, agent="framing",
        denied="any market size figure",
        why="The boundary decides every number that follows. Choosing it after "
            "seeing a size is how a market gets defined to flatter a figure."),
    StandingQuestion(
        "Q2", "How large is this market, measured from published aggregates "
        "downward?", section="size_top_down", agent="sizing-td",
        needs=("Q1",), denied="the bottom-up estimate",
        raises=("Whose figure is it, and were they paid by somebody in the "
                "market?",
                "What does that aggregate include that this market does not?"),
        why="Cheap and fast, and the source of most inflated numbers, because "
            "most people stop at the first analyst figure they find."),
    StandingQuestion(
        "Q3", "How large is this market, counted from units upward?",
        section="size_bottom_up", agent="sizing-bu",
        needs=("Q1",), denied="the top-down estimate",
        raises=("Does this agree with the top-down figure, and if not, why?",
                "What is the revenue per unit, and whose revenue is it?"),
        why="Slower and operationally grounded. Every filing in the corpus used "
            "this method. Independence from Q2 is the entire point — their "
            "agreement is evidence and their divergence is a finding."),
    StandingQuestion(
        "Q4", "How fast is it growing, and on whose forecast?", section="growth",
        agent="growth", needs=("Q1",),
        denied="any single company's own projection",
        raises=("Is that growth in units or in price?",
                "How far out does the forecast run before it is extrapolation?"),
        why="agilon applied CMS's own published growth rates rather than an "
            "analyst CAGR. A filer's forecast is not a market forecast."),
    StandingQuestion(
        "Q5", "How concentrated is it?", section="structure", kind=COMPUTED,
        agent="structure", needs=("Q1",), denied="prose about competition",
        raises=("Is that concentration measured or estimated?",
                "How much of the market do the largest four hold?"),
        why="HHI and CR4 are arithmetic with published thresholds. A model asked "
            "to 'consider the concentration' returns a plausible adjective."),
    StandingQuestion(
        "Q6", "Who competes in it?", section="competitors", agent="competitors",
        needs=("Q1",), denied="market-size findings",
        raises=("Which of them are actually in this segment rather than "
                "adjacent to it?",
                "Is anyone large enough to absorb this as a feature?"),
        why="So a large number never becomes evidence about who is in the "
            "market. These are separate questions and conflating them is how a "
            "deck's framing survives."),
    StandingQuestion(
        "Q7", "What does it cost to operate in it?", section="economics",
        agent="economics", needs=("Q1",),
        denied="any single firm's own economics",
        raises=("What does it cost to start, as distinct from to run?",
                "Where does the money go — labour, materials, rent?"),
        why="The corpus constraint: every filing takes its value-per-unit from "
            "its own books, and a standalone report has no books."),
    StandingQuestion(
        "Q8", "What rules govern it — licences, permits, thresholds?",
        section="regulation", agent="regulation", needs=("Q1",),
        denied="everything except statute and licensing bodies",
        raises=("Is there a threshold below which the rules do not apply?",
                "Is any of this changing?"),
        why="Narrow context, cheap model, and the one section where a missing "
            "exemption changes whether the business is legal to start."),
    StandingQuestion(
        "Q9", "How hard is it to enter, and is that getting harder or easier?",
        section="barriers", kind=DERIVED, agent="barriers",
        needs=("Q5", "Q7", "Q8"), denied="raw sources",
        raises=("What is the single hardest thing about entering?",),
        why="IBISWorld grades barriers high/medium/low AND trends them "
            "increasing/decreasing/steady. A level plus a direction beats a "
            "paragraph. Reasoned over findings, never over evidence."),
    StandingQuestion(
        "Q10", "Where is this market in its life cycle?", section="lifecycle",
        kind=DERIVED, agent="lifecycle", needs=("Q4", "Q5"),
        denied="raw sources", seen_in=("ibisworld",),
        why="IBISWorld has this in every report and no S-1 does, because a "
            "filer would rather not say its market is mature."),
    StandingQuestion(
        "Q11", "What could not be established, and why?", section="gaps",
        kind=COMPUTED, agent="", needs=(), seen_in=(),
        why="Ours. Neither profession writes it — both are paid to deliver an "
            "answer, and a gap is the opposite of the product they sell."),
)

BY_ID: Dict[str, StandingQuestion] = {q.id: q for q in STANDING}

#: Sections in the order a reader should meet them. Definition first because
#: nothing else means anything without it; gaps last because a reader should
#: finish knowing the limits of what they just read.
SECTION_ORDER: Tuple[str, ...] = tuple(q.section for q in STANDING)


def load_bearing() -> List[StandingQuestion]:
    """Questions both professional formats ask. The spine of the report."""
    return [q for q in STANDING if len(q.seen_in) >= 2]


def order() -> List[StandingQuestion]:
    """The questions in an order that satisfies every dependency.

    A topological sort rather than a hand-written list, because `needs` is a
    data dependency: barriers cannot be graded before concentration and
    operating cost exist. Hand-ordering works until somebody adds a question
    and does not notice they have moved it above the thing it reads.
    """
    done: List[StandingQuestion] = []
    seen: set = set()
    remaining = list(STANDING)
    while remaining:
        progressed = False
        for question in list(remaining):
            if all(n in seen for n in question.needs):
                done.append(question)
                seen.add(question.id)
                remaining.remove(question)
                progressed = True
        if not progressed:
            unresolved = ", ".join(q.id for q in remaining)
            raise ValueError(
                f"these questions depend on each other in a cycle and none can "
                f"go first: {unresolved}. A cycle here means two answers each "
                f"claim to need the other, which cannot be true of a data "
                f"dependency.")
    return done


@dataclass
class Answer:
    """What a question got answered with, or why it did not."""

    question_id: str
    #: Free-text conclusion a reader sees.
    statement: str = ""
    #: The number, when the answer is one.
    value: Optional[float] = None
    value_text: str = ""
    unit: str = ""
    as_of: str = ""
    kind: str = RETRIEVED
    confidence: str = "low"
    source_ids: List[str] = field(default_factory=list)
    #: Set when the question could not be answered. An answered question and an
    #: unanswerable one are different states, and "" is neither.
    unanswered_because: str = ""
    #: Anything section-specific: HHI, CR4, ring breakdowns, a grade plus a
    #: trend. Kept open so a section can carry its own shape without every
    #: section needing a field here.
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def answered(self) -> bool:
        return not self.unanswered_because and bool(
            self.statement or self.value is not None or self.detail)

    @property
    def checkable(self) -> bool:
        """Whether a reader could go and verify this themselves."""
        return self.answered and (bool(self.source_ids)
                                  or self.kind in (COMPUTED, DERIVED, SUPPLIED))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["answered"] = self.answered
        d["checkable"] = self.checkable
        return d


class AnswerSet:
    """Every answer for one market report.

    The primary artifact. Renderers read this; nothing renders from prose.
    """

    def __init__(self, market: str) -> None:
        self.market = market
        self.answers: Dict[str, Answer] = {}
        #: Follow-ups raised during the run that were answered inline. Kept so
        #: the report can show its own working; NOT a queue for the reader.
        self.extra: List[Tuple[str, str]] = []

    def record(self, answer: Answer) -> Answer:
        self.answers[answer.question_id] = answer
        return answer

    def get(self, qid: str) -> Optional[Answer]:
        return self.answers.get(qid)

    def answered(self) -> List[Answer]:
        return [a for a in self.answers.values() if a.answered]

    def unanswered(self) -> List[Answer]:
        return [a for a in self.answers.values() if not a.answered]

    def section(self, name: str) -> Optional[Answer]:
        for question in STANDING:
            if question.section == name:
                return self.answers.get(question.id)
        return None

    def closure(self) -> Dict[str, Any]:
        """Whether the report leaves the reader with questions.

        The completeness test, and the one that matters. Every answered section
        raises questions a reader will immediately have; each of those must be
        addressed somewhere before the report is finished. An open one is a
        hole in the deliverable, not further reading.

        Deliberately conservative about what counts as addressed: a follow-up
        is closed when some answer in the set actually speaks to it, and the
        default is open. A completeness check that grades itself generously is
        worth less than no check at all.
        """
        open_items: List[Dict[str, str]] = []
        closed = 0
        haystack = " ".join(
            f"{a.statement} {a.value_text} {' '.join(str(v) for v in a.detail.values())}"
            for a in self.answers.values() if a.answered).lower()

        for question in STANDING:
            answer = self.answers.get(question.id)
            if answer is None or not answer.answered:
                continue          # an unanswered section raises nothing yet
            for follow_up in question.raises:
                if self._addressed(follow_up, haystack):
                    closed += 1
                else:
                    open_items.append({
                        "raised_by": question.id,
                        "section": question.section,
                        "question": follow_up})

        # An unanswered standing question is also a question the reader leaves
        # with. Counting only follow-ups of ANSWERED sections meant a report
        # that answered two of eleven questions reported `complete: True`,
        # because the nine it skipped raised nothing — a gate that cannot fail,
        # quoted as though it had passed. Completeness has to mean both.
        missing = [
            {"raised_by": q.id, "section": q.section,
             "question": q.text,
             "why": (self.answers[q.id].unanswered_because
                     if q.id in self.answers else "never attempted")}
            for q in STANDING
            if q.id not in self.answers or not self.answers[q.id].answered]

        total = closed + len(open_items)
        complete = not open_items and not missing
        note = ""
        if missing:
            note = (f"{len(missing)} of {len(STANDING)} standing questions are "
                    f"unanswered. ")
        if open_items:
            note += (f"{len(open_items)} follow-up question(s) this report "
                     f"raises are not answered in it. ")
        if note:
            note += ("A reader finishing this would still have to go and ask, "
                     "which is the failure this check exists to catch.")

        return {
            "follow_ups": total,
            "closed": closed,
            "open": open_items,
            "unanswered_standing": missing,
            "complete": complete,
            "note": note,
        }

    @staticmethod
    def _addressed(follow_up: str, haystack: str) -> bool:
        """Whether anything in the report speaks to a raised question.

        Content-word overlap, and a demanding threshold. This is a check on our
        own completeness, so a generous reading of it would be self-serving.
        """
        import re

        stop = {"what", "does", "that", "this", "the", "and", "for", "are",
                "is", "it", "of", "in", "to", "a", "an", "or", "how", "much",
                "many", "than", "with", "from", "them", "they", "which",
                "actually", "rather", "single", "before", "there", "into",
                "whose", "were", "somebody", "anyone", "large", "enough",
                "where", "does", "have", "been", "will", "far", "out", "not",
                "any", "why", "if"}
        words = {w for w in re.findall(r"[a-z]{3,}", follow_up.lower())
                 if w not in stop}
        if not words:
            return False
        hit = sum(1 for w in words if w in haystack)
        return hit >= max(2, len(words) // 2)

    def coverage(self) -> Dict[str, Any]:
        """How much of the standing report this run actually produced.

        Reported rather than implied. A report answering four of eleven
        questions is a real output, and a reader is entitled to know that
        before they act on it.
        """
        total = len(STANDING)
        answered = len(self.answered())
        checkable = len([a for a in self.answers.values() if a.checkable])
        return {
            "questions": total,
            "answered": answered,
            "checkable": checkable,
            "unanswered": total - answered,
            "fraction": round(answered / total, 3) if total else 0.0,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market,
            "coverage": self.coverage(),
            "closure": self.closure(),
            "answers": {qid: a.to_dict() for qid, a in self.answers.items()},
            "questions": [q.to_dict() for q in STANDING],
            "extra_questions": [{"text": t, "because": b} for t, b in self.extra],
        }
