# The market report schema, derived from filings

Cycles 1–2. Everything here comes from documents on disk in `sections/` and
`studies/`, not from a description of what a market report ought to contain. Where
I am generalizing from too few examples, it says so.

Corpus: Klaviyo (B2B SaaS, 2023), FIGS (consumer-professional apparel, 2021),
Cricut (consumer hardware, 2021 — the commissioned study itself), agilon health
(Medicare primary care, 2021), Privia Health (physician enablement, 2021), plus
U.S. Lighting Group as a negative control.

> **Cycle 2 headline:** the formula survived contact with regulated healthcare
> services, but the corpus exposed a constraint that changes the product. **The
> VALUE term is proprietary in every single filing.** See §1a. This is the first
> thing the evidence has told me that I did not already believe.

---

## 1. The finding that matters

**All three size their market with the same formula, and the count always comes
from government data.**

```
market size  =  COUNT of units  ×  RATE that qualify  ×  VALUE per unit per year
```

| | COUNT (base population) | RATE (qualifying filter) | VALUE per unit | Result |
|---|---|---|---|---|
| **Klaviyo** | businesses in target geographies, from Analysys Mason / Statista | segmented by employee-count band (Micro/Small/Medium/Enterprise) | own average ARR per customer, per band | $16B SAM / $34B US TAM |
| **FIGS** | 20M+ healthcare professionals, **from the Bureau of Labor Statistics** | ~85% now buy their own uniforms | implied ~$600/professional/year | $12.0B US |
| **Cricut** | adult population 18+ per country, extrapolated | survey incidence: "made ≥1 creative project in 12 months" | — (headcount TAM, not dollarized) | 85M SAM / 402M TAM |
| **agilon** | 17.5M Medicare beneficiaries affiliated with independent PCPs, **from CMS** | independent = "not employed by health systems or insurance providers"; then a named-states geographic filter | "$10,000 estimated average annual revenue per Medicare member **to us**" | $175B (2020) |
| **Privia** | national healthcare spend, **from CMS** | — (no narrowing shown in the captured range) | — | $3T headline |

Klaviyo paid two vendors for a business count that **County Business Patterns
publishes free — by NAICS, by geography, by employee-size band.** FIGS cited BLS
directly for its base and paid Frost & Sullivan for the rate, the value and the
growth.

So the expensive part of a commissioned study is not the count. It is the
**rate** and the **value per unit**. That is where a paid survey earns its money,
and it is where we will have to be cleverest or most honest.

## 1a. The constraint that changes the product

**Every filing sources the VALUE term from its own books.**

- Klaviyo — "our respective average ARR per customer per segment"
- agilon — "$10,000 estimated average annual revenue per Medicare member **to us**"
- FIGS — market size from a commissioned study, share computed against its own revenue
- Cricut — sidesteps it by never dollarizing; the TAM is a headcount

There is no "us" in a standalone market report. **The one term nobody publishes
is the one every filing takes from internal data.** That is not a gap to close
later by trying harder; it is structural, and it decides what our product can
honestly claim.

Three ways out, in descending order of defensibility:

1. **Industry average revenue per establishment**, from the Economic Census —
   real, free, and published by NAICS. Gives a market total that is *the
   industry's* revenue rather than *a company's* opportunity. Different question,
   honestly answered.
2. **Per-capita or per-beneficiary spend** from CMS (healthcare), the Consumer
   Expenditure Survey (households), or BLS OEWS (wages as a proxy for
   labour-driven spend). Also real, also free.
3. **A stated assumption with a range**, flagged as an assumption — which is what
   a filing does when it says "we believe our opportunity outside the United
   States is at least as large."

Option 1 is the one to build. It reframes the deliverable from "your addressable
market" to "this industry's measured size", which we can actually source, and
which is the honest thing to sell to someone who has no revenue yet.

### What this means for the sizing agent

Two archetypes, and the router should pick between them from the customer
definition:

- **B2B** — establishments × ARPU by size band. Count from CBP/Economic Census
  (free). ARPU is the gap.
- **B2C / professional** — population or workforce × incidence rate × annual
  spend. Count from ACS or BLS OEWS (free). Incidence from behavioral surveys
  (BLS American Time Use Survey, CEX) where one exists; otherwise the gap.
