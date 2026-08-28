"""The parameter a report type must fix before it researches anything.

`measures.py` came first and was written as though the problem belonged to
market share. It does not. **Every report type has a dimension that must be
named upfront, or the report is unlabelled** — and an unlabelled report is not
a slightly worse report, it is a chart whose axis nobody can name:

    market share   →  basis          units, revenue, usage, subscribers…
    market size    →  price level    wholesale, retail, manufacturer revenue
    regulation     →  jurisdiction   which country's law, which regulator
    growth         →  period         which years, and whose forecast
    demographics   →  population     who is counted, and observed or claimed

Each one was learned the same way. The hearing-aid run reported 2025 market
totals from $7.5B to $15.11B, and a sixth source reached $21.61B by folding in
hearing implants — nearly three to one, driven entirely by boundary and price
level, neither of which any publisher stated. That is the market-size version
of the units-versus-revenue problem, and it will keep recurring in a new
vocabulary for every type added until the pattern itself is the thing in code.

**Two kinds of dimension, and the difference is real.**

*Enumerated* dimensions have a fixed, knowable set of values. Basis is one:
there are only so many ways to divide a market, and each has its own failure
mode worth writing down. Enumerating them lets the system produce one report
per value and say which values it could not source.

*Open* dimensions cannot be enumerated. Jurisdiction is one — there are two
hundred-odd of them and no useful purpose is served by listing them. An open
dimension still has to be *named*, it just cannot be *chosen from*. The
guidance travels with the dimension rather than with each value.

Both kinds refuse to default. A dimension that quietly picks a value is worse
than one that refuses, because the reader never learns a choice was made.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = ["Option", "Dimension", "register", "get", "registered",
           "BASIS", "PRICE_LEVEL", "JURISDICTION", "PERIOD", "POPULATION"]


@dataclass(frozen=True)
class Option:
    """One value a dimension can take.

    Every field is written to be handed to a model. `counts` scopes the opening
    questions, `refuse` tells the reader what not to record, `homes` tells the
    opener where to look, and `confusable_with` names what a source is likeliest
    to have supplied instead — which is the check that catches a usage share
    arriving where a sales share was asked for.
    """

    key: str
    #: How a person would name it: "share of revenue", "at retail prices".
    label: str
    #: What is being counted or measured, in one sentence.
    counts: str
    #: The quantity underneath — currency, count, rate. Not the presentation
    #: unit; a share is always a percentage whatever it is a share of.
    quantity: str = "count"
    #: How this value is misread. Given as instruction and, where checkable,
    #: verified after the fact.
    refuse: str = ""
    #: Where a figure on this footing is usually published.
    homes: str = ""
    #: Keys a source is likely to supply instead of this one. The common
    #: corruption is not a wrong number, it is a right number on the wrong
    #: footing, and that is undetectable once it is in a chart.
    confusable_with: Tuple[str, ...] = ()
    #: Words suggesting a statement is on this footing. Used to sort findings,
    #: never to invent one.
    cues: Tuple[str, ...] = ()
    #: When this value applies at all. Advisory; upstream decides.
    applies_when: str = ""


@dataclass(frozen=True)
class Dimension:
    """The parameter one kind of report must be scoped by."""

    key: str
    #: The question this dimension answers, phrased as a person would ask it:
    #: "measured how?", "priced at what level?", "under whose law?"
    label: str
    #: Why leaving it unstated ruins the report. Goes into the brief verbatim,
    #: so it is written as an explanation rather than as a note to ourselves.
    why: str
    #: The values, when they can be enumerated. Empty means an open dimension —
    #: named but not chosen from. See the module docstring.
    options: Tuple[Option, ...] = ()
    #: What an open dimension's value should look like, for the caller.
    expects: str = ""

    @property
    def open(self) -> bool:
        return not self.options

    def get(self, key: str) -> Optional[Option]:
        wanted = (key or "").strip().lower().replace("-", "_")
        for option in self.options:
            if option.key == wanted:
                return option
        return None

    def resolve(self, names: Sequence[str]) -> Tuple[List[Option], List[str]]:
        """Named values in, options out, plus the ones this does not know.

        Unknown names come back rather than being dropped or guessed. A caller
        naming a value this dimension has never heard of is a real event —
        either something worth registering or a typo — and silently producing
        six reports when seven were asked for is the kind of quiet shortfall
        nobody notices.

        An open dimension accepts anything and builds an option on the spot,
        carrying the dimension's own guidance, because there is no list to
        check against and refusing everything would make the dimension useless.
        """
        out: List[Option] = []
        unknown: List[str] = []
        seen = set()
        for raw in names or ():
            name = str(raw).strip()
            if not name:
                continue
            if self.open:
                key = name.lower().replace(" ", "_")
                if key in seen:
                    continue
                seen.add(key)
                out.append(Option(key=key, label=f"{self.label} {name}",
                                  counts=self.expects or self.why,
                                  refuse=self.why, homes=""))
                continue
            found = self.get(name)
            if found is None:
                unknown.append(name)
                continue
            if found.key in seen:
                continue
            seen.add(found.key)
            out.append(found)
        return out, unknown


_REGISTRY: Dict[str, Dimension] = {}


def register(dimension: Dimension) -> Dimension:
    _REGISTRY[dimension.key] = dimension
    return dimension


def get(key: str) -> Optional[Dimension]:
    return _REGISTRY.get((key or "").strip().lower().replace("-", "_"))


def registered() -> List[Dimension]:
    return list(_REGISTRY.values())


# --------------------------------------------------------------- enumerated

#: The seven yardsticks a market can be divided by. They moved here from
#: `measures.py`, which now re-exports them: two definitions of what "share of
#: units sold" means is exactly the kind of drift this module exists to stop.
BASIS = register(Dimension(
    key="basis",
    label="measured as",
    why=("A market share is not one question. A share of revenue and a share "
         "of units can name different leaders, because a company selling "
         "fewer dearer products leads one and trails the other, and the gap "
         "between the two is routinely larger than the gap between "
         "competitors. Every figure in one report must be on one basis; a "
         "separate report covers each of the others."),
    options=(
        Option(
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
        ),

        Option(
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
        ),

        Option(
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
        ),

        Option(
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
        ),

        Option(
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
        ),

        Option(
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
        ),

        Option(
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
        ),
    )))


PRICE_LEVEL = register(Dimension(
    key="price_level",
    label="priced at",
    why=("The same goods have several different totals depending on where in "
         "the chain you count the money, and the differences are large. A "
         "manufacturer's wholesale total and end-customer retail spend on the "
         "identical devices differ by the entire distribution margin — in "
         "hearing aids that margin is most of the price. A market size with no "
         "stated price level cannot be compared with anything, and a share "
         "computed against the wrong one is wrong by that margin."),
    options=(
        Option(
            key="wholesale",
            label="wholesale value",
            counts="what manufacturers were paid by whoever distributes or "
                   "dispenses the product",
            quantity="currency",
            refuse="Do not mix this with retail spend. Say whether it is net "
                   "of returns and rebates, because trade terms in some "
                   "industries move this by double digits.",
            homes="manufacturers' filed segment revenue; trade associations, "
                  "which often report member shipments at wholesale",
            confusable_with=("retail", "manufacturer_revenue"),
            cues=("wholesale", "net wholesale", "ex-factory", "shipment value",
                  "sold to dispensers", "sold to distributors", "trade sales"),
        ),
        Option(
            key="retail",
            label="retail spend",
            counts="what end customers actually paid, including the margin of "
                   "whoever sold it to them",
            quantity="currency",
            refuse="This is the largest of the price levels and is the one "
                   "most syndicated reports quote without saying so. Never "
                   "compute a manufacturer's share against it without "
                   "removing the distribution margin, or every maker is "
                   "understated by that margin.",
            homes="retail scanner panels and consumer spend surveys, mostly "
                  "proprietary; occasionally a national statistics office",
            confusable_with=("wholesale", "manufacturer_revenue"),
            cues=("retail", "consumer spend", "end user price", "shelf price",
                  "at retail", "consumer spending"),
        ),
        Option(
            key="manufacturer_revenue",
            label="manufacturer revenue",
            counts="the reported revenue of the companies that make the "
                   "product, as they book it",
            quantity="currency",
            refuse="Not the same as wholesale value. A vertically integrated "
                   "maker that owns its own retail books the retail margin "
                   "inside its own revenue, so its total is not comparable "
                   "with a manufacturer-only competitor's without separating "
                   "the wholesale line. Sonova and Demant are both this case.",
            homes="audited annual reports and segment disclosures, which are "
                  "free",
            confusable_with=("wholesale", "retail"),
            cues=("group revenue", "segment revenue", "reported revenue",
                  "net sales", "turnover"),
        ),
    )))


POPULATION = register(Dimension(
    key="population",
    label="counting",
    why=("A demographic figure is meaningless without saying who was counted "
         "and how. Self-reported and observed populations differ "
         "systematically and in a known direction — people misreport "
         "behaviour they are asked about. A figure about buyers, a figure "
         "about users and a figure about the whole addressable population are "
         "three different numbers, and the largest is often quoted as though "
         "it were the smallest."),
    options=(
        Option(
            key="buyers",
            label="people who bought",
            counts="those who actually purchased in the period",
            refuse="Buyers are not users and not households. Say the period; "
                   "a year's buyers of something bought once a decade is a "
                   "tiny fraction of its users.",
            homes="retailer and manufacturer disclosures; national household "
                  "expenditure surveys",
            confusable_with=("users", "eligible"),
            cues=("buyers", "purchasers", "customers", "bought", "purchased"),
        ),
        Option(
            key="users",
            label="people who use it",
            counts="those using the product, whether or not they bought it",
            refuse="For anything durable or shared, users vastly outnumber "
                   "buyers in any one year. Never present a user count as "
                   "demand.",
            homes="usage panels; government health and activity surveys",
            confusable_with=("buyers", "eligible"),
            cues=("users", "wearers", "use", "usage", "active"),
        ),
        Option(
            key="eligible",
            label="people who could",
            counts="those who meet the criteria to be in this market at all, "
                   "whether or not they participate",
            refuse="This is the number most often inflated into a market "
                   "size. An eligibility count is a ceiling, not demand, and "
                   "the gap between it and buyers is usually the whole story "
                   "— say what that gap is rather than hiding it.",
            homes="census and national statistics; prevalence studies for "
                  "health markets",
            confusable_with=("buyers", "users"),
            cues=("eligible", "could benefit", "prevalence", "living with",
                  "population aged", "addressable"),
        ),
    )))


# --------------------------------------------------------------------- open

JURISDICTION = register(Dimension(
    key="jurisdiction",
    label="under the law of",
    why=("Rules are territorial. A regulation report with no stated "
         "jurisdiction silently becomes a report about the United States, "
         "which is wrong for most markets anyone asks about and wrong in a "
         "way the reader cannot see. Name the country or bloc, and name the "
         "regulator, because one market is often governed by several."),
    expects="a country, state or bloc — 'United States', 'European Union', "
            "'California', 'Ireland'"))


PERIOD = register(Dimension(
    key="period",
    label="over",
    why=("A growth rate with no stated endpoints cannot be checked and usually "
         "cannot be reproduced. Give both years and the value at each. Name "
         "whoever produced any forecast: a projection is somebody's opinion "
         "and belongs to them, and where a public programme funds the market, "
         "that programme's own published growth beats any analyst CAGR."),
    expects="two years, or a year range — '2020-2025', '2024 to 2029'"))

