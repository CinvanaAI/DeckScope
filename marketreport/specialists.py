"""Specialists — agents with one job, that return a panel.

A specialist is three things and nothing else:

1. **The questions it opens with**, written the way a person would ask them.
2. **What it does with the findings** beyond handing them to the shaper — the
   cross-checks that are specific to its job.
3. **Its name**, so a panel can say what made it.

Everything else is borrowed: `deckscope.research.ResearchLoop` runs the loop,
`router.py` decides whether a question goes to a search engine or a government
dataset, `security/` screens what comes back, and `shaper.py` turns the findings
into a shape. None of that is new. It was all here, wired only to deck analysis.

The point of writing specialists this way — questions plus cross-checks, not a
long prompt — is that the interesting behaviour lands in code that can be
tested. `market_share`'s useful trick is noticing that two trackers disagree
because they are counting different things, and that is `_disagreements()`
below: forty lines of comparison over `MetricID`, running whether or not the
model happens to think of it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from .panel import ABSENT, Figure, Panel, unanswered
from .shaper import build_panel, implied_total, make_shaper

__all__ = ["Specialist", "register", "get", "registered", "run_specialist",
           "MARKET_SHARE"]


@dataclass
class Specialist:
    """One job, its opening questions, and its cross-checks."""

    name: str
    #: What this specialist answers, in the words a person would use. Shown to
    #: the manager when it decides what to dispatch, so it is a description of
    #: the job rather than of the implementation.
    job: str
    #: `{market}` and `{place}` are filled from the request.
    seeds: Sequence[str] = ()
    #: The beat each seed belongs to, same length as `seeds`.
    beats: Sequence[str] = ()
    #: How this job goes wrong, in one or two sentences. Given to the question
    #: generator so the opening questions are chosen to avoid the failure, and
    #: checked in code afterwards wherever it is checkable.
    refuse: str = ""
    #: Runs after the loop, before the shaper. Returns extra figures and
    #: caveats — the specialist's own analysis, in Python.
    check: Optional[Callable[..., Dict[str, Any]]] = None
    #: How many loop iterations this job is worth.
    iterations: int = 10
    #: Standing questions in the market report this specialist can answer.
    #:
    #: This is the convergence Von named: "how you gonna make a market report
    #: if you can't make the market share report you just made?" Q5 (how
    #: concentrated is it) and Q6 (who competes) ARE the market-share question.
    #: The Census HHI answer is a proxy that only works for fragmented US
    #: trades and returns "unconcentrated" for nearly all of them.
    #:
    #: Declared on the specialist rather than on the question so a new
    #: specialist can claim a section without editing the report's spine.
    answers: Sequence[str] = ()

    def questions(self, market: str, place: str = "") -> List[Dict[str, Any]]:
        where = place or "worldwide"
        rows = []
        for text, beat in zip(self.seeds, self.beats or ["sizing"] * len(self.seeds)):
            rows.append({"text": text.format(market=market, place=where),
                         "beat": beat, "weight": "high"})
        return rows


_SPECIALISTS: Dict[str, Specialist] = {}


def register(spec: Specialist) -> Specialist:
    _SPECIALISTS[spec.name] = spec
    return spec


def get(name: str) -> Optional[Specialist]:
    return _SPECIALISTS.get((name or "").strip().lower())


def registered() -> List[Specialist]:
    return [_SPECIALISTS[k] for k in sorted(_SPECIALISTS)]


# ------------------------------------------------- the market-share checks

def _entities(panel: Panel) -> List[str]:
    """The named players this panel is about, taken from its own slices.

    The panel already knows who is in the market — every wedge is labelled with
    a company. Reusing that as the entity vocabulary is better than a general
    named-entity guess, because it is exactly the set the answer talks about.
    """
    names = []
    for series in panel.series:
        for wedge in series.slices:
            name = wedge.label.strip().lower()
            if name and name not in names and "else" not in name:
                names.append(name)
    return names


def _mentions(finding: Any, entities: Sequence[str]) -> Optional[str]:
    text = str(getattr(finding, "statement", "") or "").lower()
    for name in entities:
        if name and name in text:
            return name
    return None


def _series_of(finding: Any, panel: Panel) -> Optional[str]:
    fid = str(getattr(finding, "id", ""))
    for series in panel.series:
        if any(w.finding_id == fid for w in series.slices):
            return series.label
    return None


def _disagreements(findings: Sequence[Any], panel: Panel) -> List[str]:
    """Two sources measuring the same thing and reporting different numbers.

    This is the move that produced the cell-phone answer by hand. IDC said
    Samsung led, Counterpoint said Apple, and the contradiction was not noise to
    resolve — it was the doorway to the finding.

    Getting it to fire on the right pairs took two corrections, both of which
    the generic `relation()` cannot make because they are facts about *this*
    kind of question:

    **Two companies are not two sources.** "Samsung held 22% shipment share"
    and "Xiaomi held 11% shipment share" share almost all their content words,
    so `comparable()` admitted them and the numeric distance did the rest. They
    were reported as a disagreement between sources when they are simply two
    different companies. So a pair must name the SAME company.

    **Two yardsticks are not two sources either.** Samsung at 22% of units and
    16% of revenue is the entire point of the panel, not an inconsistency in it.
    `measure` is `rate` for both — the metric identity is deliberately coarse
    and cannot separate shipment share from revenue share — so the panel's own
    series membership does that job instead.

    Both corrections live here rather than in `metrics.py` on purpose. They are
    true of market-share questions and would be wrong somewhere else, and the
    generic layer is only supposed to be right about one thing: may these two
    numbers be compared at all.
    """
    from deckscope.research.closing import relation

    entities = _entities(panel)
    notes: List[str] = []
    seen: set = set()
    items = [f for f in findings if getattr(f, "value", None) is not None]

    for i, left in enumerate(items):
        for right in items[i + 1:]:
            pair = tuple(sorted((str(getattr(left, "id", "")),
                                 str(getattr(right, "id", "")))))
            if pair in seen:
                continue
            seen.add(pair)

            who_left, who_right = (_mentions(left, entities),
                                   _mentions(right, entities))
            if who_left != who_right:
                continue        # different companies, or one is market-wide

            series_left, series_right = (_series_of(left, panel),
                                         _series_of(right, panel))
            if series_left != series_right:
                continue        # different yardsticks — that IS the finding

            try:
                verdict, why = relation(left, right)
            except Exception:  # noqa: BLE001 - a bad pair must not end the run
                continue
            if verdict != "disagree":
                continue

            about = f"{who_left.title()}'s " if who_left else "the market's "
            notes.append(
                f"Two sources disagree about {about}"
                f"{(series_left or 'figures').lower()}: "
                f"\"{left.statement}\" against \"{right.statement}\". "
                f"Nobody counts this market directly — every tracker models it "
                f"— so a spread between reputable firms is the normal noise "
                f"floor, and a figure quoted to one decimal from a single "
                f"tracker is hiding that.")
    return notes[:4]


def _market_share_check(*, findings: Sequence[Any], panel: Panel,
                        **_: Any) -> Dict[str, Any]:
    """Market-share's own analysis: convergence, and the size of the gap.

    Two things worth doing in code, both of which I did by hand:

    **Cross-check the total by a second path.** If one finding gives a player's
    revenue and another gives that player's share, the implied market total
    follows — and if a third finding states the total directly, the two paths
    either agree or they do not. That is the convergence check the market report
    already runs on its two sizings, applied to whatever the loop happened to
    find.

    **Say how far apart the two yardsticks are.** When a panel carries a share
    pair, the interesting number is not either share; it is the ratio between a
    player's revenue share and its unit share. Apple at 49% of money on 20% of
    phones is a 2.4x premium, and that single figure is the finding.
    """
    extra_figures: List[Figure] = []
    caveats: List[str] = _disagreements(findings, panel)

    if len(panel.series) == 2:
        first, second = panel.series
        by_label = {s.label.lower(): s for s in second.slices}
        gaps = []
        for wedge in first.slices:
            other = by_label.get(wedge.label.lower())
            if other is None or wedge.value <= 0:
                continue
            ratio = other.value / wedge.value
            if ratio >= 1.5 or ratio <= 0.67:
                gaps.append((wedge.label, ratio, wedge.value, other.value))
        gaps.sort(key=lambda g: -abs(g[1] - 1.0))
        for label, ratio, left, right in gaps[:3]:
            extra_figures.append(Figure(
                label=f"{label}: {second.measure} vs {first.measure}",
                value=round(ratio, 2),
                value_text=f"{ratio:.1f}x",
                unit="ratio", state="derived",
                operands=[f"{label} {first.measure}",
                          f"{label} {second.measure}"],
                how=f"{right:g}% ÷ {left:g}%",
                note=(f"{label} takes {right:g}% of {second.measure} on "
                      f"{left:g}% of {first.measure}")))
        if gaps:
            caveats.append(
                f"The two series rank the market differently, which is the "
                f"finding rather than an inconsistency: {first.measure} and "
                f"{second.measure} are different questions about one market.")

    # The convergence check, when the findings happen to support it.
    totals = [f for f in panel.figures
              if f.unit and f.unit.upper().startswith("USD") and f.value]
    shares = [f for f in panel.figures if f.unit == "%" and f.value]
    if len(totals) == 1 and len(shares) == 1:
        implied = implied_total(shares[0], totals[0])
        if implied is not None:
            extra_figures.append(implied)
            caveats.append(
                "The market total above is reached two ways — read directly "
                "from a source, and implied by one player's revenue over its "
                "revenue share. Where those two agree the figure is worth more "
                "than either alone; where they do not, the gap is reported "
                "rather than averaged away.")

    return {"figures": extra_figures, "caveats": caveats}


MARKET_SHARE = register(Specialist(
    name="market-share",
    job=("who holds what share of a market, by units and by revenue, and how "
         "big the whole market is"),
    seeds=(
        "What share of the {market} market in {place} does each company hold, "
        "by units shipped or sold, in the most recent published quarter?",
        "What share of {market} revenue in {place} does each company hold, and "
        "how does that differ from their share of units?",
        "How large is the total {market} market in {place} in money, and is "
        "that figure wholesale or retail value?",
        "How many units of {market} were sold in {place} in the most recent "
        "period, and is that growing or shrinking?",
        "Which research firms publish {market} market share for {place}, and "
        "where do their numbers disagree?",
        "What is the average selling price of {market} in {place}, overall and "
        "by the largest companies?",
    ),
    beats=("competitors", "competitors", "sizing", "sizing", "competitors",
           "economics"),
    refuse=("Never mix a usage share with a sales share, or a unit share with "
            "a revenue share, in one chart — they measure different "
            "populations and the gap between them is usually larger than the "
            "gap between competitors. Never blend two research firms' numbers "
            "into a single series; they define the category differently. "
            "Where the market name could mean two markets — the makers or the "
            "sellers, the devices or the service — settle that first, because "
            "every share figure downstream depends on it."),
    check=_market_share_check,
    iterations=14,
    answers=("Q5", "Q6"),
))


def specialist_for(question_id: str) -> Optional[Specialist]:
    """The specialist that claims a standing question, if one does."""
    for spec in registered():
        if question_id in (spec.answers or ()):
            return spec
    return None


# ---------------------------------------------------------------- running

def run_specialist(spec: Specialist, *, market: str, place: str = "",
                   provider: Any, researcher: Any,
                   registry: Any = None, policy: Any = None,
                   budget: Any = None, framing: Optional[Dict[str, Any]] = None,
                   shaper: Optional[Callable[..., Dict[str, Any]]] = None,
                   on_event: Optional[Callable[[str], None]] = None,
                   on_usage: Optional[Callable] = None) -> Panel:
    """Open the questions, run the loop, shape the answer.

    Nothing here is new machinery. The loop, the router, the reader, the
    screening and the source registry are the ones deck analysis has used all
    along — this function is the wiring that was missing, not an engine.

    `shaper` is injectable for the same reason the loop's `reader` is: the
    binding and the cross-checks are deterministic and get tested with a fake
    shaper, so none of the interesting behaviour needs a model to verify.
    """
    from deckscope.research.findings import FindingRegistry
    from deckscope.research.loop import Budget, ResearchLoop
    from deckscope.research.questions import QuestionQueue
    from deckscope.research.reader import make_reader
    from deckscope.security.policy import SecurityPolicy
    from deckscope.sources import SourceRegistry

    emit = on_event or (lambda *_: None)
    registry = registry if registry is not None else SourceRegistry()
    policy = policy if policy is not None else SecurityPolicy()
    budget = budget or Budget(max_iterations=spec.iterations,
                              max_retrievals=spec.iterations * 3)

    question_text = f"{spec.job.capitalize()} — {market}" + (
        f" in {place}" if place else "")

    # Ask the model what to ask, and fall back to the templates only if that
    # fails. The templates were the whole opening move here until now, which
    # made this door subject-blind: it asked the same six questions of every
    # market, and one of them wants "the average selling price" of a subject
    # that may not be sold in units at all. The `report` path was already
    # generating its questions; this one was left behind, and it is the door
    # people actually use.
    #
    # The templates also produce malformed English whenever the market name
    # already contains its geography — a live run asked about "the hearing aid
    # manufacturers worldwide market in worldwide", which is a worse search
    # query than either half alone.
    from .section_agent import _opening_questions
    from .reports import Section

    brief = Section(key=spec.name, title=spec.job.capitalize(),
                    brief=spec.job, refuse=spec.refuse or "")
    try:
        rows = _opening_questions(section=brief, subject=market, place=place,
                                  report=None, provider=provider, context={},
                                  on_usage=on_usage)
        source = "generated"
    except Exception as exc:  # noqa: BLE001 - templates still research something
        emit(f"{spec.name}: could not generate questions ({exc}); "
             f"falling back to the templates")
        rows, source = spec.questions(market, place), "template"

    queue = QuestionQueue()
    queue.seed(rows)
    emit(f"{spec.name}: {len(queue.questions)} opening questions ({source})")

    findings = FindingRegistry()
    loop = ResearchLoop(
        researcher=researcher, registry=registry, queue=queue,
        findings=findings, reader=make_reader(provider, on_usage=on_usage),
        policy=policy, budget=budget, framing=framing or {}, on_event=emit)
    run = loop.run()

    established = list(findings.findings)
    if not established:
        panel = unanswered(
            question_text,
            "nothing could be established. " + (
                ((run.get("budget") or {}).get("stopped_because"))
                or "the loop found no sources it could read for these "
                   "questions"),
            agent=spec.name)
        panel.provenance = _provenance(run, queue, established)
        return panel

    emit(f"{spec.name}: shaping {len(established)} findings")
    shape = shaper or make_shaper(provider, on_usage=on_usage)
    try:
        shaped = shape(question=question_text, findings=established,
                       registry=registry)
    except Exception as exc:  # noqa: BLE001 - a shaping failure is reportable
        panel = unanswered(
            question_text,
            f"the research found {len(established)} findings but the shaping "
            f"stage failed: {exc}", agent=spec.name)
        panel.provenance = _provenance(run, queue, established)
        return panel

    panel = build_panel(question_text, established, shaped, agent=spec.name)

    if spec.check is not None:
        try:
            extra = spec.check(findings=established, panel=panel,
                               market=market, place=place)
        except Exception as exc:  # noqa: BLE001
            extra = {"caveats": [f"the {spec.name} cross-checks did not run: "
                                 f"{exc}"]}
        panel.figures.extend(extra.get("figures") or [])
        panel.caveats.extend(extra.get("caveats") or [])

    # A question the loop could establish NOTHING for is a figure in the ABSENT
    # state, not a silence. This is what stops the panel looking more complete
    # than the run behind it.
    #
    # "Established nothing" is the test, not "was closed as unanswerable".
    # Those are different: the closing rule wants corroboration from two
    # independent domains, so a question answered by one good source stays
    # formally unanswerable while having produced perfectly real findings. The
    # first version reported those as absent, so a panel could show a figure in
    # its chart AND a line underneath saying the question behind it could not be
    # answered. Both statements true, together incoherent.
    from deckscope.research.questions import UNANSWERABLE

    produced = {getattr(f, "question_id", None) for f in established}
    for question in queue.questions:
        if getattr(question, "status", "") != UNANSWERABLE:
            continue
        if getattr(question, "id", None) in produced:
            continue
        panel.figures.append(Figure(
            label=question.text[:70], state=ABSENT,
            because=question.closed_because or "no source could answer it"))

    panel.provenance = _provenance(run, queue, established)
    return panel


def _provenance(run: Dict[str, Any], queue: Any,
                findings: Sequence[Any]) -> Dict[str, Any]:
    """What the run read and spent.

    Kept on the panel so a stored panel can be audited months later without the
    process that made it. A panel is a record; this is the part that makes it
    one.
    """
    budget = (run or {}).get("budget") or {}
    return {
        "questions_opened": len(getattr(queue, "questions", []) or []),
        "questions_closed": len([q for q in getattr(queue, "questions", [])
                                 if not getattr(q, "open", True)]),
        "findings": len(findings),
        "retrievals": budget.get("retrievals"),
        "iterations": budget.get("iterations"),
        "seconds": budget.get("seconds"),
        "stopped_because": budget.get("stopped_because", ""),
        # Which questions went to a dataset and which to a search. A wrong
        # answer is often a wrong routing decision, and this is where that
        # shows up rather than being blamed on the model.
        "routing": (run or {}).get("routing"),
        "unanswered": [u.get("question") for u in (run or {}).get("unanswered")
                       or []],
    }
