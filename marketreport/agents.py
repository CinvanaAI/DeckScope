"""The agents that answer the retrieved questions.

One agent per question, each with a different slice of context and, more
importantly, a different set of denials. See AGENTS.md for the table of what
each is given and what it is refused, and why the refusals do more work than
the grants.

Every one of these refuses rather than degrades. An agent that cannot answer
returns an `Answer` carrying the reason, and that reason reaches the reader in
the section where it matters — not a footnote, because somebody deciding
something needs to know which part of the answer is thin.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .questions import COMPUTED, RETRIEVED, SUPPLIED, Answer, StandingQuestion
from .report import MarketDefinition, register, unanswered
from .sizing import Ring, Sizing, Term
from .sources.census import (CBP_YEAR, ECN_YEAR, Unavailable,
                             establishment_count, revenue_per_establishment)
from . import fixtures
from .structure import cagr as compound_rate, from_size_bands, shape

#: CBP employee-size bands, in the order the API returns them.
SIZE_BANDS = ("1-4", "5-9", "10-19", "20-49", "50-99",
              "100-249", "250-499", "500-999", "1000+")


# --------------------------------------------------------------- Q1 framing

@register("framing")
def framing(*, market: MarketDefinition, question: StandingQuestion,
            seen: Dict[str, Optional[Answer]]) -> Answer:
    """Restate the boundary the user supplied, and refuse a useless one.

    Supplied rather than inferred, on purpose. This agent is denied any market
    size precisely so the boundary cannot be adjusted after somebody sees a
    number they like.
    """
    if not market.label:
        return unanswered(question, "no market was named")
    if not market.usable_naics:
        return unanswered(
            question,
            f"a 4-6 digit NAICS industry code is required and "
            f"{market.naics or 'none'} was supplied. A 1-3 digit code is a "
            f"whole economic sector — every count taken against it would be "
            f"about a different market while looking authoritative.")

    if market.demo and not fixtures.covered(market.naics):
        return unanswered(
            question,
            f"the offline demo has no recorded data for NAICS {market.naics}. "
            f"It covers 561730 (landscaping services). Run without --demo and "
            f"with a Census key for any other industry.")

    parts = [f"{market.label} (NAICS {market.naics})",
             f"in {market.geography_label}"]
    if market.customer:
        parts.append(f"serving {market.customer}")
    if market.demo:
        parts.append("ILLUSTRATIVE DEMO — figures are recorded samples, not "
                     "measurements")
    return Answer(
        question_id=question.id, kind=SUPPLIED,
        statement=", ".join(parts) + ".",
        confidence="high", detail=market.to_dict(), demo=market.demo)


# ------------------------------------------------------- Q2 / Q3 the sizes

@register("sizing-bu")
def sizing_bottom_up(*, market: MarketDefinition, question: StandingQuestion,
                     seen: Dict[str, Optional[Answer]]) -> Answer:
    """Count units and multiply. The method every filing in the corpus used.

    Establishments from County Business Patterns, revenue per establishment
    from the Economic Census. Note what that makes the number: **the industry's
    measured revenue**, not one company's addressable opportunity. Every filing
    surveyed used its own realized revenue for the second, which no outside
    party can source — so we answer the question we can answer and say which
    one it is.
    """
    sizing = Sizing(
        market.label,
        basis="bottom-up: establishment counts x industry average revenue per "
              "establishment. Measures the industry's revenue, not one firm's "
              "opportunity")

    rings: List[Ring] = []
    problems: List[str] = []

    def count(**geo) -> Optional[Term]:
        if market.demo:
            return _demo_count(market.naics, **geo)
        try:
            return establishment_count(market.naics, year=CBP_YEAR, **geo)
        except Unavailable as exc:
            problems.append(str(exc))
            return None

    def value(**geo) -> Optional[Term]:
        if market.demo:
            return _demo_value(market.naics, **geo)
        try:
            return revenue_per_establishment(market.naics, year=ECN_YEAR, **geo)
        except Unavailable as exc:
            problems.append(str(exc))
            return None

    national_count, national_value = count(), value()
    if national_count and national_value:
        rings.append(Ring(label="United States", count=national_count,
                          value=national_value))

    if market.state_fips:
        state_count = count(state_fips=market.state_fips)
        state_value = value(state_fips=market.state_fips) or national_value
        if state_count and state_value:
            rings.append(Ring(label=market.geography_label
                              if not market.county_fips else
                              f"state {market.state_fips}",
                              count=state_count, value=state_value))
        if market.county_fips and state_value:
            county_count = count(state_fips=market.state_fips,
                                 county_fips=market.county_fips)
            if county_count:
                rings.append(Ring(
                    label=market.geography_label,
                    count=county_count,
                    value=Term(kind="value", value=state_value.value,
                               unit=state_value.unit, as_of=state_value.as_of,
                               source=state_value.source,
                               source_url=state_value.source_url,
                               method="derived",
                               note="the state average applied at county level; "
                                    "the Economic Census suppresses county "
                                    "receipts for most industries, so this is "
                                    "reasonable and is not measured")))

    for ring in rings:
        sizing.add(ring)

    if sizing.headline is None:
        return unanswered(
            question,
            problems[0] if problems else
            "no establishment count or industry revenue could be retrieved")

    # The headline is the geography the USER asked about, not the widest one
    # we happen to have. A report requested for Maricopa County that leads with
    # the national figure has answered a question nobody asked, and the number
    # it leads with is the one that gets quoted.
    focus = sizing.rings[-1]
    wider = sizing.rings[0] if len(sizing.rings) > 1 else None
    headline = focus.size

    statement = (f"Counted from the ground up, {market.label} in "
                 f"{market.geography_label} is {_money(headline)}.")
    if wider is not None and wider.size:
        statement += (f" That is {headline / wider.size * 100:.1f}% of the "
                      f"{_money(wider.size)} national total.")
    if market.demo:
        statement += f" ({fixtures.DEMO_NOTE})"

    return Answer(
        question_id=question.id, kind=RETRIEVED,
        statement=statement,
        value=headline, value_text=_money(headline), unit="USD",
        as_of=str(ECN_YEAR),
        confidence="medium" if not problems else "low", demo=market.demo,
        source_ids=[t.source for r in sizing.rings for t in r.terms if t.sourced],
        detail={"sizing": sizing.to_dict(), "rings": len(sizing.rings),
                "arithmetic": [r.arithmetic() for r in sizing.rings],
                # Operand-level lineage, so the convergence check (Q12) can
                # tell independent evidence from correlated arithmetic. The
                # focus ring multiplies the LOCAL establishment count by a
                # per-establishment average whose scope depends on which
                # rings resolved.
                "material_operands": sorted({
                    f"establishments:local:CBP{CBP_YEAR}",
                    ("avg_revenue:state:ECN%d" % ECN_YEAR)
                    if len(sizing.rings) > 1 else
                    ("avg_revenue:national:ECN%d" % ECN_YEAR)}),
                "problems": problems})


@register("sizing-td")
def sizing_top_down(*, market: MarketDefinition, question: StandingQuestion,
                    seen: Dict[str, Optional[Answer]]) -> Answer:
    """Start from a national aggregate and narrow to the geography.

    **What this figure honestly is — an external audit did the algebra.** The
    national total here is CONSTRUCTED as per-establishment average x national
    establishment count, and apportioning by the local share of establishments
    cancels the national count straight back out:

        avg x national_est x (local_est / national_est)  =  avg x local_est

    So this figure is the local establishment count times the NATIONAL
    per-establishment average, and the bottom-up figure is the same local
    count times the STATE average. They share a material operand — the local
    count — and their comparison is therefore a national-vs-state average
    sensitivity check, NOT independent corroboration. The convergence agent
    (Q12) reads the operand lineage recorded on both answers and says exactly
    that; an earlier version of this docstring claimed the opposite, and the
    claim did not survive the algebra.

    Blind execution (this agent never sees the bottom-up answer) still
    prevents conversational anchoring; it cannot make shared operands
    independent. A directly PUBLISHED national receipts total would improve
    this — the average would drop out of the lineage — but apportionment by
    establishments would still share the local count. Genuine independence
    needs a second method with disjoint operands (e.g. customers x
    independently sourced spend), which is future work recorded in BUILD.md.
    """
    if market.demo:
        national_receipts = (fixtures.revenue(market.naics, "")
                             * fixtures.count(market.naics))
        national_estabs = fixtures.count(market.naics)
        local_estabs = fixtures.count(market.naics, market.state_fips,
                                      market.county_fips)
        source = f"Economic Census {ECN_YEAR} (demo)"
    else:
        try:
            per = revenue_per_establishment(market.naics, year=ECN_YEAR)
            national = establishment_count(market.naics, year=CBP_YEAR)
        except Unavailable as exc:
            return unanswered(question, str(exc))
        national_receipts = (per.value or 0) * (national.value or 0)
        national_estabs = int(national.value or 0)
        source = per.source
        geo: Dict[str, str] = {}
        if market.state_fips:
            geo["state_fips"] = market.state_fips
        if market.county_fips:
            geo["county_fips"] = market.county_fips
        if geo:
            try:
                local_estabs = int(
                    (establishment_count(market.naics, year=CBP_YEAR,
                                         **geo).value or 0))
            except Unavailable as exc:
                return unanswered(question, str(exc))
        else:
            local_estabs = national_estabs

    if not national_receipts or not national_estabs:
        return unanswered(question, "no national receipts total could be "
                                    "retrieved to narrow")

    share = (local_estabs / national_estabs) if national_estabs else 0.0
    size = national_receipts * share

    statement = (f"Starting from the {_money(national_receipts)} national total "
                 f"for {market.label} and apportioning it by "
                 f"{market.geography_label}'s {share * 100:.2f}% share of "
                 f"establishments gives {_money(size)}. Because the national "
                 f"total is itself built from a per-establishment average, "
                 f"this reduces to the local establishment count times the "
                 f"national average — so where it differs from the bottom-up "
                 f"figure, the difference measures how local establishments "
                 f"depart from national size, and where the two agree, that "
                 f"is a sensitivity check on the averages, not independent "
                 f"corroboration (the local count is shared).")
    if market.demo:
        statement += f" ({fixtures.DEMO_NOTE})"

    return Answer(
        question_id=question.id, kind=RETRIEVED, statement=statement,
        value=size, value_text=_money(size), unit="USD", as_of=str(ECN_YEAR),
        confidence="low" if market.demo else "medium", demo=market.demo,
        source_ids=[] if market.demo else [source],
        detail={"national_receipts": national_receipts,
                "national_establishments": national_estabs,
                "local_establishments": local_estabs,
                # After cancellation, the material operands are the local
                # count and the NATIONAL average — the national count drops
                # out of the algebra (see this agent's docstring).
                "material_operands": sorted({
                    f"establishments:local:CBP{CBP_YEAR}",
                    f"avg_revenue:national:ECN{ECN_YEAR}"}),
                "establishment_share": share,
                "assumption": "local establishments are of national average size",
                "demo": market.demo})


# ------------------------------------------------------------ Q5 structure

@register("structure")
def structure(*, market: MarketDefinition, question: StandingQuestion,
              seen: Dict[str, Optional[Answer]]) -> Answer:
    """Concentration, computed from establishment counts by size band.

    Arithmetic with published thresholds, so no model touches it. A model asked
    to consider the concentration of a market returns a plausible adjective;
    `sum(share ** 2)` returns a number the reader can check against the
    DOJ/FTC guidelines.
    """
    geo: Dict[str, str] = {}
    if market.state_fips:
        geo["state_fips"] = market.state_fips
    if market.county_fips:
        geo["county_fips"] = market.county_fips

    bands: Dict[str, int] = {}
    problems: List[str] = []
    for band in SIZE_BANDS:
        if market.demo:
            got = fixtures.count(market.naics, geo.get("state_fips", ""),
                                 geo.get("county_fips", ""), band)
            if got:
                bands[band] = got
            continue
        try:
            term = establishment_count(market.naics, year=CBP_YEAR,
                                       size_band=band, **geo)
        except Unavailable as exc:
            problems.append(str(exc))
            break
        if term.value:
            bands[band] = int(term.value)

    if not bands:
        return unanswered(
            question,
            problems[0] if problems else
            "County Business Patterns returned no size-band detail for this "
            "industry and geography, which it suppresses for small areas to "
            "protect individual businesses")

    conc = from_size_bands(bands)
    if conc.hhi is None:
        return unanswered(question, conc.because or conc.caveat)

    # HHI alone is close to useless here and the critique was right about it:
    # every real trade lands far below the threshold and reads
    # "unconcentrated", and it cannot tell 1,422 sole traders from 1,422 large
    # firms because it measures share EQUALITY, not scale. So the shape
    # measures run alongside it and carry the reading when HHI cannot.
    national_bands: Dict[str, int] = {}
    if market.demo:
        for band in SIZE_BANDS:
            got = fixtures.count(market.naics, "", "", band)
            if got:
                national_bands[band] = got
        local_pop = fixtures.population(market.state_fips, market.county_fips)
        national_pop = fixtures.population()
    else:
        # Population needs the American Community Survey, which is not wired
        # up. The density measure is simply absent rather than estimated.
        local_pop = national_pop = 0

    form = shape(bands, population=local_pop or None,
                 national_bands=national_bands or None,
                 national_population=national_pop or None)

    statement = (f"In {market.geography_label}, {market.label} is "
                 f"{conc.reading} — {conc.because}. "
                 f"The largest four hold about "
                 f"{(conc.cr4 or 0) * 100:.0f}% between them, across "
                 f"{conc.firms:,} establishments.")
    if form.reading:
        statement += (f" More usefully for a market this fragmented, it is "
                      f"{form.reading}: {form.because}.")
    statement += f" Concentration is estimated, not measured: {conc.caveat}"

    return Answer(
        question_id=question.id, kind=COMPUTED, statement=statement,
        value=conc.hhi, value_text=f"HHI {conc.hhi:,.0f}", unit="HHI",
        as_of=str(CBP_YEAR), confidence="medium", demo=market.demo,
        detail={"concentration": conc.to_dict(), "size_bands": bands,
                "shape": form.to_dict()})


# ------------------------------------------------------------- Q4 growth

@register("growth")
def growth(*, market: MarketDefinition, question: StandingQuestion,
           seen: Dict[str, Optional[Answer]]) -> Answer:
    """Growth from two vintages of the same series.

    Not built. The honest way to do it is to read the same official series at
    two dates and compute the change — which needs vintage-addressable access to
    CBP, and is a real piece of work rather than a lookup.

    What it must not do is take a CAGR from an analyst report. agilon applied
    CMS's own published growth rates and footnoted them; a filer's forecast is
    not a market forecast, and neither is a vendor's.
    """
    if not market.demo:
        return unanswered(
            question,
            "growth needs the same official series read at two vintages, and "
            "only the current one is wired up. An analyst CAGR would be "
            "available and is refused: a projection published by somebody "
            "selling into this market is not a measurement of it.")

    now = fixtures.count(market.naics, market.state_fips, market.county_fips)
    then = fixtures.prior_count(market.naics, market.state_fips,
                                market.county_fips)
    if not now or not then:
        return unanswered(question, "no earlier vintage is recorded for this "
                                    "industry and geography")

    years = CBP_YEAR - fixtures.PRIOR_YEAR
    rate = compound_rate(then, now, years)
    if rate is None:
        return unanswered(question, "the two vintages do not span a usable "
                                    "period")
    cagr = rate
    return Answer(
        question_id=question.id, kind=RETRIEVED,
        statement=(f"In {market.geography_label}, establishments grew from "
                   f"{then:,} in "
                   f"{fixtures.PRIOR_YEAR} to {now:,} in {CBP_YEAR}, a "
                   f"compound rate of {cagr * 100:.1f}% a year. This is growth "
                   f"in the NUMBER OF FIRMS, not in revenue — the two can move "
                   f"in opposite directions when a market consolidates. "
                   f"({fixtures.DEMO_NOTE})"),
        value=cagr, value_text=f"{cagr * 100:.1f}%/yr", unit="%",
        as_of=str(CBP_YEAR), confidence="medium", demo=True,
        source_ids=[f"County Business Patterns {fixtures.PRIOR_YEAR} and "
                    f"{CBP_YEAR}"],
        detail={"prior_year": fixtures.PRIOR_YEAR, "prior_count": then,
                "current_year": CBP_YEAR, "current_count": now,
                "basis": "establishment count, not revenue",
                "demo": True})


# ---------------------------------------------------------- Q6 competitors

@register("competitors")
def competitors(*, market: MarketDefinition, question: StandingQuestion,
                seen: Dict[str, Optional[Answer]]) -> Answer:
    """Who is actually in this market.

    Not built. Denied market-size findings on purpose — a large number is not
    evidence about who is in a market, and letting the two mix is how a deck's
    framing survives a research pass.
    """
    if not market.demo:
        return unanswered(
            question,
            "no competitor source is wired up yet. EDGAR full-text search over "
            "SIC codes and state licensing registries are the two free routes; "
            "neither is built.")

    named = fixtures.PARTICIPANTS.get(market.naics) or []
    if not named:
        return unanswered(question, "the demo records no participants for this "
                                    "industry")
    lines = "; ".join(f"{p['name']} ({p['note']})" for p in named)
    return Answer(
        question_id=question.id, kind=RETRIEVED,
        statement=(f"Named participants: {lines}. These are the firms large "
                   f"enough to be publicly visible; the establishment count "
                   f"shows the market is mostly firms too small to name "
                   f"individually. ({fixtures.DEMO_NOTE})"),
        confidence="medium", as_of=str(CBP_YEAR), demo=True,
        source_ids=["SEC EDGAR", "public filings"],
        detail={"participants": named, "demo": True})


# ------------------------------------------------------------ Q7 economics

@register("economics")
def economics(*, market: MarketDefinition, question: StandingQuestion,
              seen: Dict[str, Optional[Answer]]) -> Answer:
    """What it costs to operate: revenue and payroll per establishment.

    Both come from data already retrieved for the sizing, so this is close to
    free. What it deliberately cannot give is a startup cost — that is a
    different quantity, it is not published by industry, and inferring it from
    operating figures would be exactly the unit mismatch the comparison layer
    exists to catch.
    """
    geo: Dict[str, str] = {}
    if market.state_fips:
        geo["state_fips"] = market.state_fips

    if market.demo:
        per_establishment = _demo_value(market.naics, **geo)
        if per_establishment is None:
            return unanswered(question, "the demo has no revenue figure for "
                                        "this industry")
    else:
        try:
            per_establishment = revenue_per_establishment(
                market.naics, year=ECN_YEAR, **geo)
        except Unavailable as exc:
            return unanswered(question, str(exc))

    detail: Dict[str, Any] = {
        "revenue_per_establishment": per_establishment.value,
        "as_of": per_establishment.as_of,
        "source": per_establishment.source,
        # Named rather than left absent, because the barriers agent reads this
        # key and a silent None there would grade barriers on two signals while
        # appearing to use three.
        "startup_cost": None,
        "startup_cost_note":
            "not established. Startup capital is not published by industry, and "
            "deriving it from operating revenue would compare two different "
            "quantities.",
    }

    counts = (_demo_count(market.naics, **geo) if market.demo else None)
    if counts is None and not market.demo:
        try:
            counts = establishment_count(market.naics, year=CBP_YEAR, **geo)
        except Unavailable:
            counts = None
    if counts is not None and counts.value:
        detail["establishments"] = int(counts.value)

    return Answer(
        question_id=question.id, kind=RETRIEVED,
        statement=(f"The average establishment in {market.label} takes in about "
                   f"{_money(per_establishment.value)} a year "
                   f"({per_establishment.source}, {per_establishment.as_of}). "
                   f"What it costs to *start* is not established — that figure "
                   f"is not published by industry."),
        value=per_establishment.value,
        value_text=_money(per_establishment.value),
        unit="$ per establishment per year", as_of=per_establishment.as_of,
        confidence="medium", source_ids=[per_establishment.source],
        demo=market.demo, detail=detail)


# ----------------------------------------------------------- Q8 regulation

@register("regulation")
def regulation(*, market: MarketDefinition, question: StandingQuestion,
               seen: Dict[str, Optional[Answer]]) -> Answer:
    """Licences, permits and thresholds.

    Not built. This is the section where a missing exemption threshold changes
    whether a business is legal to start, so a half-answer is worse here than
    anywhere else in the report.
    """
    if not market.demo:
        return unanswered(
            question,
            "no licensing source is wired up yet. State licensing registries "
            "are the right route and are per-state, which makes this real work "
            "rather than a lookup.")

    rules = fixtures.LICENSING.get(market.state_fips)
    if not rules:
        return unanswered(
            question,
            f"the demo records no licensing rules for state "
            f"{market.state_fips or '(none given)'}. Licensing is per-state, "
            f"so a national answer to this question does not exist.")

    return Answer(
        question_id=question.id, kind=RETRIEVED,
        statement=(f"{rules['note']}. The threshold is {rules['threshold']}, "
                   f"administered by the {rules['body']}. The threshold is the "
                   f"part that decides whether a small operator needs the "
                   f"licence at all. ({fixtures.DEMO_NOTE})"),
        confidence="medium", as_of=str(CBP_YEAR), demo=True,
        source_ids=[rules["body"]],
        detail={"licence_count": rules["count"],
                "licence_note": rules["note"],
                "threshold": rules["threshold"], "demo": True})


def _money(value: Optional[float]) -> str:
    if value is None:
        return "not established"
    for cut, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= cut:
            return f"${value / cut:,.1f}{suffix}"
    return f"${value:,.0f}"


# ------------------------------------------------------------ demo helpers
#
# These return the same `Term` shape the live backends do, so the demo path
# exercises the real assembly rather than a parallel one. Every Term carries the
# demo marker in its note, which is how the label survives all the way to the
# rendered page instead of living only in the caller's head.

def _demo_count(naics: str, *, state_fips: str = "",
                county_fips: str = "") -> Optional[Term]:
    total = fixtures.count(naics, state_fips, county_fips)
    if not total:
        return None
    return Term(kind="count", value=float(total), unit="establishments",
                as_of=str(CBP_YEAR),
                source=f"County Business Patterns {CBP_YEAR} (demo)",
                method="measured", note=fixtures.DEMO_NOTE)


def _demo_value(naics: str, *, state_fips: str = "",
                county_fips: str = "") -> Optional[Term]:
    per = fixtures.revenue(naics, state_fips)
    if not per:
        return None
    return Term(kind="value", value=per,
                unit="$ per establishment per year", as_of=str(ECN_YEAR),
                source=f"Economic Census {ECN_YEAR} (demo)", method="measured",
                note="industry average revenue per establishment — this makes "
                     "the total the INDUSTRY's revenue, not one firm's "
                     f"addressable opportunity. {fixtures.DEMO_NOTE}")
