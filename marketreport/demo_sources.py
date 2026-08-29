"""Recorded pages, so the whole panel path runs with no keys and no network.

**These are real.** Every excerpt below was retrieved on 2026-08-27 from the URL
recorded beside it, while answering the client's cell-phone question by hand. They are
quotations from published research, trimmed to the sentences that carry the
figures, not text I wrote to be plausible.

That distinction is the whole reason this file exists rather than another
`fixtures.py`. `CRITIQUE.md` #1 is that the Census demo runs on numbers I
invented — labelled, but invented — and that a stranger running it would
conclude the product works when what works is the fixture. A demo built from
recorded real responses teaches true things, and its arithmetic is validated
against real inputs.

The trade is that it goes stale. Q2 2026 figures are correct for Q2 2026 and
will be wrong about the market by the end of the year, which is why every
excerpt carries its retrieval date and the demo says on its face that it is a
replay of a specific day rather than a live look.

Nothing here is a substitute for a search key. It is a way to see the machinery
work, and a fixed input that makes the machinery testable.
"""
from __future__ import annotations

from typing import Any, Dict, List

RETRIEVED = "2026-08-27"

#: (title, url, excerpt, published). Excerpts are quotations, trimmed.
PAGES: List[Dict[str, str]] = [
    {
        "title": "SAG: Global Smartphone Shipments Fall 8% in Q2 2026; "
                 "Samsung and Apple Gain Market Share",
        "url": "https://smartanalyticsglobal.com/"
               "lobal-smartphone-market-share-q2-2026-samsung-apple/",
        "published": "2026-07-13",
        "snippet": (
            "Samsung ranked No.1 in the global smartphone market in Q2 2026, "
            "capturing 22% market share, up from 19% one year ago. Apple "
            "captured 20% of global smartphone shipments in Q2 2026, up from "
            "17% in Q2 2025. Xiaomi ranked third globally with 11% market "
            "share, down from 14% a year earlier. OPPO Group, including "
            "OnePlus and Realme, ranked fourth with 11% global market share. "
            "vivo Group, including iQOO, captured 8% of global smartphone "
            "shipments in Q2 2026, down from 9% one year ago. Global "
            "smartphone shipments declined 8% year-over-year in Q2 2026."),
    },
    {
        "title": "IDC Worldwide Quarterly Mobile Phone Tracker, Q2 2026",
        "url": "https://www.idc.com/promo/smartphone-market-share/",
        "published": "2026-07-15",
        "snippet": (
            "Worldwide smartphone shipments reached 277.5 million units in Q2 "
            "2026, a 6.7% decline year over year. Samsung led with 22.6% "
            "share on 62.7 million units. Apple followed with 20.1% share on "
            "55.8 million units. Xiaomi held 11.2% share on 31.2 million "
            "units."),
    },
    {
        "title": "Apple Captures Nearly Half of Global Smartphone Revenue as "
                 "Q2 Market Share Hits Record (Counterpoint Research)",
        "url": "https://finance.biggo.com/news/"
               "e5dbccbc-771f-4510-9adf-895a725f9631",
        "published": "2026-08-01",
        "snippet": (
            "Apple captured 49% of global smartphone market revenue in the "
            "second quarter of 2026, a record for the period, according to "
            "Counterpoint Research. Apple's average selling price climbed to "
            "$946 from $879 a year earlier. Samsung's smartphone revenue "
            "accounted for only 16% of the global market in Q2, with an "
            "average selling price around $270. Global smartphone revenue "
            "grew 7% year-over-year in the second quarter. Samsung's Mobile "
            "Experience division posted an operating loss of approximately "
            "700 billion won in the second quarter."),
    },
    {
        "title": "Global Smartphone Revenues Grew 5% YoY in Q3 2025 "
                 "(Counterpoint Research)",
        "url": "https://counterpointresearch.com/en/insights/"
               "global-smartphone-revenues-q3-2025",
        "published": "2025-10-31",
        "snippet": (
            "The global smartphone market's revenue climbed 5% YoY in Q3 "
            "2025, reaching $112 billion, the highest ever level for a third "
            "quarter. The global Average Selling Price hit the highest ever "
            "Q3 level, reaching $351. Apple led the market in terms of "
            "revenue with a 43% share at 6% YoY growth."),
    },
    {
        "title": "Global Smartphone Market Share: Quarterly "
                 "(Counterpoint Research)",
        "url": "https://counterpointresearch.com/en/insights/"
               "global-smartphone-share",
        "published": "2026-05-18",
        "snippet": (
            "Apple led in Q1 2026 for the first time with 21% market share "
            "and 9% YoY growth. Samsung ranked second with 21% and remained "
            "flattish. Xiaomi held 12%, OPPO 10% and vivo 7%. The global "
            "smartphone market remained under pressure in Q1 2026, with "
            "shipments declining 3% YoY driven by the shortage of memory "
            "components and weaker demand."),
    },
]

