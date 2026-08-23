# Compared to what?

```bash
deckscope run deck.pdf --opportunity
deckscope demo --opportunity        # illustrative figures, no keys needed
```

Off by default: it costs extra calls, and on a deck with no publicly traded competitors
it has less to say.

---

## The gap this fills

Every other part of DeckScope answers "is this deck's story consistent with its market."
None of it answered the question an investor is actually holding: **against what
alternative?**

When a deck names an incumbent that happens to be publicly traded, the alternative is not
hypothetical. You could buy the incumbent. That is the real benchmark, and it was the one
thing DeckScope never measured against.

---

## Why there are no return forecasts

The obvious version of this feature emits "estimated 5-year return: 3.2x, confidence:
medium". DeckScope does not, and the reason is not squeamishness.

No model knows what a seed-stage company will be worth in five years. A number like that
has the *shape* of analysis without the substance, and attaching a confidence rating makes
it worse — it is precision applied to a guess. It would also be, by a wide margin, the
least supportable claim in a project whose whole character is refusing to state things it
cannot cite: DeckScope drops citations to sources that were never supplied, downgrades
"strong evidence" claims that cite nothing, and reports an empty bibliography rather than
inventing one. A fabricated return projection sitting at the top of the report would undo
all of that.

**So the question is inverted.** Rather than predicting an outcome, DeckScope computes the
outcome that would be *required* to match each benchmark.

That is more useful anyway. "This needs to reach roughly $27M ARR within five years, and
the base rate for that is about 4%" tells you what to go and verify. "3.2x" tells you
nothing you can act on.

---

## What it actually computes

All arithmetic, all checkable by hand:

```
ownership at entry   = ask / post-money
ownership at exit    = entry x (1 - future dilution)
exit value required  = (ask x target multiple + preference stack) / ownership at exit
implied revenue      = exit value required / category exit multiple
```

Worked, for a $4M ask on a $24M post at the defaults:

| Step | Value |
|---|---|
| Ownership at entry | 4 / 24 = **16.7%** |
| After 50% future dilution | **8.3%** |
| Proceeds needed for 3x | 4M x 3 = 12M |
| Plus 1x preference ahead | + 4M = **16M** |
| Exit value required | 16M / 0.083 = **$192M** |
| Implied revenue at 6x | **$32M ARR** |

Then the same calculation is repeated with the target multiple set to what each listed
competitor **actually returned** over the period — so "beating Microsoft" becomes a
specific revenue number rather than a sentiment.

---

## The assumptions are the answer

Every figure above rests on four inputs, and the report prints them beside the result:

| Assumption | Default | Flag | Why it matters |
|---|---|---|---|
| Future dilution | 50% | `--dilution 0.6` | The single largest lever. 30% vs 70% dilution more than doubles the required exit. |
| Exit revenue multiple | 6x | `--exit-multiple 10` | Category-dependent and cycle-dependent. |
| Horizon | 5 years | `--horizon 7` | Sets the growth rate implied by the requirement. |
| Preference stack | 1x | config only | What later investors take before this round sees anything. |

These are conventional defaults, not authoritative ones. Change them and every number
changes — which is the honest position, because the range of plausible outcomes really is
that wide.

**One caveat the report states itself:** where a deck gives a monthly growth rate,
DeckScope computes how long the requirement would take at that rate — and immediately says
that the extrapolation assumes a rate which essentially never holds, because growth decays
as the base grows. Read it as a floor on difficulty, not a schedule.

---

## Where the numbers come from

| What | Source | Notes |
|---|---|---|
| Is this competitor listed, and its ticker | Market-data backend | `search` by default — no extra key |
| Market cap, revenue, historical returns | Same | Marked `provenance` so you know whether it came from an API or a news sentence |
| Base rates for stage and category | Research backend, cited | **Uncited rates are dropped**, not included |
| Everything else | Arithmetic | Reproducible by hand from the table above |

The search backend is deliberately conservative: it rejects a "ticker" that is really
prose, and rejects a five-year return outside a plausible band, because an unconverted
percentage silently entering the arithmetic would corrupt every figure downstream.

**Three states, kept distinct:** *listed* (here is the ticker), *private* (positive
evidence it is not investable), and *unknown* (nothing found — which is not the same as
"no").

### Adding a market-data API

```python
from deckscope.market_data import register_market_data
from deckscope.market_data.base import MarketDataProvider, Listing

class MyFeed(MarketDataProvider):
    name = "my_feed"
    precision = "exact"

    def lookup(self, company, *, context=""):
        row = my_api.quote(company)
        return Listing(name=company, ticker=row["symbol"],
                       market_cap=row["cap"], total_return_5y=row["ret5y"],
                       provenance="api")

register_market_data(MyFeed)
```

Then `opportunity: {market_data: my_feed}`. Same registry pattern as providers, research
backends and renderers.

---

## Absorption risk

The other half of "compared to what". A category can be real, growing, and still a bad
place to be — because it stops existing.

Antivirus. File sync. VPN. Screen sharing. Password management. Basic monitoring. Each was
a genuine market with funded companies in it, and each was substantially absorbed by a
platform that already owned the customer relationship. The companies were not
out-competed; the market stopped being separate.

