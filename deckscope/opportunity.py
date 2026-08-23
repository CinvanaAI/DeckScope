"""Opportunity cost: what would have to be true for this to beat the alternative.

The question an investor actually faces is not "is this deck any good" but
"compared to what". If the deck names an incumbent you could simply buy shares
in, that incumbent is the real benchmark, and nothing else in DeckScope was
measuring against it.

**This module does not forecast returns, and that is deliberate.** No model knows
what a seed-stage company will be worth in five years, and a number like
"estimated return 3.2x, confidence medium" is a guess wearing the clothes of an
analysis. It would also be, by a wide margin, the least supportable claim in a
codebase that spends most of its effort refusing to state things it cannot cite.

So the question is inverted. Instead of predicting an outcome, this computes the
outcome that would be *required* — given the ask, the valuation, realistic
dilution, and the category's own exit multiples — to beat simply holding the
listed comparable. Every number below is either arithmetic you can check by hand
or an input that arrived with a citation.

That is more useful than a point estimate anyway: "this needs to reach roughly
$90M ARR within five years, and the base rate for that is 4%" tells you what to go
and verify. "3.2x" tells you nothing you can act on.

Not investment advice. It is arithmetic, and the assumptions are yours to change.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------- parsing

_MULT = {"k": 1e3, "m": 1e6, "mm": 1e6, "bn": 1e9, "b": 1e9, "t": 1e12}
_MONEY = re.compile(
    r"(?P<cur>[$€£])?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>k|mm|m|bn|b|t)?\b",
    re.I)


def parse_money(text: Any) -> Optional[float]:
    """"$4M" -> 4000000.0. Returns None when there is no figure to read."""
    if isinstance(text, (int, float)):
        return float(text)
    if not text:
        return None
    m = _MONEY.search(str(text))
    if not m:
        return None
    try:
        value = float(m.group("num").replace(",", ""))
    except ValueError:
        return None
    unit = (m.group("unit") or "").lower()
    return value * _MULT.get(unit, 1.0)


def parse_percent(text: Any) -> Optional[float]:
    """"18%" -> 0.18. "18% MoM" -> 0.18. Returns a fraction, not a percentage."""
    if isinstance(text, (int, float)):
        return float(text) / 100.0 if abs(float(text)) > 1 else float(text)
    if not text:
        return None
    m = re.search(r"(\d[\d.]*)\s*%", str(text))
    if not m:
        return None
    try:
        return float(m.group(1)) / 100.0
    except ValueError:
        return None


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    for cutoff, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= cutoff:
            return f"${value / cutoff:,.1f}{suffix}"
    return f"${value:,.0f}"


# ---------------------------------------------------------------- inputs

@dataclass
class Assumptions:
    """Everything the arithmetic rests on, in one place so it can be argued with.

    Defaults are conventional rather than authoritative. Change them; the whole
    calculation is a pure function of these.
    """

    #: Total ownership given up in later rounds, before any exit.
    future_dilution: float = 0.50
    #: Revenue multiple at exit for this category.
    exit_revenue_multiple: float = 6.0
    #: Horizon in years.
    horizon_years: int = 5
    #: Liquidation preference stack ahead of this investor, as a multiple of the
    #: round size. 1.0 means later investors get their money back first.
    preference_stack: float = 1.0
    #: Fraction of seed-stage companies that return nothing at all. Sourced when
    #: research supplies it; otherwise left None and reported as unknown.
    total_loss_rate: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RequiredOutcome:
    """What the startup must reach to match a given return multiple."""

    target_multiple: float
    entry_ownership: Optional[float] = None
    ownership_at_exit: Optional[float] = None
    exit_value_required: Optional[float] = None
    implied_arr_required: Optional[float] = None
    current_arr: Optional[float] = None
    growth_multiple_required: Optional[float] = None
    implied_annual_growth: Optional[float] = None
    achievable_at_current_growth: Optional[bool] = None
    years_at_current_growth: Optional[float] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["exit_value_required_display"] = _fmt_money(self.exit_value_required)
        d["implied_arr_required_display"] = _fmt_money(self.implied_arr_required)
        return d


def required_outcome(*, ask: Optional[float], post_money: Optional[float],
                     target_multiple: float, assumptions: Assumptions,
                     current_arr: Optional[float] = None,
                     current_growth_monthly: Optional[float] = None
                     ) -> RequiredOutcome:
    """Work backwards from a target multiple to the exit it demands.

    All of this is arithmetic:
        ownership at entry   = ask / post-money
        ownership at exit    = entry x (1 - future dilution)
        exit value required  = (ask x target multiple + preference stack) / ownership
        implied ARR required = exit value / category revenue multiple
    """
    out = RequiredOutcome(target_multiple=target_multiple, current_arr=current_arr)

    if not ask or not post_money or post_money <= 0:
        out.note = ("The deck does not state both an ask and a post-money valuation, "
                    "so the ownership maths cannot be run.")
        return out

    entry = ask / post_money
    at_exit = entry * (1.0 - max(0.0, min(0.95, assumptions.future_dilution)))
    out.entry_ownership = round(entry, 4)
    out.ownership_at_exit = round(at_exit, 4)
    if at_exit <= 0:
        out.note = "Dilution assumption leaves no ownership at exit."
        return out

    proceeds_needed = ask * target_multiple
    stack = ask * max(0.0, assumptions.preference_stack)
    exit_value = (proceeds_needed + stack) / at_exit
    out.exit_value_required = exit_value

    if assumptions.exit_revenue_multiple > 0:
        arr = exit_value / assumptions.exit_revenue_multiple
        out.implied_arr_required = arr
        if current_arr and current_arr > 0:
            out.growth_multiple_required = round(arr / current_arr, 1)
            years = max(1, assumptions.horizon_years)
            out.implied_annual_growth = round((arr / current_arr) ** (1 / years) - 1, 3)
            if current_growth_monthly and current_growth_monthly > 0:
                annual = (1 + current_growth_monthly) ** 12 - 1
                out.achievable_at_current_growth = annual >= out.implied_annual_growth
                try:
                    out.years_at_current_growth = round(
                        math.log(arr / current_arr) / math.log(1 + annual), 1)
                except (ValueError, ZeroDivisionError):
                    out.years_at_current_growth = None
                # This extrapolation assumes the current monthly rate holds. It
                # does not: growth decays as the base grows, and a rate sustained
                # for four months says very little about the fifth year. The
                # figure is a floor on the difficulty, not a schedule.
                out.note = (
                    f"'{current_growth_monthly:.0%} per month' compounds to "
                    f"{annual:.0%} a year, and the figure above assumes that rate "
                    f"holds for the whole period. It essentially never does — growth "
                    f"decays as the base grows. Read this as the minimum difficulty, "
                    f"not a timetable.")
    return out


# ------------------------------------------------------- the comparison

@dataclass
class ComparableReturn:
    """What a listed competitor actually did. Sourced, not projected."""

    name: str
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    market_cap: Optional[float] = None
    revenue: Optional[float] = None
    revenue_growth: Optional[float] = None
    total_return_5y: Optional[float] = None     # as a multiple, e.g. 2.4
    total_return_1y: Optional[float] = None
    source_ids: List[str] = field(default_factory=list)
    as_of: Optional[str] = None
    note: str = ""

    @property
    def investable(self) -> bool:
        return bool(self.ticker)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["investable"] = self.investable
        d["market_cap_display"] = _fmt_money(self.market_cap)
        d["revenue_display"] = _fmt_money(self.revenue)
        return d


@dataclass
class OpportunityComparison:
    """The whole side-by-side, ready to render."""

    company: str
    assumptions: Assumptions
    comparables: List[ComparableReturn] = field(default_factory=list)
    #: One RequiredOutcome per benchmark, keyed by what it is benchmarked against.
    requirements: Dict[str, RequiredOutcome] = field(default_factory=dict)
    base_rates: List[Dict[str, Any]] = field(default_factory=list)
    unavailable: List[str] = field(default_factory=list)
    headline: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "assumptions": self.assumptions.to_dict(),
            "comparables": [c.to_dict() for c in self.comparables],
            "requirements": {k: v.to_dict() for k, v in self.requirements.items()},
            "base_rates": self.base_rates,
            "unavailable": self.unavailable,
            "headline": self.headline,
            "disclaimer": DISCLAIMER,
        }


DISCLAIMER = (
    "This is arithmetic, not a forecast. It states what the company would have to "
    "achieve to match each benchmark under the stated assumptions — it does not "
    "predict whether it will. No return figure here is projected: the comparable's "
    "returns are historical and sourced, and the base rates are published. Change "
    "the assumptions and every number changes. Not investment advice.")


def build_comparison(*, company: str, ask: Optional[float], post_money: Optional[float],
                     current_arr: Optional[float], current_growth_monthly: Optional[float],
                     comparables: List[ComparableReturn],
                     assumptions: Optional[Assumptions] = None,
                     base_rates: Optional[List[Dict[str, Any]]] = None
                     ) -> OpportunityComparison:
    """Assemble the comparison. Pure function of its inputs."""
    a = assumptions or Assumptions()
    out = OpportunityComparison(company=company, assumptions=a,
                                comparables=list(comparables),
                                base_rates=list(base_rates or []))

    # A fixed reference point, so there is always something to read even when no
    # comparable is listed.
    out.requirements["3x (a common venture threshold)"] = required_outcome(
        ask=ask, post_money=post_money, target_multiple=3.0, assumptions=a,
        current_arr=current_arr, current_growth_monthly=current_growth_monthly)

    investable = [c for c in comparables if c.investable and c.total_return_5y]
    for comp in investable:
        label = f"holding {comp.name}" + (f" ({comp.ticker})" if comp.ticker else "")
        out.requirements[label] = required_outcome(
            ask=ask, post_money=post_money, target_multiple=comp.total_return_5y,
            assumptions=a, current_arr=current_arr,
            current_growth_monthly=current_growth_monthly)

    if not investable:
        listed = [c for c in comparables if c.investable]
        if listed:
            out.unavailable.append(
                f"{len(listed)} named competitor(s) are publicly traded, but their "
                f"historical returns could not be sourced, so no benchmark multiple "
                f"could be set.")
        else:
            out.unavailable.append(
                "None of the named competitors appear to be publicly traded, so there "
                "is no listed alternative to compare against. The 3x reference above "
                "still applies.")

    out.headline = _headline(out, current_arr)
    return out


def _headline(comp: OpportunityComparison, current_arr: Optional[float]) -> str:
    """One sentence stating the requirement, never a prediction."""
    benchmark = next((k for k in comp.requirements if k.startswith("holding")), None)
    key = benchmark or next(iter(comp.requirements), None)
    if not key:
        return ""
    req = comp.requirements[key]
    if req.implied_arr_required is None:
        return req.note or ""
    arr = _fmt_money(req.implied_arr_required)
    years = comp.assumptions.horizon_years
    if current_arr and req.growth_multiple_required:
        return (f"To match {key} over {years} years, this company would need to reach "
                f"roughly {arr} in revenue — about {req.growth_multiple_required}x its "
                f"current {_fmt_money(current_arr)} — after typical dilution.")
    return (f"To match {key} over {years} years, this company would need to exit at "
            f"roughly {_fmt_money(req.exit_value_required)}, implying about {arr} in "
            f"revenue at category multiples.")
