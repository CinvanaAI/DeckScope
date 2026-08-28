"""The other report types, as specialists.

`specialists.py` holds market-share and the machinery. This holds the rest, so
that file stays about *how a specialist runs* and this one is about *what
reports exist*. Importing this module registers them.

Each was chosen from the research in `docs/REPORT_TYPES.md` on two tests, and
both had to pass: does a real reader use it for a real decision, and can it be
built from citable facts. Everything that failed the second test is absent and
named there rather than half-built here — voice of customer, win/loss and buyer
personas need primary interviews, and SAM and SOM are functions of one
company's capabilities that we do not have.

**Every one declares its dimension.** That is the whole point of adding them
this way rather than as more section briefs. A market size with no stated price
level, a regulation report with no stated jurisdiction and a growth rate with
no stated period are all the same defect wearing different clothes, and the
hearing-aid run showed what it costs: five publishers sizing one market from
$7.5B to $15.11B, and a sixth at $21.61B, with not one of them saying where in
the chain they counted the money.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from .panel import ABSENT, DERIVED, Figure, Panel
from .reports import ReportType, Section
from .reports import register as register_type
from .specialists import Specialist, register

__all__ = ["MARKET_SIZE", "GROWTH", "REGULATION", "COMPETITIVE_LANDSCAPE",
           "DEMOGRAPHICS", "GROWTH_REPORT"]


# ------------------------------------------------------------- market size

#: A per-unit amount, in the words sources actually use for one. Checked
#: directly rather than through `metrics.classify`, which returns "unknown" for
#: all three of the statements this had to separate: its PRICE rule matches
#: `\bprice\b`, so "wholesale prices range from $400" slips past on the plural.
#: A narrow explicit test that works beats a general one that does not.
#: Two branches, because enumerating the nouns alone was too brittle: the
#: first list omitted "person" and so failed to recognise "average annual spend
#: is $120 per person" as a per-unit figure, which is FIGS's actual value term.
#: The second branch catches any "per <noun>" in a sentence that is plainly
#: about money, which is the general case; the first catches the money words
#: that carry no "per" at all.
_PER_UNIT = re.compile(
    r"\b(unit price|selling price|invoice|asp\b|average (annual )?"
    r"(price|spend|revenue|cost|value)|price per|prices? (range|of)"
    r"|per (unit|device|item|piece|head|capita|each))\b"
    r"|(?=.*\b(spend|spent|price|prices|cost|paid|pays|revenue|invoice|"
    r"charge)\b).*\bper [a-z][a-z-]+\b", re.I)


def _per_unit(statement: str) -> bool:
    return bool(_PER_UNIT.search(statement or ""))


def _size_check(*, findings: Sequence[Any], panel: Panel, market: str,
                place: str = "", **_: Any) -> Dict[str, Any]:
    """The checks a sizing claim has to survive.

    All five S-1s in the corpus size a market the same way — COUNT of units ×
    RATE that qualify × VALUE per unit — and the reason to prefer that shape is
    that a reader can disagree with an arithmetic and cannot disagree with
    "$34 billion". So the check is not whether the number is right. It is
    whether the number can be argued with.
    """
    figures: List[Figure] = []
    caveats: List[str] = []

    # Market totals only. Filtering on the currency unit alone swept in every
    # per-unit price as well, and the live run duly reported "published totals
    # for this market disagree, from $774 to $400-3500" — comparing the average
    # wholesale invoice for one hearing aid against the price range for one
    # hearing aid, and calling both market sizes. A price and a total are the
    # same unit and differ by nine orders of magnitude.
    sizes = [f for f in findings
             if getattr(f, "value", None) is not None
             and str(getattr(f, "unit", "")).upper() in ("USD", "EUR", "GBP")
             and not _per_unit(str(getattr(f, "statement", "")))]

    # A spread between independent estimates is the finding, not a nuisance to
    # average away. Averaging is the one thing that must not happen here: the
    # mean of two definitions is a number describing no market at all.
    if len(sizes) >= 2:
        low = min(sizes, key=lambda f: abs(f.value))
        high = max(sizes, key=lambda f: abs(f.value))
        if abs(low.value) > 0 and abs(high.value) / abs(low.value) > 1.5:
            caveats.append(
                f"Published totals for this market disagree by more than half "
                f"again, from {low.value_text or low.value} to "
                f"{high.value_text or high.value}. In every case examined so "
                f"far a spread this wide came from the category boundary or "
                f"the price level rather than from measurement error, so the "
                f"useful question is what each publisher counted, not which "
                f"is correct. They are not averaged, deliberately: the mean of "
                f"two definitions describes no market.")

    # Assemble the arithmetic from whatever terms the run established, rather
    # than only complaining that none is shown. `sizing.py` has had COUNT x
    # RATE x VALUE since the beginning and nothing was feeding it; `terms.py`
    # sorts findings into the three factors so a reader gets the calculation
    # where it can be made, and the name of the missing factor where it cannot.
    from .terms import assemble, shortfall

    by_term = {"count": [], "rate": [], "value": []}
    for finding in findings:
        unit = str(getattr(finding, "unit", "")).upper()
        statement = str(getattr(finding, "statement", ""))
        if unit == "COUNT":
            by_term["count"].append(finding)
        elif unit == "%":
            by_term["rate"].append(finding)
        elif unit in ("USD", "EUR", "GBP") and _per_unit(statement):
            # Only PER-UNIT money is the value term. A market total is an
            # output of the arithmetic, not an input to it, and feeding one in
            # here would multiply a total by a count.
            by_term["value"].append(finding)

    ring, gaps = assemble(place or "worldwide", by_term)
    if ring.size is not None:
        figures.append(Figure(
            label="Market size, computed here",
            value=ring.size, value_text=f"${ring.size:,.0f}",
            unit="USD", state=DERIVED,
            operands=[t.kind for t in ring.terms if t.known],
            how=ring.arithmetic(),
            because="computed from the terms below, not quoted from a "
                    "publisher"))
    elif any(t.known for t in ring.terms):
        caveats.append(shortfall(ring, gaps))

    # The method sentence. A size with no arithmetic beside it is the exact
    # thing the corpus never does and the syndicated reports always do.
    shown = [f for f in panel.figures if f.state == DERIVED and f.operands]
    shown += [f for f in figures if f.state == DERIVED and f.operands]
    if sizes and not shown:
        caveats.append(
            "No figure here is shown with its arithmetic. Every filing in the "
            "corpus states a size as a count times a qualifying rate times a "
            "value per unit, with each term sourced, because that is what "
            "lets a reader disagree with it. Treat these as quoted totals "
            "rather than as a sizing this report performed.")

    # Only absent if nothing published one AND nothing could be computed. The
    # first version checked `sizes` alone, so a panel that had just derived
    # $2.04B from three sourced terms also carried a figure saying no total for
    # this market exists. Both statements were produced by the same function,
    # four lines apart.
    if not sizes and ring.size is None:
        figures.append(Figure(
            label="A total for this market",
            state=ABSENT,
            because="no source reached published a money total on the price "
                    "level this report is scoped to, and the terms needed to "
                    "compute one are not all established"))
    return {"figures": figures, "caveats": caveats}


MARKET_SIZE = register(Specialist(
    name="market-size",
    job="how large a market is in money, and by what arithmetic",
    dimension="price_level",
    seeds=(
        "How large is the {market} market in {place}, and at what price level "
        "is that total counted?",
        "How many units or customers are there in {market} in {place}, and who "
        "counts them?",
        "What does one unit of {market} cost in {place}, and is that a "
        "wholesale or a retail price?",
        "Which firms publish a {market} market size for {place}, and where do "
        "their totals disagree?",
    ),
    beats=("sizing", "sizing", "economics", "sizing"),
    refuse=(
        "Never state a size without the method sentence beside it. A reader "
        "can disagree with an arithmetic; they cannot disagree with '$34 "
        "billion'. Never average two published totals — where they disagree "
        "it is almost always because they drew the category boundary "
        "differently, and the mean of two definitions describes no market. "
        "Never fold an adjacent market into the headline number; size it "
        "separately with its own basis."),
    check=_size_check,
    iterations=14,
    answers=("Q2", "Q3"),
))


# ------------------------------------------------------------------ growth

def _growth_check(*, findings: Sequence[Any], panel: Panel, **_: Any
                  ) -> Dict[str, Any]:
    """A rate whose endpoints are not shown cannot be checked."""
    caveats: List[str] = []
    rates = [f for f in findings if "%" in str(getattr(f, "unit", ""))]
    endpoints = [f for f in findings
                 if getattr(f, "value", None) is not None
                 and str(getattr(f, "unit", "")).upper() in ("USD", "EUR", "GBP",
                                                             "COUNT")]
    if rates and len(endpoints) < 2:
        caveats.append(
            "A growth rate appears here without both of the values it was "
            "computed between. A CAGR with no visible endpoints cannot be "
            "reproduced and usually cannot be checked — treat it as the "
            "publisher's claim rather than as a measurement.")
    return {"figures": [], "caveats": caveats}


GROWTH = register(Specialist(
    name="growth",
    job="how fast a market is growing, between which years, and on whose "
        "forecast",
    dimension="period",
    seeds=(
        "How fast is the {market} market in {place} growing, between which two "
        "years, and what was the value at each?",
        "Who publishes a growth forecast for {market} in {place}, and what "
        "does it assume?",
        "Is {market} in {place} funded or reimbursed by a public programme "
        "that publishes its own projections?",
    ),
    beats=("sizing", "sizing", "regulation"),
    refuse=(
        "Never give a rate without both endpoints and both years. Name "
        "whoever produced any forecast — a projection is somebody's opinion "
        "and belongs to them. Where a public programme funds this market, its "
        "own published growth beats any analyst CAGR, and saying so is the "
        "finding. Do not extend a historical series forward yourself; a "
        "forecast this report invented is worse than no forecast."),
    check=_growth_check,
    iterations=10,
    answers=("Q4",),
))


#: Growth had a specialist and no report type, so `deckscope reports` did not
#: list it while `--report growth` ran it — the catalogue and the thing it
#: catalogues disagreeing about what exists. Registered here beside the
#: specialist so the two cannot drift apart again.
GROWTH_REPORT = register_type(ReportType(
    key="growth",
    title="Growth",
    answers="How fast a market is growing, between which two years, and on "
            "whose forecast — with both endpoints shown so the rate can be "
            "checked.",
    limits="Forward projections are the most consistently paywalled figure in "
           "this domain. History is free from government series; a forecast "
           "is reported only where somebody else published one, and is never "
           "extrapolated here.",
    basis="Two dated values and the rate between them. A CAGR whose endpoints "
          "are not shown cannot be reproduced.",
    sections=(
        Section(
            key="endpoints",
            title="The two points the rate is between",
            brief=("Establish the value of this market at the start and end "
                   "of the period, each with its own source and its own "
                   "date. The rate is derived from these, not quoted."),
            refuse="Never state a growth rate whose endpoints are not both "
                   "shown. A rate on its own cannot be checked and usually "
                   "cannot be reproduced.",
        ),
        Section(
            key="rate",
            title="The rate, and whose it is",
            brief=("State the growth rate between those years and name "
                   "whoever produced it. Where the figure is a forecast "
                   "rather than a measurement, say so in the same sentence."),
            needs=("endpoints",),
            refuse="A forecast is somebody's opinion and belongs to them. An "
                   "unattributed projection is not a finding.",
            paid="Multi-year forecasts are the most commonly paywalled "
                 "figure in this industry.",
            paid_source="IBISWorld, Gartner, IDC, Euromonitor",
        ),
        Section(
            key="drivers",
            title="What is actually moving it",
            brief=("What accounts for the change — more buyers, higher "
                   "prices, a regulatory opening, a replacement cycle? A rate "
                   "with no mechanism behind it cannot be judged for whether "
                   "it will continue."),
            needs=("rate",),
            refuse="Do not restate the rate as its own cause. 'Growing "
                   "because demand is growing' is not a driver.",
            required=False,
        ),
    ),
))


# -------------------------------------------------------------- regulation

def _regulation_check(*, findings: Sequence[Any], panel: Panel, **_: Any
                      ) -> Dict[str, Any]:
    """"Heavily regulated" is not a finding. A named instrument is."""
    caveats: List[str] = []
    vague = ("heavily regulated", "highly regulated", "strict regulation",
             "subject to regulation", "regulatory environment", "compliance "
             "requirements")
    for finding in findings:
        low = str(getattr(finding, "statement", "")).lower()
        if any(phrase in low for phrase in vague) and not any(
                word in low for word in ("act", "directive", "regulation no",
                                         "section", "rule", "statute",
                                         "title", "code", "law no")):
            caveats.append(
                f"One finding describes this market as regulated without "
                f"naming an instrument: \"{str(finding.statement)[:110]}\". "
                f"That is a impression, not a rule. A named statute, "
                f"directive or licence with its threshold is the only kind of "
                f"regulatory finding a reader can act on.")
            break
    return {"figures": [], "caveats": caveats}


REGULATION = register(Specialist(
    name="regulation",
    job="which rules govern a market, named specifically, with their "
        "thresholds",
    dimension="jurisdiction",
    seeds=(
        "Which statutes, directives or licences govern {market} in {place}, by "
        "name?",
        "Which regulator supervises {market} in {place}, and what does it "
        "publish?",
        "What thresholds apply in {market} in {place} — size, licence, "
        "certification — and who is exempt?",
        "What has changed recently in the rules governing {market} in "
        "{place}?",
    ),
    beats=("regulation", "regulation", "regulation", "regulation"),
    refuse=(
        "A named statute, directive, licence or regulator, or nothing. "
        "'Heavily regulated' is not a finding. Give thresholds where they "
        "exist, because the threshold is the part people miss and the part "
        "that decides whether a rule applies to them at all. Name exemptions "
        "with the rules they exempt from. Do not generalise one country's "
        "rules to another — this report covers one jurisdiction and says so."),
    check=_regulation_check,
    iterations=12,
    answers=("Q8",),
))


# ---------------------------------------------------- competitive landscape

def _landscape_check(*, findings: Sequence[Any], panel: Panel, **_: Any
                     ) -> Dict[str, Any]:
    """Barriers are reasoned, not measured, and must be marked as such."""
    caveats: List[str] = []
    if any("barrier" in str(getattr(f, "statement", "")).lower()
           for f in findings):
        caveats.append(
            "Barriers to entry here are an argument built from sourced facts "
            "— capital requirements, licensing, distribution control — not a "
            "measurement. Read the facts underneath and judge the argument "
            "yourself; nobody publishes a barrier-to-entry number.")
    return {"figures": [], "caveats": caveats}


COMPETITIVE_LANDSCAPE = register(Specialist(
    name="competitive-landscape",
    job="who competes in a market, what stops a newcomer entering, and what "
        "substitutes for it",
    dimension="basis",
    seeds=(
        "Who are the participants in {market} in {place}, and is the list "
        "stable or consolidating?",
        "What does it take to enter {market} in {place} — capital, licences, "
        "distribution, scale?",
        "What substitutes for {market} in {place}, and is substitution "
        "growing?",
        "Have there been recent acquisitions or exits in {market} in {place}?",
    ),
    beats=("competitors", "failure", "competitors", "company"),
    refuse=(
        "Name participants individually; 'fragmented' and 'consolidated' are "
        "conclusions, not evidence. A barrier to entry needs a fact behind it "
        "— a capital figure, a licence, an exclusive distribution "
        "arrangement — not an assertion that the market is hard. Substitutes "
        "depend entirely on where the market boundary was drawn, so restate "
        "the boundary before naming any. A pending acquisition that would "
        "change the participant list outranks any share figure, because it "
        "invalidates the list rather than adding to it."),
    check=_landscape_check,
    iterations=12,
    answers=("Q9",),
))


# ------------------------------------------------------------ demographics

def _demographics_check(*, findings: Sequence[Any], panel: Panel, **_: Any
                        ) -> Dict[str, Any]:
    """Self-reported and observed populations differ, and in a known direction."""
    caveats: List[str] = []
    surveyed = [f for f in findings
                if any(word in str(getattr(f, "statement", "")).lower()
                       for word in ("survey", "self-reported", "respondents",
                                    "polled", "asked"))]
    if surveyed:
        caveats.append(
            f"{len(surveyed)} finding(s) here come from people being asked "
            f"rather than from people being counted. Self-reported behaviour "
            f"differs from observed behaviour systematically, not randomly — "
            f"respondents overstate socially approved activity and understate "
            f"the rest — so these are not interchangeable with a census or a "
            f"transaction count.")
    return {"figures": [], "caveats": caveats}


DEMOGRAPHICS = register(Specialist(
    name="demographics",
    job="who the customers in a market are, and how they were counted",
    dimension="population",
    seeds=(
        "Who buys {market} in {place} — age, income, household type — and "
        "which source counted them?",
        "How many people in {place} are eligible for {market}, and how many "
        "actually participate?",
        "How is the customer base for {market} in {place} changing?",
    ),
    beats=("demand", "demand", "demand"),
    refuse=(
        "Say who was counted and how. A count of buyers, a count of users and "
        "a count of everyone eligible are three different numbers and the "
        "largest is routinely quoted as though it were the smallest. Never "
        "present an eligibility count as demand — the gap between eligible "
        "and participating is usually the whole story, so state it. Keep "
        "self-reported and observed figures apart."),
    check=_demographics_check,
    iterations=10,
))
