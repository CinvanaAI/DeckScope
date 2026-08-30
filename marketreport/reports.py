"""Report types — the menu the user picks from.

The client's correction, and he was right: the job is not to reproduce anybody's
product. It is to notice which reports we can actually build from public
sources, build those, and put them in front of the user to choose from.

So this is a registry, not an architecture. **A report type is a name and a
list of section briefs.** Adding one is about twenty lines. That is the whole
design, and the reason it took so long to arrive at is that I kept trying to
derive the taxonomy from first principles instead of writing down the reports
that are obviously useful.

Every section becomes a `Panel` — a question, answered, carrying the shape it
should be drawn in and the provenance of every figure. That machinery already
exists and does not care which report a section belongs to.

What each type owes the reader, and what the code enforces:

- **a brief per section**, not a question list, so the agent can ask what the
  evidence turns out to require rather than what I guessed in advance
- **a refusal per section** — the specific way this section goes wrong
- **an honest upgrade slot** where a paid source would genuinely sharpen it,
  shown only when that section actually came back thin
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from .panel import Panel, unanswered

__all__ = ["Section", "ReportType", "register", "get", "registered",
           "build_report"]


@dataclass
class Section:
    """One part of a report, and what it owes the reader."""

    key: str
    title: str
    #: What this section must establish, in plain words. A brief, not a
    #: question — the questions worth asking depend on what the first answers
    #: turn up, and a fixed list cannot be surprised.
    brief: str
    #: Sections this one reads first.
    needs: Sequence[str] = ()
    #: The specific way this section goes wrong.
    refuse: str = ""
    #: Where the evidence for this typically lives. A hint to the agent, not a
    #: restriction — naming the usual home of an answer saves a search without
    #: forbidding a better one.
    sources: str = ""
    #: What a paid subscription would add, and which one. Shown only when the
    #: section came back thin.
    paid: str = ""
    paid_source: str = ""
    #: How consistently this appears in the real documents this type imitates,
    #: where that was checked. Empty where it was not.
    corpus: str = ""
    required: bool = True


@dataclass
class ReportType:
    """One kind of report: a name, who it is for, and its sections."""

    key: str
    title: str
    #: One sentence a user picks from. Written for the person choosing, not for
    #: the developer — this is menu text.
    answers: str
    sections: Sequence[Section] = ()
    #: What this type is honestly bad at. Shown alongside the offer, because a
    #: menu that only lists strengths teaches nothing about which item to pick.
    limits: str = ""
    #: Where the structure came from.
    basis: str = ""

    def order(self) -> List[Section]:
        """Sections in dependency order, declared order preserved.

        A section whose inputs are missing still runs — it runs without them
        and says so. Holding it back turns one thin section into a cascade of
        silences, which is how a report comes to read as though the data does
        not exist when only one part of it was hard.
        """
        done: List[Section] = []
        seen: set = set()
        remaining = list(self.sections)
        while remaining:
            progressed = False
            for candidate in list(remaining):
                if all(n in seen for n in candidate.needs):
                    done.append(candidate)
                    seen.add(candidate.key)
                    remaining.remove(candidate)
                    progressed = True
            if not progressed:
                done.extend(remaining)
                break
        return done


_TYPES: Dict[str, ReportType] = {}


def register(report: ReportType) -> ReportType:
    _TYPES[report.key] = report
    return report


_LOADED = False


def _load_all() -> None:
    """Import the modules that register the rest of the report types.

    Without this the registry answered differently depending on what else the
    caller had already imported: a fresh process saw five types, and the CLI
    saw seven, because `growth` is registered by `catalog` and `industry-report`
    by `s1`, and neither had a reason to be loaded. Same function, same
    process, two different answers about what this software can produce.

    That is worse than a missing type. Anything that lists capabilities — the
    CLI, the web UI, a test asserting the catalogue matches the agents — was
    reporting whichever subset its own import graph happened to pull in, and
    every one of them looked correct.
    """
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from . import catalog, s1  # noqa: F401 - imported for their registrations


def get(key: str) -> Optional[ReportType]:
    _load_all()
    return _TYPES.get((key or "").strip().lower())


def registered() -> List[ReportType]:
    _load_all()
    return [_TYPES[k] for k in sorted(_TYPES)]


# ===================================================================== types

register(ReportType(
    key="market-share",
    title="Market share",
    answers="Who holds what share of a market, by units and by revenue, and "
            "how those two disagree.",
    limits="Country-level and segment-level share is usually paywalled. Where "
           "only a usage or installed-base proxy is public, that is what you "
           "get, labelled as such.",
    basis="The shape of the answer I produced by hand for cell phones, which "
          "found that units and revenue rank the market differently.",
    sections=(
        Section(
            key="boundary",
            title="Which market this is",
            brief=("Establish what market is meant before measuring it. Where "
                   "a name covers several markets — 'cell phones' can mean "
                   "handset makers or network operators — give each reading "
                   "and say who is in it."),
            refuse="Never settle an ambiguous market silently. A report about "
                   "the wrong market is internally consistent and "
                   "undetectably wrong.",
            sources="trade press, industry associations, the trackers' own "
                    "category definitions",
        ),
        Section(
            key="units",
            title="Share by units",
            brief=("Who ships or sells the most, as a percentage, from one "
                   "tracker. Name the tracker and the period. If the source "
                   "only breaks out the top few, say what the remainder is."),
            needs=("boundary",),
            refuse="Never blend two trackers into one series. They model the "
                   "market differently and blending averages two independent "
                   "estimates into a chart claiming to be one of them.",
            sources="IDC, Counterpoint, Canalys press releases; trade press "
                    "reporting on them",
            paid="Country and segment breakdowns are behind the paywall; the "
                 "free tier is usually global and top-five only.",
            paid_source="Counterpoint, IDC, Canalys",
        ),
        Section(
            key="revenue",
            title="Share by revenue",
            brief=("Who takes the most money, as a percentage. This is a "
                   "different question from units and the answer is often a "
                   "different company — that gap is usually the finding."),
            needs=("boundary",),
            refuse="Do not present a usage share or installed-base share as a "
                   "revenue share. They measure different populations.",
            sources="the same trackers' revenue releases; company filings for "
                    "the listed players",
        ),
        Section(
            key="why",
            title="Why the two differ",
            brief=("If units and revenue rank the market differently, explain "
                   "what causes it — price mix, segment position, input "
                   "costs. State the ratio between a player's revenue share "
                   "and its unit share."),
            needs=("units", "revenue"),
            refuse="Only write this section if the two series actually "
                   "disagree. Manufacturing a difference to have something to "
                   "say is worse than saying they agree.",
            required=False,
        ),
    ),
))


register(ReportType(
    key="market-size",
    title="Market size",
    answers="How big a market is in money and units, and exactly how that "
            "number was calculated.",
    limits="The per-unit VALUE term is proprietary in every filing examined. "
           "Where it cannot be sourced, an industry average is substituted "
           "and the report says what that makes the number mean.",
    basis="COUNT x RATE x VALUE — the formula all five filings in "
          "market-corpus use, without exception.",
    sections=(
        Section(
            key="boundary",
            title="Which market this is",
            brief=("What is inside this market and what is outside — which "
                   "activities, which customers, which geographies. The "
                   "boundary decides every number after it."),
            refuse="Do not define the market after seeing a size figure. That "
                   "is how a boundary gets drawn to fit a number.",
            corpus="3/3 filings state this explicitly",
        ),
        Section(
            key="count",
            title="How many units there are",
            brief=("The base population — businesses, people, households, "
                   "beneficiaries. This is almost always free government "
                   "data. Klaviyo paid two vendors for a business count "
                   "County Business Patterns publishes for nothing."),
            needs=("boundary",),
            refuse="Do not accept a vendor's count when a statistical agency "
                   "publishes one. Cite the agency.",
            sources="County Business Patterns, Economic Census, BLS, ACS, "
                    "CMS, Eurostat, national statistics offices",
            corpus="5/5 — the count comes from government data every time",
        ),
        Section(
            key="rate",
            title="What share of them qualify",
            brief=("The filter that turns the base population into the actual "
                   "market — FIGS: '~85% of medical professionals now buy "
                   "their own uniforms'. This is where a commissioned survey "
                   "earns its fee."),
            needs=("count",),
            refuse="If no published incidence exists, say so and state the "
                   "assumption with a range. Never present an assumed rate as "
                   "a measured one.",
            sources="behavioural surveys, trade association statistics, "
                    "government expenditure surveys",
            paid="The qualifying rate is one of the two terms a commissioned "
                 "study is actually bought for.",
            paid_source="Frost & Sullivan, Euromonitor, Mintel",
        ),
        Section(
            key="value",
            title="What each one is worth per year",
            brief=("Revenue per unit per year. In every filing examined this "
                   "came from the filer's own books — 'our average ARR per "
                   "customer', '$10,000 per member to us'. There is no 'us' "
                   "in a standalone report, so use the industry average "
                   "revenue per establishment and say what that changes."),
            needs=("count",),
            refuse="Never present an industry average as a company's "
                   "opportunity. It answers 'how big is this industry', not "
                   "'how big is your slice'.",
            sources="Economic Census receipts, CMS spend per beneficiary, "
                    "Consumer Expenditure Survey",
            paid="The per-unit value is the other term a commissioned study "
                 "is bought for, and the one nobody publishes.",
            paid_source="Frost & Sullivan, IBISWorld, Euromonitor",
            corpus="5/5 — proprietary in every single filing",
        ),
        Section(
            key="total",
            title="The market size, with its arithmetic",
            brief=("Multiply the three terms and show the multiplication. "
                   "Every filing follows its size claim with the method "
                   "sentence. A reader can disagree with an arithmetic; they "
                   "cannot disagree with a number."),
            needs=("count", "rate", "value"),
            refuse="Never state a size without the operands beside it.",
            corpus="3/3 — never a bare number",
        ),
        Section(
            key="rings",
            title="The same market, narrowed geographically",
            brief=("Size it again at each level — national, regional, local — "
                   "each with its own count rather than a scaled-down "
                   "version of the one above."),
            needs=("total",),
            refuse="Do not scale a national figure by population share unless "
                   "no local count exists, and say so when you do.",
            corpus="1/5 — only agilon, and it is the best thing in the corpus",
            required=False,
        ),
    ),
))


register(ReportType(
    key="demographics",
    title="Who the customers are",
    answers="The age, income, location and behaviour of the people who buy or "
            "use something — with the survey behind each figure named.",
    limits="Behavioural detail about a specific product is usually a paid "
           "panel. Public sources give population structure and broad "
           "category behaviour well, and product-level usage weakly.",
    basis="Census and national statistics publish population structure for "
          "free; the gap is always behaviour, not demography.",
    sections=(
        Section(
            key="population",
            title="The population this is drawn from",
            brief=("Define whose demographics these are — everyone in a "
                   "country, users of a category, buyers of a product — and "
                   "give the size of that base from an official count."),
            refuse="Do not describe 'users' without saying how a user was "
                   "counted. Self-reported use and measured use differ "
                   "substantially and consistently.",
            sources="ACS, Census, Eurostat, national statistics offices",
        ),
        Section(
            key="structure",
            title="Age, income and location",
            brief=("Break the population down on the axes that matter for "
                   "this question, with the survey and year for each cut."),
            needs=("population",),
            refuse="Never mix vintages in one breakdown without saying so.",
            sources="ACS tables, national census microdata summaries",
        ),
        Section(
            key="behaviour",
            title="What they actually do",
            brief=("Incidence and frequency — how many do the thing, how "
                   "often. Distinguish a survey that asked from a panel that "
                   "measured, because they disagree and the direction of the "
                   "disagreement is predictable."),
            needs=("population",),
            refuse="Do not report a self-reported frequency as measured "
                   "behaviour.",
            sources="American Time Use Survey, Consumer Expenditure Survey, "
                    "Ofcom and equivalent regulators, published panel summaries",
            paid="Product-level behavioural panels are the paid layer here, "
                 "and there is rarely a free substitute.",
            paid_source="Nielsen, Circana, GWI, Kantar",
        ),
        Section(
            key="change",
            title="How this is shifting",
            brief=("Compare against an earlier vintage of the same survey. "
                   "Two readings of one series beats any single snapshot."),
            needs=("structure",),
            refuse="Do not compare two different surveys and call the "
                   "difference a trend.",
            required=False,
        ),
    ),
))


register(ReportType(
    key="competitive-landscape",
    title="Who competes and how hard it is to enter",
    answers="The named participants, how concentrated the market is, and what "
            "stands between an entrant and a customer.",
    limits="Private company revenue is rarely public. Concentration from "
           "establishment size bands is a defensible approximation, not a "
           "measurement of firm-level share.",
    basis="The intersection of the S-1 competition section and IBISWorld's "
          "Competitive Forces chapter.",
    sections=(
        Section(
            key="participants",
            title="Who is in it",
            brief=("Name the companies individually, largest first, with what "
                   "each one actually does. Say which are public and which "
                   "are private, because that decides what else is knowable "
                   "about them."),
            refuse="Do not list a category where a company belongs. 'Regional "
                   "operators' is not a participant.",
            sources="EDGAR full-text search, state registries, trade "
                    "association member lists",
        ),
        Section(
            key="concentration",
            title="How concentrated it is",
            brief=("HHI and CR4 against the published DOJ/FTC thresholds — "
                   "under 1,500 unconcentrated, 1,500-2,500 moderate, over "
                   "2,500 concentrated. Say what the shares were computed "
                   "from."),
            needs=("participants",),
            refuse="HHI over establishment size bands says nothing about "
                   "scale — a market of 1,400 sole traders and one of 1,400 "
                   "large firms score identically. Report the average size "
                   "alongside it.",
            sources="County Business Patterns size bands; published share "
                    "where it exists",
        ),
        Section(
            key="barriers",
            title="How hard it is to enter",
            brief=("Grade the barrier high, medium or low AND say whether it "
                   "is rising, falling or steady. A level plus a direction "
                   "beats a paragraph."),
            needs=("concentration",),
            refuse="A barrier needs a mechanism — capital, licence, network "
                   "effect, contract length. 'Competition is intense' is not "
                   "a barrier.",
            corpus="IBISWorld grades and trends every one",
        ),
    ),
))


register(ReportType(
    key="regulation",
    title="What rules apply",
    answers="The statutes, licences and thresholds that govern operating in a "
            "market, named specifically.",
    limits="Coverage is strong where a regulator publishes online and weak "
           "where rules are local or administered case by case.",
    basis="Named in the Risk Factors Summary of all five corpus filings.",
    sections=(
        Section(
            key="regimes",
            title="Which regimes apply",
            brief=("Name the statutes and the agencies. agilon names the "
                   "False Claims Act, the corporate practice of medicine "
                   "doctrine and CMS methodology risk — that specificity is "
                   "the whole value."),
            refuse="'Heavily regulated' is not a finding. A named statute or "
                   "nothing.",
            sources="CFR, agency websites, state licensing boards, EUR-Lex",
            corpus="5/5",
        ),
        Section(
            key="thresholds",
            title="The thresholds people miss",
            brief=("Where a rule applies above a job value, a headcount, a "
                   "revenue level or a customer count, state the number. The "
                   "threshold is the part that decides whether a rule "
                   "applies to a reader at all."),
            needs=("regimes",),
            refuse="Do not state a threshold without its jurisdiction and the "
                   "date it took effect.",
        ),
        Section(
            key="direction",
            title="What is changing",
            brief=("Pending rulemaking, consultations, enforcement trends. "
                   "Where nothing is pending, say so — a quiet regulator is "
                   "itself information."),
            needs=("regimes",),
            required=False,
        ),
    ),
))


# ================================================================= assembly

def build_report(report: ReportType, subject: str, *, place: str = "",
                 run_section: Callable[..., Panel],
                 on_event: Optional[Callable[[str], None]] = None
                 ) -> Dict[str, Any]:
    """Run one report type over one subject.

    `run_section` is the agent — given a section brief and what earlier
    sections found, it researches and returns a panel. Injected rather than
    owned, because the research is the part a frontier model with tools does
    well and a hand-written question list does badly.

    What this function owns is what must hold regardless of which model ran:
    the order, the dependencies, the honest coverage count, and the fact that
    a section which could not be answered still appears and says why.
    """
    emit = on_event or (lambda *_: None)
    panels: List[Panel] = []
    done: Dict[str, Panel] = {}

    for spec in report.order():
        emit(f"— {spec.title}")
        context = {k: done[k] for k in spec.needs
                   if k in done and done[k].answered}
        missing = [k for k in spec.needs if k not in context]
        try:
            panel = run_section(section=spec, subject=subject, place=place,
                                context=context, report=report,
                                on_event=emit)
        except Exception as exc:  # noqa: BLE001 - one bad section is not a run
            # Name the exception type: "failed: ProviderError(...)" is an
            # outage the reader can shrug at; "failed: TypeError(...)" is a
            # bug in DeckScope, and the reader deserves the discriminator.
            panel = unanswered(spec.title,
                               f"the {spec.key} section failed — "
                               f"{type(exc).__name__}: {exc}",
                               agent=spec.key)
        panel.agent = spec.key
        if missing and panel.answered:
            panel.caveats.append(
                f"Written without {', '.join(missing)}, which could not be "
                f"established — so it is less grounded than its wording "
                f"suggests.")
        panels.append(panel)
        done[spec.key] = panel

    return {
        "type": report.key,
        "title": report.title,
        "subject": subject,
        "place": place,
        "panels": panels,
        "coverage": coverage(report, panels),
        "upgrades": upgrades(report, panels),
        "limits": report.limits,
    }


def coverage(report: ReportType, panels: Sequence[Panel]) -> Dict[str, Any]:
    """How much of this report stands up. Counted, never asserted."""
    answered = [p for p in panels if p.answered]
    required = [s for s in report.sections if s.required]
    got = {p.agent for p in answered}
    figures = sum(p.coverage()["figures"] for p in panels)
    checkable = sum(p.coverage()["checkable"] for p in panels)
    return {
        "sections": len(panels),
        "answered": len(answered),
        "missing_required": [s.key for s in required if s.key not in got],
        "figures": figures,
        "checkable": checkable,
        "fraction_checkable": round(checkable / figures, 3) if figures else 0.0,
    }


def upgrades(report: ReportType, panels: Sequence[Panel]) -> List[Dict[str, str]]:
    """Where a paid source would sharpen a section that came back thin.

    An offer, not an advert. Only sections that actually ran short appear —
    offering an upgrade on a section that came back complete is how a useful
    prompt turns into a sales pitch, and one advert makes the honest ones
    unbelievable too.
    """
    by_key = {s.key: s for s in report.sections}
    offers: List[Dict[str, str]] = []
    for panel in panels:
        spec = by_key.get(panel.agent)
        if spec is None or not spec.paid:
            continue
        stats = panel.coverage()
        thin = (not panel.answered or stats["absent"] > 0
                or stats["fraction_checkable"] < 0.5)
        if not thin:
            continue
        offers.append({
            "section": spec.key, "title": spec.title,
            "what": spec.paid, "sources": spec.paid_source,
            "established": f"{stats['checkable']} of {stats['figures']} "
                           f"figures checkable",
        })
    return offers
