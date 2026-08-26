"""Von's original question, sized properly: landscaping in Phoenix, Arizona.

The question that started this — "I have $5,000 and I want to open a landscaping
business in Phoenix" — asked for a market the old system answered from a web
search. This sizes it the way the corpus shows filings doing it, with concentric
geographic narrowing, and refuses the terms it cannot source.

NAICS 561730 is Landscaping Services. Arizona is state FIPS 04; Maricopa County,
which contains Phoenix, is county FIPS 013.

Run it with a Census key present and it produces three sized rings. Run it
without one and it produces three rings whose sizes are `None`, each naming the
missing term and how to fix it. **Both outcomes are correct.** The second is what
the product does on first run, and a market report that says "I could not
establish this, here is why" is worth more than one that quietly substitutes a
plausible number.
"""
from __future__ import annotations

from ..sizing import Ring, Sizing, Term
from ..sources.census import (CBP_YEAR, ECN_YEAR, Unavailable,
                              establishment_count, revenue_per_establishment,
                              unavailable_term)

NAICS = "561730"          # Landscaping Services
ARIZONA = "04"
MARICOPA = "013"


def _count(**kw) -> Term:
    try:
        return establishment_count(NAICS, year=CBP_YEAR, **kw)
    except Unavailable as exc:
        return unavailable_term("count", str(exc))


def _value(**kw) -> Term:
    try:
        return revenue_per_establishment(NAICS, year=ECN_YEAR, **kw)
    except Unavailable as exc:
        return unavailable_term("value", str(exc))


def build() -> Sizing:
    """Three rings: national, Arizona, Maricopa County."""
    sizing = Sizing(
        "Landscaping services (NAICS 561730)",
        basis="establishment-based: counts from County Business Patterns, "
              "value from Economic Census average revenue per establishment. "
              "This measures the industry's revenue, not one firm's opportunity")

    # The value term is only published at national and state level for most
    # industries; county receipts are widely suppressed to protect individual
    # businesses. Reusing the state figure at county level is a defensible
    # approximation but it IS an approximation, and the note says so rather
    # than letting the county ring look as solid as the state one.
    national_value = _value()
    state_value = _value(state_fips=ARIZONA)

    sizing.add(Ring(
        label="United States",
        count=_count(),
        value=national_value))

    sizing.add(Ring(
        label="Arizona",
        count=_count(state_fips=ARIZONA),
        value=state_value))

    county_value = state_value
    if county_value.known:
        county_value = Term(
            kind="value", value=county_value.value, unit=county_value.unit,
            as_of=county_value.as_of, source=county_value.source,
            source_url=county_value.source_url, method="derived",
            note="Arizona's average applied to Maricopa County. The Economic "
                 "Census suppresses county receipts for most industries, so "
                 "this is the state figure standing in — reasonable, and not "
                 "the same as measured")

    sizing.add(Ring(
        label="Maricopa County (Phoenix)",
        count=_count(state_fips=ARIZONA, county_fips=MARICOPA),
        value=county_value))
    return sizing


def render() -> str:
    return build().render()
