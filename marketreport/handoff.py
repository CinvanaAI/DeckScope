"""The handoff: a brief in, one report per measure out.

This is the receiving end of a boundary Von drew:

    "when the AI looks at the pitch deck or whatever the input system is, it
    then says 'I identify this market' and then says 'This market measures in
    these units' and then it hands off those things to the market share report
    agent and says 'generate these market share reports'"

Which settles a question this code had been getting wrong. The report agent
does not resolve ambiguity, because by the time anything reaches it there is
none left to resolve: whatever read the input already decided which market this
is and which yardsticks it is meaningfully sold in. The agent's job is to
receive that decision and carry it out — one report per measure, every one of
them, including the measures that turn out to have no data behind them.

The upstream that produces a `Brief` is not built yet. That does not change
what this side has to look like, and building the receiver first means the
boundary is a real contract rather than a shape the two ends negotiate later.
A `Brief` can be constructed by hand, by a manager, or by a deck reader, and
none of them need to know anything about how research works.

**Why one report per measure rather than one report with several series.**
A share of revenue and a share of units are different answers to different
questions and they routinely name different leaders. Putting them in one
document makes the reader compare them, which is exactly the comparison that
is invalid. Putting them in separate reports, each of which says on its face
what it measures, makes the reader choose one — and choosing is the correct
operation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .measures import resolve
from .panel import Panel

__all__ = ["Brief", "run_brief"]


@dataclass
class Brief:
    """What upstream hands over: one market, and the yardsticks to measure it by."""

    #: The market as upstream resolved it — already disambiguated. "Hearing aid
    #: manufacturers", not "hearing aids", if that is the reading it chose.
    market: str
    #: Measure keys from `marketreport.measures`. One report is produced for
    #: each, in this order. An unknown key is reported, never skipped quietly.
    measures: Sequence[str] = ()
    place: str = ""
    #: Industry codes and geography ids the dataset backends need.
    framing: Dict[str, Any] = field(default_factory=dict)
    #: Which specialist to run. One today; the parameter exists so a second
    #: report type does not need this module rewritten.
    specialist: str = "market-share"
    #: Free text from upstream about why this market was read this way. Carried
    #: onto every panel so a reader can see the boundary decision that shaped
    #: what they are looking at, which is otherwise invisible downstream.
    definition: str = ""

    def __post_init__(self) -> None:
        if not str(self.market).strip():
            raise ValueError(
                "a brief needs a market. An empty market would research the "
                "phrase 'in worldwide' and return a report about nothing, "
                "which is worse than refusing.")
        if not self.measures:
            from .measures import registered
            raise ValueError(
                f"a brief for {self.market!r} names no measures, so there is "
                f"nothing to produce. Deciding which yardsticks a market is "
                f"sold in belongs upstream: this stage would have to guess, "
                f"and a guessed basis is the one error the whole split exists "
                f"to prevent. Registered measures: "
                f"{', '.join(m.key for m in registered())}")


def run_brief(brief: Brief, *, provider: Any, researcher: Any,
              registry: Any = None, policy: Any = None,
              on_event: Optional[Callable[[str], None]] = None,
              on_usage: Optional[Callable] = None,
              run: Optional[Callable[..., Panel]] = None) -> Dict[str, Any]:
    """Produce one report per measure named in the brief.

    Returns `{"panels": [...], "unknown": [...], "failed": [...]}`.

    One `SourceRegistry` is shared across every measure on purpose. The reports
    are separate documents but they are one piece of work, and two of them
    reading the same page must give it the same citable ID — otherwise a reader
    holding both has two bibliographies that disagree about what S3 means.

    A measure that raises does not stop the others. Losing the revenue report
    because the units report threw is a worse outcome than a partial set, and
    the failure is returned rather than logged, so the caller can show it
    beside the reports that worked.
    """
    from deckscope.sources import SourceRegistry
    from .specialists import get as get_specialist, run_specialist

    emit = on_event or (lambda *_: None)
    shared = registry if registry is not None else SourceRegistry()

    spec = get_specialist(brief.specialist)
    if spec is None:
        raise ValueError(f"no specialist named {brief.specialist!r} is "
                         f"registered")

    measures, unknown = resolve(brief.measures)
    for name in unknown:
        emit(f"  ignoring unknown measure {name!r} — nothing was produced for "
             f"it. Registered measures are named in marketreport.measures.")

    runner = run or run_specialist
    panels: List[Panel] = []
    failed: List[Dict[str, str]] = []

    for measure in measures:
        emit(f"— {brief.market} — {measure.label} —")
        try:
            panel = runner(spec, market=brief.market, place=brief.place,
                           measure=measure, provider=provider,
                           researcher=researcher, registry=shared,
                           policy=policy, framing=brief.framing,
                           on_event=emit, on_usage=on_usage)
        except Exception as exc:  # noqa: BLE001 - one measure must not sink the set
            emit(f"  the {measure.label} report failed: {exc}")
            failed.append({"measure": measure.key, "label": measure.label,
                           "error": str(exc)[:300]})
            continue
        if brief.definition:
            panel.caveats.append(
                f"This report covers the market as it was defined upstream: "
                f"{brief.definition}")
        panels.append(panel)

    return {"panels": panels, "unknown": unknown, "failed": failed,
            "registry": shared}


def coverage(result: Dict[str, Any]) -> Dict[str, Any]:
    """Which measures produced something and which came back empty.

    An empty report is a result, not a gap in the set — it establishes that
    nobody publishes that basis for this market, which is the finding that
    tells a reader what a paid source would actually buy them. So this counts
    them separately rather than folding them into a single completeness
    percentage that would make an honest empty report look like a failure.
    """
    panels: Sequence[Panel] = result.get("panels") or ()
    answered = [p for p in panels if p.answered]
    empty = [p for p in panels if not p.answered]
    return {
        "requested": len(panels) + len(result.get("failed") or []),
        "answered": len(answered),
        "unsourceable": len(empty),
        "failed": len(result.get("failed") or []),
        "unknown": list(result.get("unknown") or []),
        "measures": [{"measure": p.measure or "(none named)",
                      "label": p.measure_label or "",
                      "answered": p.answered,
                      "figures": len(p.figures),
                      "headline": p.headline or p.problem}
                     for p in panels],
    }
