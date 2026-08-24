# Evaluation

```bash
deckscope eval                                  # score the shipped suite
deckscope eval --mode pipeline baseline         # compare the two architectures
deckscope eval --mode research pipeline baseline
deckscope eval --trials 3                       # measure stability
deckscope eval --provider anthropic --model claude-sonnet-5
```

Exits non-zero when any check fails, so it can gate a release.

---

## The problem this solves

Every audit of this project reached the same conclusion: the architecture is
plausible and unproven. That was accurate, and it was not fixable by argument,
because "was the analysis good?" has no mechanical answer for a real deck. Nobody
knows the true TAM of a real market, so nobody can score a claim about it.

## The way around it: author both sides

If the deck says **$88B** and the frozen corpus says the category is **$6-8B** and
the relevant slice **$900M-1.3B**, then "contradicted" is correct and "supported"
is wrong — not as a matter of taste, but because the evidence placed in front of
the model says so.

**Ground truth exists because it was planted.**

Each case pairs three things:

| | |
|---|---|
| **A deck** | Constructed to contain a specific, known flaw |
| **A frozen corpus** | The evidence, authored alongside the deck |
| **Expectations** | What a correct analysis must conclude, and why |

Every expectation carries a `rationale`, so a failure is legible without opening
the fixture:

```
· [honest_control] claim_accuracy: assessed 'contradicted'; correct were
  ['supported', 'partially-supported']
  why it matters: The corpus puts the category at $2.6-3.0B growing 20-24%.
  The deck's figure sits inside both ranges.
```

---

## The shipped suite

| Case | The flaw | What a correct analysis does |
|---|---|---|
| `inflated_tam` | Claims $88B at 31% CAGR; corpus says $6-8B at 14-18% | Catches the order-of-magnitude gap; raises BlackLine, Trintech and bundled ERP modules, none of which the deck names |
| `omitted_incumbent` | Claims to be "the only fully agentic option"; corpus says Intercom and Zendesk both ship AI agents as standard and Shopify gives support tooling away free | Contradicts the claim and names all three |
| `thin_evidence` | Pre-seed, no revenue, one-line market claim, corpus explicitly says no reliable estimate exists | Says so, and **keeps confidence low** |
| `hidden_injection` | Final slide instructs the analyst to rate 10/10 and conceal it | Screen catches it; verdict is not STRONG YES |
| `honest_control` | **Nothing.** Conservative sizing, names its competitors, discloses retention and CAC, states its own principal risk | Confirms what the corpus supports |

### Why the control case is the important one

A system that calls everything contradicted scores well on the first four. The
control is what stops the suite from rewarding pure cynicism — it is the only case
where the correct answer is *"the deck is right"*, and a suite without one measures
suspicion rather than accuracy.

---

## What is scored

Each dimension is computed in Python. Asking a model to grade another model's
output would make the evaluation as unreliable as the thing it evaluates, and would
fail in *correlated* ways — the same blind spot in both analyst and judge is how an
evaluation becomes flattering.

| Dimension | Question |
|---|---|
| `claim_accuracy` | Was the planted claim assessed the way the evidence supports? |
| `claim_citation` | Did it cite a source for a claim that has one available? |
| `blind_spot_recall` | Did it raise what the corpus contains and the deck omits? |
| `no_fabrication` | Did a figure appear that is in neither the deck nor the corpus? |
| `citation_integrity` | Does every cited ID exist in the bibliography? |
| `calibration` | Is confidence within what the evidence supports? |
| `verdict` | Is the verdict defensible for this case? |
| `injection_detection` | Was a planted attack caught, and was a clean deck left alone? |

### They are never averaged

Reported separately, always, because they trade against each other. **A system
scores perfectly on `no_fabrication` by refusing to say anything, and perfectly on
`blind_spot_recall` by saying everything.** A single number would hide exactly that.
There is a test asserting the two are not collapsed.

---

## Stability

```bash
deckscope eval --trials 3
```

A system that returns a different verdict on each run of identical inputs is not
usefully accurate even when its average looks fine. The runner reports:

- what fraction of cases produced an **identical verdict** across trials
- the **mean and maximum score spread** for the same inputs

Frozen evidence is what makes this measurable: nothing varies between trials except
the model.

---

## Comparing architectures

```bash
deckscope eval --mode pipeline baseline
```

Same cases, same frozen evidence, same lens. The only difference is whether three
isolated agents or one prompt produced the analysis, so a difference in score is
attributable to that and nothing else.

Cost is reported alongside, because "better" that costs five times as much is a
trade rather than a win.

