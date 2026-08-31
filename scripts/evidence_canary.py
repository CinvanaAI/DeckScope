"""Drive the shipped grants/nonprofits evidence clients against their
live APIs — the hermetic suite's counterpart, in the census-canary mold.

Every request here is one the verticals actually send (same modules,
same functions, no re-implementation), and every check is structural:
the contract recorded in recorded/phase0/ still holds — not that any
particular total has stayed the same, which is the world's business.

A red run means an upstream contract moved (or a service is down). It
files the news; it does not block merges.
"""
from __future__ import annotations

import sys

FAILURES: list[str] = []


def require(cond: bool, msg: str) -> None:
    """Not `assert`: a canary must fly identically under python -O."""
    if not cond:
        raise RuntimeError(msg)


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"  ok    {name}")
    except Exception as exc:  # noqa: BLE001 - the canary's whole job
        FAILURES.append(f"{name}: {type(exc).__name__}: {exc}")
        print(f"  MOVED {name}: {exc}")


def nsf() -> None:
    from deckscope.research.grantsources import nsf_awards

    rec = nsf_awards("smartphone", limit=3)
    require(isinstance(rec.total, int) and rec.total >= 0,
            "totalCount is no longer an int")
    require(bool(rec.hits), "live NSF returned no awards for a broad term")
    require(rec.hits[0].url.startswith(
        "https://www.nsf.gov/awardsearch/showAward?AWD_ID="),
        "award URL shape changed")


def nih() -> None:
    from deckscope.research.grantsources import nih_projects

    rec = nih_projects("smartphone sensing", limit=3)
    require(isinstance(rec.total, int) and rec.total >= 0,
            "meta.total is no longer an int")
    for h in rec.hits:
        require(h.url.startswith(
            "https://reporter.nih.gov/project-details/"),
            "project URL shape changed")


def usaspending() -> None:
    from deckscope.research.grantsources import usaspending_awards

    rec = usaspending_awards("smartphone", limit=3)
    require(isinstance(rec.total, int) and rec.total >= 0,
            "the paged floor count is no longer an int")


def pubmed() -> None:
    from deckscope.research.grantsources import pubmed_count

    rec = pubmed_count("smartphone sensing")
    require(isinstance(rec.total, int) and rec.total >= 0,
            "esearch Count is no longer parseable")


def propublica() -> None:
    from deckscope.research.nonprofitsources import org_record, search_orgs

    cands = search_orgs("Feeding America", limit=3)
    require(bool(cands) and bool(cands[0].ein),
            "search returned no organizations")
    rec = org_record(363673599)
    require(bool(rec.name), "org detail lost its name")
    require(bool(rec.filings), "filings_with_data came back empty")
    latest = rec.filings[0]
    require(latest.total_revenue is not None,
            "totrevenue missing from the extract — the reconciliation's "
            "primary field")
    require(latest.fiscal_end_month in range(1, 13),
            "tax_prd no longer encodes the fiscal end month — the "
            "fiscal-basis law depends on it")


def main() -> int:
    print("evidence canary: driving the shipped clients live")
    check("NSF awards.json (GET)", nsf)
    check("NIH RePORTER v2 (POST)", nih)
    check("USAspending spending_by_award (POST)", usaspending)
    check("PubMed esearch (GET, XML)", pubmed)
    check("ProPublica Nonprofit Explorer v2 (GET)", propublica)
    if FAILURES:
        print(f"\n{len(FAILURES)} contract(s) moved:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all five evidence contracts hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
