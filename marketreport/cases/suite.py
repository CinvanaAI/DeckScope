"""The cases. Real pages, real facts, and traps written from the same pages.

Every excerpt is a quotation from the URL beside it, retrieved on the date
recorded. Nothing here was written to be plausible — that is the whole point,
and it is the same rule `demo_sources.py` follows and for the same reason: a
harness built on invented material grades the fixture, not the system.

**How the traps were written.** Not invented freely. Each one is the sentence
this exact corpus would produce if a stage got its job slightly wrong, and
almost all of them are failures that have actually happened in this repository:

  * a real figure attached to the wrong subject
  * a rate applied to a population it was not measured on
  * a US figure stated as a worldwide one
  * a plausible round number nobody published
  * a conclusion that would follow if one more fact were true

A trap that no realistic run would ever trip teaches nothing. These are near
misses on purpose.
"""
from __future__ import annotations

from .schema import Case, Expect, Trap, register

__all__ = ["REGULATION_US", "DEMOGRAPHICS_US", "GROWTH_WORLDWIDE",
           "MARKET_SHARE_SMARTPHONES", "MARKET_SIZE_WHOLESALE"]


# ==================================================================== rules

REGULATION_US = register(Case(
    id="regulation-hearing-aids-us",
    name="US hearing aid regulation, from the rule itself",
    market="hearing aids",
    report="regulation",
    measure="United States",
    retrieved="2026-08-28",
    notes=("Chosen because the primary source IS the free source: the eCFR "
           "and the Federal Register are the rule, not a description of it. "
           "This is the one report type where public sourcing beats a paid "
           "summary rather than approximating it."),
    pages=[
        {
            "title": "eCFR :: 21 CFR 800.30 — Over-the-counter hearing aid "
                     "controls",
            "url": "https://www.ecfr.gov/current/title-21/chapter-I/"
                   "subchapter-H/part-800/subpart-B/section-800.30",
            "published": "2026-08-28",
            "snippet": (
                "This section specifies the requirements for over-the-counter "
                "(OTC) air-conduction hearing aids. Air-conduction hearing "
                "aids that satisfy the requirements in paragraphs (c) through "
                "(f) of this section are considered available over the "
                "counter. An OTC hearing aid shall bear specific information "
                "in the labeling, with the outside package bearing warnings "
                "and other important information."),
        },
        {
            "title": "Federal Register :: Medical Devices; Ear, Nose, and "
                     "Throat Devices; Establishing Over-the-Counter Hearing "
                     "Aids",
            "url": "https://www.federalregister.gov/documents/2022/08/17/"
                   "2022-17230/medical-devices-ear-nose-and-throat-devices-"
                   "establishing-over-the-counter-hearing-aids",
            "published": "2022-08-17",
            "snippet": (
                "The FDA is defining and establishing general controls for an "
                "over-the-counter category of hearing aids, with the "
                "intention that these controls provide for reasonable "
                "assurance of safety and effectiveness for these devices. "
                "Labeling requirements advise that individuals under the age "
                "of 18 should consult with a doctor and refrain from using "
                "OTC hearing aids. The labeling includes a listing of red "
                "flag conditions, signs or symptoms that should prompt a "
                "consultation with a doctor, preferably an ear-nose-throat "
                "doctor."),
        },
        {
            "title": "AAO-HNS Summary: FDA Over-The-Counter Hearing Aids "
                     "Final Rule",
            "url": "https://www.entnet.org/advocacy/regulatory-advocacy/"
                   "over-the-counter-sale-of-hearing-aids/"
                   "aao-hns-summary-fda-over-the-counter-hearing-aids-final-rule/",
            "published": "2026-08-28",
            "snippet": (
                "The final rule establishes that no State or local government "
                "shall establish or continue in effect any law, regulation, "
                "order, or other requirement specifically related to hearing "
                "products that would restrict or interfere with the "
                "servicing, marketing, sale, dispensing, use, customer "
                "support, or distribution of OTC hearing aids that is "
                "different from or in addition to the federal regulations. "
                "OTC hearing aids are intended for adults with perceived mild "
                "to moderate hearing impairment."),
        },
        {
            "title": "eCFR :: 21 CFR 801.422 — Prescription hearing aid "
                     "labeling",
            "url": "https://www.ecfr.gov/current/title-21/chapter-I/"
                   "subchapter-H/part-801/subpart-H/section-801.422",
            "published": "2026-08-28",
            "snippet": (
                "Prescription hearing aid labeling requirements are set out "
                "separately from the over-the-counter controls, and apply to "
                "hearing aids that are not available over the counter."),
        },
    ],
    expect=[
        Expect(r"800\.30|21 CFR 800",
               "The OTC controls are one specific section of the CFR. A "
               "regulation report that cannot name the instrument has "
               "produced an impression, not a finding.",
               weight=2.0, must_cite=True),
        Expect(r"over.the.counter|\bOTC\b",
               "The whole subject of the corpus.", weight=2.0),
        Expect(r"mild to moderate",
               "The severity threshold is what decides who the category is "
               "for, and it is the part readers miss.", weight=2.0),
        Expect(r"\b18\b|under the age of 18|adults",
               "An age threshold with a named exclusion.", weight=1.5),
        Expect(r"pre.?empt|State or local government|different from or in "
               r"addition to",
               "Federal preemption of state rules is the provision with the "
               "largest commercial consequence in this corpus.", weight=1.5),
        Expect(r"red.flag",
               "A named labelling requirement rather than a general one."),
        Expect(r"801\.422|prescription hearing aid labeling",
               "Prescription devices are governed separately, which is the "
               "boundary of the OTC category."),
    ],
    traps=[
        Trap(r"severe|profound",
             "The rule covers mild to moderate impairment only. Extending it "
             "to severe or profound loss is the single most consequential "
             "way to misread this corpus, and nothing here says it."),
        Trap(r"European Union|\bEU\b|CE mark|MDR",
             "This is United States law. A jurisdiction-scoped report that "
             "reaches for EU rules has done exactly what the jurisdiction "
             "dimension exists to prevent."),
        Trap(r"requires? a prescription for all|prescription is required",
             "Backwards. The rule creates a category that does NOT require "
             "one."),
        Trap(r"\bFTC\b|Federal Trade Commission",
             "The FDA issued this. Naming the wrong regulator is worse than "
             "naming none, because it sends the reader to the wrong body."),
        Trap(r"states? (?:may|can) impose (?:additional|stricter)",
             "The opposite of the preemption provision, which forbids state "
             "requirements different from or in addition to the federal "
             "ones."),
    ],
))


