"""Answer the standing questions, in dependency order, and assemble the report.

The composition layer. Each standing question has an agent that owns it; this
walks them in an order that satisfies the data dependencies, records what came
back, and then checks its own completeness.

Two things it deliberately does not do.

**It does not let the two sizing agents see each other.** Q2 (top-down) and Q3
(bottom-up) are the same question asked twice by design — the profession's own
advice is to run both independently and read convergence as a reliability
signal. If either could see the other's answer it would anchor on it, and the
signal would be manufactured rather than observed.

**It does not treat an unanswered question as an absent section.** Every question
produces an `Answer`; an unanswerable one carries the reason. A report with a
missing section looks like an oversight. A report with a section that says
"this could not be established, and here is why" is doing its job.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from .questions import (COMPUTED, DERIVED, STANDING, Answer, AnswerSet,
                        StandingQuestion, order)
from .structure import (Barriers, Concentration, barriers, lifecycle,
                        saturation)

#: An agent takes the market definition plus whatever prior answers it is
#: allowed to see, and returns an Answer. Registered rather than hard-wired so
#: a backend can be swapped without touching this file.
Agent = Callable[..., Answer]

_AGENTS: Dict[str, Agent] = {}


def register(name: str) -> Callable[[Agent], Agent]:
    def wrap(fn: Agent) -> Agent:
        _AGENTS[name] = fn
        return fn
    return wrap


def agent_for(name: str) -> Optional[Agent]:
    return _AGENTS.get(name)


def registered() -> List[str]:
    return sorted(_AGENTS)


class MarketDefinition:
    """What the user told us the market is. The answer to Q1.

    Deliberately the user's to supply rather than ours to infer. The boundary
    decides every number that follows, and a boundary chosen after seeing a size
    is how a market gets defined to flatter a figure.
    """

    def __init__(self, *, label: str, naics: str = "", state_fips: str = "",
                 county_fips: str = "", customer: str = "",
                 geography_label: str = "", demo: bool = False) -> None:
        #: Answer from recorded fixtures instead of the live APIs. Carried on
        #: the definition rather than passed separately so it reaches the
        #: renderer — a demo figure must be labelled everywhere it appears,
        #: not only where the caller remembered.
        self.demo = bool(demo)
        self.label = label.strip()
        self.naics = "".join(c for c in str(naics) if c.isdigit())
        self.state_fips = str(state_fips or "").strip()
        self.county_fips = str(county_fips or "").strip()
        self.customer = customer.strip()
        self.geography_label = (geography_label
                                or self._default_geography()).strip()

    def _default_geography(self) -> str:
        if self.county_fips and self.state_fips:
            return f"county {self.state_fips}{self.county_fips}"
        if self.state_fips:
            return f"state {self.state_fips}"
        return "United States"

    @property
    def usable_naics(self) -> bool:
        """A 1-3 digit code is a whole economic sector, which would make every
        count meaningless while looking authoritative."""
        return 4 <= len(self.naics) <= 6

    def to_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "naics": self.naics, "demo": self.demo,
                "state_fips": self.state_fips, "county_fips": self.county_fips,
                "customer": self.customer,
                "geography_label": self.geography_label,
                "usable_naics": self.usable_naics}


def unanswered(question: StandingQuestion, because: str) -> Answer:
    """An honest non-answer. Not an empty one — those read as oversights."""
    return Answer(question_id=question.id, kind=question.kind,
                  unanswered_because=because)


def build(market: MarketDefinition, *,
          on_event: Optional[Callable[[str], None]] = None,
          only: Optional[List[str]] = None) -> AnswerSet:
    """Answer every standing question for one market."""
    emit = on_event or (lambda *_: None)
    answers = AnswerSet(market.label)
    started = time.time()

    for question in order():
        if only and question.id not in only:
            continue

        # Dependencies first. A question whose inputs are missing is not a
        # failure of its agent, and saying which input was missing is more
        # useful than saying the section is empty.
        missing = [n for n in question.needs
                   if not (answers.get(n) and answers.get(n).answered)]
        if missing:
            answers.record(unanswered(
                question,
                f"needs {', '.join(missing)}, which "
                f"{'was' if len(missing) == 1 else 'were'} not established"))
            emit(f"  {question.id} {question.section}: skipped, needs "
                 f"{', '.join(missing)}")
            continue

        agent = _AGENTS.get(question.agent) if question.agent else None
        if agent is None:
            if question.id == "Q11":
                answers.record(_gaps(answers))
                continue
            answers.record(unanswered(
                question, f"no agent is registered for {question.agent!r}"))
            emit(f"  {question.id} {question.section}: no agent")
            continue

        # Only the answers this question declares it needs. The denials in
        # AGENTS.md are enforced here rather than requested in a prompt —
        # sizing-td cannot anchor on sizing-bu because it is never handed it.
        visible = {n: answers.get(n) for n in question.needs}
        try:
            answer = agent(market=market, question=question, seen=visible)
        except Exception as exc:  # noqa: BLE001 - one bad agent must not end the run
            answer = unanswered(question, f"the {question.agent} agent failed: {exc}")

        # Demo taints everything downstream of it. A barriers grade derived from
        # demo concentration is a demo answer, and reporting it as live would
        # let invented numbers acquire a provenance badge by passing through one
        # more function. The rule is structural: inherit from what you read.
        if not answer.demo and any(
                (answers.get(n) is not None and answers.get(n).demo)
                for n in question.needs):
            answer.demo = True

        answers.record(answer)
        emit(f"  {question.id} {question.section}: "
             + ("answered" if answer.answered
                else f"unanswered — {answer.unanswered_because[:70]}"))

    # Q11 last, always, because it reports on everything before it.
    if not only or "Q11" in (only or []):
        answers.record(_gaps(answers))

    answers.extra.append(("elapsed", f"{time.time() - started:.1f}s"))
    return answers


def _gaps(answers: AnswerSet) -> Answer:
    """Q11 — what could not be established, and why.

    Computed from the run's own record rather than written. Neither professional
    format has this section; both are paid to deliver an answer, and a gap is
    the opposite of the product they sell.
    """
    holes = []
    for question in STANDING:
        answer = answers.get(question.id)
        if question.id == "Q11" or answer is None:
            continue
        if not answer.answered:
            holes.append({"question": question.id, "section": question.section,
                          "asked": question.text,
                          "because": answer.unanswered_because})

    closure = answers.closure()
    statement = (
        f"{len(holes)} of {len(STANDING) - 1} questions could not be answered."
        if holes else "Every standing question was answered.")
    if closure["open"]:
        statement += (f" {len(closure['open'])} follow-up question(s) this "
                      f"report raises are not answered in it.")

    return Answer(
        question_id="Q11", kind=COMPUTED, statement=statement,
        confidence="high",
        detail={"unanswered": holes,
                "open_follow_ups": closure["open"],
                "coverage": answers.coverage()})


@register("convergence")
def _convergence_agent(*, market: MarketDefinition, question: StandingQuestion,
                       seen: Dict[str, Optional[Answer]]) -> Answer:
    """Compare the two independent size estimates.

    The reason both were built. Two methods that never see each other's work
    and then agree is evidence; two that diverge is a finding about where the
    local market departs from the national average. Averaging them would throw
    away the only thing their independence bought.

    Uses the shared three-way comparison, so a pair that measures different
    things comes back INCOMPARABLE and settles nothing rather than being read
    as disagreement.
    """
    top_down, bottom_up = seen.get("Q2"), seen.get("Q3")
    if not (top_down and bottom_up and top_down.answered and bottom_up.answered):
        return unanswered(question, "both size estimates are needed to compare "
                                    "them, and at least one is missing")

    verdict, because = top_down.compare(bottom_up)
    lines = [f"top-down:   {top_down.value_text}",
             f"bottom-up:  {bottom_up.value_text}"]

    if verdict == "agree":
        statement = (
            f"The two methods agree ({because}). They were run independently "
            f"and neither saw the other, so agreement here is genuine "
            f"corroboration rather than one figure anchoring the other.")
        confidence = "high"
    elif verdict == "disagree":
        ratio = (max(top_down.value or 0, bottom_up.value or 0)
                 / max(min(top_down.value or 0, bottom_up.value or 0), 1))
        bigger = "top-down" if (top_down.value or 0) > (bottom_up.value or 0) \
            else "bottom-up"
        statement = (
            f"The two methods disagree — {because}, with the {bigger} figure "
            f"the larger. That is not an error to reconcile. Top-down assumes "
            f"establishments here are of national average size; bottom-up uses "
            f"the local average directly. A gap of {ratio:.1f}x says "
            f"establishments in this geography are "
            f"{'smaller' if bigger == 'top-down' else 'larger'} than typical, "
            f"which is a real finding about the market.")
        confidence = "medium"
    else:
        statement = (f"The two estimates could not be compared: {because}. "
                     f"Neither corroborates nor contradicts the other.")
        confidence = "low"

    return Answer(
        question_id=question.id, kind=COMPUTED, statement=statement,
        confidence=confidence,
        detail={"verdict": verdict, "because": because,
                "top_down": top_down.value, "bottom_up": bottom_up.value,
                "detail_lines": lines})


# ------------------------------------------------------------ derived agents
#
# These two read other ANSWERS and never raw evidence, which is the denial that
# makes them safe to run last. Both are arithmetic plus a published threshold,
# so neither uses a model.

@register("barriers")
def _barriers_agent(*, market: MarketDefinition, question: StandingQuestion,
                    seen: Dict[str, Optional[Answer]]) -> Answer:
    conc = _concentration_from(seen.get("Q5"))
    cost = None
    economics = seen.get("Q7")
    if economics is not None and economics.answered:
        cost = economics.detail.get("startup_cost")
    licences = None
    note = ""
    regulation = seen.get("Q8")
    if regulation is not None and regulation.answered:
        licences = regulation.detail.get("licence_count")
        note = regulation.detail.get("licence_note", "")

    graded: Barriers = barriers(conc=conc, startup_cost=cost,
                                licences=licences, licence_note=note)
    if not graded.level:
        return unanswered(question, graded.because)
    return Answer(
        question_id=question.id, kind=DERIVED,
        statement=f"Barriers to entry are {graded.level} and {graded.trend}.",
        confidence="medium", detail=graded.to_dict())


@register("lifecycle")
def _lifecycle_agent(*, market: MarketDefinition, question: StandingQuestion,
                     seen: Dict[str, Optional[Answer]]) -> Answer:
    growth_answer = seen.get("Q4")
    growth = growth_answer.value if growth_answer and growth_answer.answered else None
    conc = _concentration_from(seen.get("Q5"))
    stage, because = lifecycle(growth, conc)
    if not stage:
        return unanswered(question, because)

    # Penetration and growth read together, which is how the profession reads
    # saturation. We have no penetration figure — that needs the RATE term, and
    # nobody publishes it — so `saturation()` reports on growth alone AND says
    # what remains unknown, rather than implying a fuller reading than we have.
    full = saturation(None, growth)

    statement = f"This market is in its {stage} stage — {because}."
    if full.reading:
        statement += f" On saturation it reads as {full.reading}: {full.because}."

    return Answer(
        question_id=question.id, kind=DERIVED,
        statement=statement, confidence="medium",
        detail={"stage": stage, "because": because,
                "saturation": full.to_dict()})


def _concentration_from(answer: Optional[Answer]) -> Optional[Concentration]:
    """Rebuild a Concentration from a recorded answer's detail."""
    if answer is None or not answer.answered:
        return None
    raw = answer.detail.get("concentration")
    if not isinstance(raw, dict):
        return None
    return Concentration(**{k: v for k, v in raw.items()
                            if k in Concentration.__dataclass_fields__})
