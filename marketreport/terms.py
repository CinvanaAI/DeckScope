"""Sizing a market as three separate researches, not one.

`sizing.py` has had the arithmetic since the beginning — COUNT × RATE × VALUE,
with a `Term` that may be `None` and a `Ring` that refuses to guess when one is
missing. What nothing did was *research the terms separately*, so the
market-size specialist went looking for "the market size" as a single fact,
found other people's totals, and reported the spread between them.

The first live market-size run is the argument for splitting it. Sizing hearing
aids at wholesale:

    COUNT   23.16 million units, 2025, EHIMA — free, exact, and defined as
            precisely the population being sized: net wholesale units sold by
            manufacturers to dispensers.
    RATE    not applicable; every unit sold is in the market by definition.
    VALUE   nothing. No worldwide average wholesale price has been published
            since 2019, and the best figure found was United States only.

One report, blended, says "the market cannot be sized" and looks like a
failure. Three reports say the count is settled, the rate is not needed, and
one number is missing — which is a completely different message, and the true
one. It also says exactly what a commissioned study would buy: not a report,
one price.

**The terms have genuinely different sourcing, which is why splitting helps.**

    COUNT   almost always free. Government statistics, regulators, trade
            associations. This is the term the corpus filings source most
            confidently and it is the one this system is best at.
    RATE    a qualifying screen — what fraction of that count is actually in
            this market. Usually a survey, sometimes a definition, occasionally
            nobody's business but the analyst's.
    VALUE   proprietary in every filing examined. This is what the paid
            research firms are actually selling.

Blending them hides that structure. A reader shown "$X billion" cannot tell
whether the weak term was the count or the price, and those imply completely
different amounts of trust.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .sizing import MEASURED, UNAVAILABLE, Ring, Term

__all__ = ["TermBrief", "TERMS", "brief_for", "assemble", "shortfall"]


@dataclass(frozen=True)
class TermBrief:
    """What to research for one factor, and how it goes wrong."""

    kind: str                       # count | rate | value
    label: str
    #: The question, with `{market}` and `{place}` to fill.
    asks: str
    #: What this factor is, for the opener.
    counts: str
    #: Where a figure for it is usually published. The whole reason to split.
    homes: str
    #: How this particular term is got wrong.
    refuse: str
    #: Whether free public sources normally carry it. Advisory and honest:
    #: it sets the reader's expectation before the research spends anything.
    usually_free: bool = True


TERMS: Tuple[TermBrief, ...] = (
    TermBrief(
        kind="count",
        label="how many there are",
        asks="How many units of {market} were sold in {place} in the most "
             "recent year, and who counts them?",
        counts="the number of things, people or establishments the market is "
               "built from, before any qualifying filter",
        homes="government statistics — the Economic Census, County Business "
              "Patterns, BLS QCEW — plus regulators and trade associations, "
              "which often publish member volumes free",
        refuse="State the period and the population. A count of units sold in "
               "a year and a count of units in service are different numbers "
               "and the second is far larger for anything durable. Do not "
               "accept a count for a different geography than the one asked "
               "for.",
        usually_free=True,
    ),
    TermBrief(
        kind="rate",
        label="what fraction of them qualify",
        asks="What share of {market} in {place} actually buys or participates, "
             "and what screen was applied?",
        counts="the fraction of the count that is genuinely in this market — "
               "the qualifying screen between an eligibility ceiling and real "
               "demand",
        homes="prevalence and incidence studies, household expenditure "
              "surveys, and participation rates published by regulators",
        refuse="This is where a market gets inflated. 'Could benefit from' and "
               "'is interested in' are not screens — Cricut's TAM counts "
               "anyone who 'likes, buys, used to make or is interested in' "
               "custom items and resolves to most adults alive. If no screen "
               "is published, say so; a rate of 1.0 is a claim that everybody "
               "counted is a customer, and it needs saying out loud rather "
               "than assuming.",
        usually_free=True,
    ),
    TermBrief(
        kind="value",
        label="what each one is worth per year",
        asks="What is the average amount spent per unit of {market} in "
             "{place} per year, and at what price level?",
        counts="the money per qualifying unit per year, at the price level "
               "this report is scoped to",
        homes="rarely anywhere free. Company filings sometimes imply it "
              "(revenue divided by a disclosed unit count); otherwise it is "
              "the term commissioned studies exist to sell",
        refuse="Say at which price level. Wholesale and retail differ by the "
               "whole distribution margin. Do not take a price from one "
               "country and apply it to a worldwide count, and do not take a "
               "price from one year and apply it to another year's count — "
               "the product of two mismatched terms is not an estimate, it is "
               "an artefact.",
        usually_free=False,
    ),
)


def brief_for(kind: str) -> Optional[TermBrief]:
    for term in TERMS:
        if term.kind == kind:
            return term
    return None


def _pick(findings: Sequence[Any], brief: TermBrief) -> Optional[Any]:
    """The finding that best answers one term, or None.

    Prefers a real figure over an absence, and an earlier finding over a later
    one, because the loop asks its strongest question first. It does not
    choose between two competing figures — that is a judgment, and where two
    sources disagree about a term the disagreement belongs in the panel rather
    than being resolved silently here.
    """
    wanted = {"count": ("count",), "rate": ("%",),
              "value": ("USD", "EUR", "GBP")}[brief.kind]
    for finding in findings:
        if getattr(finding, "value", None) is None:
            continue
        if str(getattr(finding, "method", "")) == "absent":
            continue
        unit = str(getattr(finding, "unit", "")).upper()
        if any(w.upper() == unit for w in wanted):
            return finding
    return None


def assemble(label: str, by_term: Dict[str, Sequence[Any]], *,
             price_level: str = "") -> Tuple[Ring, List[str]]:
    """Findings per term in, a Ring out, plus what could not be filled.

    Returns the ring even when terms are missing, because a ring with a hole
    in it is the useful artifact: it shows the reader which factor is absent
    and therefore what it would take to close the gap. `Ring.size` is `None`
    in that case and `Ring.missing` names the terms, both of which
    `sizing.py` has always done — it simply had nobody feeding it.
    """
    built: Dict[str, Term] = {}
    gaps: List[str] = []

    for brief in TERMS:
        findings = list(by_term.get(brief.kind) or ())
        found = _pick(findings, brief)
        if found is None:
            gaps.append(brief.kind)
            built[brief.kind] = Term(kind=brief.kind, value=None,
                                     method=UNAVAILABLE,
                                     note=f"{brief.label}: nothing published. "
                                          f"Usually found in {brief.homes}.")
            continue
        value = float(found.value)
        if brief.kind == "rate" and value > 1.0:
            value = value / 100.0      # a percentage, as `Term` insists
        built[brief.kind] = Term(
            kind=brief.kind, value=value,
            unit=str(getattr(found, "unit", "") or ""),
            as_of=str(getattr(found, "as_of", "") or ""),
            source=", ".join(getattr(found, "source_ids", []) or []) or "",
            method=MEASURED,
            note=str(getattr(found, "statement", ""))[:160])

    # A rate nobody publishes is not the same as a rate of one. Where the count
    # already describes the market exactly — units SOLD, rather than a
    # population that might buy — every counted unit qualifies, and saying so
    # explicitly is better than an absent term that reads like a failure.
    ring = Ring(label=label, count=built["count"], value=built["value"],
                rate=built["rate"],
                note=f"priced at {price_level}" if price_level else "")
    return ring, gaps


def shortfall(ring: Ring, gaps: Sequence[str]) -> str:
    """What it would take to complete this sizing, in one paragraph.

    The most useful sentence a sizing report can produce when it cannot
    produce a number, and the one a syndicated report never writes: not "data
    was unavailable" but *which* factor, why it is missing, and where it would
    have to come from.
    """
    if not gaps:
        return ""
    named = [brief_for(k) for k in gaps]
    named = [b for b in named if b is not None]
    have = [t.kind for t in ring.terms if t.known]

    parts = []
    if have:
        verb = "is" if len(have) == 1 else "are"
        parts.append(f"{len(have)} of the three terms {verb} established "
                     f"({', '.join(have)}).")
    missing = []
    for brief in named:
        if brief.usually_free:
            why = ("usually free, so its absence is a gap in the search "
                   "rather than in the world")
        else:
            why = ("rarely published free — this is the term commissioned "
                   "studies exist to sell")
        missing.append(f"**{brief.label}** — {why}. Look in {brief.homes}.")
    parts.append("Missing: " + "; ".join(missing))
    parts.append(
        "No total is stated, and the terms present are not multiplied by a "
        "substitute for the missing one. That substitution is how a sizing "
        "becomes a confident number nobody can trace back.")
    return " ".join(parts)
