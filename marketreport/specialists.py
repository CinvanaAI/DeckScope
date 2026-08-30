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


def _load_catalog() -> None:
    """Register the other report types.

    Deferred to first use rather than imported at the top, because `catalog`
    imports this module for `Specialist` and `register`. Called by `get` and
    `registered`, so nobody has to remember to import it — a specialist that
    exists but is invisible until some unrelated module happens to be loaded
    is the kind of ordering bug that only shows up in the packaged wheel.
    """
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from . import catalog  # noqa: F401 - imported for its registrations


_LOADED = False


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
    #: The parameter this job must be scoped by before it researches anything,
    #: as a key from `dimensions.py`. Market share is scoped by basis, market
    #: size by price level, regulation by jurisdiction. One report per value.
    #:
    #: Empty means the job has no such parameter, which is rare and should be
    #: deliberate rather than an oversight — every type examined so far had
    #: one, and the ones that looked like they did not turned out to have been
    #: quietly defaulting.
    dimension: str = ""
    #: How this job knows what it knows: "measured", "reasoned" or "mixed".
    #:
    #: A market share is measured — somebody counted. Barriers to entry are
    #: reasoned — nobody publishes a barrier-to-entry number, and the answer is
    #: an argument built over sourced facts. Both are legitimate; presenting
    #: the second as the first is not, and the difference is invisible once
    #: both are set in the same typeface with citations underneath.
    #:
    #: Declared per specialist rather than inferred, because it is a property
    #: of the question rather than of what the run happened to find.
    evidence: str = "measured"
    #: Runs after the loop, before the shaper. Returns extra figures and
    #: caveats — the specialist's own analysis, in Python.
    check: Optional[Callable[..., Dict[str, Any]]] = None
    #: How many loop iterations this job is worth.
    iterations: int = 10
    #: Standing questions in the market report this specialist can answer.
    #:
    #: This is the convergence the client named: "how you gonna make a market report
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
    _load_catalog()
    return _SPECIALISTS.get((name or "").strip().lower())


def registered() -> List[Specialist]:
    _load_catalog()
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
    #: (what is measured) -> {finding id: finding}. One entry per disagreement,
    #: however many pairs it decomposes into.
    groups: Dict[Any, Dict[str, Any]] = {}
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

            # Grouped by what is being measured, not emitted per pair. Five
            # sources sizing one market produce ten pairs, and the live run
            # printed three caveats that opened with the same sentence about
            # the same IMARC figure. One disagreement described three times
            # reads as three disagreements, which is itself a distortion of
            # the evidence — and it buries the others.
            about = f"{who_left.title()}'s " if who_left else "the market's "
            key = (about, (series_left or "figures").lower())
            groups.setdefault(key, {})
            for side in (left, right):
                groups[key][str(getattr(side, "id", ""))] = side

    for (about, series), members in groups.items():
        values = sorted(members.values(), key=lambda f: abs(f.value))
        low, high = values[0], values[-1]
        others = len(values) - 2
        notes.append(
            f"{len(values)} sources disagree about {about}{series}, from "
            f"{low.value_text or low.value} to {high.value_text or high.value}"
            + (f" with {others} more in between" if others > 0 else "")
            + f". At the ends: \"{low.statement}\" against "
              f"\"{high.statement}\". Nobody counts this market directly — "
              f"every tracker models it — so a spread between reputable firms "
              f"is the normal noise floor, and a figure quoted to one decimal "
              f"from a single tracker is hiding that.")
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
    dimension="basis",
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


#: What each kind of knowing means, said to the reader in their words.
EVIDENCE_NOTES = {
    "reasoned": (
        "This report is an argument, not a measurement. Nobody publishes the "
        "answer to this question as a number; what is below is reasoning over "
        "sourced facts. Read the facts and judge the argument — do not quote "
        "the conclusion as a finding."),
    "mixed": (
        "Part of this report is measured and part of it is reasoned. Figures "
        "carry their own provenance, and anything not marked as sourced or "
        "derived is a judgment made here rather than a fact somebody "
        "published."),
}


def _stamp(panel: Panel, measure: Any) -> None:
    """Record which yardstick this panel is on, including when it is on none.

    A panel with no measure is not neutral, it is unlabelled, and an unlabelled
    share chart is the thing every source in the hearing-aid run turned out to
    be publishing. Saying so on the panel is the minimum.
    """
    if measure is None:
        panel.caveats.append(
            "No measure was named for this report, so the figures in it may "
            "be on different bases — a share of revenue and a share of units "
            "are different answers and can name different leaders. Ask for a "
            "specific measure to get a report that holds one basis "
            "throughout.")
        return
    panel.measure = measure.key
    panel.measure_label = measure.label
    if panel.headline and measure.label.lower() not in panel.headline.lower():
        panel.headline = f"{panel.headline.rstrip('.')} ({measure.label})."


