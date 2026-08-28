# What reports to build, and which of them we can actually make

Researched 2026-08-27. Every claim here is sourced; where a judgment is mine it
says so.

This exists because "add more report types" is the wrong instruction to act on
directly. Two things have to be settled per type first, and they are separate
questions:

1. **Does anyone actually use it, and for what decision?**
2. **Can it be built from citable facts, for *this* market?**

The second question is the one that kills most candidates, and it is not
answerable in the abstract. Producibility is per-market. Unit share is
producible for cell phones — Counterpoint publishes it — and not for hearing
aids, where EHIMA counts the units and will not split its members. Both are
"market share reports."

---

## The generalization that has to come first

`marketreport/measures.py` exists because a market share is not one question,
and the basis has to be fixed before the research rather than confessed after
it. That is not a fact about market share. **Every report type has a dimension
that must be named upfront or the report is unlabelled**, and each one below
carries its own.

Adding five report types without generalizing this first means five types that
each rediscover the units-versus-revenue problem in their own vocabulary. The
`Measure` shape — key, label, what it counts, how it is misread, where it is
published, what it is confused with — generalizes; the seven registered
measures are just the market-share instance of it.

---

## Who reads what

### The investment reader

**Commercial due diligence** is what private equity commissions before buying
something. Its four core components are competitive landscape analysis, voice
of customer research, market sizing and TAM analysis, and win/loss analysis
([BluWave](https://www.bluwave.net/commercial-due-diligence-explained/)),
alongside customer segmentation, retention, sales channels, customer
acquisition cost and product differentiation
([Visme](https://visme.co/blog/due-diligence-report/)).

Two of those four are not producible from public sources at all. Voice of
customer and win/loss require interviewing the target's customers and its lost
deals. No amount of search substitutes for a phone call with someone who chose
a competitor. That is a hard boundary and it should be stated in the product
rather than approximated.

**The S-1 industry section** is the other investment document, and it is the
one this repo already has real evidence about: twelve sections transcribed from
five filed S-1s, with per-section frequency recorded in
`marketreport/s1.py`. Regulation and risk appear in 5/5. Definition, size and
structural attractiveness in 3/3. Growth in 2/3. Geographic narrowing in 1/5 —
and that one, agilon's, is the best thing in the corpus.

### The industry reader

**IBISWorld's actual chapter list**, from their own documentation: About This
Industry, At A Glance, Performance, Products & Markets, Geographic Breakdown,
Competitive Forces, Companies, External Environment, Financial Benchmarks, Key
Statistics, Key Success Factors, Call Prep Questions
([IBISWorld Help](https://help.ibisworld.com/en/articles/8265490-industry-report-collections),
[St. Thomas](https://libguides.stthomas.edu/ibisworld/industry_reports)).

Competitive Forces decomposes into market share concentration, barriers to
entry, substitutes and supply chain. Key Statistics carries twenty years of
history and five years of projections.

### The go-to-market reader

TAM / SAM / SOM, where SAM narrows TAM by geography, product capability,
regulation and segment fit, and SOM narrows again by competitive density and
sales capacity
([HG Insights](https://hginsights.com/blog/tam-sam-som-the-complete-guide-to-market-sizing/)).
Buyer personas are built from customer surveys and focus groups
([HubSpot](https://blog.hubspot.com/marketing/tam-sam-som)) — primary research
again, and again not producible.

Note what SAM and SOM actually are: **TAM is a research output; SAM and SOM are
functions of a specific company's capabilities.** We can produce the first and
cannot produce the other two without knowing the company. That is a clean
boundary and worth respecting rather than blurring.

### The credit reader

The credit memo blends financial data, qualitative context and strategy for a
loan committee. Its drivers are repayment capacity, liquidity, management
quality, **industry conditions**, collateral coverage and covenant headroom
([Abrigo](https://www.abrigo.com/blog/commercial-credit-analysis-101-back-to-basics/),
[CLA](https://www.claconnect.com/en/resources/blogs/financial-services/commercial-credit-risk-analysis-building-stronger-underwriting-foundations)).

Only "industry conditions" is a market report. The rest is borrower-specific.
So the credit reader wants a narrow thing — industry cyclicality, failure
rates, margin structure, concentration — not a general market study.

### The strategy reader

Porter's five forces — new entrants, supplier power, buyer power, substitutes,
rivalry — used to compare markets for entry and anticipate structural shifts
([Wikipedia](https://en.wikipedia.org/wiki/Porter's_five_forces_analysis),
[Umbrex](https://umbrex.com/resources/frameworks/strategy-frameworks/porters-five-forces/)).
Usually paired with a value chain analysis, which is internal and therefore
outside what we can source.

---

## What free public data actually supports

This is the half that decides everything, and it is better than expected.

| Source | What it gives | Cadence |
|---|---|---|
| [County Business Patterns](https://www.census.gov/topics/business-economy/data.html) | Establishments, employment, annual and Q1 payroll, by county and industry | Annual; 2023 latest as of 2026 |
| [Economic Census](https://guides.loc.gov/industry-research/census-bureau) | Capital expenditure, employment, expenses, inventories, payroll, sales/receipts | Every 5 years |
| [BLS QCEW](https://www.bls.gov/cew/) | Employment and wages covering 95%+ of US jobs, county to national, by industry | Quarterly |
| [IRS Statistics of Income](https://plainbizbench.com/methodology) | **Profit margin, receipts and net income benchmarks by industry** | Annual |
| SEC EDGAR | Audited segment revenue for US filers | Continuous |
| Regulators and trade associations | Subscribers, capacity, licensed counts, unit volumes | Varies |

The IRS SOI line is the significant one. It means **IBISWorld's Financial
Benchmarks chapter has a free public counterpart** — margins and receipts by
industry, from tax returns rather than from modelling. That is the single best
producibility finding of this research.

The EDGAR caveat found in the live run stands: EDGAR holds *SEC filers*. For a
worldwide market most large firms are not among them, and a company listed in
Zurich or Copenhagen files with its own regulator.

---

## The verdict, per type

Ordered by what I would build, with the reason.

### 1. Market size — BUILD NEXT

**Fixed-before-research parameter:** the price level. Manufacturer wholesale
and end-customer retail differ by the entire distribution margin, and the
hearing-aid run showed what happens without it — published 2025 totals from
$7.5B to $15.11B, and $21.61B under a definition that folded in hearing
implants. Nearly 3:1, driven by boundary, not measurement error.

**Producible:** yes, and better than the syndicated version, because the
COUNT × RATE × VALUE arithmetic can be shown. COUNT is nearly always free
government data. All five corpus filings use this formula.

**Why first:** market share is meaningless without it — a percentage needs a
denominator — and we already know its parameter, so it is the cleanest proof
that the generalization works.

### 2. Financial benchmarks — BUILD

**Parameter:** whose margin. One company's margins are not the industry's, and
the corpus economics brief already says so.

**Producible:** yes, and this is the surprise. IRS SOI gives margins and net
income by industry; Economic Census gives receipts and payroll; QCEW gives
wages. A defensible margin benchmark is free.

**Caveat:** US only. Everything in that table is a US federal source.

### 3. Regulation — BUILD

**Parameter:** which jurisdiction. Unstated, this silently becomes "the US",
which is wrong for most markets anyone asks about.

**Producible:** yes. Statutes and regulator publications are public and
authoritative — the rare case where the free source is the *primary* source
rather than a proxy for one.

**Evidence:** 5/5 in the S-1 corpus. Nothing else scores that.

### 4. Concentration and barriers to entry — BUILD

**Parameter:** the same measure dimension market share already has, because
concentration is computed from shares.

**Producible:** partly. Census gives concentration ratios and HHI for US
industries free. Barriers to entry are reasoned from regulation, capital
intensity and filings rather than measured — that is a judgment section and
should be marked as one.

### 5. Growth — BUILD, with a stated limit

**Parameter:** the period, and whose forecast. A CAGR without both endpoints
cannot be checked.

**Producible:** history yes, forecast no. Historical series are free from BLS
and Census. Forward projections are the most consistently paywalled figure in
this whole domain, and where a public programme funds the market its own
projections beat any analyst CAGR — agilon does exactly this with CMS.

**Do not fabricate a forecast.** Report published ones with attribution, or
report that none exists.

### 6. Geographic breakdown — BUILD LATER

**Parameter:** the rings, and whether each is counted or scaled.

**Producible:** yes for the US, via CBP and QCEW at county level. This is
agilon's $175B → $80B → $24B narrowing, and it was the best section in the
corpus. It is later only because it is US-shaped and most questions so far
have been worldwide.

### 7. Porter's five forces — BUILD WITH CARE

**Parameter:** the market boundary, which decides what counts as a substitute.

**Producible:** as structured judgment over sourced facts, not as measurement.
Four of the five forces can be grounded — supplier and buyer concentration from
filings, substitutes from the boundary, rivalry from concentration. It must be
labelled as reasoning, or it becomes the kind of confident unsourced prose this
whole project exists to avoid.

### 8. TAM — BUILD; SAM and SOM — REFUSE

TAM is a research output. SAM and SOM are functions of one company's
capabilities, coverage and sales capacity, and we do not have the company.
Producing them anyway would mean inventing the constraints. Say so instead —
that refusal is more useful than a number.

### 9. Voice of customer, win/loss, buyer personas — CANNOT BUILD

These need primary interviews and surveys. They are two of the four core
components of commercial due diligence, so this is a real limit on how much of
a CDD we can replace, and it should be stated plainly in the product rather
than approximated with public proxies.

This is also the honest answer to "what is the paid research actually selling."
Some of it is construction we can match. Some of it is **access to people we
cannot phone.**

---

## Build order

1. Generalize the `Measure` pattern into a report-type parameter, so a type
   declares its fixed-before-research dimension the way market share declares
   its basis.
2. Port **market size** through it — parameter already known, and market share
   depends on it.
3. Add **financial benchmarks** and **regulation** — both free-sourceable, both
   high-frequency in the corpus.
4. Port the four existing registered types onto the same handoff so the
   pipeline is uniform.
5. Add **concentration**, **growth**, **geographic rings**.
6. Decide separately whether to ship the judgment-shaped types (five forces)
   and how to mark them.

Each type gets the same treatment market share now has: a named parameter, one
report per value of it, an honest empty report when the basis is unsourceable
for that particular market, and a card in the gallery that says which basis it
is on.
