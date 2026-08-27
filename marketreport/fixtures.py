"""Recorded responses, so the whole report can run with no key and no network.

Two jobs, and the second is the one that matters.

**Demonstration.** Without a Census key every section reports "not established",
which is correct behaviour and a poor way to see what the product is. `--demo`
runs the same code against these and produces a complete report.

**Testing the assembled shape.** Unit tests can check that HHI is computed
correctly; only an end-to-end run can check that a complete report actually
holds together — that the barriers agent reads the concentration the structure
agent wrote, that the life-cycle stage follows from the growth figure, that
closure goes green when everything is answered. That path was untestable while
every agent refused.

**These are illustrative figures, not measurements**, and the report says so on
every line they touch. They are shaped like real Census responses and are in the
right order of magnitude for the industry, because a fixture that produced
absurd numbers would let absurd arithmetic pass. They are not the real values
and must never be quoted as though they were — which is why `demo=True` reaches
the renderer rather than being a flag only the caller knows about.
"""
from __future__ import annotations

from typing import Any, Dict, List

#: The marker that follows every demo figure all the way to the page.
DEMO_NOTE = ("illustrative figure from the offline demo, not a measurement — "
             "run with a Census key for the real value")

#: Landscaping Services, the market Von asked about first. Establishment counts
#: are shaped like a real County Business Patterns response: a long tail of very
#: small operators and almost nothing large, which is what a trade like this
#: actually looks like and what makes the concentration reading interesting.
_LANDSCAPING_BANDS_US: Dict[str, int] = {
    "1-4": 62_000, "5-9": 21_500, "10-19": 14_200, "20-49": 8_900,
    "50-99": 2_600, "100-249": 1_100, "250-499": 230, "500-999": 70,
    "1000+": 25,
}
_LANDSCAPING_BANDS_AZ: Dict[str, int] = {
    "1-4": 1_180, "5-9": 430, "10-19": 290, "20-49": 185,
    "50-99": 58, "100-249": 24, "250-499": 5, "500-999": 2, "1000+": 1,
}
_LANDSCAPING_BANDS_MARICOPA: Dict[str, int] = {
    "1-4": 760, "5-9": 285, "10-19": 195, "20-49": 124,
    "50-99": 38, "100-249": 16, "250-499": 3, "500-999": 1,
}


def _total(bands: Dict[str, int]) -> int:
    return sum(bands.values())


#: Keyed the way the agents ask: (naics, state, county, size_band).
COUNTS: Dict[Any, int] = {}
for _band, _n in _LANDSCAPING_BANDS_US.items():
    COUNTS[("561730", "", "", _band)] = _n
for _band, _n in _LANDSCAPING_BANDS_AZ.items():
    COUNTS[("561730", "04", "", _band)] = _n
for _band, _n in _LANDSCAPING_BANDS_MARICOPA.items():
    COUNTS[("561730", "04", "013", _band)] = _n
COUNTS[("561730", "", "", "")] = _total(_LANDSCAPING_BANDS_US)
COUNTS[("561730", "04", "", "")] = _total(_LANDSCAPING_BANDS_AZ)
COUNTS[("561730", "04", "013", "")] = _total(_LANDSCAPING_BANDS_MARICOPA)

#: Average annual receipts per establishment. Order-of-magnitude right for a
#: labour-heavy service trade.
REVENUE_PER_ESTABLISHMENT: Dict[Any, float] = {
    ("561730", ""): 386_000.0,
    ("561730", "04"): 402_000.0,
}

#: The same establishment count at an earlier vintage, which is what makes a
#: growth figure possible. Growth read from two vintages of one official series
#: is the honest method; an analyst CAGR is the one we refuse.
PRIOR_COUNTS: Dict[Any, int] = {
    ("561730", "", ""): 104_900,
    ("561730", "04", ""): 1_985,
    ("561730", "04", "013"): 1_310,
}
PRIOR_YEAR = 2017

#: Licensing, for the regulation agent. Real in shape: landscaping is licensed
#: in some states and not others, and the threshold is the part people miss.
LICENSING: Dict[str, Dict[str, Any]] = {
    "04": {
        "count": 1,
        "note": ("Arizona requires a contractor licence for landscaping work "
                 "above a stated job value; below that threshold an exemption "
                 "applies"),
        "threshold": "$1,000 per job including labour and materials",
        "body": "Arizona Registrar of Contractors",
    },
}

#: Named participants, for the competitor agent.
PARTICIPANTS: Dict[str, List[Dict[str, str]]] = {
    "561730": [
        {"name": "BrightView Holdings", "note": "publicly traded (NYSE: BV); "
                                                "the largest US commercial "
                                                "landscaper"},
        {"name": "The Davey Tree Expert Company", "note": "employee-owned, "
                                                          "files with the SEC"},
        {"name": "Aspen Grove Landscape Group", "note": "private equity "
                                                        "consolidator"},
        {"name": "TruGreen", "note": "adjacent — lawn treatment rather than "
                                     "full-service landscaping"},
    ],
}


#: Population, for the per-capita density measure. Real ACS figures rounded —
#: these are the one class of demo number that is close to the true value,
#: because population is not industry-specific and is easy to state correctly.
POPULATION: Dict[Any, int] = {
    ("", ""): 333_300_000,        # United States
    ("04", ""): 7_430_000,        # Arizona
    ("04", "013"): 4_550_000,     # Maricopa County
}


def population(state: str = "", county: str = "") -> int:
    return POPULATION.get((state, county), 0)


def count(naics: str, state: str = "", county: str = "",
          size_band: str = "") -> int:
    """A recorded establishment count, or 0 when the fixture has none."""
    return COUNTS.get((naics, state, county, size_band), 0)


def revenue(naics: str, state: str = "") -> float:
    """Recorded average revenue per establishment, falling back to national."""
    return (REVENUE_PER_ESTABLISHMENT.get((naics, state))
            or REVENUE_PER_ESTABLISHMENT.get((naics, ""))
            or 0.0)


def prior_count(naics: str, state: str = "", county: str = "") -> int:
    return PRIOR_COUNTS.get((naics, state, county), 0)


def covered(naics: str) -> bool:
    """Whether the demo has anything for this industry.

    Checked rather than assumed, so `--demo` on an industry the fixtures do not
    cover reports honestly instead of silently producing an empty report that
    looks like a real failure of the live backends.
    """
    return any(key[0] == naics for key in COUNTS)
