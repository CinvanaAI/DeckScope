# Benchmark artifacts

> **Status: STALE against current prompts (as of 2026-08-29).** The answers
> committed here were produced for the prompts as they stood at the recorded
> commit. The comparison/lens prompts have since changed (materiality, the
> so_what bar, question sharpening, investor-lens actions), so the replay
> correctly reports cache misses: these scores describe the code that
> produced them, not the code on this branch. The artifacts remain
> byte-verified. To make the numbers current, re-drive the benchmark against
> today's prompts and replace this notice with the new run's date.

Every real-model number quoted in the README and in `docs/EVALUATION.md` was produced
by the run in this directory, and everything needed to check it is here: the exact
prompt each answerer was given, the exact answer it returned, the hash of both, the
scores, and the per-case output fingerprints.

**They replay.** Not "the manifest agrees with itself" — the committed answers are fed
back through the evaluator and must reproduce the recorded scores and fingerprints:

```bash
python scripts/replay_benchmark.py --all
```

That calls no model, runs offline, and runs in CI on every push. If a change to
DeckScope alters a prompt, the replay misses the cache and fails, which is the point:
the retained numbers stop describing the code the moment the code moves.

## Why the first bundle did not replay

Worth recording, because the failure was subtle and the fix is structural.

The first attempt hashed each prompt to name its file, then scrubbed machine paths out
of the prompt text *afterwards*. Seventeen of thirty-four ids therefore no longer
equalled the hash of the file beside them, and the pipeline cases — the ones whose
prompts contained the deck's path — could not replay at all. The manifest was
internally consistent the whole time, which is precisely why the check that existed
(`does the file match its recorded hash?`) passed while the property that mattered
(`is this the prompt the pipeline generates?`) was false.

The fix is not to scrub more carefully. It is that **machine-specific paths never
enter a prompt**: the deck agent sends the file's name rather than its path, and the
manual provider canonicalizes any that slip through *before* hashing, writing or
sending. Prompts are portable by construction, so nothing has to be edited after the
fact — and `scripts/replay_benchmark.py` checks `id == sha256(prompt)[:16]` directly
rather than trusting the manifest.

## What is here

```
benchmarks/2026-08-nine-cases/
  prompts/<id>.txt     exactly what was sent, byte for byte
  answers/<id>.json    exactly what came back
  result.json          scores, token counts, verdicts, fingerprints, generation
                       conditions, and a sha256 of every prompt and answer
```

`<id>` is the first 16 hex characters of the sha256 of the prompt text, which is also
how the `manual` provider keys its answer cache.

## Results

Nine cases, both modes, 36 exchanges.

| mode | checks | input tokens |
|---|:--:|:--:|
| baseline (one prompt) | **95 / 95** | 20,610 |
| pipeline (three agents) | **94 / 95** | 195,310 |

The pipeline's one failure is worth reading rather than rounding away. On
`anchored_category` it named **LangSmith** — a real product in the category, which
appears in neither the deck nor the frozen corpus. Every prompt says: *never invent a
number, a date, a company, or a URL.* This is world knowledge leaking past the
evidence boundary, and it is the failure mode this project exists to catch. The
baseline, working from the same corpus, did not do it.

So on the only run where either mode failed anything, the mode that failed was the
expensive one, at 9.5× the input tokens.

## Caveats that belong with these numbers

- **The cases are one author's**, and that author's bias ran toward the pipeline
  winning. A tie — or a loss — is therefore the informative direction.
- **Answering was independent; authoring was not.** Each exchange was answered by a
  separate agent given only its own prompt file. The cases and their planted answers
  were still written by the operator of the harness.
- **Token counts are character-based estimates** from the manual provider, consistent
  across modes but not billing figures.
- **Nine constructed cases are a smoke test, not a benchmark.** Harder cases from a
  second author remain the most valuable contribution this project could receive.
- **No paths were scrubbed after the fact.** The bundle generator refuses to write a
  prompt containing a machine path, so if one ever appears the pipeline gets fixed
  rather than the artifact.