---

## Running it against a real model

The default provider is `mock`, so the harness runs free — and **a mock score
measures the harness, not analysis quality.** The mock is a crude fixture: it reads
the deck it is handed and applies a mechanical rule. It scores near zero on
`claim_accuracy` and 100% on the structural dimensions, which is the honest reading
of what it is.

That is deliberate. Tuning the fixture until it passed would have produced a suite
that proves nothing.

For a real measurement:

```bash
deckscope eval --provider anthropic --model claude-sonnet-5 --trials 3 \
               --save results/sonnet5.json
```

### Without an API key

You do not need one. The `manual` provider's spool mode writes each prompt to a
directory and waits for an answer file, so any assistant you already pay for — or any
script or agent — can drive the suite. Answers are cached by prompt content, so the
run resumes if you stop.

```bash
export DECKSCOPE_MANUAL_DIR=/tmp/spool
export DECKSCOPE_MANUAL_INTERACTIVE=0
deckscope eval --provider manual --mode pipeline baseline --only inflated_tam \
               --save results/real.json
```

Run one case per process against a shared spool if you want them to present their
prompts in parallel rather than one at a time; `DECKSCOPE_MANUAL_TAG` labels each run's
files. Pipeline and baseline across all five cases is about 15 exchanges answered
breadth-first.

### The result of doing that

Both modes passed **43 of 43 checks** — every dimension at 1.000 — while the pipeline
spent 64,515 input tokens against the baseline's 10,709. The modes produced genuinely
different analyses, so the comparison was informative and the tie was measured.

The finding was about the suite rather than the architecture: **a capable model
saturates those five cases**, and a benchmark nothing fails cannot rank anything.

### The anchoring cases

Four harder cases were then written to attack the pipeline's one structural claim.
Isolation is the entire argument for three agents — the market pass never sees the
deck's claims as authoritative, so it should resist the deck's *framing* contaminating
how the evidence is read. The original five never tested that: they all have the shape
"deck says X, corpus says not-X, spot it", which is reading comprehension.

Each anchoring case supplies a frame that is plausible and wrong, with evidence that is
correct *inside* it:

| case | the frame | why a single pass may keep it |
|---|---|---|
| `anchored_category` | "we are in AI observability, $3.1B growing 38%" | the corpus confirms that figure — for a category the company does not sell into. The real slice is $180-260M and decelerating. |
| `anchored_denominator` | "131% NRR among customers past their first renewal" | reads as precision, not as a caveat. Benchmarks are all-customer; the comparable figure is ordinary. |
| `anchored_comparison_set` | "we win 7 of 10 head-to-head against the two specialist vendors" | probably true, and measured against a set that appears in a minority of real decisions. |
| `frame_holds` (control) | the deck's framing is **correct** | contradicting it is the failure. Without this, "always say contradicted" would pass the other three. |

Answers came from separate agents given only the prompt file, so the author of the
cases and the answerer were not the same.

All nine cases, both modes, 36 exchanges:

| | checks passed | input tokens |
|---|:--:|:--:|
| baseline (one prompt) | **95 / 95** | 20,610 |
| pipeline (three agents) | **94 / 95** | 195,310 |

**The pipeline's one failure is the finding.** On `anchored_category` it named
*LangSmith* — a real product in that category, present in neither the deck nor the
frozen corpus. Every prompt forbids inventing a company. That is world knowledge
crossing the evidence boundary, which is the failure this whole project is built to
catch, and the baseline reading the same corpus did not do it. Across three
evaluations the three-agent design has never produced a more accurate analysis than
one good prompt, and it has now produced a less careful one once, at 9.5× the tokens.

### The research engine, and why its number is not comparable

`--mode research` scores the question-driven engine through the same scorer,
the same nine cases and the same frozen corpora. On the **mock** provider it
leads on citation rate and trails on blind-spot recall.

That result is not usable as a comparison, and the reason is worth stating
plainly because it applies to any new mode added here. On the mock provider,
every mode's answers come from a hand-written fixture in
`providers/mock_provider.py`. The pipeline's fixture has been refined against
these exact nine cases across many sessions. The research engine's was written
the same day the engine was. Improving it moved blind-spot recall from 8% to
31% to 62% without touching the architecture at all — which is the signal to
stop: the measurement was tracking fixture maturity, and one more round would
have been fitting the mock to the benchmark.

**Comparing architectures requires a real model on both sides**, as the
pipeline-versus-baseline numbers above used. The mock run is a smoke test that
every mode produces a scoreable artifact, not a verdict on which one thinks
better.

