"""The industry report — the S-1 shape, as one report type among several.

This was its own module for a while, which was the same mistake as the last
two times: a second system doing what the first one does. It is a
`ReportType` now, registered beside market-share and demographics, and the
only thing special about it is that its section list was transcribed from
five real filings rather than designed.

`stretches()` lives here because the corpus is where the phrases came from,
but it runs over any report that makes a size claim. It is the check for
constructions that make a market bigger without measuring the expansion —
a filing writes them and discloses them; this names them.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from .panel import Panel
from .reports import ReportType, Section, register

__all__ = ["INDUSTRY_REPORT", "stretches", "STRETCH_PHRASES"]


_S1_SECTIONS = (
    Section(
        key="problem",
        title="The problem this market exists to solve",
        brief=("What is hard, expensive or badly served today for the people "
               "who buy in this market? Establish the customer's difficulty "
               "before any figure is quoted, in the words the industry uses. "
               "This is qualitative and load-bearing — it is what makes the "
               "market boundary defensible rather than convenient."),
        corpus="3/3 — always precedes sizing",
        refuse="Do not quote a market size here. That comes later and must "
               "not be allowed to shape the definition.",
    ),
    Section(
        key="definition",
        title="What this market is, exactly",
        brief=("State which activities, which customer types and which "
               "geographies are inside this market and which are outside. "
               "Where two readings are both plausible, give both and say what "
               "each one would include — the boundary decides every number "
               "that follows."),
        corpus="3/3 — always explicit about geography and customer type",
        needs=("problem",),
        refuse="Do not settle an ambiguous boundary silently. Two plausible "
               "definitions are a finding, not a problem to resolve.",
    ),
    Section(
        key="size",
        title="How large it is, and how that was calculated",
        brief=("Size the market as COUNT of units × RATE that qualify × VALUE "
               "per unit per year, and state each term with its source. All "
               "five filings use this formula. The COUNT is almost always free "
               "government data. Where the VALUE cannot be sourced — it is "
               "proprietary in every filing examined — say which substitute "
               "was used and what that makes the number mean."),
        corpus="3/3 — never a bare number, always the arithmetic",
        needs=("definition",),
        refuse="Never state a size without the method sentence beside it. A "
               "reader can disagree with an arithmetic; they cannot disagree "
               "with '$34 billion'.",
        paid="A commissioned study prices the RATE and the VALUE terms — the "
             "two this cannot source for free. With one connected, the size "
             "stops depending on an industry-average substitute.",
        paid_source="Frost & Sullivan, Euromonitor, IBISWorld",
    ),
    Section(
        key="rings",
        title="The market, narrowed geographically",
        brief=("Size the market again at each level that matters — national, "
               "then region or state, then local — each ring sized separately "
               "with its own count. The narrowing is purely geographic, so it "
               "is reproducible from the same source at each level."),
        corpus="1/5 — only agilon does it, and it is the best thing in the "
               "corpus: $175B national → $80B in its states → $24B in its "
               "counties",
        needs=("size",),
        refuse="Do not derive a smaller ring by scaling the larger one by "
               "population unless no count exists at that level — and say so "
               "when you do.",
        required=False,
    ),
    Section(
        key="growth",
        title="How fast it is growing, and on whose forecast",
        brief=("Give growth as a rate between two named years with both "
               "endpoints stated. Name whoever produced the forecast. Where a "
               "market's money comes from a public programme, that "
               "programme's own published growth rates beat any analyst CAGR "
               "— agilon applies CMS's projected enrollment and spend growth "
               "and footnotes it."),
        corpus="2/3 — FIGS gives 6.1% CAGR, $12.0B 2020 → $16.0B 2025",
        needs=("size",),
        refuse="Never give a CAGR without both endpoints and the years. A "
               "growth rate whose start and end are not shown cannot be "
               "checked and usually cannot be reproduced.",
        paid="Forecasts are the most commonly paywalled figure in this whole "
             "document.",
        paid_source="IBISWorld, Gartner, IDC",
    ),
    Section(
        key="attractive",
        title="Why this market is structurally attractive",
        brief=("What about the structure of this market — not the moment — "
               "makes it a good or bad place to put money? Recurring versus "
               "one-off purchase, discretionary versus not, switching costs, "
               "replenishment cycle. FIGS: 'non-discretionary, recession "
               "resistant, much less susceptible to fashion or fad risk, "
               "continuously needs to be replenished.'"),
        corpus="3/3 — qualitative and load-bearing in every filing",
        needs=("definition",),
        refuse="Structural means it would still be true next year. A recent "
               "growth spurt is not a structural property.",
    ),
    Section(
        key="competitors",
        title="Who competes, and what share they hold",
        brief=("Name the participants individually and give their share where "
               "it is published, saying what the share measures — units, "
               "revenue, subscribers or installed base are four different "
               "questions and they routinely disagree about who leads."),
        corpus="unverified in the corpus — every filing's competition section "
               "fell outside the retrievable range, so this section is built "
               "from what the genre implies rather than from what was read",
        needs=("definition",),
        refuse="Never mix a usage share with a sales share in one chart. They "
               "measure different populations and the difference is usually "
               "larger than the gap between competitors.",
        paid="Country-level and segment-level share is the single most "
             "consistently paywalled data in this industry, and the firms "
             "selling it collect it from channel panels they own.",
        paid_source="Counterpoint, IDC, Canalys, Nielsen, Circana",
    ),
    Section(
        key="incumbents",
        title="Where the incumbents are weak",
        brief=("What are the established players failing to do? FIGS: the "
               "sector 'has operated for over 100 years with little "
               "innovation'. Klaviyo runs a section titled 'Key Limitations "
               "of Existing Solutions'. This is the argument for why anything "
               "new gets in at all."),
        corpus="2/3",
        needs=("competitors",),
        refuse="An incumbent weakness needs evidence — a complaint, a "
               "regulatory action, a metric — not an assertion that they are "
               "slow.",
    ),
    Section(
        key="economics",
        title="What it costs to operate in it",
        brief=("What does a participant spend to serve a customer, and what "
               "does it keep? Gross margin, cost structure, the inputs whose "
               "price moves the whole industry. When an input cost moves "
               "sharply, that is often the real story — Samsung ranked first "
               "in smartphone shipments in Q2 2026 and posted an operating "
               "loss, because memory prices ate the margin on cheap handsets."),
        corpus="implied rather than a named section; the Economic Census "
               "publishes receipts and payroll by industry, which is the free "
               "route",
        needs=("definition",),
        refuse="Do not present one company's margins as the industry's.",
    ),
    Section(
        key="regulation",
        title="What rules govern it",
        brief=("Name the specific regimes, statutes and licences — not "
               "'the sector is regulated'. Give thresholds where they exist, "
               "because the threshold is the part people miss. agilon names "
               "the False Claims Act, the corporate practice of medicine "
               "doctrine, and CMS methodology risk."),
        corpus="5/5 — present in every Risk Factors Summary",
        needs=("definition",),
        refuse="A named statute or nothing. 'Heavily regulated' is not a "
               "finding.",
    ),
    Section(
        key="adjacent",
        title="Adjacent markets, sized separately",
        brief=("What sits next to this market that a participant could "
               "credibly expand into, and how large is that — as its own "
               "number with its own basis. FIGS sizes 40 million "
               "non-healthcare uniform wearers separately from its core."),
        corpus="3/3 — and never folded into the headline number",
        needs=("size",),
        refuse="An adjacent market is never added to the headline figure. It "
               "is a second number with its own basis.",
        required=False,
    ),
    Section(
        key="risks",
        title="The same market, described defensively",
        brief=("Describe this market as its Risk Factors section would: what "
               "could go wrong, what depends on things outside anyone's "
               "control, what would make the size above an overestimate. "
               "Use the same evidence, with the opposite incentive."),
        corpus="5/5 — every filing describes its market twice, and agilon "
               "explicitly tells the reader to read the TAM against the "
               "risks",
        needs=("size", "growth", "regulation"),
        refuse="This section may not be softer than the evidence. If the case "
               "section and this one disagree, that disagreement is the "
               "finding and both stay.",
    ),
)


INDUSTRY_REPORT = register(ReportType(
    key="industry-report",
    title="Full industry report",
    answers="The whole picture, in the shape an S-1 industry section uses: "
            "the problem, the boundary, the size and its arithmetic, growth, "
            "who competes, the economics, the rules, and the same market "
            "described defensively.",
    limits="Long. Twelve sections, and the thin ones are marked rather than "
           "padded. The five-year forecast that a syndicated report carries "
           "is not reproducible from public sources and is reported only "
           "where somebody else published one.",
    basis="Transcribed from the industry sections of five filed S-1s — "
          "Klaviyo, FIGS, Cricut, agilon health and Privia Health. Each "
          "section carries how many of the five had it.",
    sections=_S1_SECTIONS,
))


#: Phrases that do the work of a measurement without being one. Transcribed
#: from the corpus, not invented: these are the exact constructions the filings
#: used to expand a market without measuring the expansion.
STRETCH_PHRASES = (
    ("at least as large",
     "an assumption standing in for a measurement — Klaviyo doubles its "
     "headline to $68B on the belief that its international opportunity is "
     "'at least as large' as its domestic one"),
    ("interested in",
     "an intent screen rather than a behaviour screen — Cricut's TAM counts "
     "anyone who 'likes, buys, used to make or is interested in' custom "
     "items, which resolves to most adults alive and produces a 402 million "
     "person TAM"),
    ("could benefit from",
     "a capability claim standing in for demand"),
    ("addressable in principle",
     "a boundary with no filter applied"),
    ("we believe our opportunity",
     "belief presented in the position where a source would go"),
    ("total spend on",
     "a whole spending category treated as the market for one product in it — "
     "Privia opens at $3 trillion of national health spend and never narrows"),
)


def stretches(panels: Sequence[Panel]) -> List[Dict[str, str]]:
    """Definitional stretches, found and named.

    The one axis where this beats a filing rather than imitating one.

    Every construction below is real and came out of the corpus. A bank writes
    them, discloses them clearly enough to be technically honest, and lets the
    headline number stand. We compute them and put them on the page — because a
    reader who is deciding something needs to know that half the TAM came from
    a sentence rather than a source.
    """
    found: List[Dict[str, str]] = []
    for panel in panels:
        haystacks = [panel.headline] + list(panel.caveats)
        haystacks += [f.label for f in panel.figures]
        haystacks += [f.note for f in panel.figures if f.note]
        for text in haystacks:
            low = (text or "").lower()
            for phrase, why in STRETCH_PHRASES:
                if phrase in low:
                    found.append({
                        "section": panel.agent or panel.question[:40],
                        "phrase": phrase,
                        "where": text[:160],
                        "why": why,
                    })
    # An estimated figure inside a sizing section is the same problem wearing
    # different clothes: a number in the position where a source belongs.
    for panel in panels:
        if panel.agent not in ("size", "rings", "adjacent"):
            continue
        for figure in panel.figures:
            if figure.state == "estimated":
                found.append({
                    "section": panel.agent,
                    "phrase": figure.label,
                    "where": figure.value_text or "",
                    "why": "a figure in a sizing section that was inferred "
                           "rather than sourced or computed — the position "
                           "where a filing would put a citation",
                })
    return found