def _off_basis(panel: Panel, measure: Any, axis: Any = None) -> None:
    """Flag figures that read as a measure this report is not on.

    Cue matching, and openly so — it catches a source that announced its own
    basis in words, which is the common case and the only one detectable from
    text. It cannot catch a bare number silently on the wrong footing; nothing
    can, which is why the report is scoped before the search rather than
    filtered after it.
    """
    lookup = axis.get if axis is not None else (lambda k: None)
    suspects = [m for m in (lookup(k) for k in measure.confusable_with)
                if m is not None]
    if not suspects:
        return

    mine = set(measure.cues)
    for series in panel.series:
        for slice_ in series.slices:
            text = f"{series.label} {series.measure} {slice_.label}".lower()
            if any(cue in text for cue in mine):
                continue
            for other in suspects:
                if any(cue in text for cue in other.cues):
                    panel.caveats.append(
                        f"'{slice_.label}' in the {series.label.lower()} "
                        f"series reads as {other.label}, but this report is "
                        f"{measure.label}. Those measure different "
                        f"populations. Check it against its source before "
                        f"relying on it, or read the {other.label} report "
                        f"instead.")
                    break


def _or_list(keys: Sequence[str], axis: Any = None) -> str:
    """"units or an installed base" — for naming what a source may substitute.

    Looked up inside the dimension the report is scoped by. A price-level
    report's confusable values are other price levels, and resolving them in
    the basis vocabulary would find none of them and fall back to "a figure on
    another basis" — both wrong and useless.
    """
    lookup = axis.get if axis is not None else (lambda k: None)
    labels = [m.label for m in (lookup(k) for k in keys or ()) if m]
    if not labels:
        return "a figure on another basis"
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " or " + labels[-1]


def specialist_for(question_id: str) -> Optional[Specialist]:
    """The specialist that claims a standing question, if one does."""
    for spec in registered():
        if question_id in (spec.answers or ()):
            return spec
    return None


# ---------------------------------------------------------------- running

