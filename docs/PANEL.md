# The panel

Several AI services analyze the same deck, then read each other's work, argue, and revise.

```bash
deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-4o gemini
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

### 4. Consensus

A chair — by default the first panelist's backend, overridable with `--chair` — receives
every final analysis, every revision log, and the **measured** agreement numbers, and
produces the consensus report.

---

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
| `contested_claims` | claim IDs where panelists reached different assessments |
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
training data and failure modes. `anthropic:claude-sonnet-5 openai:gpt-4o gemini` will
disagree more usefully than three Claude variants.

**Two is enough to be useful; three is the sweet spot.** Beyond four, cost and prompt
size rise faster than the marginal disagreement.

**Mixing a strong and a cheap model is a legitimate design.** The cheap one often catches
things the strong one glosses over, and disagreement between them is a signal to look
closer.

```bash
# a serious panel
deckscope panel deck.pdf --panel anthropic:claude-opus-5 openai:gpt-4o gemini:gemini-2.5-pro --rounds 2

# a cheap panel
deckscope panel deck.pdf --panel anthropic:claude-haiku-4-5-20251001 gemini:gemini-2.0-flash

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

A three-model panel on one lens is about five to six times a single analysis. The
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

## From Python

```python
from deckscope.ensemble import analyze_with_panel

result = analyze_with_panel(
    "deck.pdf",
    ["anthropic:claude-sonnet-5", "openai:gpt-4o", "gemini"],
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
                       ProviderConfig(name="openai", model="gpt-4o")],
              rounds=2, chair=ProviderConfig(name="anthropic"))
result = panel.run()
panel.render(result)
```

---

## From an AI assistant

Through MCP, the `analyze_deck_panel` tool takes the same arguments. See
[MCP.md](MCP.md).
