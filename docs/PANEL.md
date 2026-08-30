# The panel

Several AI services analyze the same deck, then read each other's work, argue, and revise.

```bash
deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-5.2 gemini
deckscope demo --panel        # see it work, free, no keys
```

---

## Why not just average them

The naive version of "use several models" is to run three and average the scores. That is
worse than using one, for two reasons.

Averaging destroys the only genuinely new information a panel produces: **where competent
analysts disagree**. A split panel on market sizing is not noise to be smoothed away — it
marks precisely where the evidence is thin enough that reasonable readings diverge. That
is where your own diligence should start.

And averaging rewards being agreeable. A model that hedges toward the middle scores well
against an average; a model that is right and alone scores badly. DeckScope's revision
prompt explicitly forbids this: *"Do not average toward the group. If the panel disagreed
with you and you were right, the revision should look almost identical to your original."*

---

## The four rounds

### 1. Independent

Each panelist runs the complete three-agent pipeline alone — its own deck extraction, its
own market research, its own comparison. In parallel threads, with separate cache
namespaces so they cannot share answers.

They do not know the other panelists exist.

**How independent is "independent".** Worth being precise, because the word does a lot of
work in claims about ensembles. Each panelist uses its own model and issues its own
search queries. But they all read the same deck, their research agendas are derived from
the same kind of extraction pass, and they frequently retrieve overlapping sources. If
the best available source on a market is wrong, every panelist inherits that error and
their agreement will look like corroboration.

This is **role-separated analysis with model diversity**, not independent market
discovery. The consensus report's reliability section says so, and names shared blind
spots where it can identify them.

### Citations across panelists

Each panelist numbers its own sources from S1, so their local IDs are not comparable.
Before any cross-review happens, DeckScope merges every panelist's bibliography into a
single global namespace, de-duplicating by URL, and rewrites each panelist's citations to
the merged IDs.

This matters more than it sounds. Without it — and an earlier version was without it —
Panelist B's "S1" resolves against Panelist A's bibliography, and a figure gets attributed
to a document that never contained it. A report that cites confidently and wrongly is
worse than one that does not cite at all.

### 2. Cross-review

Each panelist now receives every other panelist's **deck extraction, market analysis and
comparison** — not just the verdicts. Reasoning matters: two analysts can reach the same
verdict for incompatible reasons, and that is not agreement.

Panelists are **anonymized** as `Panelist A`, `Panelist B`. A model asked to review
"Claude's analysis" is being asked a different question than one reviewing "Panelist B's
analysis". The anonymization is there so the work is judged, not the brand.

Each returns a structured review:

| Field | What goes in it |
|---|---|
| `agreements` | substantive points where their analysis matches yours |
| `disagreements` | typed as **evidence** (one has a source the other lacks), **interpretation** (same evidence, different reading), or **weighting** (same reading, different view of what matters) |
| `errors_found` | material or minor, with why it is wrong and the source IDs |
| `evidence_they_have_that_you_lack` | |
| `blind_spots_they_caught` | |
| `position_changes` | what you concede, from → to, prompted by whom, and on what evidence |
| `positions_held` | what you keep, and the specific reason the challenge fails |
| `self_assessment` | what was honestly weakest in your own first pass |

The typing of disagreements matters more than it looks. "We disagree about the TAM"
is not actionable. "They cite S7, a regulator filing; I relied on S3, a vendor report"
is.

### 3. Revise

Each panelist rewrites its own comparison to reflect what it conceded — scores, claim
assessments and verdict all move, not just the wording — and logs every change with its
reason and what prompted it. Confidence rises when others independently confirmed it on
separate evidence, and falls when a serious challenge went unresolved.

A panelist that conceded nothing skips this round and its original stands.

### 4. Vote

Each panelist ranks the others' finished reports — not on whether they agree with it, but
on whether the conclusions follow from the evidence cited, whether figures are traceable,
whether it keeps "wrong" apart from "unproven" apart from "unverifiable", and whether its
confidence matches its evidence. An analysis that reaches a different verdict on better
reasoning is meant to rank *above* one that agrees on worse reasoning.

Rules that matter:

- **Nobody ranks themselves.** Enforced in the `Ballot` type, not just at tally time.
- **Borda count, not first-past-the-post.** With three or four panelists a plurality
  winner can be almost everyone's last choice.