# ============================================================= who they are

DEMOGRAPHICS_US = register(Case(
    id="demographics-hearing-loss-us",
    name="Who has hearing loss in the US, and how it was counted",
    market="hearing aids",
    report="demographics",
    measure="eligible",
    retrieved="2026-08-28",
    notes=("The prevalence figures here disagree with each other by design — "
           "they are measured on different age bands and under two different "
           "WHO thresholds. A correct report keeps them apart. Averaging them "
           "or quoting one as 'the' rate is the failure this case is built to "
           "catch, and it is the eligibility-versus-demand confusion that the "
           "population dimension exists for."),
    pages=[
        {
            "title": "Age-Related Hearing Loss (Presbycusis) — NIDCD, NIH",
            "url": "https://www.nidcd.nih.gov/health/age-related-hearing-loss",
            "published": "2026-08-28",
            "snippet": (
                "About one in three people in the United States between the "
                "ages of 65 and 74 has hearing loss, and nearly half of those "
                "older than 75 have difficulty hearing."),
        },
        {
            "title": "Prevalence of Hearing Loss and Hearing Aid Use Among US "
                     "Medicare Beneficiaries Aged 71 Years and Older",
            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10383002/",
            "published": "2023-07-01",
            "snippet": (
                "In a nationally representative sample of older adults, 65.3% "
                "of those aged 71 years or older had hearing loss, "
                "representing 21.5 million individuals. By age 90 years, "
                "96.2% of adults had hearing loss."),
        },
        {
            "title": "Hearing Loss Among Older Adults in the National Health "
                     "and Aging Trends Study",
            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10736633/",
            "published": "2023-12-01",
            "snippet": (
                "When using updated World Health Organization categories for "
                "measuring hearing loss, prevalence increased from 67.9% to "
                "82.7% of adults over 70 years. The change reflects the "
                "measurement threshold rather than any change in the "
                "population."),
        },
    ],
    expect=[
        Expect(r"65\.3%|65 ?percent",
               "The headline prevalence figure, on a named age band, from a "
               "nationally representative sample.", weight=2.0,
               must_cite=True),
        Expect(r"21\.5 ?million",
               "The population count that turns a rate into a market size "
               "term.", weight=2.0, must_cite=True),
        Expect(r"71 ?years|aged 71",
               "The age band the 65.3% is measured on. A prevalence rate "
               "without its band is not usable.", weight=2.0),
        Expect(r"one in three|65 (?:and|to) 74|33%",
               "A second band from a different source, which is what makes "
               "the age dependence visible."),
        Expect(r"67\.9%|82\.7%",
               "The two WHO thresholds. Their gap is larger than most "
               "differences anyone would call a finding."),
        Expect(r"threshold|categor|definition|measurement",
               "The reason the two figures differ. Reporting both numbers "
               "without the reason is worse than reporting one.", weight=2.0),
    ],
    traps=[
        Trap(r"65\.3% of (?:all )?(?:adults|Americans|the population)(?! aged)",
             "65.3% is the rate among adults 71 and older, not among adults "
             "generally. Moving a rate off the population it was measured on "
             "is the commonest way a demographic figure becomes false while "
             "staying quotable."),
        Trap(r"(?:average|mean) prevalence of (?:7[0-9]|6[0-9])(?:\.\d)?%",
             "The 67.9% and 82.7% figures are the same population under two "
             "different thresholds. Averaging them produces a number "
             "describing no measurement anyone made."),
        Trap(r"21\.5 million (?:hearing aid )?(?:users|wearers|customers|"
             r"buyers)",
             "21.5 million is the number of people WITH hearing loss, not "
             "the number who own or bought a hearing aid. This is the "
             "eligibility-versus-demand slip the population dimension exists "
             "to prevent, and the gap between the two is most of the story."),
        Trap(r"worldwide|globally|global population",
             "Every source here is United States. A demographics report that "
             "silently generalises to the world has changed the denominator "
             "by a factor of twenty."),
    ],
    absences=[
        Expect(r"not (?:established|published|available|reported)|"
               r"no source|could not be|nobody publishes",
               "Nothing in this corpus says how many people BUY a hearing "
               "aid, only how many have hearing loss. A report that does not "
               "say so leaves the reader to assume the gap is zero."),
    ],
))


