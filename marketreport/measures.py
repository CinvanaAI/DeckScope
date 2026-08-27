"""What a share can be measured in — the vocabulary of the handoff.

A market share is not one question. "Who leads the cell phone market in
Ireland" is at least four different questions, and they have different answers:
StatCounter's usage share, the mobile operators' subscriber share, wireless
service revenue, and handset units sold. Whichever one you draw, the others are
also true, and a reader shown one chart assumes it is the only chart.

The old design treated this as a hazard to warn about. The live hearing-aid run
showed why that is not enough: the panel's loudest caveat was that no publisher
stated whether its shares were units or revenue, so the single most important
property of the chart arrived at the *end*, as a defect in the sources. It is
not a defect in the sources. It is a parameter, and it belongs at the front.

So a measure is now named before the research starts, and one report is
produced per measure. Upstream decides which market this is and which measures
it is meaningfully sold in; this module is the shared vocabulary both ends use
to say so, and `run_specialist` receives one measure per run.

**Every field here is written to be given to a model.** `counts` scopes the
questions, `refuse` tells the reader what not to record, `homes` tells the
opener where to look, and `confusable_with` names the specific measure a source
is most likely to have supplied instead — which is the check that catches a
usage share arriving where a sales share was asked for.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = ["Measure", "register", "get", "registered", "resolve", "suggest",
           "REVENUE", "UNITS", "USAGE", "INSTALLED_BASE", "SUBSCRIBERS",
           "OUTLETS", "CAPACITY"]


@dataclass(frozen=True)
class Measure:
    """One yardstick a market can be divided by."""

    key: str
    #: How a person would name it: "share of revenue", "share of units sold".
    label: str
    #: What is being counted, in one sentence. Goes into the opener prompt as
    #: the scope of the whole run.
    counts: str
    #: The unit a slice is expressed in once computed. Always "%" for a share;
    #: kept explicit because the underlying quantity differs and the figures
    #: alongside the chart are in it.
    quantity: str
    #: How this measure is misread, given to the reader and checked after.
    refuse: str
    #: Where a figure on this basis is usually published.
    homes: str
    #: Measures a source is likely to supply instead of this one. The most
    #: common corruption is not a wrong number, it is a right number on the
    #: wrong basis, and it is undetectable once it is in a chart.
    confusable_with: Tuple[str, ...] = ()
    #: Words in a statement that suggest it is on this basis. Used to sort
    #: findings to the right report, never to invent one.
    cues: Tuple[str, ...] = ()
    #: Markets where this measure does not apply at all — asking for units of
    #: a service, or usage of a durable good, wastes the budget and returns
    #: noise. Advisory; upstream decides.
    applies_when: str = ""


_REGISTRY: Dict[str, Measure] = {}


def register(measure: Measure) -> Measure:
    _REGISTRY[measure.key] = measure
    return measure


def get(key: str) -> Optional[Measure]:
    return _REGISTRY.get((key or "").strip().lower().replace("-", "_"))


def registered() -> List[Measure]:
    return list(_REGISTRY.values())


REVENUE = register(Measure(
    key="revenue",
    label="share of revenue",
    counts="the money customers spent, divided between the companies that "
           "booked it",
    quantity="currency",
    refuse="Do not mix this with a share of units. A company selling fewer, "
           "dearer products can lead on revenue and trail badly on volume, and "
           "the gap between the two is routinely larger than the gap between "
           "competitors. Say at which price level the revenue is counted — "
           "manufacturer wholesale and end-customer retail differ by the whole "
           "distribution margin.",
    homes="company annual reports and segment disclosures, which are audited "
          "and free; trade press summaries of them",
    confusable_with=("units", "installed_base"),
    cues=("revenue", "sales", "turnover", "value", "$", "usd", "eur",
          "billion", "million"),
))

UNITS = register(Measure(
    key="units",
    label="share of units sold",
    counts="the number of things sold or shipped in a period, divided between "
           "the companies that sold them",
    quantity="count",
    refuse="Do not mix this with a share of revenue, and do not accept an "
           "installed base in its place — units sold in a period and units in "
           "service are different populations, and the second is far larger "
           "for anything durable. State the period; a quarter and a year are "
           "not interchangeable.",
    homes="channel panels and shipment trackers, which are proprietary in "
          "almost every market; occasionally a regulator or trade association",
    confusable_with=("installed_base", "revenue"),
    cues=("units", "shipments", "shipped", "volume", "sold", "handsets",
          "devices", "pieces"),
    applies_when="the market sells discrete countable things rather than a "
                 "service or a subscription",
))

USAGE = register(Measure(
    key="usage",
    label="share of usage",
    counts="observed activity — sessions, page views, traffic, time — divided "
           "between the products generating it",
    quantity="count",
    refuse="This is the one most often mistaken for a sales share and it is "
           "the most different. It measures the installed base in ACTION, so "
           "it is weighted by how much each user uses the thing and it lags "
           "sales by the replacement cycle. Never place a usage share and a "
           "sales share in one chart. Name the panel and its geography — usage "
           "panels are samples, and their country-level numbers can be thin.",
    homes="measurement panels such as StatCounter and Similarweb, and the "
          "platforms' own published telemetry",
    confusable_with=("installed_base", "units"),
    cues=("usage", "traffic", "sessions", "page views", "pageviews",
          "browsing", "statcounter", "active"),
    applies_when="the product is used repeatedly and that use can be observed",
))

INSTALLED_BASE = register(Measure(
    key="installed_base",
    label="share of installed base",
    counts="the things currently in service, divided between the companies "
           "that made them",
    quantity="count",
    refuse="A stock, not a flow. It reflects years of past sales, so a company "
           "that has stopped selling can still lead it. Never present it as "
           "current share and never mix it with units sold.",
    homes="regulators, registries, census-style surveys, and companies' own "
          "active-device disclosures",
    confusable_with=("units", "usage"),
    cues=("installed base", "in service", "in use", "active devices",
          "fleet", "households with"),
    applies_when="the product is durable and stays in service for years",
))

SUBSCRIBERS = register(Measure(
    key="subscribers",
    label="share of subscribers",
    counts="paying accounts or connections, divided between the providers "
           "holding them",
    quantity="count",
    refuse="Say whether this counts accounts, connections or people — one "
           "household may hold several, and providers publish whichever "
           "flatters them. Do not read it as revenue share: prices per "
           "subscriber differ widely between prepaid and contract.",
    homes="telecom and utility regulators, who usually publish this free and "
          "quarterly; the providers' own results",
    confusable_with=("revenue", "installed_base"),
    cues=("subscribers", "subscriptions", "connections", "accounts", "lines",
          "customers", "sim"),
    applies_when="the market is sold as an ongoing service rather than a "
                 "one-off purchase",
))

OUTLETS = register(Measure(
    key="outlets",
    label="share of outlets",
    counts="physical locations trading in this market, divided between their "
           "owners",
    quantity="count",
    refuse="Locations are not sales. A chain of small outlets can lead on "
           "count and trail badly on revenue. Where the market is served both "
           "physically and online, say what this excludes.",
    homes="company store counts, franchise disclosures, and the Census County "
          "Business Patterns establishment counts, which are free",
    confusable_with=("revenue",),
    cues=("stores", "outlets", "locations", "branches", "clinics",
          "establishments", "sites"),
    applies_when="the market is served through physical premises",
))

CAPACITY = register(Measure(
    key="capacity",
    label="share of capacity",
    counts="productive capacity — beds, seats, megawatts, tonnes per year — "
           "divided between its owners",
    quantity="count",
    refuse="Capacity is not output and output is not revenue. Say whether the "
           "figure is installed capacity or capacity actually utilised; the "
           "difference is the whole story in any market with a cycle.",
    homes="sector regulators and industry associations, which usually publish "
          "capacity because it is a planning input",
    confusable_with=("units", "installed_base"),
    cues=("capacity", "beds", "seats", "megawatts", "gigawatts", "tonnes",
          "throughput"),
    applies_when="the market is supply-constrained and capacity is the "
                 "binding quantity",
))


def resolve(names: Sequence[str]) -> Tuple[List[Measure], List[str]]:
    """Turn handed-off measure names into measures, and name the unknown ones.

    Returns `(measures, unknown)`. Unknown names are returned rather than
    dropped or guessed: upstream naming a measure this module has never heard
    of is a real event — either a new measure worth registering or a typo — and
    silently running six reports when seven were asked for is the kind of
    quiet shortfall nobody notices.
    """
    out: List[Measure] = []
    unknown: List[str] = []
    seen = set()
    for name in names or ():
        found = get(str(name))
        if found is None:
            unknown.append(str(name))
            continue
        if found.key in seen:
            continue
        seen.add(found.key)
        out.append(found)
    return out, unknown


def suggest(text: str) -> List[Measure]:
    """Measures a piece of text reads as being on.

    A convenience for upstream and a sorting aid downstream — never a
    substitute for being told. A finding that matches no cue is not assigned a
    measure, because guessing the basis of a number is the exact error this
    whole module exists to prevent.
    """
    low = f" {(text or '').lower()} "
    hits: List[Measure] = []
    for measure in _REGISTRY.values():
        if any(cue in low for cue in measure.cues):
            hits.append(measure)
    return hits
