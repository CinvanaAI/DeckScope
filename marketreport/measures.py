"""The seven yardsticks a market share can be measured in.

The definitions themselves now live in `dimensions.py`, as the options of the
`basis` dimension. This module is the door they were originally behind and it
keeps working unchanged — but it no longer *owns* them, because the problem
turned out not to belong to market share.

Every report type has a parameter that must be fixed before research or the
report is unlabelled: basis for market share, price level for market size,
jurisdiction for regulation, period for growth, population for demographics.
That generalization is `dimensions.py`. Keeping a second copy of the seven
measures here would be exactly the drift the dimension module exists to stop —
two definitions of what "share of units sold" means, diverging quietly.

So: `Measure` is `Option`, and everything below reads through `BASIS`.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .dimensions import BASIS, Option as Measure

__all__ = ["Measure", "register", "get", "registered", "resolve", "suggest",
           "REVENUE", "UNITS", "USAGE", "INSTALLED_BASE", "SUBSCRIBERS",
           "OUTLETS", "CAPACITY"]


def get(key: str) -> Optional[Measure]:
    return BASIS.get(key)


def registered() -> List[Measure]:
    return list(BASIS.options)


def resolve(names: Sequence[str]) -> Tuple[List[Measure], List[str]]:
    """Named measures in, measures out, plus the ones nobody registered."""
    return BASIS.resolve(names)


def register(measure: Measure) -> Measure:
    """Add a yardstick at runtime.

    Rebuilds the dimension rather than mutating it — `Dimension` is frozen, and
    a registry that can be edited in place is a registry two callers can
    disagree about.
    """
    from dataclasses import replace

    from . import dimensions

    kept = tuple(o for o in BASIS.options if o.key != measure.key)
    dimensions.register(replace(BASIS, options=kept + (measure,)))
    globals()["BASIS"] = dimensions.get("basis")
    return measure


def suggest(text: str) -> List[Measure]:
    """Measures a piece of text reads as being on.

    A convenience for whoever writes the brief and a sorting aid downstream —
    never a substitute for being told. A finding matching no cue is assigned no
    measure, because guessing the basis of a number is the precise error this
    whole mechanism exists to prevent.
    """
    low = f" {(text or '').lower()} "
    return [m for m in BASIS.options if any(cue in low for cue in m.cues)]


def _by_key(key: str) -> Measure:
    found = BASIS.get(key)
    if found is None:  # pragma: no cover - a packaging fault, not a user one
        raise RuntimeError(
            f"the {key!r} measure is missing from the basis dimension. This "
            f"module re-exports them, so an absence here means dimensions.py "
            f"was edited without updating its callers.")
    return found


REVENUE = _by_key("revenue")
UNITS = _by_key("units")
USAGE = _by_key("usage")
INSTALLED_BASE = _by_key("installed_base")
SUBSCRIBERS = _by_key("subscribers")
OUTLETS = _by_key("outlets")
CAPACITY = _by_key("capacity")
