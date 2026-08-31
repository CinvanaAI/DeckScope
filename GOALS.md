# What this is for

The one-page version. Detailed build requirements live in [BUILD.md](BUILD.md);
what the market report must contain lives in
[market-corpus/SCHEMA.md](market-corpus/SCHEMA.md).

---

## The product

**An evidence engine: hand it a document that makes claims, and get back
the claims checked against public sources, the unknowns named, and the
questions that remain — with every figure traceable.** The sections below
describe the two verticals that proved the engine: the market report an
investment bank produces once at enormous cost, and the pitch deck read
against that evidence. New verticals are declarations over the same
engine, not new systems — and two more now ride it end to end, free and
keyless: grant/SBIR proposals against the federal funding record, and
nonprofit documents against the organization's own IRS filings. Both
are ungraded until the evaluation harness holds them to an answer key,
and say so in every report.

## The first vertical pair

**Produce, on demand, for any market, the document an investment bank produces
once — at enormous cost — when a company goes public.**

Every S-1 has an industry section. It is not a line-item SEC requirement; it is
market practice, shaped by liability and by bankers needing to justify a price.
It states a market's size *with the arithmetic shown*, its growth, its structure,
who competes, what it costs to operate, and what the rules are. It costs
millions to produce and thousands of examples are free on EDGAR.

That document is the deliverable. Not "a market report" in the abstract — that
specific document, generated for a market the user names, from data that exists
today rather than at some filing date in the past.

## Why this beats what already exists

**Against a bank:** we are not paid to make the market look big. A bank's
industry section is motivated — it exists to support a price. Ours can say "this
could not be established", which theirs never does, and can name a definitional
stretch rather than perform one.

**Against an analyst PDF:** those assert a number. A filing states a
*calculation* — "N businesses in these size bands × $R average revenue, from
these sources, as of this date". A calculation can be checked and disagreed
with. That discipline is the product.

**Against asking a chat model:** cost, ownership, confidentiality, and provider
choice. A deck under NDA cannot go to a third-party API at all. See NDA mode.

## The three things that must stay true

1. **The arithmetic is the deliverable.** Never a bare number. Every figure
   carries its operands, its sources and its date, or it is reported as not
   established.
2. **A missing term is not a zero.** When something cannot be sourced, say so
   and say why. A report that admits a gap beats one carrying a plausible number
   nobody can trace.
3. **The evidence decides, not the model.** Confidence is counted from what
   closed, not asked for. Verdicts are capped by what the research supports.
   Rules that decide anything are code, not prompt text.

## What is measured, and what is not

The formula every filing in the corpus uses:

```
market size  =  COUNT of units  ×  RATE that qualify  ×  VALUE per unit per year
```

**COUNT is free government data** — County Business Patterns, BLS, CMS, ACS.
Klaviyo paid two vendors for a number the Census publishes.

**VALUE is the hard one.** Every filing takes it from its own books —
"our average ARR per segment", "$10,000 revenue per member *to us*". A
standalone market report has no "us". The honest substitute is Economic Census
average revenue per establishment, which answers *"how big is this industry"*
rather than *"how big is your opportunity"*. Different question, correctly
answered, and the right one for somebody with no revenue yet.

## Where DeckScope fits

DeckScope is not the product. It is a **consumer** of the product: analysing a
pitch deck means generating the market report, then diffing the deck against it.
The claim audit, the blind spots and the ask-versus-requirement gap all fall out
of that diff.

## How progress is judged

**The loss must come from outside.** Filed S-1s are the test set — thousands of
them, free, written by people paid to get it right. Two ways to use them:

- **Structural parity.** Does our report contain what theirs contains? Is every
  claim sourced, every method stated?
- **Backtest.** Freeze the clock at a filing date and reproduce the section from
  data available then. Harder, because every source must be date-filtered.

What does *not* count: any score produced by our own mock provider. That
measures fixture maturity. It has already fooled me once — three rounds of
"improving" a fixture moved a number from 8% to 62% while the architecture never
changed.

## Non-goals

- Predicting whether a business will succeed.
- Replacing the user's judgment. The nephew who asked for $5,000 when the
  evidence says $10,000 is a *finding*; whether to fund him anyway is the user's
  call, and depends on things no dataset holds.
- Being cheap at the expense of being checkable.
