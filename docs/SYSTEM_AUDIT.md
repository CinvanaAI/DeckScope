# System audit — 2026-08-30 (third external audit worked)

The state of the system after three external audits and the internal
hostile-reviewer passes. The standing rule, unchanged:

> **A gate's status is the hosted run's status for the exact commit.**
> Local verification is evidence about local verification. This document
> may say "fixed and verified locally; hosted run pending" — never "all
> gates pass" ahead of the run that decides it.

## Hosted CI history (the actual record)

| Commit | Hosted result |
|---|---|
| 85e7b86 | red — 3 jobs (Ruff, clean-wheel acceptance, Windows/Py3.9) |
| f98bf23 | **13 of 14 green** — all nine OS/Python combos, eval, core install, clean wheel, MCP handshake passed; lint red on 3 findings in one test file (shadowed `os` imports) |
| this branch | those 3 fixed, plus 5 more of the same shape found by the widened sweep (2 in production); hosted run pending |

## Fourth cycle: self-audit, class-level fixes (2026-08-30)

The client's question — "every time we bring this to an external auditor, it just
finds more stuff" — answered by attacking the *classes*, not instances:

- **Claims checker in CI** (`scripts/check_claims.py`): eight documented
  claims re-derived from the tree on every run — gate language against the
  standing rule (its first run caught this very document saying "the gates
  pass" below a table saying "hosted run pending"), benchmark staleness
  admission coupled to the CI flag, panels-under-app-dir re-derived by
  import, the panel cost multiple against the measured table, MCP surface
  parity, first-run format promises against the loader, the runner's
  collection-split line, pyproject/README lead alignment. Each check is
  tested to fire on its seeded drift, and a crashing check is a failure.
- **Request-contract tests** (`tests/test_request_contracts.py`): the
  NAICS2022 class generalized. The four search backends had zero tests;
  now the endpoint, credential location (header vs body, exact name), and
  vendor parameter names are pinned at the transport seam for tavily,
  serper, brave, exa, and the Anthropic/OpenAI adapters — plus a
  cross-cutting check that no credential ever rides in a URL.
- **Live canary** (`.github/workflows/canary.yml`, weekly + on demand):
  drives the shipped census.py against the real API — the half no hermetic
  test can cover, where NAICS2022 actually lived. Needs the free
  CENSUS_API_KEY repo secret; without it the canary fails loudly rather
  than skipping, because a canary that cannot fly must not show green.
- **Bugs may no longer wear the honest-limit costume**: an exception
  escaping a deterministic report agent now renders as "a DEFECT in
  DeckScope, not a limit of the evidence — {type}: …" on the page (the
  build() docstring's own warning, finally enforced at its last gap);
  section failures name the exception type so a TypeError cannot read as
  an outage; the deterministic cross-checks say DEFECT instead of "did
  not run". Concurrent panel saves in the same second no longer overwrite
  (suffix, per-pid temp files; verified live); the HTML `_link` escaping
  contract is documented at the function with all six call sites audited.

## Fifth cycle: the fourth external audit, worked (2026-08-30)

The fourth audit's centerpiece was a mathematical identity error: County
Business Patterns counts ESTABLISHMENTS (locations), an establishment may
belong to a multi-establishment company, and the same CBP row is compatible
with firm HHI ~100 and firm HHI 10,000. The pseudo-HHI is gone: firm
concentration from size bands is now reported as NOT IDENTIFIABLE, the
structure answer describes establishment-size dispersion (what the data
counts), barriers and life-cycle no longer consume a number about the wrong
entity, the HHI thresholds that remain (for real firm shares) are the 2023
Merger Guidelines' 1,000/1,800 with their vintage stated, and the growth
answer says ESTABLISHMENTS, not firms.

The other P1s: the reconciliation's model-written readings are now audited
against each stored report's own id namespace (a fabricated [S999] is
removed and the removal announced — reproduced from the audit before
fixing); uploaded decks are working copies deleted when their run ends,
swept at startup, documented in the storage table, and the claims checker
now derives the storage inventory from the code so an undocumented write
location is a red build.

P2s: chat addenda number monotonically across a session and chat answers
pass a deterministic citation audit against the session's id namespace;
the gap-query step accepts the real complete_json array contract (tested
against the actual base implementation, after the audit showed the fake
had tested the author's assumption); Census source_urls carry every
non-secret request parameter and render under their figures; the
thoroughness dial reaches specialist budgets via Budget.scaled; custom
cache dirs use the real ACL helper, stored panels are chmod 600, and the
API example no longer parks a confidential cache in the repo; the panel
cost tables carry the current measured 10.7x with README coupled to
PANEL.md by the checker; Q12 no longer calls the two sizings independent;
the flagship demo's comparator gained a period-basis guard and a range
parser, mixed evidence reads as partially-supported, and the analysis
JSON can no longer masquerade as retrieved evidence — the demo now calls
the inflated TAM contradicted, the plausible price supported, and the
margin claim partly supported, which is what its own corpus says.
Dependabot and a weekly pip-audit are in place.

Honestly still open from that audit: the model-mediated claim/report join,
the large-module refactors, live validation of the fixtures-only report
types, and — as ever — the real-model benchmark re-drive.

## The third audit's centerpiece: independence was an algebra error

The audit did the arithmetic the convergence agent's own wording skipped.
The "top-down" market size constructed its national total from the same
per-establishment average, so apportioning by establishment share cancelled
straight back to `average × local establishments` — the same local count the
bottom-up figure uses. The two "independent" methods shared a material
operand, and their agreement — presented as "genuine corroboration" — was a
sensitivity check between the national and state averages. An error in the
shared count would move both figures identically and never surface.

Fixed at the level the audit prescribed: every sizing answer now records
**operand-level lineage** (`material_operands` in its detail), and the
convergence agent reads the overlap — shared operands force the sensitivity
framing and cap confidence at medium; disjoint operands earn the
corroboration claim; missing lineage forfeits it rather than assuming it.
The top-down agent's docstring now carries the cancellation algebra where
its old claim of independence used to be, and the shipped demo's own Q12
says "not independent corroboration" about its own figures. Pinned in all
three directions.

## Also from the third audit

- **Economic Census schema**: the 2022 EC exposes `NAICS2022`; this module
  sent `NAICS2017` (correct for CBP, wrong for EC), so every live EC request
  asked for a variable the endpoint does not have — invisible to tests that
  stub the HTTP layer. The classification variable is now mapped per
  dataset and vintage, tested at the parameter level, and the deliberate
  CBP-2022-not-2023 vintage choice is documented at the constants.
- **Surface alignment**: MCP `analyze_deck` now accepts `market_reports`
  (same config bit as the CLI flag and app checkbox) and returns the
  reconciliation; pyproject's description matches the README's actual lead;
  CRITIQUE.md and PANEL.md drift corrected (HTML exists; panel cost stated
  as the measured ~12×, pointing at the table rather than prose).

## Verification state (locally, Linux sandbox, this branch)

All collected tests pass (the runner prints the function/class split every
run); custom linter clean; demos exit 0; committed reference replays green;
identity/secret sweeps clean. Hosted CI has the last word.

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
pass and its two engines were parallel. On this branch every local gate is
green — including the ones that were lying — and the hosted run is pending;
the CI history table above is the record that decides it. The engines share
one evidence path, the demo tells the truth, the localhost boundary is closed,
and the benchmark admits its own staleness rather than implying currency.
What stands between this and "release-ready" is no longer engineering
hygiene; it is external validation spend: one real-model benchmark re-drive
and the blind comparison the build plan already describes.