def run_specialist(spec: Specialist, *, market: str, place: str = "",
                   measure: Any = None,
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

    # The measure is the yardstick this run is scoped to, named by whoever
    # dispatched it. One run answers one measure. It is not a hint and it is
    # not resolved here: the stage that decided what market this is also
    # decided which yardsticks it is meaningfully sold in, and handed them
    # over. Running without one is still allowed — a caller with no opinion
    # gets the old undifferentiated behaviour — but it is the degraded case,
    # and the panel says so rather than quietly producing a chart whose axis
    # nobody named.
    from .dimensions import Option
    from .dimensions import get as get_dimension

    # Resolved against THIS specialist's dimension, not against basis. Market
    # size is scoped by price level and regulation by jurisdiction; looking
    # every value up in the basis vocabulary would silently reject "wholesale"
    # and accept nothing but shares.
    if isinstance(measure, str):
        axis = get_dimension(spec.dimension) if spec.dimension else None
        if axis is None:
            raise ValueError(
                f"the {spec.name!r} specialist declares no dimension, so the "
                f"value {measure!r} cannot be resolved. Either give the "
                f"specialist a `dimension` from marketreport.dimensions or "
                f"pass an Option directly.")
        resolved, unknown = axis.resolve([measure])
        if unknown or not resolved:
            known = ", ".join(o.key for o in axis.options) or axis.expects
            raise ValueError(
                f"{measure!r} is not a value of the {axis.key!r} dimension "
                f"that {spec.name!r} is scoped by. Expected one of: {known}")
        measure = resolved[0]
    if measure is not None and not isinstance(measure, Option):
        raise TypeError(
            f"measure must be a dimension Option or a registered key, not "
            f"{type(measure).__name__}. Guessing here would put a number on a "
            f"basis nobody chose, which is the error this parameter exists to "
            f"prevent.")

    scope = f" — {measure.label}" if measure is not None else ""
    question_text = (f"{spec.job.capitalize()} — {market}"
                     + (f" in {place}" if place else "") + scope)

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

    # The measure rewrites the brief rather than being appended to it. A
    # yardstick mentioned in passing gets ignored by the opener about as often
    # as it is honoured; a yardstick that IS the job produces questions that
    # search for it.
    if measure is not None:
        job = (f"{spec.job}, measured strictly as {measure.label} — "
               f"{measure.counts}")
        axis = get_dimension(spec.dimension)
        noun = axis.key.replace("_", " ") if axis is not None else "basis"
        refuse = (f"{measure.refuse}\n\nEverything in this report is on one "
                  f"{noun}: {measure.label}. A figure on any other {noun} does "
                  f"not belong here, however good it is, because a separate "
                  f"report covers each of the others and mixing them is the "
                  f"failure this split exists to prevent. The likeliest "
                  f"substitution to catch a source making is "
                  f"{_or_list(measure.confusable_with, get_dimension(spec.dimension))}.\n\n{spec.refuse}")
        sources_hint = measure.homes
    else:
        job, refuse, sources_hint = spec.job, (spec.refuse or ""), ""

    # The title is scoped too. Leaving it as the specialist's generic job
    # meant the heading read "...by units and by revenue" directly above a
    # brief saying to report revenue only — the two most prominent lines in
    # the prompt contradicting each other, with the wrong one first.
    #
    # Built from the job rather than from a fixed sentence. The first version
    # said "Who holds what X of a market", which is the market-share question
    # wearing every other report's parameter: a market-size run was headed
    # "Who holds what wholesale value of a market", which is not a question
    # anyone asks.
    title = spec.job.capitalize()
    if measure is not None:
        axis = get_dimension(spec.dimension)
        joiner = axis.label if axis is not None else "measured as"
        title = f"{title} — {joiner} {measure.label}"
    brief = Section(key=spec.name, title=title,
                    brief=job, refuse=refuse, sources=sources_hint)
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
        # A measure nobody publishes still gets a report, and the report says
        # which measure it is. This is the case that matters most: "unit share
        # of hearing aids" is unsourceable — neither Sonova nor Demant
        # discloses volumes and the trackers sell that number rather than
        # publishing it — and a reader needs to see that as a named, empty
        # report sitting beside the revenue one. An unlabelled failure looks
        # like the run broke; a labelled one tells them what a paid source
        # would buy.
        if measure is not None:
            why = (f"nothing could be established on this basis. No source "
                   f"reached publishes {measure.label} for this market. "
                   f"Where it is published it is usually found in "
                   f"{measure.homes}. "
                   + (((run.get("budget") or {}).get("stopped_because")) or ""))
        else:
            why = "nothing could be established. " + (
                ((run.get("budget") or {}).get("stopped_because"))
                or "the loop found no sources it could read for these "
                   "questions")
        panel = unanswered(question_text, why, agent=spec.name)
        _stamp(panel, measure)
        panel.provenance = _provenance(run, queue, established)
        return panel

    emit(f"{spec.name}: shaping {len(established)} findings")
    shape = shaper or make_shaper(provider, on_usage=on_usage)
    try:
        shaped = shape(question=question_text, findings=established,
                       registry=registry, job=(job if measure is not None
                                               else None))
    except Exception as exc:  # noqa: BLE001 - a shaping failure is reportable
        panel = unanswered(
            question_text,
            f"the research found {len(established)} findings but the shaping "
            f"stage failed: {exc}", agent=spec.name)
        _stamp(panel, measure)
        panel.provenance = _provenance(run, queue, established)
        return panel

    panel = build_panel(question_text, established, shaped, agent=spec.name)
    _stamp(panel, measure)

    # An off-basis figure is the specific corruption this split exists to
    # stop, and it is invisible once drawn: a chart labelled "share of units"
    # carrying a revenue number looks exactly like a correct chart. Checked
    # rather than instructed, because instruction is advisory.
    if measure is not None:
        _off_basis(panel, measure, get_dimension(spec.dimension))

    note = EVIDENCE_NOTES.get(spec.evidence)
    if note:
        panel.caveats.insert(0, note)

    if spec.check is not None:
        try:
            extra = spec.check(findings=established, panel=panel,
                               market=market, place=place)
        except Exception as exc:  # noqa: BLE001
            # The cross-checks are deterministic arithmetic — no model, no
            # network. An exception here is a DEFECT, and "did not run"
            # would let it read as an ordinary limitation.
            extra = {"caveats": [f"DEFECT in DeckScope: the {spec.name} "
                                 f"cross-checks raised "
                                 f"{type(exc).__name__}: {exc}"]}
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
