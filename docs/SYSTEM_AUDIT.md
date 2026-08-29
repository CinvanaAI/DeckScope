# System audit — 2026-08-29

The state of the system after working both audits: an external audit of a
fresh clone at `dbf8d4d`, and the internal hostile-reviewer passes. Every
claim below was verified by executing it on this branch, in this order,
before being written down. Nineteen defects have now been found in this
project's life; every one was found by *using* the product — running it,
replaying it, reading its output as its reader — and never by reading the
code. That is the operating lesson of this repository, and the audit below
was conducted accordingly.

## Verification state (executed on this branch)

| Gate | Result |
|---|---|
| Full test suite (canonical runner, both test styles) | **935 ran (516 functions + 419 class methods), 0 failed, 0 errored, 38 files** |
| Custom linter (incl. new annotation-name resolution) | clean — 176 files |
| Ruff-class findings (undefined names, unused imports) | fixed at source; Ruff pinned in CI |
| `deckscope demo` / `--panel` / `--injected` | exit 0, all three |
| Committed reference run (cold cache, from committed files) | replays green |
| Committed benchmark bundle | byte-verified; **STALE against current prompts, stated in its README** — CI accepts staleness only while that admission exists |
| Personal identifiers / personal paths | zero (`Von`, home paths, email all scrubbed; ships clean in the wheel) |

## Security

Strong for the product's stage, and now with the last known localhost gap
closed. Standing: prompt-injection screening with file-level forensics
(hidden slides, speaker notes, invisible text), trust-boundary fencing on
every untrusted input including the scoper's deck block, hostile-source
quarantine, SSRF protection with DNS pinning and redirect revalidation,
archive-expansion limits, secret redaction over MCP, Windows ACL handling.
New this cycle: the local web server validates the Host header against its
own loopback names (DNS rebinding refused, verified live: rebound host →
403) and no longer serves the token-bearing page to anyone who asks — the
launch URL's token is required, so a rebinding page can never read the key
to the token-gated endpoints. Admitted limits are unchanged and documented
in docs/SECURITY.md: image-borne injection, snippet-only source screening,
novel attacks.

## Reliability

The verification infrastructure itself was this cycle's biggest finding.
The dependency-free runner collected only module-level functions — **419 of
924 tests silently never ran under it**, while CI ran a different runner
that collected classes but lacked fixtures. Each was green about a
different subset. There is now one canonical runner collecting both styles
(TestCase by inheritance, not by name), supplying every fixture, and
reporting functions and class methods separately so a collection regression
is visible on every run; the old path delegates to it, so CI is unchanged.
Beyond that: crash shield (calm sentence + crash file, exit 70), `run.log`
flight recorder beside every run, cost receipt on the terminal, corpus
files protected from CRLF conversion, UTF-8 declared on every subprocess
capture, and the prompt-cache epoch is now a hash of the prompt templates —
a prompt edit invalidates every cached answer mechanically, after the
hand-bumped epoch failed the first time it was actually needed.

## Analysis quality (the substance)

The external audit's most important functional finding — the top-down vs
bottom-up market sizings of one question refused as "two different
subjects" — is fixed at three layers: sentence-position capitalization can
no longer mint an entity (grammar, not a noun stoplist), a keyword-derived
measure loses to the value's own unit, and structural identity finally
reaches the comparator (findings of one question waive the vocabulary guard
when a derivation is involved). The company-separation guard survives, both
directions pinned. The earlier quality bindings all stand: uncited
assessments downgrade visibly; zero-evidence runs withhold the verdict;
contested claims carry materiality; the deck is checked against its own
arithmetic; the summary's figures are audited against the deck and cited
evidence; the headline's verb matches its verdict mix.

## Product coherence (the two halves)

The audit's largest product-level criticism — "two partially parallel
systems" — is now closed in its staged form. With market reports enabled,
the pipeline runs: deck → scoper → specialist reports → **one merged
registry** → findings into the comparison prompt (each tagged with the deck
claim it checks) → verdict → reconciliation computed once, in memory. The
CLI flag and the app checkbox set the same config bit. What remains for
full consolidation is recorded in BUILD.md Stage 4: mechanical joining of
audit rows to their reports, and shrinking the legacy market pass to
boundary work.

## User experience

Deck-first app with a privacy line at the drop zone; two plain-language
go-deeper checkboxes; the reconciliation shown inline as claim → finding →
bearing and delivered as a styled HTML page; "How to read the report"
teaching the three marks; setup deliberately in the terminal with the
reason stated; a crash is one sentence and a file path. The demo — the
product's first impression — now says only true things: figures label their
own measurements, units are honest, and no rank token becomes a company.

## Evidence integrity

Sources carry retrieval timestamps and snippet hashes from capture, and the
References tables show the retrieval date — because a URL is a pointer, not
evidence, and the recorded IDC page has already moved on from the snippet
it once carried. Panels keep their own bibliographies; the run keeps one
registry; merges follow the remap contract.

## Honestly open

- **Real-model validation is still the big one.** The committed benchmark
  describes the old prompts (stated in its README); the three-way
  comparison on a real model, the external human-blind evaluation, and the
  time-frozen backtests in the build plan have not been run. The structure
  is validated; the quality of real-model judgment under the new prompts
  has been exercised once, live, through the manual spool — not at scale.
- **Claim-to-source-span binding** (the exact supporting excerpt per
  figure, not just a source ID) is designed but not built.
- **The large modules** (cli, mock provider, webapp) are due the refactor
  the external audit recommends; the lab-notebook comments should migrate
  to ADRs as that happens.
- The audit-row-to-report join is by instruction, not yet by code.

## Verdict

The external audit called `dbf8d4d` "a strong, ambitious alpha — not a
release-ready diligence product," principally because its own gates did not
pass and its two engines were parallel. On this branch the gates pass —
all of them, including the ones that were lying — the engines share one
evidence path, the demo tells the truth, the localhost boundary is closed,
and the benchmark admits its own staleness rather than implying currency.
What stands between this and "release-ready" is no longer engineering
hygiene; it is external validation spend: one real-model benchmark re-drive
and the blind comparison the build plan already describes.