# ================================================================== growth

GROWTH_WORLDWIDE = register(Case(
    id="growth-hearing-aids-worldwide",
    name="Hearing aid unit growth, both endpoints shown",
    market="hearing aids",
    report="growth",
    measure="2020-2025",
    retrieved="2026-08-28",
    notes=("A six-year series from one publisher on one definition, which is "
           "rarer than any single figure. The 2020 point is a pandemic "
           "collapse, so any rate computed from that base is flattered — "
           "which is the trap. Nothing in this corpus is a forecast, so a "
           "report that produces one has invented it."),
    pages=[
        {
            "title": "Hearing aid sales — EHIMA",
            "url": "https://www.ehima.com/about-ehima/hearing-aid-sales/",
            "published": "2026-05-01",
            "snippet": (
                "EHIMA member unit sales: 2020, 14.12 million, down 17.2%; "
                "2021, 19.34 million, up 37.0%; 2022, 20.25 million, up 4.7%; "
                "2023, 21.81 million, up 7.7%; 2024, 22.69 million, up 4.0%; "
                "2025, 23.16 million, up 2.1%. Figures are net wholesale unit "
                "numbers sold by manufacturers to dispensers, aggregated "
                "across members."),
        },
        {
            "title": "EHIMA Reports Continued Growth in Global Hearing Aid "
                     "Sales in 2025",
            "url": "https://hearingreview.com/hearing-products/hearing-aids/"
                   "ehima-reports-continued-growth-in-global-hearing-aid-"
                   "sales-in-2025",
            "published": "2026-05-06",
            "snippet": (
                "EHIMA reported global hearing aid sales by its members of "
                "23.16 million units in 2025, an increase of 2.1% compared "
                "with 2024. EHIMA members are the world's largest hearing "
                "instrument manufacturers. No breakdown by individual "
                "manufacturer is published."),
        },
    ],
    expect=[
        Expect(r"23\.16 ?million|23,160,000",
               "The end point of the series.", weight=2.0, must_cite=True),
        Expect(r"14\.12 ?million",
               "The start point. A growth rate whose endpoints are not both "
               "shown cannot be checked, which is this report type's whole "
               "refusal.", weight=2.0, must_cite=True),
        Expect(r"2020",
               "The start year. A rate with no years attached is "
               "unreproducible.", weight=2.0),
        Expect(r"2025",
               "The end year.", weight=2.0),
        Expect(r"EHIMA",
               "Whose figures these are. A series belongs to its publisher.",
               weight=1.5, must_cite=True),
        Expect(r"2\.1%",
               "The most recent year's rate, which is the one that describes "
               "the market now."),
        Expect(r"wholesale|to dispensers",
               "The price level and population the units are counted on."),
    ],
    traps=[
        Trap(r"\b(?:1[0-9]|[2-9][0-9])(?:\.\d)?% (?:CAGR|compound|annual "
             r"growth)",
             "A compound rate off the 2020 base is flattered by a pandemic "
             "collapse — 2020 fell 17.2% and 2021 rebounded 37%. Any "
             "double-digit CAGR from this series is an artefact of the "
             "starting point, and nothing in the corpus states one."),
        Trap(r"(?:forecast|projected|expected|will reach|by 20(?:2[7-9]|3\d))",
             "There is no forecast in this corpus. Extending the series "
             "forward is the single thing this report type refuses to do, "
             "because a projection this report invented is worse than no "
             "projection."),
        Trap(r"23\.16 ?million (?:people|patients|users|wearers)",
             "23.16 million is units sold to dispensers in one year, not "
             "people. Units sold in a period and people using the product "
             "are different populations, and for a durable good the second "
             "is far larger."),
        Trap(r"market (?:grew|growth) (?:by )?\$",
             "The series is in units. Nothing here attaches money to it, so "
             "a growth figure in currency has been invented or imported."),
    ],
    absences=[
        Expect(r"not (?:established|published|available)|no (?:forecast|"
               r"source)|could not be|nobody publishes|does not publish",
               "EHIMA publishes no per-manufacturer split and no forecast. "
               "Both are things a reader will assume exist unless told."),
    ],
))


