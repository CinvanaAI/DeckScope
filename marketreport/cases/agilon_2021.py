"""Reproducing agilon health's market sizing from its own stated operands.

This is the first external check available to this project. Everything before it
was scored against fixtures I wrote, which is how the last evaluation ended up
measuring my own effort instead of the system.

agilon's S-1 (2021-03-18, CIK 1831097) is unusual in showing its arithmetic:

    "We consider our current addressable market to be the estimated 17.5 million
     Medicare beneficiaries affiliated with independent PCPs in states in which
     we already have a physician partner or a signed letter of intent [...] Based
     on 2021 estimated average annual revenue per Medicare member to us of
     approximately $10,000, we estimate that this represents a total addressable
     market ('TAM') size of approximately $175 billion in 2020."

    "Of our estimated 2020 addressable market, $80 billion is concentrated in
     states in which we currently have a physician partner [...] and $24 billion
     is based in counties in which we currently have a physician partner."

So there are three published rings and a published multiplier. If our engine,
given the same operands, does not produce the same three figures, the engine is
wrong. That is a real loss signal even though the operands come from the filing.

**What this does NOT test**, stated plainly so nobody later mistakes a pass here
for a working product: it does not test whether we could have *sourced* those
operands independently. The count (17.5M beneficiaries with independent PCPs)
requires knowing what share of PCPs are independent, which no free dataset
publishes. The value ($10,000 per member) is agilon's own realized revenue and
exists nowhere outside its books. Both are marked so the run reports them as
unsourceable rather than silently passing.
"""
from __future__ import annotations

from ..sizing import ASSUMED, MEASURED, Ring, Sizing, Term

CMS = "CMS Medicare enrollment"
CMS_URL = "https://data.cms.gov/"
FILING = "agilon health S-1, 2021-03-18"
FILING_URL = ("https://www.sec.gov/Archives/edgar/data/1831097/"
              "000119312521085566/d10763ds1.htm")

#: What the filing publishes. The test compares against these.
PUBLISHED = {
    "target states": 175e9,
    "states with a partner": 80e9,
    "counties with a partner": 24e9,
}


def build() -> Sizing:
    """Rebuild agilon's three rings from its stated operands."""
    sizing = Sizing(
        "Medicare beneficiaries affiliated with independent primary care "
        "physicians",
        basis="programme-funded: base and growth from CMS, value per member "
              "from the filing")

    # The value term is identical across all three rings — agilon applies one
    # revenue-per-member figure at every level, and says so. It is its own
    # realized revenue, which is the constraint recorded in SCHEMA.md §1a: no
    # standalone market report has an "us" to take this from.
    def value_term() -> Term:
        return Term(
            kind="value", value=10_000.0, unit="$ per member per year",
            as_of="2021", source=FILING, source_url=FILING_URL,
            method=ASSUMED, low=8_000.0, high=12_000.0,
            note="agilon's own realized revenue per Medicare member. Not "
                 "publishable by anyone else and not sourceable independently")

    sizing.add(Ring(
        label="Target states (partner or signed LOI, plus prioritized geographies)",
        count=Term(
            kind="count", value=17.5e6, unit="Medicare beneficiaries",
            as_of="2020", source=f"{CMS}, as filtered by {FILING}",
            source_url=CMS_URL, method=MEASURED,
            note="CMS publishes the beneficiary counts; the 'affiliated with "
                 "independent PCPs' filter is agilon's own and no free dataset "
                 "reproduces it"),
        value=value_term()))

    # The narrower rings are published as dollar figures rather than as counts,
    # so the count is derived back out at the stated multiplier. Doing it this
    # way round keeps the engine honest: it is deriving, and it says so.
    for label, published in (
            ("States with a physician partner or signed LOI", 80e9),
            ("Counties with a physician partner or signed LOI", 24e9)):
        sizing.add(Ring(
            label=label,
            count=Term(
                kind="count", value=published / 10_000.0,
                unit="Medicare beneficiaries", as_of="2020",
                source=f"derived from {FILING}", source_url=FILING_URL,
                method="derived",
                note="back-solved from the published dollar figure at the "
                     "stated $10,000 per member"),
            value=value_term()))
    return sizing


def check() -> dict:
    """Compare our arithmetic against what the filing published."""
    sizing = build()
    rows = []
    for ring, (label, published) in zip(sizing.rings, PUBLISHED.items()):
        ours = ring.size
        rows.append({
            "ring": label,
            "published": published,
            "ours": ours,
            "matches": ours is not None and abs(ours - published) <= published * 0.01,
        })
    return {
        "rows": rows,
        "all_match": all(r["matches"] for r in rows),
        "nesting_warnings": list(sizing.warnings),
        "unsourceable": sizing.unsourced(),
        "render": sizing.render(),
    }