- **A preference cycle is named, not broken.** If A > B > C > A, no ordering satisfies the
  panel and the report says so. That is a real finding: the panelists disagree about which
  *analysis* is strongest, not merely about the company.
- **A reason is required** with each ranking, so the vote is auditable.

Turn it off with `--no-vote`.

### 5. Consensus

A chair — by default the first panelist's backend, overridable with `--chair` — receives
every final analysis, every revision log, and the **measured** agreement numbers, and
produces the consensus report.

The chair's synthesis is the headline, but it is a committee document, and a committee
document can smooth away the disagreement that is the most useful thing here. So each
panelist's own report is kept intact and listed in the panel report, ordered by how the
rest of the panel ranked it. You get both: the synthesis, and the single-author versions
with the panel's own assessment of which is strongest.

---

## When does the panel stop?

There is no one right answer, so this is a strategy rather than a constant.

| `--strategy` | Behaviour | Use when |
|---|---|---|
| `adaptive` *(default)* | Looks at how the panel actually behaved after round 1, then delegates to one of the others. Records which it chose and why. | You don't want to think about it |
| `convergence` | Stops once positions stop changing and scores are stable. **Can skip review entirely** when the panel already agreed independently. | Cost matters and most decks are straightforward |
| `confidence_floor` | Keeps going while any panelist is low-confidence or claims are contested. When it hits the cap anyway, says so explicitly rather than presenting the result as settled. | A real decision rests on this |
| `fixed` | Exactly N rounds, regardless. | Reproducibility, benchmarking |

```bash
deckscope panel deck.pdf --panel anthropic openai --strategy convergence
deckscope panel deck.pdf --panel anthropic openai gemini --strategy confidence_floor --rounds 4
deckscope panel deck.pdf --panel anthropic openai --rounds 0      # no review at all
```

Three panelists who independently reached the same verdict with a tight spread do not need
introducing to each other, and `convergence` will skip straight to the vote — the report
records that it saved the rounds and why. Conversely, `confidence_floor` will refuse to
present a low-confidence result as settled just because it ran out of budget.

Every stopping decision is logged, and the panel report contains a collapsed table showing
the spread, agreement, position changes and contested claims after each round, with the
reason it continued or stopped. The run explains its own cost.

## Agreement is measured, not estimated

Asking a model "how much did the panel agree" produces a vibe. DeckScope computes it in
Python and gives the numbers to the chair as input:

| Metric | What it is |
|---|---|
| `verdict.distribution` | how many panelists picked each verdict |
| `verdict.agreement` | unanimous / majority / split |
| `score.spread` | max − min of the weighted totals |
| `score.stdev` | population standard deviation |
| `score.convergence` | tight (≤5) / moderate (≤15) / wide |
| `dimensions[d].spread` | per-scorecard-dimension disagreement; ≥3 marks it contested |
| `claims[].assessments` | the full claim × panelist agreement matrix |
| `contested_claims` | cluster keys where panelists reached different assessments |
| `single_panelist_claims` | claims only one panelist raised — silence, not disagreement |
| `movement` | per panelist: verdict and score before and after, positions changed and held |
| `total_position_changes` | how much the panel actually moved |

These appear in the report and in the `Panel`, `Claim agreement` and `Score spread`
sheets of the Excel output.

---

## What the report leads with

The panel report has a different shape from a single-model report, because it answers a
different question.

1. **Where the panel landed** — every panelist's verdict, score, drift and what changed.
2. **Summary** — the chair's narrative.
3. **What every panelist agreed on** — with *why it is robust* for each point.
4. **Where the panel split** — each position, its evidence quality, where the evidence
   actually points, and **what would settle it**.
5. **Claim-by-claim across the panel** — the agreement matrix, with contested claims
   flagged.
6. **Scorecard across the panel** — sorted by spread, so the most contested dimension is
   first.
7. **Minority report** — each dissent stated at its strongest, with why it deserves a
   hearing.
8. **What changed when the panelists read each other** — conceded, held, and each
   panelist's self-assessment.
9. **How much this agreement is worth** — including blind spots the whole panel may share.
10. **Annex** — each panelist's final analysis, with its revision log.
11. The usual References and Input integrity screen.

---

## How much agreement is actually worth

The report says this out loud rather than letting a reader assume consensus means truth:

- Models trained on overlapping data, reading the **same bibliography**, agree for
  correlated reasons. That is agreement about a source, not independent corroboration.