# ============================================================ market share

def _share_case():
    """Built from `demo_sources.PAGES` rather than a copy of them.

    Those five smartphone pages are already the recorded corpus the demo runs
    on — real quotations, retrieved 2026-08-27 — and duplicating them here
    would be the two-definitions drift the dimension module already exists to
    stop, one directory over.
    """
    from ..demo_sources import PAGES, RETRIEVED

    return Case(
        id="market-share-smartphones-q2-2026",
        name="Smartphone share, where units and revenue disagree about the "
             "leader",
        market="cell phones",
        report="market-share",
        measure="",     # unscoped on purpose: the two-basis split IS the story
        retrieved=RETRIEVED,
        notes=("The corpus's whole point is a reversal: Samsung leads units "
               "with 22% (SAG) / 22.6% (IDC) while holding 16% of revenue, "
               "and Apple holds 49% of revenue on ~20% of units. A correct "
               "report keeps the two bases and the two publishers apart. The "
               "traps are the three ways this corpus gets blended: averaging "
               "the publishers, moving Apple's revenue share onto shipments, "
               "and promoting Samsung's unit lead to a revenue lead."),
        pages=tuple(PAGES),
        expect=[
            Expect(r"22(?:\.6)?%",
                   "Samsung's unit share, from either publisher.",
                   weight=2.0, must_cite=True),
            Expect(r"49%",
                   "Apple's revenue share — the right-hand side of the "
                   "reversal.", weight=2.0, must_cite=True),
            Expect(r"16%",
                   "Samsung's revenue share. Without it the unit lead reads "
                   "as leadership, which is the misreading the corpus "
                   "exists to prevent.", weight=2.0),
            Expect(r"20(?:\.1)?%",
                   "Apple's unit share, so both companies appear on both "
                   "bases."),
            Expect(r"Counterpoint",
                   "The revenue figures belong to their publisher.",
                   weight=1.5, must_cite=True),
            Expect(r"IDC|SAG|Smart ?Analytics",
                   "A second publisher named, which is what makes the "
                   "unit-share disagreement visible as a disagreement."),
            Expect(r"\$946",
                   "Apple's average selling price — the mechanism of the "
                   "reversal, not just its result."),
        ],
        traps=[
            Trap(r"22\.3%",
                 "The average of SAG's 22% and IDC's 22.6%. No source says "
                 "it; two trackers' numbers blended into one is the exact "
                 "corruption the per-publisher series exist to prevent."),
            Trap(r"Samsung(?:'s)? (?:led|leads|ranked (?:No\.?\s?1|first)) "
                 r"(?:on |in |by |the )?revenue",
                 "Samsung leads units and holds 16% of revenue. Promoting "
                 "the unit lead to a revenue lead is a real number given the "
                 "wrong crown."),
            Trap(r"49% of (?:global )?(?:smartphone )?(?:shipments|units)",
                 "49% is Apple's share of REVENUE. The same number moved to "
                 "shipments is the basis swap this whole report type is "
                 "scoped against."),
            Trap(r"revenue (?:fell|declined|dropped|shrank)",
                 "Revenue grew 7% in Q2 and 5% in Q3; SHIPMENTS declined 8%. "
                 "Moving the decline from units to money inverts the "
                 "market's actual story."),
        ],
    )


