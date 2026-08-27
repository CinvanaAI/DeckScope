# How market reports actually get made

Field notes. Gathered before designing anything, because the previous version of
this system was built from my idea of what a market report is, and that idea was
wrong in ways the corpus later showed. Sources are linked; where I am inferring
rather than citing, it says so.

Companion to [market-corpus/SCHEMA.md](market-corpus/SCHEMA.md), which derives
the same thing from filings rather than from practice.

---

## 1. Who does this for a living

Three distinct professions produce the document we are trying to produce, and
they do it differently.

**Sell-side / IPO.** Bank equity capital markets team plus industry coverage,
company management, and both sets of counsel. The industry section of an S-1 is
drafted collaboratively; the *issuer* is legally responsible for it. For the
market numbers they very often commission a third-party study — Frost &
Sullivan, YouGov, Analysys Mason — and file the consent as an exhibit. That
consent is the machine-readable marker for "this filing has real market work in
it" (see SCHEMA.md).

**Syndicated research.** IBISWorld, Frost & Sullivan, Gartner, Euromonitor.
Analysts own a set of industries and refresh a fixed report structure on a
cycle. IBISWorld's NAICS collection covers ~700 industries at the 5-digit level,
30–40 pages each. This is the closest analogue to what we are building: same
document, many markets, produced repeatedly rather than once.

**Consulting / diligence.** Engagement manager, associates, plus expert-network
calls. Bespoke per engagement.

The one we should imitate is **syndicated research**, because it is the only one
of the three that solves the same problem we have: one format, any market, on
demand.

---

## 2. The methods, and the one that matters most

### Top-down versus bottom-up is not a choice

The consistent professional advice is to run **both** and treat the result as a
signal:

> "The strongest analyses run both methods and compare the results, using
> convergence or divergence as a signal of model reliability."
> — [HG Insights](https://hginsights.com/blog/market-sizing-the-complete-guide-to-calculating-tam-sam-som-and-building-a-data-driven-growth-strategy/)

This is the single most useful thing in this research, because it is an
architecture rather than a technique. Two independent sizing agents, run on the
same market, and **their disagreement is a reported finding rather than a
problem to reconcile**. We already have the machinery: `relation()` returns
`AGREE` / `DISAGREE` / `INCOMPARABLE`, and contested findings survive into the
report instead of being averaged.

- **Top-down** — start from a published aggregate and narrow. Cheap, and the
  source of most inflated TAMs, because most people stop at "find an analyst
  report that quantifies the market and cite that figure".
- **Bottom-up** — count units and multiply. Slower, operationally grounded, and
  the method every filing in our corpus actually used.

### Document the assumptions, not just the answer

> "The assumptions are as important as the final numbers, because they are what
> reviewers, investors, and executives will scrutinize."

Which is what `Term(method=ASSUMED)` with a required range already enforces.

### Primary research is the paid part

Expert networks are *primary* research, not an alternative to it. Structured
calls with practitioners answer **why** and **how**; surveys answer **how many**
and **how often**
([Infomineo](https://infomineo.com/services/business-research/expert-network-vs-primary-research-how-to-choose-the-right-approach/)).
Frost & Sullivan runs phone interviews, web surveys, in-person interviews and
focus groups, then validates secondary findings against them
([Frost & Sullivan](https://www.frost.com/analytics/customer-analytics/data-collection-capabilities/)).

**We cannot do this and should stop pretending otherwise.** It is the honest
boundary of the product: we can be as good as their *secondary* research and
better than their *incentives*, and we cannot originate a survey. Where the RATE
term needs primary data, the answer is a public substitute or a stated
assumption with a range — never a number that looks measured.

---

## 3. A second schema, independent of the S-1 one

IBISWorld reports run: **About · At a Glance · Performance · Products and
Markets · Geographic Breakdown · Competitive Forces · Companies · External
Environment · Financial Benchmarks · Key Statistics**
([IBISWorld](https://content.ibisworld.com/media/vbccmlg5/ibisworld-new-report-structure.pdf)).

Two details worth copying exactly:

- **Barriers to entry are graded and trended** — high/medium/low, *and*
  increasing/decreasing/steady. A level plus a direction is far more useful than
  a paragraph.
- **Four to six key success factors, ranked.** Not a list of everything that
  matters; a short ordered list. The discipline is in the cap.

### Where the two schemas agree

Overlaying IBISWorld's structure on the S-1 structure derived from filings, the
intersection is the spine — and the intersection is what we build:

| Section | S-1 | IBISWorld |
|---|---|---|
| Definition and boundary | yes | About / definitions |
| Size with method | yes | Key Statistics |
| Growth, historical and forecast | yes | Performance / Outlook |
| Concentration and share | yes | Competitive Forces |
| Named participants | yes | Companies |
| Cost structure / unit economics | partly | Financial Benchmarks |
| Barriers to entry | yes | Competitive Forces |
| Regulation | yes | External Environment |
| Geographic breakdown | yes | Geographic Breakdown |
| Lifecycle stage | no | Life Cycle |
| **What could not be established** | no | no |

The last row is ours. Neither profession writes it, for the same reason: both
are paid to deliver an answer.

---

## 4. Saturation and concentration — the computable part

These have real formulas, which means agents rather than prose.

| Measure | Formula | Reading |
|---|---|---|
| Penetration rate | customers ÷ potential market | high ⇒ saturated |
| Growth rate | Δ market size over time | high ⇒ not saturated |
| Concentration ratio CR-N | Σ share of largest N firms | CR4 > 60% ⇒ concentrated |
| **HHI** | Σ (share²) across all firms | <1500 unconcentrated · 1500–2500 moderate · >2500 concentrated |

HHI squares the shares, so it weights large firms heavily and is sensitive to
inequality in a way a simple ratio is not
([AnalystPrep](https://analystprep.com/cfa-level-1-exam/economics/use-and-limitation-of-concentration-measures-in-identifying-market-structure/)).
The DOJ/FTC thresholds above are the standard reading.

**All of this is computable from establishment counts by employee-size band,
which County Business Patterns publishes free.** We do not need firm-level
revenue to say something true about concentration — size-band distribution gives
a defensible approximation, and the approximation can be labelled as one.

---

## 5. What this changes about the build

1. **Two sizing agents, not one.** Top-down and bottom-up, independently, with
   divergence reported. This is the architecture the profession endorses and it
   maps onto machinery we already have.
2. **Saturation is arithmetic.** HHI, CR4, penetration — computed in Python from
   CBP size bands, not asked of a model.
3. **Barriers get a level and a direction.** Copy IBISWorld.
4. **Key success factors are capped at six and ranked.** The cap is the point.
5. **Lifecycle stage** is a section neither our S-1 schema nor our current code
   has, and IBISWorld has it in every report. Add it.
6. **Primary research is out of scope, permanently.** Say so in the report, in
   the section where it would have mattered, rather than in a footnote.
