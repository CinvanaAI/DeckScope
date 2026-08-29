# What DeckScope is for

The record of a planning pass that started from "What is a pitch deck?" and
worked down to code. Written 2026-08-28. Every claim below about what the
product does was executed before being written; the deliberate refusals at the
end are commitments, not omissions.

## What a pitch deck is

A pitch deck is a persuasion document. Ten to twenty slides built to make one
reader take one action — invest — and every number in it was chosen, framed,
and rounded by the party that benefits from the reader believing it. It is not
a lie, usually. It is a best case: the biggest defensible market definition,
the steepest defensible growth window, the competitor list that flatters.

That is the product's reason to exist. The deck's numbers cannot be evaluated
by reading the deck, only by reading the world the deck describes — and the
person receiving the deck rarely has the time to do that reading before the
meeting.

## Who is holding it

**The investor** (primary — the default lens, and the guest this build was
readied for). Their end game is not "a score". It is walking into the founder
meeting knowing more about the market than the founder expects them to know,
holding questions the founder has not prepped for. Everything above the fold
serves that: what the deck claims that evidence does not support, what it
leaves out, what could not be established, and what to go find out next —
with a source ID on anything they intend to say out loud.

**The founder** (`--lens founder`) wants the same audit run against
themselves before an investor runs it. Same machinery, opposite chair.

**The analyst** wants the underlying market evidence with the deck's framing
stripped out — which is what the market reports half produces, deck or no
deck.

## Was this "too report heavy"?

Partly, yes — and the diagnosis mattered more than the admission. The report
engine grew ahead of the deck journey because reports are where the honest-
sourcing machinery lives, and that machinery is the hard part. But the
primary persona arrives holding a deck, and for a while the product greeted
them with a market-report form: the builder's newest feature where the
visitor's task should be.

The resolution was not to demote the reports. It was to put them in their
place in the journey: **the deck journey is the product; the market reports
are its evidence layer.** The deck analysis reads the deck, the scoper
decides which market this really is and which yardsticks its claims lean on,
and the specialists then produce the reports that let a reader check the
story — one report per measure, each stating on its face what it measures.
Reports are also reachable directly, second on the page, for the analyst who
has no deck. Both doors go through the same engine
(`marketreport.scoping.dispatch_for_deck`), so they cannot drift apart.

## What the client wants → what exists

Everything in the left column was derived by sitting in the client's chair;
the right column was verified by running it.

| The investor wants | Provided by |
| --- | --- |
| "Is the TAM real?" | market-size reports per price level, with the COUNT×RATE×VALUE arithmetic shown and missing terms named, never substituted |
| "Who actually holds this market?" | market-share reports per basis (units ≠ revenue, kept as separate documents) |
| "Is the growth story someone else's number?" | growth reports; the deck's figure is compared against independently retrieved ones |
| "What did the deck leave out?" | the omissions section, with its own provenance |
| "What would I have to believe?" | the claim-by-claim audit; contested claims carry the source that contests them |
| "Is this worth my fund's money?" | the opportunity-cost arithmetic, defaults stated, every step shown so the reader can disagree with it |
| "Can I trust any of this?" | citation audit over the final artifact; a headline assembled by code from counts; `deckscope check` grading the machinery against recorded pages where fabrication can never be offset by recall |

## The deliberate refusals

These are load-bearing. Each one was considered and declined for a reason,
and building it badly would cost the product its only real asset — that it
does not bullshit.

- **No comps engine.** "Your ARR is above the median seed comp" requires a
  dataset of private seed rounds nobody publishes reliably. The demo once
  implied this capability; that line was removed. If a comps claim ever
  appears, it will carry a source or it will not appear.
- **No SAM/SOM.** Serviceable market math requires knowing the company's
  channel and capacity — facts held by the founder, not the web. A SAM
  computed without them is TAM wearing a costume.
- **No investment advice.** The report ends at "here is what is supported,
  contested, missing, and uncheckable." The decision is the reader's job,
  and the product says so on the page.
- **No API keys through the browser.** Setup lives in the terminal wizard.
  Teaching users to paste secret keys into web pages is a habit this tool
  refuses to teach, and the app's unconfigured screen explains exactly that.
- **The scoper refuses rather than guesses.** A deck with no discernible
  market produces zero reports and a stated reason. Nothing is invented for
  the sake of having output.

## The engineering posture

One shared engine per capability (CLI flag and app checkbox call the same
function). Refusal over guessing at every boundary. Every defect found in
live runs is pinned by a regression test before it is fixed — 480+ tests run
by a dependency-free runner, because the day the suite silently ran 16 of 47
tests is documented in `scripts/run_tests.py`. A custom linter with a
name-resolution pass. Crash handling that writes the full story to a file
and shows the guest one calm sentence (`DECKSCOPE_RAW_ERRORS=1` for the raw
traceback). A `run.log` flight recorder beside every run's outputs, and the
run's cost — seconds, model, tokens — printed on the terminal receipt.

## The quality doctrine

A second planning pass (2026-08-29) graded not the machinery but the answer —
a finished report read end to end in the investor's chair, against the bar of
a first-rate diligence memo. The diagnosis in one line: **the computed parts
were honest and the judgment parts were unbound.** What that reading found,
and what now binds them:

- "Assessment: Contradicted" rendered directly above "no evidence was
  supplied." Now: any assessment — supported included — with no citation is
  downgraded to unverifiable by the validator, with the downgrade printed on
  the claim. Agreeing with the deck for free is still a verdict with nothing
  behind it.
- "LEAN NO · confidence: low" rendered on a run that cited nothing external —
  the deck graded by a model's priors, dressed as a conclusion. Now: zero
  cited sources withholds the verdict outright, in the block every renderer
  builds from, with the reason printed where the verdict would have been.
- Ten findings read as ten equal dings. Now: contested claims carry
  **materiality** — fatal, damaging, or cosmetic — answering the one question
  a list cannot: *does the investment story survive this claim being
  corrected?* The canonical move: a tenfold TAM overstatement whose own SOM
  survives the correction costs credibility, not the thesis. Ungraded
  materiality is dropped, never defaulted — a faked severity is worse than
  none.
- The deck's own arithmetic was never checked. Now: `deckscope/consistency.py`
  runs deterministic cross-checks before anything external is consulted —
  TAM ≥ SAM ≥ SOM, the growth claim against the plan's implied monthly rate,
  price × customers against revenue, LTV/CAC as quoted against as computed —
  and reports conflicts with the arithmetic shown, consistencies as facts,
  and unrunnable checks with the missing input named. These are the strongest
  findings in the report because the founder cannot argue with either number:
  both are theirs. The parser refuses per-seat prices and annual-vs-monthly
  comparisons rather than manufacture a contradiction.
- The market reports never came back to the deck. Now: every dispatched
  report is read back against the claim that dispatched it —
  `marketreport/reconcile.py` produces one document per run: the claim, what
  the report established (with its source IDs and stored panel id), and the
  bearing of one on the other. An unanswered report reconciles too: "nobody
  publishes this" means the deck's number rests on something no reader can
  check, which is a finding, not a failure.
- Investor reports assigned the founders homework. Now the investor lens's
  actions are the reader's own diligence moves; fixing the deck belongs to
  the founder lens.

## Honestly unproven

The three-agent pipeline has not been proven better than a single careful
prompt on a real model at scale (the benchmark harness exists; the paid runs
have not been bought). The scoper's judgment quality on real decks has been
exercised through the manual spool, not batch-graded. The README's Status
table is the authoritative list, kept deliberately unvarnished.