NOTE = (f"replay of pages recorded on {RETRIEVED} — real published research, "
        f"not live, and correct as of the quarter each one describes")


#: The report types these pages can actually answer. They are five smartphone
#: market-share articles; nothing in them says a word about regulation, buyer
#: demographics or growth drivers.
#:
#: Without this the demo ran every report type against them and returned the
#: same market-share headline each time — "Samsung leads on units; Apple leads
#: on revenue" — under the heading of a regulation report and a demographics
#: report. The demo is what somebody runs to learn what the tool does, so that
#: was not a thin answer, it was a false lesson about four of the seven types.
SUPPORTS = ("market-share", "competitive-landscape")


def covered(market: str, report: str = "") -> bool:
    """Whether the recorded pages can answer this report about this market.

    Checked rather than assumed, on both axes. Running the demo outside what
    the pages hold produces something that reads like a real failure of the
    live backends when it is only a demo pointed at the wrong thing — and, for
    the wrong report type, something worse: a confident answer to a question
    the sources never addressed.
    """
    words = {"phone", "phones", "smartphone", "smartphones", "handset",
             "handsets", "mobile"}
    if not any(word in (market or "").lower() for word in words):
        return False
    return not report or report.strip().lower() in SUPPORTS


def why_not(market: str, report: str = "") -> str:
    """The specific reason `covered` said no, for the caller to print."""
    if not covered(market):
        return (f"the offline demo only has recorded pages for the mobile "
                f"phone market, and this is about {market or 'nothing'!r}")
    return (f"the recorded pages are five smartphone market-share articles. "
            f"They cannot support a {report!r} report — nothing in them "
            f"addresses that question, so the demo would answer it from the "
            f"wrong material and look confident doing it. Recorded demos "
            f"exist for: {', '.join(SUPPORTS)}")


class RecordedResearcher:
    """A `Researcher` that serves every query from the recorded pages.

    Returns everything for every query rather than trying to match. Matching
    would make the demo look cleverer than the system: the loop's job is to
    read what it gets and the reader's job is to answer the question from it,
    and a researcher that pre-filters to the perfect page for each question
    quietly does both of their jobs and hides whether they work.
    """

    name = "recorded"
    needs_key = False

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def search(self, query: str, max_results: int = 8) -> List[Any]:
        from deckscope.research.base import SearchResult

        return [SearchResult(title=page["title"], url=page["url"],
                             snippet=page["snippet"],
                             published=page["published"], source_query=query)
                for page in PAGES[:max_results]]

    def search_many(self, queries: List[str], max_results: int = 8) -> List[Any]:
        from deckscope.research.base import Researcher

        return Researcher.search_many(self, queries, max_results=max_results)

    def health_check(self) -> Dict[str, Any]:
        return {"ok": True, "backend": self.name, "results": len(PAGES)}