- Agreement reached **after** cross-review is more meaningful than agreement reached
  immediately — the second may just be a shared prior.
- Agreement reached **for different reasons** is stronger than agreement reached for the
  same reason. The chair is asked to distinguish these.
- Every panelist shares the same blind spot when the blind spot is in the source material.

Use panel agreement to raise confidence. Do not use it to establish fact.

---

## Composing a panel

**Diversity of provider beats diversity of model.** Two models from the same family share
training data and failure modes. `anthropic:claude-sonnet-5 openai:gpt-5.2 gemini` will
disagree more usefully than three Claude variants.

**Two is enough to be useful; three is the sweet spot.** Beyond four, cost and prompt
size rise faster than the marginal disagreement.

**Mixing a strong and a cheap model is a legitimate design.** The cheap one often catches
things the strong one glosses over, and disagreement between them is a signal to look
closer.

```bash
# a serious panel
deckscope panel deck.pdf --panel anthropic:claude-opus-5 openai:gpt-5.2 gemini:gemini-2.5-pro --rounds 2

# a cheap panel
deckscope panel deck.pdf --panel anthropic:claude-haiku-4-5-20251001 gemini:gemini-flash-latest

# a local panel, entirely offline
deckscope panel deck.pdf --panel openai_compatible:llama3.1:8b openai_compatible:qwen2.5:14b --research none
```

Save a default panel with `deckscope setup`, then just:

```bash
deckscope panel deck.pdf
```

---

## Cost and time

Roughly: *(panelists × a single run)* + *(panelists × one review call)* +
*(panelists × lenses × one revision call)* + *(lenses × one chair call)*.

A three-model panel on one lens costs far more than three single analyses:
the current fixture measures roughly 12× the single-run input tokens (the
table below shows the exact multiple from the last measured run), because
every review round carries the other panelists' full analyses inside each
prompt. The
independent round runs in parallel, so wall-clock time is closer to a single run plus two
sequential rounds.

`--rounds 0` skips review entirely and gives you parallel independent analyses plus the
measured agreement — cheap, and still more informative than one model.

---

## When a panelist fails

The run continues. The failure is recorded in `panelists_failed` and printed in the
report with its error message.

If only one panelist survives, the consensus verdict reads **"single panelist — no
cross-check was possible"** and the report states plainly that nothing has been
corroborated. It does not quietly present a one-model result as a panel finding.

---

## Is any of this better than one good prompt?

Now measurable, and the first numbers are worth reading carefully.

```bash
deckscope eval --mode pipeline baseline panel
```

On all nine shipped evaluation cases, under the built-in mock provider:

| | claim accuracy | claim citation | relative input cost |
|---|:--:|:--:|:--:|
| baseline (one prompt) | 0.333 | 0.667 | 0.2× |
| pipeline (three agents) | 0.333 | 0.588 | 1.0× |
| panel (three panelists) | 0.196 | 0.800 | 12.7× |

The panel scores *lower* on accuracy and *higher* on citation — it cites what it asserts
more reliably and gets more of those assertions wrong. **This is the mock**, a
deterministic fixture written for offline testing. It tells you the harness works end to
end and that the panel machinery produces a materially different analysis. It tells you
nothing about whether three real models reviewing each other beats one good model,
because no real model was involved.

### What is being scored, and what it costs

Two things in this table were wrong until recently, and both flattered the panel.

**The scored artifact.** The evaluator used to score the panelist the vote ranked
first. But `voting.tally` deliberately returns no winner on a tie or a preference
cycle — and on the shipped three-member demo every panelist scores 1.5, preferences
form an A > B > C > A cycle, and the panel correctly reports that there is no winner.
The evaluator sorted anyway and scored Panelist A, because alphabetical order broke the
tie. The published number was not the accuracy of a panel decision; it was the accuracy
of an arbitrarily chosen analyst. It now scores the **chair's consensus** — the artifact
the report leads with and a reader actually reads — which exists whether or not the vote
reached a decision. `consensus_verdict.call` and `claim_consensus[]` already carried the
same meaning as `verdict.call` and `claim_audit[]`; nothing was invented to make this
work, and the consensus rows now carry `source_ids` so the panel's own claims are
traceable.