- **Programme-funded** *(new in cycle 2)* — start from a national spending
  account and narrow. agilon and Privia both begin at CMS. The base is a
  government programme's own published enrollment and spend-per-beneficiary, and
  the forward projection uses **that programme's own growth rates**, not an
  analyst CAGR. Applies to healthcare, education, defence, infrastructure — any
  market whose money originates in a public budget, which is a large share of the
  economy and the easiest of the three to source well.

### Concentric narrowing (new in cycle 2)

agilon does not report one number. It reports three nested rings, each sized:

| Ring | Size |
|---|---|
| Beneficiaries with independent PCPs, in target states | $175B |
| …of which, states where it already has a partner or signed LOI | $80B |
| …of which, counties where it already has a partner or signed LOI | $24B |

This is far more useful than a single figure and it is trivially reproducible
from government data, because the narrowing is purely geographic. Our report
should do this by default rather than as an option: **national → state →
county**, each sized, using CBP or CMS at each level.

---

## 2. Sections actually present

Ordered by how consistently they appeared. Two of three is marked as such — with
n=3 that is a weak signal and the next cycle should confirm or kill it.

| Section | In corpus | Notes |
|---|---|---|
| Market definition / boundary | 3/3 | Always states which geographies and which customer types are in scope, explicitly |
| Size, with method stated | 3/3 | Never a bare number. Always the arithmetic — see §1 |
| Growth, as CAGR to a named year | 2/3 | FIGS: "6.1% CAGR, $12.0B 2020 → $16.0B 2025". Klaviyo omits a category CAGR entirely |
| Own share of the market | 2/3 | FIGS "approximately 2.1%"; Cricut "more than 4% penetration". Computed against the size just stated |
| Why the market is structurally attractive | 3/3 | FIGS: "non-discretionary, recession resistant, less susceptible to fashion risk, recurring replenishment". This is qualitative and load-bearing |
| Incumbent weakness | 2/3 | FIGS: "operated for over 100 years with little change"; Klaviyo: "Key Limitations of Existing Solutions" |
| Customer problem, before any market data | 3/3 | Always precedes sizing. "Challenges Facing Our Customers" |
| Adjacent / expansion market, sized separately | 3/3 | FIGS: 40M non-healthcare uniform wearers; Klaviyo: verticals beyond retail; Cricut: countries beyond the primary four |
| International, sized separately from domestic | 3/3 | Always broken out, never blended into one number |
| "Industry and Market Data" disclaimer | 3/3 | A named section governing every figure in the document |
| Forward projection from the source's own growth rates | 1/5 | agilon applies CMS's projected enrollment and spend-per-beneficiary growth to reach $253B by 2025. Footnoted to the source. Better practice than an analyst CAGR |
| Concentric geographic narrowing | 1/5 | agilon: $175B → $80B → $24B. Only one filing does it; it is the best thing in the corpus |
| TAM cross-referenced to its own risk factors | 1/5 | agilon: "In considering our total addressable market, please also see Risk Factors—Risks Related to Our Business" |
| Regulatory regimes, named | 5/5 **in the Risk Factors Summary** | Resolved in cycle 2 — see §4. agilon names the False Claims Act, corporate practice of medicine, CMS methodology risk, reimbursement-rate risk |
| Competitive landscape, named individually | past truncation | Still unverified |

---

## 3. Rhetorical patterns worth copying, and one worth refusing

**Copy: the method sentence.** Every sizing claim is followed by how it was
computed. "We calculate this opportunity using business count data sourced from
X, focusing on the number of businesses in the geographies we operate in,
segmenting them into bands by employee count, then multiplying by our average ARR
per segment." A reader can disagree with that. They cannot disagree with "$34
billion."

**Copy: separating what is measured from what is asserted.** FIGS attributes the
$12.0B to a named, dated study. The "40 million uniform-wearing workers" is
attributed too. The claim that those markets are "ripe for disruption" is flagged
as belief — "in our view".

**Copy: sizing expansion separately.** Adjacent markets never get folded into the
headline number. They are a second number with their own basis.

**Refuse: the definitional stretch.** Cricut's TAM screen — anyone who "likes,
buys, used to make, or is interested in" custom items — resolves to most adults
alive, producing a 402 million person TAM. Klaviyo's global figure is "we believe
our opportunity outside the United States is at least as large as our domestic
opportunity", which is an assumption doing the work of a measurement and doubles
the headline to $68B. Both are disclosed clearly enough to be caught, which is
the disclosure regime functioning. **Our report should compute these and then
name them.** That is the axis where we beat a bank rather than imitate one.

