# Benchmark artifacts

Every real-model number quoted in the README and in `docs/EVALUATION.md` was produced
by one of the runs in this directory, and everything needed to check it is here: the
exact prompt each agent was given, the exact answer it returned, the hash of both, the
scores, and the per-case output fingerprints.

This exists because a benchmark result with no retained artifacts is a claim, not
evidence. The numbers may well be right; without the prompts and answers nobody can
tell, and a project whose whole subject is traceable evidence should not ask to be taken
on trust about its own measurements.

## What is here

```
benchmarks/
  2026-08-original-five/     the five original cases, pipeline vs baseline
  2026-08-anchoring-four/    the four anchoring cases, pipeline vs baseline
    prompts/<id>.txt         exactly what was sent, byte for byte
    answers/<id>.json        exactly what came back
    result.json              scores, token counts, verdicts, fingerprints, and a
                             sha256 of every prompt and answer above
```

The `<id>` is the first 16 hex characters of the sha256 of the prompt text, which is
also how the `manual` provider caches answers. So an id in `result.json` can be
recomputed from the prompt file, and a prompt file cannot be silently edited without the
manifest disagreeing with it.

## Results

| run | mode | checks | input tokens |
|---|---|:--:|:--:|
| original five | baseline | 43 / 43 | 10,709 |
| original five | pipeline | 43 / 43 | 64,515 |
| anchoring four | baseline | 52 / 52 | 9,901 |
| anchoring four | pipeline | 52 / 52 | 87,121 |

Both modes pass everything in both runs. The pipeline spends six to nine times the input
tokens to draw level. See [docs/EVALUATION.md](../docs/EVALUATION.md) for what that does
and does not establish.

## Reproducing

Answers are cached by prompt content, so re-running scores the retained answers without
calling any model. From a checkout:

```bash
export DECKSCOPE_MANUAL_DIR=$PWD/benchmarks/2026-08-anchoring-four
export DECKSCOPE_MANUAL_INTERACTIVE=0
deckscope eval --provider manual --mode pipeline baseline \
  --only anchored_category anchored_denominator anchored_comparison_set frame_holds \
  --save rescored.json
```

The spool expects `asked/<id>.prompt.txt` and `answers/<id>.txt`; the directories here
are named `prompts/` and `answers/*.json` for legibility, so copy or symlink them into
that layout first. A prompt that does not match byte-for-byte will miss the cache and
block waiting for a new answer — which is the point. It means the pipeline changed, and
the old numbers no longer describe it.

## Caveats that belong with these numbers

- **The cases are one author's**, and that author's bias ran toward the pipeline
  winning. A tie is therefore the informative direction.
- **The original five were answered by the same agent that operated the harness.** That
  is not a blind evaluation and is the likeliest reason for a clean sweep. The anchoring
  four were answered by separate agents given only their own prompt file, which fixes the
  answering half of the problem and not the authoring half.
- **Token counts are character-based estimates** from the manual provider, consistent
  across modes but not billing figures.
- **Nine constructed cases are a smoke test, not a benchmark.** Harder cases from a
  second author remain the most valuable contribution this project could receive.
- **Absolute paths were scrubbed** from the prompt files before they were committed;
  nothing else in them was altered, and the hashes are of the scrubbed text.