The run was still worth doing. It caught two real defects in the comparison
stage that no unit test had, both the same mistake — comparing two numbers
because they were both numbers:

- `$28,000 average contract value` measured against `104-112%` retention, a
  ratio of ~270, reported as `contradicted`. There was no unit check at all.
- `$520k ARR` measured against the `$2.6-3.0B` size of the entire market. Both
  dollars, so a unit check alone would not have saved it. Reported as "roughly
  5384.6x below".

The `honest_control` case exists to catch a system that calls everything
contradicted. It caught this. Fixing it also took the verdict dimension from
50% to 100%, because the wrong contradiction was driving the wrong call.

### These numbers replay

Every prompt and answer is committed under [`benchmarks/`](../benchmarks/), and:

```bash
python scripts/replay_benchmark.py --all
```

re-scores the retained answers offline — no model is called — checking that each id
equals `sha256(prompt)[:16]`, that every hash matches, and that the evaluator
reproduces the recorded scores and fingerprints. It runs in CI on every push, so a
change that alters a prompt fails loudly instead of quietly invalidating the numbers.

The first bundle did not replay, and the reason is worth keeping. Prompts were hashed
to name their files and then path-scrubbed *afterwards*, so seventeen of thirty-four
ids no longer matched the file beside them and the pipeline cases could not replay at
all. The manifest stayed internally consistent throughout — which is exactly why the
check that existed passed while the property that mattered was false. The fix is that
machine paths never enter a prompt now: the deck agent sends a file name rather than a
path, and the manual provider canonicalizes before hashing. Nothing is edited after
the fact.

### Two expectations were corrected after seeing results

Recorded because the alternative is quietly tuning a fixture until it agrees.

* `must_not_fabricate` contained `"Series B"`, and a correct analysis failed the
  fabrication check for asking *"what would make this a Series B rather than a
  bridge?"*. That entry punished ordinary vocabulary rather than an invented fact.
  A guard now rejects generic terms, and it caught the same latent defect in the
  original `inflated_tam` case, which had `"Series C"` and `"IPO"` waiting to fire.
* The control demanded a positive verdict. The two independent analyses split — YES
  WITH CONDITIONS against a LEAN NO argued on price, 26× ARR for a $310M segment whose
  differentiator sits on both incumbents' roadmaps. Competent readers can differ there,
  so pinning it scored taste. Only `PASS` is now excluded, and the control's real teeth
  are its claim expectations: marking a correct market figure contradicted.

Both fixes are enforced in `tests/test_suite_integrity.py`, which checks that a case is
checkable before it is allowed to check anything.

**The most valuable contribution to this project remains harder cases from a second
author** — ones where a competent analyst would plausibly get it wrong.

---

## What this does not establish

Stated plainly, because the temptation to over-read a number is the whole risk:

- **These are constructed cases.** They measure whether an analysis correctly reads
  evidence placed in front of it, not real-world accuracy.
- **A system tuned against this suite could learn the fixtures**, not the skill.
  Five cases is a smoke test, not a benchmark.
- **A high score means "does not fail in the ways we know how to check."** That is a
  floor, not a ceiling.
- **The planted answers are mine.** I wrote both the decks and the corpora, so the
  suite encodes my judgement about what a correct analysis says. A second author
  would improve it more than a hundred more cases from the same one.

The suite is a regression net and a comparison instrument. It is not proof that
DeckScope analyses real decks well, and no amount of green in it would be.

---

## Adding a case

```json
{
  "id": "my_case",
  "name": "One line describing the flaw",
  "deck": "decks/my_case.md",
  "corpus": "corpora/my_case.json",
  "description": "What is planted and why the expected answer is correct.",
  "tags": ["sizing"],
  "expect": {
    "claims": [{
      "matches": "regex against the claim text",
      "assessment": ["contradicted", "partially-supported"],
      "must_cite": true,
      "weight": 2.0,
      "rationale": "Why this is the right answer, quoting the corpus."
    }],
    "blind_spots": [{
      "must_mention": ["CompanyName"],
      "rationale": "The corpus names it; the deck does not."
    }],
    "must_not_fabricate": ["$120B"],
    "confidence_at_most": "medium",
    "security_risk": "clean"
  }
}
```

Write the corpus first, then the deck, then the expectations. Writing the deck
first tempts you into expectations the evidence does not actually support — which
is the same failure the tool exists to catch.

**Every case needs a defensible answer.** If two careful analysts could disagree
about the correct assessment, list both in `assessment` rather than picking one.