**The cost.** The 3.0× figure was the sum of each panelist's independent pipeline —
what N separate runs would have cost — and excluded review, revision, voting and the
chair entirely. Those calls *are* the panel. Counted honestly the multiple is an order
of magnitude, and `stats.token_usage` now reports `independent_analyses` and
`panel_rounds` separately so the two are never conflated again.

What the suite does establish is that a tie means something: it separates the panel from
the pipeline by 14 points, so it is not blind to architectural differences, and every
multi-mode run reports whether the modes actually produced different analyses. A delta of
zero therefore means the modes agreed, not that the comparison never happened.

Note also that the pipeline ties the baseline exactly.

### The same suite, driven by a real model

The pipeline and baseline have since been run against a real frontier model, through
the `manual` provider's spool mode (see [PROVIDERS.md](PROVIDERS.md#bring-your-own-model-manual)),
which needs no API key. Both modes passed **43 of 43 checks** — every dimension at
1.000 — while the pipeline spent 6× the input tokens. The modes produced genuinely
different analyses, so the tie was measured rather than manufactured.

That did not settle the question in the pipeline's favour — it said the suite had no
headroom. Four harder **anchoring cases** were then written to attack the pipeline's
one structural claim, isolation, and answered by separate agents that saw only the
prompt. Over all nine cases the baseline passed 95 of 95 and the pipeline 94 of 95, at
9.5× the input tokens — the pipeline's single failure being a company it named from
world knowledge that appears in neither the deck nor the corpus. See
[EVALUATION.md](EVALUATION.md#the-anchoring-cases).

So across three evaluations the three-agent pipeline has never separated from a single
prompt on any measured dimension, and has now scored below it once. What it buys is the
standalone market analysis, not accuracy.

The panel has not been run this way. It would take roughly 90 exchanges rather than 15,
and the case for spending them is weak while the two cheaper modes still cannot be told
apart — if splitting one analyst into three roles buys nothing, the prior on nine roles
across three panelists is not encouraging. The interesting version of the panel
experiment is different: use genuinely different *models*, since the mock result hinted
that whatever helps comes from disagreement between analysts rather than from role
separation.

You can also run the control on your own decks:

```bash
deckscope run deck.pdf --mode baseline    # one prompt, one call per lens
deckscope run deck.pdf --mode both        # run each, then compare
```

`--mode both` writes both reports plus `mode_comparison.json`, and prints the differences:
verdict agreement, score gap, how many claims each examined, how many carried a citation,
how many blind spots each named, and what each cost in tokens and seconds.

It deliberately **does not declare a winner**. Whether the extra passes bought anything is
a judgement about reasoning quality that a count of claims cannot make. The comparison
tells you where to look.

The baseline is a real mode, not benchmark scaffolding — scaffolding rots when nobody runs
it, and roughly a third of the cost is genuinely the right trade on a deck you already
understand.

## From Python

```python
from deckscope.ensemble import analyze_with_panel

result = analyze_with_panel(
    "deck.pdf",
    ["anthropic:claude-sonnet-5", "openai:gpt-5.2", "gemini"],
    lens="investor", rounds=1, formats=["html", "pdf"])

print(result.consensus["investor"]["consensus_verdict"])
print(result.metrics["investor"]["contested_claims"])

for p in result.working:
    print(p.label, p.name, len(p.review["position_changes"]), "conceded")
```

Or with full control:

```python
from deckscope.config import ProviderConfig, RunConfig
from deckscope.ensemble import Panel

panel = Panel(config, [ProviderConfig(name="anthropic", model="claude-sonnet-5"),
                       ProviderConfig(name="openai", model="gpt-5.2")],
              rounds=4,
              strategy="confidence_floor",     # or a RoundStrategy instance
              vote=True,
              chair=ProviderConfig(name="anthropic"))
result = panel.run()
panel.render(result)

print(result.stats["stopped_because"])
print(result.votes["investor"].order, result.votes["investor"].winner)
for entry in result.round_log:
    print(entry["after_round"], entry["reason"])
```

Strategies are pluggable — subclass `RoundStrategy`, implement `_decide`, and pass an
instance. See `deckscope/panel/strategies.py`.

```python
from deckscope.baseline import BaselineAnalyst, compare_modes

analyst = BaselineAnalyst(config)
baseline = analyst.run()
analyst.close()
print(compare_modes(pipeline_result, baseline))
```

---

## From an AI assistant

Through MCP, the `analyze_deck_panel` tool takes the same arguments. See
[MCP.md](MCP.md).