MARKET_SHARE_SMARTPHONES = register(_share_case())


# ============================================================= market size

MARKET_SIZE_WHOLESALE = register(Case(
    id="market-size-hearing-aids-wholesale",
    name="A wholesale sizing with the value term missing",
    market="hearing aids",
    report="market-size",
    measure="wholesale",
    retrieved="2026-08-28",
    notes=("The live run that shaped terms.py, frozen as a case. The COUNT "
           "term is free and exact; the VALUE term does not exist worldwide "
           "after 2019. The correct report states the gap and refuses the "
           "multiplication. The heavyweight trap is any total between $10B "
           "and $19B: nothing in the corpus says one, so its presence proves "
           "the forbidden arithmetic — 23.16M units times some per-unit "
           "price — was performed on mismatched terms."),
    pages=[
        {
            "title": "Hearing aid sales — EHIMA",
            "url": "https://www.ehima.com/about-ehima/hearing-aid-sales/",
            "published": "2026-05-01",
            "snippet": (
                "EHIMA member unit sales: 2020, 14.12 million; 2021, 19.34 "
                "million; 2022, 20.25 million; 2023, 21.81 million; 2024, "
                "22.69 million; 2025, 23.16 million. Figures are net "
                "wholesale unit numbers sold by manufacturers to dispensers, "
                "aggregated across members. No monetary value is published."),
        },
        {
            "title": "US Hearing Aid Pricing: The Markup Ratio — Hearing "
                     "Health & Technology Matters",
            "url": "https://hearinghealthmatters.org/hearing-economics/2021/"
                   "us-hearing-aid-pricing-markup-ratio/",
            "published": "2021-06-15",
            "snippet": (
                "In 2019 the average wholesale invoice was $774 for a "
                "hearing aid in the United States, up from $457 in 2004. The "
                "average markup ratio between wholesale and retail has "
                "remained between 3x and 4x. No worldwide figure is "
                "published."),
        },
        {
            "title": "Hearing Aids Market Size, Share & Trends Report — "
                     "Grand View Research",
            "url": "https://www.grandviewresearch.com/industry-analysis/"
                   "hearing-aids-market",
            "published": "2026-01-15",
            "snippet": (
                "The global hearing aids market size was estimated at USD "
                "9.1 billion in 2025. The retail stores segment held the "
                "largest share of the market at 70.6% in 2025. The price "
                "level of the total is not stated."),
        },
        {
            "title": "Hearing Aid Market Size, Trends — IMARC Group",
            "url": "https://www.imarcgroup.com/hearing-aid-market",
            "published": "2026-01-10",
            "snippet": (
                "The global hearing aid market size reached USD 7.5 billion "
                "in 2025. The page does not state whether the figure is "
                "counted at wholesale or retail prices."),
        },
    ],
    expect=[
        Expect(r"23\.16 ?million",
               "The COUNT term — free, exact, and defined as precisely the "
               "population being sized.", weight=2.0, must_cite=True),
        Expect(r"\$774",
               "The only per-unit wholesale price found anywhere.",
               weight=1.5, must_cite=True),
        Expect(r"2019",
               "That price's year. Seven years stale, and the staleness must "
               "be visible or the number misleads.", weight=1.5),
        Expect(r"United States|US[- ]only|U\.S\.",
               "That price's geography. A US price against a worldwide count "
               "is the mismatch the report must name.", weight=1.5),
        Expect(r"wholesale",
               "The price level this report is scoped to."),
        Expect(r"\$(?:7\.5|9\.1) ?billion",
               "The published totals exist and are reported — as unlabelled, "
               "since neither states its price level."),
    ],
    absences=[
        Expect(r"not (?:published|available|established)|no (?:worldwide|"
               r"global)|could not be|missing",
               "The VALUE term does not exist at the geography and period of "
               "the COUNT term. Saying so is the report's most useful "
               "sentence — it is exactly what a commissioned study sells."),
    ],
    traps=[
        Trap(r"\$1\d(?:\.\d+)?(?!\d) ?billion",
             "23.16 million units times any plausible per-unit price lands "
             "between $10B and $19B, and nothing in the corpus states any "
             "such figure. Its presence proves the multiplication was "
             "performed on mismatched terms — a worldwide 2025 count times a "
             "US 2019 price — which is the one thing this report type "
             "refuses to do.", weight=3.0),
        Trap(r"\$(?:7\.5|9\.1) ?billion at wholesale|"
             r"wholesale (?:total|value|market) of \$(?:7\.5|9\.1)",
             "Neither publisher states a price level. Assigning one is not a "
             "reading of the source, it is an addition to it."),
        Trap(r"\$774[^.\n]{0,80}(?:worldwide|globally)|"
             r"(?:worldwide|globally)[^.\n]{0,80}\$774",
             "The $774 invoice is United States, 2019. Applied worldwide it "
             "manufactures the value term the corpus says does not exist."),
    ],
))