So the market analysis reports:

- **Verdict** — product, contested, or feature
- **Horizon** — already happening, through unlikely this decade
- **Likely absorbers** — who, what they already own that makes this a natural extension,
  and **what signals are already visible**: shipped features, acquisitions, job postings,
  roadmap statements. Evidence, not speculation.
- **Precedents** — only where the mechanism genuinely matches
- **What would prevent it** — the specific things that keep a category standalone:
  regulatory moat, data network effects, workflow depth, a buyer who will not consolidate

The prompt explicitly permits "unlikely this decade" as an answer. Manufactured concern is
as useless as manufactured confidence.

---

## Saturation, with numbers

"Concentrated" and "fragmented" cannot distinguish a wide-open wedge from a played-out
category, so the market analysis also reports:

| Field | Why |
|---|---|
| Funded competitors found | A count, not an impression |
| New-entrant trend | Accelerating / steady / slowing / stopped |
| Pricing direction | Compression is the clearest saturation signal there is |
| Consolidation activity | Recent acquisitions in the category |
| Lifecycle stage | Emerging through declining |
| Room for a new entrant | Wide-open / a niche remains / crowded but differentiable / effectively closed |

A market with three players and no new entrants in two years is a completely different
proposition from one with thirty and a new seed round every month, and both can be
described as "concentrated".

---

## Open source: the leading indicator

Where a category has an open-source dimension, it is the best available predictor of
whether a platform vendor will absorb the market — better than size, growth or funding.

**The mechanism.** While open source is meaningfully behind, commercial products are
differentiated on capability. Customers pay because they cannot get the thing free, and
the market is healthy. Once open source reaches rough parity, capability stops being the
differentiator, and whatever remains is packaging, operations, support and distribution.
A platform vendor already owns all four. It does not need to build a better product —
only a good-enough one it can give away — and the mid-market has nowhere to stand.

**Why parity alone is the wrong test.** Two cases with the same open-source position and
opposite outcomes:

| | Open source | What was left | Outcome |
|---|---|---|---|
| Docker / Kubernetes | at parity | registry, packaging, **distribution** | Could not monetize |
| Snowflake | credible alternatives throughout | **operational burden at scale**, governance | Grew regardless |

Distribution is what platforms *are*, so a company whose remaining advantage is
distribution is defending the hill the giant already occupies. Operational burden at
petabyte scale is expensive to give away even for a hyperscaler. Same commoditization
pressure; different residual; different result.

So DeckScope records both halves and derives the reading from the combination:

```
bundling risk = how far parity has progressed
              x how cheaply a platform could reproduce what remains
```

Classified by kind, since kind predicts replicability:

| Remaining differentiation | Cheap for a platform to reproduce? |
|---|---|
| distribution, packaging | Yes — it is their core asset |
| operational, support | Mostly — a hyperscaler can fund it |
| integrations | Often |
| workflow depth, data network effects, compliance | No — slow and expensive |

A company survives on its **best** defence, not its average one, so a single durable moat
among several fragile ones is enough to move the reading.

Two adjustments on top: a **narrowing** gap raises the level one step, a **widening** one
lowers it; and where the derived signal **disagrees** with the market agent's own
product-or-feature verdict, the report surfaces the disagreement rather than quietly
picking a side.

**Other things it captures:** whether pricing pressure from the free alternative is
already significant (which usually precedes bundling rather than following it), what the
company's own relationship to open source is, and for companies built *on* open source,
whether a cloud vendor could offer the same thing as a managed service.

Where a category genuinely has no open-source dimension, `applicable: false` and the
section is skipped — rather than an invented project being used to manufacture a signal.

## Adjacent markets

What the category touches: what it is **converging with**, what **substitutes** it (often
"they hire people instead"), and where the company could **expand**. Frequently the
expansion path is the answer to absorption risk — the leaders in absorbed categories
generally survived by moving upmarket into workflow, not by defending the core feature.

---

## Reading the output

The section is called **"Compared to what?"** and contains:

1. A headline stating the requirement, never a prediction
2. Each named competitor, whether you could buy it, and its actual figures with sources
3. What this company would have to reach, per benchmark
4. The assumptions, in a collapsed block
5. Sourced base rates, with populations and caveats
6. Anything that could not be determined, said plainly

If no competitor is listed, it says so and falls back to a 3x venture reference. If the
deck omits the ask or the valuation, the ownership maths cannot run and it says that
rather than inventing inputs.

---

## Limits

- **The listing lookup can be wrong.** The search backend reads figures out of prose. It
  marks its own provenance, and a listing with no source ID carries a warning in the
  report — check before relying on it.
- **Historical returns are not future returns.** Using MSFT's last five years as the bar
  for the next five is a convention, not a prediction about Microsoft.
- **Base rates may not transfer.** Populations differ by vintage, geography and selection.
  Each rate carries its caveat for that reason.
- **Absorption risk is a judgement.** The signals are evidence; the horizon is an opinion
  about them, and it is labelled with a confidence.
- **None of this is advice.** It is arithmetic with the assumptions exposed, so you can
  disagree with them precisely.
