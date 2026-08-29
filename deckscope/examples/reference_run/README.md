# A complete live run, replayable

The three prompts the pipeline actually asked, and the three answers a
capable model actually gave, for the sample deck against the frozen sample
corpus. Committed so anyone can replay a full-quality analysis — every
prompt, every schema field, materiality, the internal-consistency conflict,
the code-assembled headline — without an API key:

```bash
DECKSCOPE_PROVIDER=manual \
DECKSCOPE_MANUAL_DIR=deckscope/examples/reference_run \
DECKSCOPE_MANUAL_INTERACTIVE=0 \
deckscope run deckscope/examples/sample_deck.md \
  --corpus deckscope/examples/sample_corpus.json \
  --format md html --out ./reference_output --lens investor
```

Answers are matched to prompts by content hash, so this replays only while
the prompts the code generates stay byte-identical. **A prompt change makes
the run stall waiting for a new answer — that is the feature:** it means the
committed reference no longer describes the current prompts and must be
re-driven, not trusted.

What this run demonstrated when it was recorded (2026-08-29): the
consistency engine caught the deck's own growth-vs-milestone conflict
(10.3%/month implied vs 18% claimed) and the comparison built the meeting's
first question from it; every contested claim carried materiality and a
citation; the verdict stood because 6 of 6 sources were cited; the summary
caveat stayed silent because every figure traced; and the headline verb
matched the verdict mix — a defect this exact run exposed and fixed.

The corpus sources are FICTIONAL (example.org domains), authored beside the
sample deck so the run has known-correct answers. Nothing here is market
research.