---

## 4. What I could not establish

Stated rather than assumed away.

### Truncation is now bounded, not fatal *(cycle 2)*

Reliably **inside** the 142KB window, in all five filings:

- the whole Prospectus Summary — market definition, sizing *with its method*,
  growth, own share, customer problem, incumbent weakness, adjacency,
  international split
- the **Risk Factors Summary** — the same market described defensively, naming
  regulatory regimes and structural threats in bullet form

Reliably **outside** it: the full Business/Industry narrative, the Competition
section with rivals named individually, and the full Government Regulation
section.

This matters more than it sounds. **A filing describes its market twice, with
opposite incentives** — the Business section is the sell-side case, Risk Factors
is what the law obliges them to admit — and agilon explicitly tells the reader to
read the TAM against the risks. Both halves are in range. The schema should carry
a *case* view and a *risks* view, and treat disagreement between them as a
finding rather than something to reconcile.

- **The competition section, with rivals named one by one, remains unverified.**
  Nothing in this corpus contains one. The Risk Factors Summary names categories
  of competitor, not companies.
- **n=5, and the sample is still lopsided.** Count × Rate × Value held across B2B
  SaaS, professional apparel, consumer hardware and Medicare primary care — which
  is a genuinely broad spread and stronger than cycle 1. Still untested on:
  industrial, energy, restaurants/franchise, financial services, and anything
  outside the United States.
- **Privia is the weak case and worth keeping as one.** It opens at $3 trillion of
  national health spend and, within the captured range, never narrows. That is
  the "big number" style the product exists to push back on, and it appears in a
  real underwritten IPO — so the failure mode is not confined to bad pitch decks.
- **Where a bank genuinely beats us:** Cricut's rate came from a bespoke YouGov
  survey of 1,000+ people per country. FIGS's 85%-buy-their-own came from a
  commissioned Frost & Sullivan study. We cannot commission primary research. For
  some markets a public substitute exists (ATUS for participation, CEX for
  spend); for many it does not, and the honest output there is a range with the
  assumption named, not a point estimate.
- **Charts are images.** Klaviyo's Business section ships as thirteen .jpg files
  totalling ~12MB. Any figure that appears only in a chart is invisible to us.

---

## 5. Next cycle

Per the build-a-tick-then-adjust loop, the schema changes only when a *filing*
shows something absent here.

Cycle 2 closed: truncation is bounded (§4), and the formula survived regulated
healthcare services. Cycle 2 opened one thing that outranks everything else.

1. **Build the sizing agent against §1a option 1** — Economic Census average
   revenue per establishment, by NAICS, with concentric national → state → county
   narrowing per §1. This is the first executable piece and it is fully sourceable
   from free data. Everything else in the schema is retrieval; this is the
   construction people pay for.
2. Test it by reproducing agilon's $175B / $80B / $24B rings from CMS directly —
   a case where the filing shows its arithmetic, so we can check ours against it.
   This is the first real external loss signal available to us.
3. Add filings from industrial, restaurants/franchise and financial services. The
   competition section remains unverified; a smaller filing may reach it.
4. Build the corpus filter and test it against U.S. Lighting Group.

## 6. Operational notes on retrieval

Learned the hard way, recorded so the next cycle does not relearn them.

- **EDGAR full-text search responses are expensive** — a single query cost ~14k
  tokens of context because the JSON prints inline. Document fetches are cheap
  by comparison: they exceed the display limit and land on disk, costing only the
  error message. Prefer fetching over searching wherever a URL can be constructed.
- **`&` and `'` break the fetch proxy.** `"Consent of Frost & Sullivan"` and
  `"Portillo's Inc."` both failed — one silently, one on a 180s timeout. Phrase
  queries must avoid both characters.
- The filing **directory listing** gives every document's byte size before
  fetching, which is how to tell a 3.3MB filing from a 400KB one in advance.
- `EX-99.x` occasionally carries the commissioned market study itself rather than
  a summary of it. Those are small, complete, and the single most valuable
  document type found so far. Cricut's is the only one located; finding more is
  worth real effort.
