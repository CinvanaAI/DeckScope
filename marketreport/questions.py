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

These twelve come from the intersection of two independent professional formats:
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
    #: Questions a reader will have the moment they read this answer, each
    #: paired with the answer field that must be populated for it to count as
    #: closed: ("the question", "Q5.detail.concentration.basis").
    #:
    #: Structural rather than lexical on purpose. The first version decided
    #: closure by counting content-word overlap against our own prose, which
    #: meant a section using the right vocabulary passed without answering
    #: anything — a completeness check we graded ourselves, over text we wrote,
    #: with a rule we chose.
    raises: Tuple[Tuple[str, str], ...] = ()
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
        raises=(("Whose figure is it, and does it come from somebody selling into "
                 "this market?", "Q2.source_ids"),
                ("What does that national aggregate assume about this "
                 "geography?", "Q2.detail.assumption")),
        why="Cheap and fast, and the source of most inflated numbers, because "
            "most people stop at the first analyst figure they find."),
    StandingQuestion(
        "Q3", "How large is this market, counted from units upward?",
        section="size_bottom_up", agent="sizing-bu",
        needs=("Q1",), denied="the top-down estimate",
        raises=(("Does this agree with the top-down figure, and if not, why?",
                 "Q12.detail.verdict"),
                ("What is the revenue per unit, and whose revenue is it?",
                 "Q3.detail.arithmetic")),
        why="Slower and operationally grounded. Every filing in the corpus used "
            "this method. Independence from Q2 is the entire point — their "
            "agreement is evidence and their divergence is a finding."),
    StandingQuestion(
        "Q4", "How fast is it growing, and on whose forecast?", section="growth",
        agent="growth", needs=("Q1",),
        denied="any single company's own projection",
        raises=(("Is that growth in firms or in revenue?", "Q4.detail.basis"),
                ("Over what period was it measured?", "Q4.detail.prior_year")),
        why="agilon applied CMS's own published growth rates rather than an "
            "analyst CAGR. A filer's forecast is not a market forecast."),
    StandingQuestion(
        "Q5", "How concentrated is it?", section="structure", kind=COMPUTED,
        agent="structure", needs=("Q1",), denied="prose about competition",
        raises=(("Is that concentration measured or estimated?",
                 "Q5.detail.concentration.basis"),
                ("How much of the market do the largest four hold?",
                 "Q5.detail.concentration.cr4")),
        why="HHI and CR4 are arithmetic with published thresholds. A model asked "
            "to 'consider the concentration' returns a plausible adjective."),
    StandingQuestion(
        "Q6", "Who competes in it?", section="competitors", agent="competitors",
        needs=("Q1",), denied="market-size findings",
        raises=(("Which of them are in this segment rather than adjacent to it?",
                 "Q6.detail.participants"),),
        why="So a large number never becomes evidence about who is in the "
            "market. These are separate questions and conflating them is how a "
            "deck's framing survives."),
    StandingQuestion(
        "Q7", "What does it cost to operate in it?", section="economics",
        agent="economics", needs=("Q1",),
        denied="any single firm's own economics",
        raises=(("What does it cost to start, as distinct from to run?",
                 "Q7.detail.startup_cost_note"),),
        why="The corpus constraint: every filing takes its value-per-unit from "
            "its own books, and a standalone report has no books."),
    StandingQuestion(
        "Q8", "What rules govern it — licences, permits, thresholds?",
        section="regulation", agent="regulation", needs=("Q1",),
        denied="everything except statute and licensing bodies",
        raises=(("Is there a threshold below which the rules do not apply?",
                 "Q8.detail.threshold"),),
        why="Narrow context, cheap model, and the one section where a missing "
            "exemption changes whether the business is legal to start."),
    StandingQuestion(
        "Q9", "How hard is it to enter, and is that getting harder or easier?",
        section="barriers", kind=DERIVED, agent="barriers",
        needs=("Q5", "Q7", "Q8"), denied="raw sources",
        raises=(("What is the single hardest thing about entering?",
                 "Q9.detail.reasons"),),
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
        "Q12", "Do the two size estimates agree — and what does their "
               "agreement actually mean, given the operands they share?",
        section="convergence", kind=COMPUTED, agent="convergence",
        needs=("Q2", "Q3"), denied="",
        seen_in=("s-1", "ibisworld"),
        why="The profession's advice is to run top-down and bottom-up "
            "separately and read convergence as a reliability signal — but "
            "an external audit's algebra showed our two estimates share the "
            "local establishment count as a material operand, so this "
            "question deliberately does not call them independent: the "
            "convergence agent reads the operand overlap and says only what "
            "it supports. "
            "Building the two agents without ever comparing them left the "
            "design's central claim unexercised — two numbers on a page and no "
            "statement about what their relationship means."),
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
    """What a question got answered with, or why it did not.

    Deliberately the same shape as `deckscope.research.findings.Finding`, and it
    carries the same `metric` identity, because it IS the same idea: something
    established, with a value, a unit, a date and its sources.

    Building it separately was a real mistake and this is the repair. The
    semantic-comparison rule that stops "the market is $7B" corroborating "a
    competitor raised $7.2B" lived in one half of a repository that had two, so
    the newer half could make exactly the error the older half had been fixed
    against. One answer type, one comparison rule.
    """

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
    #: The exact reproducible request URLs (secrets stripped) behind the
    #: figure, when its sources are API datasets. The fourth audit's
    #: provenance finding: naming "County Business Patterns 2022" without
    #: the parameters that scoped the request is a pointer to a library,
    #: not to the page.
    source_urls: List[str] = field(default_factory=list)
    #: Set when the question could not be answered. An answered question and an
    #: unanswerable one are different states, and "" is neither.
    unanswered_because: str = ""
    #: True when this came from recorded sample data rather than a live source.
    #: A demo figure is never checkable: there is no source to go and read,
    #: because I made the number up. Carrying this on the answer rather than
    #: relying on the caller to remember is the difference between a labelled
    #: illustration and a figure that becomes quotable two hops downstream.
    demo: bool = False
    #: Anything section-specific: HHI, CR4, ring breakdowns, a grade plus a
    #: trend. Kept open so a section can carry its own shape without every
    #: section needing a field here.
    detail: Dict[str, Any] = field(default_factory=dict)
    #: What this number is ABOUT — subject, measure, basis, period. Filled in on
    #: construction from the shared classifier, so two answers can only be
    #: compared when they measure the same thing.
    metric: Optional[Any] = None

    def __post_init__(self) -> None:
        # Parse the magnitude out of the text, exactly as FindingRegistry.add
        # does for a Finding. Without this an Answer carrying "$7B" had
        # `value is None`, and the shared comparison rule reported "neither
        # carries a figure to compare" for two answers that plainly did —
        # the first thing the merge exposed.
        if self.value is None and self.value_text:
            from deckscope.research.findings import parse_number
            self.value = parse_number(self.value_text)
        if self.metric is None and (self.statement or self.value_text):
            from deckscope.research.metrics import classify
            self.metric = classify(self.statement, unit=self.unit,
                                   value_text=str(self.value_text or ""),
                                   as_of=self.as_of)

    def compare(self, other: "Answer"):
        """How this answer stands to another: agree, disagree, or incomparable.

        The same three-way rule the research loop uses. `INCOMPARABLE` is the
        one that matters — two numbers measuring different things are neither
        corroboration nor contradiction, and collapsing that into a boolean is
        how a market size and a funding round confirmed each other.
        """
        from deckscope.research.closing import relation
        return relation(self, other)

    @property
    def answered(self) -> bool:
        return not self.unanswered_because and bool(
            self.statement or self.value is not None or self.detail)

    @property
    def sourced(self) -> bool:
        """Whether anything backs this. Named to match `Finding.sourced`, which
        is what the shared comparison rule reads."""
        return self.checkable

    @property
    def method(self) -> str:
        """The research half calls this `method`; here it is `kind`. Aliased so
        one comparison rule can read both without knowing which it holds."""
        return self.kind

    @property
    def id(self) -> str:
        return self.question_id

    @property
    def checkable(self) -> bool:
        """Whether a reader could go and verify this themselves.

        A demo answer never can. Its `source_ids` name a dataset that was not
        actually queried, so counting it as checkable would have the demo
        report a perfect provenance record over invented numbers — which is the
        fixture-maturity trap wearing a provenance badge.
        """
        if self.demo:
            return False
        return self.answered and (bool(self.source_ids)
                                  or self.kind in (COMPUTED, DERIVED, SUPPLIED))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["answered"] = self.answered
        d["checkable"] = self.checkable
        # `asdict` leaves the metric's `subject` as a frozenset, which json
        # cannot encode — the same bug the atomic-write guard caught on the
        # research half, so it gets the same fix here rather than waiting to be
        # discovered separately.
        d["metric"] = self.metric.to_dict() if self.metric is not None else None
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
        #: Panels produced by specialists for sections they answered. Carried
        #: on the answer set so a renderer draws the chart in place, rather
        #: than the report and the panels being two artifacts a reader has to
        #: hold side by side.
        self.panels: List[Any] = []

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

        for question in STANDING:
            answer = self.answers.get(question.id)
            if answer is None or not answer.answered:
                continue          # an unanswered section raises nothing yet
            for follow_up, path in question.raises:
                if self._populated(path):
                    closed += 1
                else:
                    open_items.append({
                        "raised_by": question.id,
                        "section": question.section,
                        "question": follow_up,
                        "needs": path})

        # An unanswered standing question is also a question the reader leaves
        # with. Counting only follow-ups of ANSWERED sections meant a report
        # that answered two of twelve questions reported `complete: True`,
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

    def _populated(self, path: str) -> bool:
        """Whether the field a follow-up needs actually holds something.

        `"Q5.detail.concentration.basis"` is closed when that value exists and
        is not empty. No prose is read, so the check cannot be satisfied by
        wording — which was the whole problem with the version this replaces.
        """
        head, _, rest = path.partition(".")
        answer = self.answers.get(head)
        if answer is None or not answer.answered:
            return False
        if not rest:
            return True

        node: Any = answer
        parent: Any = None
        for part in rest.split("."):
            parent = node
            if isinstance(node, dict):
                node = node.get(part)
            else:
                node = getattr(node, part, None)
            if node is None:
                # A reasoned "not identifiable" IS an answer to the
                # follow-up. The fifth audit's product-level contradiction:
                # the report correctly established that CR4 cannot be known
                # from establishment data, then its own completeness gate
                # held the report hostage for the number it had just
                # explained cannot exist. An absence is closed when the
                # containing record ESTABLISHES it — a stated basis of
                # not-identifiable with a reason — and open when the field
                # is merely empty.
                if (isinstance(parent, dict)
                        and str(parent.get("basis", "")) == "not-identifiable"
                        and parent.get("because")):
                    return True
                return False
        # An empty list, dict or string is a field that exists and says nothing.
        if isinstance(node, (list, dict, str)) and not node:
            return False
        return True

    def coverage(self) -> Dict[str, Any]:
        """How much of the standing report this run actually produced.

        Reported rather than implied. A report answering four of twelve
        questions is a real output, and a reader is entitled to know that
        before they act on it.
        """
        total = len(STANDING)
        answered = len(self.answered())
        checkable = len([a for a in self.answers.values() if a.checkable])
        # Live and demo counted separately, because "10 of 12 answered" over
        # invented data and over real data are very different claims and the
        # first was being reported as though it were the second.
        from_demo = len([a for a in self.answers.values()
                         if a.answered and a.demo])
        return {
            "questions": total,
            "answered": answered,
            "answered_live": answered - from_demo,
            "answered_from_demo": from_demo,
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
