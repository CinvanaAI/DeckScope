# System audit — 2026-08-30 (fifth external audit worked)

The state of the system after five external audits and the internal
hostile-reviewer passes. The standing rule, unchanged:

> **A gate's status is the hosted run's status for the exact commit.**
> Local verification is evidence about local verification. This document
> may say "fixed and verified locally; hosted run pending" — never "all
> gates pass" ahead of the run that decides it.

## Hosted CI history (the actual record)

| Commit | Hosted result |
|---|---|
| 85e7b86 | red — 3 jobs (Ruff, clean-wheel acceptance, Windows/Py3.9) |
| f98bf23 | **13 of 14 green** — lint red on 3 findings in one test file |
| cbe0331 | red on Ruff alone (two E702 semicolons in one test file); all nine OS/Python combos, eval, clean wheel, core install, MCP handshake green |
| this branch | the E702s fixed and the custom linter taught the rule; hosted run pending |

## Sixth cycle: the fifth external audit, worked (2026-08-30)

The audit's stop-ship finding was the worst any auditor has produced, and
it was right: **NDA mode did not enforce its promise.** The guard was
constructed AFTER the full deck had been sent to the extraction model;
deck-derived search queries went to web search services unguarded; every
`cli` provider counted as "local" though Claude Code, Codex and Gemini
CLIs proxy hosted subscriptions; and endpoint locality was a substring
regex that `localhost.evil.com` sailed through. NDA mode is now
fail-closed: with a non-local model it refuses to START, before the deck
is read (exit 4, zero outbound calls — pinned by a spy-transport test);
web research is disabled under `--nda` in both the CLI and the library
path because search queries are built from deck claims; only Ollama
qualifies among CLIs; and locality is parsed with urlparse+ipaddress,
loopback only — a LAN address has left the machine. The README states
the enforcement instead of the aspiration.

The second finding changed an investment conclusion: the flagship
research demo contradicted a $6B SAM with evidence saying $6-8B, because
the comparison took the median VALUE of two findings (selecting a $41B
whole-category figure), computed 6.8x, and displayed it beside the other
finding's range text. The comparison now selects one finding — nearest by
ratio — reads ranges as ranges (inside a stated range is a match; outside
one, the gap runs to the nearest bound), and ties the displayed text, the
ratio, and the gap to that same finding. The exact scenario is pinned.

Also worked: establishment prose stopped saying "firms" and labels its
midpoint-derived figures as estimates; the lifecycle agent refuses to
grade a market from location-count growth (Q4's own warning, finally
enforced); barriers report their trend as "unknown" rather than "steady"
when one vintage cannot establish a direction; the closure gate accepts a
reasoned not-identifiable instead of holding the report hostage for a
number it just explained cannot exist; the fabricated organizations
("Report", "State", "Typical", "Average") are dead — entity extraction is
form-based and unified with the metrics module's rule, and blind-spot
recall DROPPED accordingly, a smaller honest number replacing a larger
fake one; RESEARCH_ENGINE.md's tables are regenerated with a stated
self-staleness rule; the custom linter learned E702 so it can no longer
be green while hosted Ruff is red; and the claims checker runs in CI
even when lint fails, so a lint red can never again hide the claims
verdict.

Honestly still open from that audit: `deckscope check --demo` passes 2 of
6 report cases (the fixtures-only report types — the 6/6 "invented
nothing" floor holds); the module refactors; the model-mediated
claim/report join; and the real-model benchmark re-drive.

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

---

# Sixth external audit worked (safety/privacy — 2026-08-31)

A privacy-focused audit of commit `2fa082e`: repository and full history
scanned (gitleaks, filenames, identities — nothing leaked, no rewrite
needed), then runtime leakage probed. Verdict accepted in full: no
published secret, but two real ways NDA mode could still send
deck-derived content to a hosted model.

**Critical — the NDA gate was CLI-deep, not engine-deep.** The library
path (`run_research` driven directly, with a frozen corpus) refused web
research and then handed deck-derived questions and corpus snippets to a
hosted provider anyway — reproduced by the auditor with one outbound call
containing a planted confidential claim. The engine now refuses at its
own front door: under an enabled guard it raises `NDAViolation` before
the first provider call unless the provider's own config parses as local
(`tiering.is_local`); a provider with no config is refused, because
unknown locality is not trusted locality. "The CLI checks" was
documentation; this is enforcement.

**High — `improve --nda` checked one provider while the pipeline used
two.** A local main model with a hosted `extract_provider` passed the
gate and sent the complete deck to the hosted extractor. Both providers
are now validated, fail-closed, before anything is read. `batch` gained
the same `--nda` (both providers, research forced off) — a folder of
inbound decks is exactly where confidential material lives, and it had
no confidential mode at all.

**The regression the audit caught in CI.** The deck-revision prompts were
appended to `templates.py` under names the panel's revision prompts
already owned (`REVISE_SYSTEM`/`REVISE_USER`); the second assignment won
at import and panel revision died with `KeyError('brief')`. The root
process failure is recorded here deliberately: after the append, the
post-change test runs were selected bites that did not include the panel
files, so a green board was reported from a red tree. Fixes: the deck
prompts are `DECK_REVISE_*`; the linter now fails any module-level name
assigned twice (the whole class, not the instance); and the sweep before
a commit is the full suite, not bites.

Also fixed: spreadsheet formula injection in the batch table
(`neutralize_cell` — a deck named `=HYPERLINK(...)` becomes inert text in
both xlsx and csv); `.gitignore` now covers `deckscope_out/` and
`deck_analysis/`, the directories the new commands actually default to;
crash reports redact the home directory from argv and traceback and open
with a review-before-sharing warning.

Board after the cycle: all 47 test files green (full sweep), lint clean,
claims checker holds, demo / improve-demo / panel-demo exit 0, identity
sweep clean.

---

# Seventh external audit worked (fresh product audit — 2026-08-31)

A full independent audit of `2fa082e` — the commit BEFORE the sixth
cycle's fixes landed, so four of its findings (prompt collision, engine
NDA, improve's extraction provider, batch cell injection, gitignore,
crash argv) confirmed work already done. The rest was new, and the
biggest was a release-blocker.

**The wrong-basis chimera.** A revenue-scoped market-share report kept a
units series, drew the units chart, and stamped "(share of revenue)"
onto the units leader — Samsung crowned on a basis where the corpus's
own figures put Apple at 49%. Root cause was a three-part relay:
`_off_basis` only *caveated* (a warning under a wrong chart does not
compete with the chart), `_stamp` appended the requested basis to a
headline built before validation, and the mock shaper's `or groups`
fallback substituted whatever basis existed. All three are gone: basis
is now ENFORCED — off-basis series, slices, and figures are excluded
with a caveat naming where they belong; a panel left with nothing
on-basis is honestly unanswered ("the sources reached publish the other
basis"); the headline is rebuilt from the retained series' top slice
when the crowned leader was excluded; and the stamp runs only after
enforcement. The mock now honors the job's "measured strictly as"
declaration and refuses to substitute.

**Panel silent degradation, the half the sixth cycle missed.** The
prompt collision was already fixed, but the swallow remained: a failed
revision was a soft `revision_error` while the summary still counted the
review's CLAIMED position changes — an expensive panel whose central
phase did nothing reported "3 position(s) changed" and exited 0. Now: a
claimed change counts only when the revision was actually applied,
`revision_failures` is a first-class metric, the round log says
"REVISION FAILED" instead of "held its original position", the summary
prints each failure, and the panel exits 6 (ran, incomplete) when any
revision failed.

**Router subject masking.** First-match keyword routing sent every
question about "revenue cycle management" to EDGAR because the market's
NAME contains "revenue". The subject is now masked out of the question
before the rules run — the words in a market's name describe the market,
not the question's intent. The auditor's full recommendation (typed
intent routing) stands as the architectural direction in BUILD.md.

Also: `safe_cell` is one shared implementation applied by the main
workbook renderer AND batch (the sixth cycle fixed batch only); the
app's and README's privacy sentences now disclose deck-derived search
queries going to the search service; `run` gained the same fail-closed
`--nda` as improve/batch/diff; the four new commands default to the
gitignored `deckscope_output`; the run help's "scores the same" claim
is reworded to match the README's honest framing, and a new claims-
checker rule fails any quality claim in cli.py that does not name its
evaluation.

Accepted as standing architecture directions, not closed: one central
outbound-policy gateway wrapping every provider and search call; an NDA
switch in the web app; typed question intent for routing; consolidating
the overlapping engines around one run model. Recorded in BUILD.md.

Board: all 48 test files green (full sweep), lint clean 198 files (new
duplicate-assignment rule included), claims checker holds (10 checks),
demo / panel / improve / report demos all exit 0, identity sweep clean.

---

# Eighth external audit worked (fresh audit of 4a5b1af — 2026-08-31)

The first audit of a commit with all prior cycles in it, and it found the
seams: places where one subsystem hands STRUCTURED MEANING to another and
the receiver was free to drop it.

**P0 — the chair out-voted the panel.** Live repro: panelists voted 2-1
for YES WITH CONDITIONS, the deterministic metrics computed the modal
verdict correctly, and the chair published LEAN NO as "majority" with a
rationale claiming two of three panelists made its call. The consensus is
now adjudicated in code (`_adjudicate_consensus`): `agreement` always
comes from the computed metrics; when the vote has a winner, the
published call IS the modal call; a chair that disagrees keeps its
judgment as a labeled `chair_recommendation` that "does not override";
and the recorded vote rides on the verdict so a reader can check the
arithmetic. The mock chair deliberately keeps its wayward call so the
demo shows the adjudicator firing — and its claim table now names every
panelist (it had been presenting a two-panelist table as a three-model
synthesis). The summary prints the overruling.

**P1 — the revenue report asked unit questions.** The scoped title
APPENDED the measure to the generic mixed-basis job, so the opener read
"…by units and by revenue — share of revenue" and asked shipment
questions; the demo masked it because the recorded researcher returns
every page for every query. The title now REPLACES the generic job
("Share of revenue — the money customers spent…"), and the mock opener
branches on the measure-leading head before any generic keyword.

**P1 — unknown basis meant "same basis".** Two unrendered findings both
got `None` from `_series_of`, and `None == None` passed the same-
yardstick gate — Apple's 20% OF SHIPMENTS vs 49% OF REVENUE published as
"two sources disagree". Unknown is now INCOMPARABLE: a pair with any
unknown series identity is compared only when both statements declare
the same basis in their own words (`_stated_basis`, cue-checked against
the basis dimension).

**P1 — confidentiality did not survive the run.** A deck analyzed under
--nda could later be `deckscope chat`-ed to a hosted provider, because
the record carried no memory of the promise. `AnalysisResult.privacy`
now persists ({"local_only": true, "source": "nda"}), run/batch stamp
it, chat refuses a hosted provider on a local-only record (exit 4)
unless `--allow-hosted` is passed deliberately, improve --from-run
refuses the same way with no flag able to bypass, and --nda with --mode
both is refused outright (a comparison harness is not a confidential
workflow). The one-gateway architecture direction stands in BUILD.md.

**Also:** the panel workbook now routes every cell through the shared
`safe_cell` (the third exporter to need it — the gateway argument in
miniature); a cli-provider with a CUSTOM command never inherits its
preset's local trust (a command may proxy anything); the benchmark
replay's summary states exactly which guarantee it checked — "All
bundles verified" is reserved for identity AND behavioral replay, and a
run where every drift was excused now says "This run proves the
artifacts, not the current pipeline's numbers", with the CI step renamed
and the README's "re-scores them offline in CI" corrected to match.

The canary workflow has `workflow_dispatch` and no recorded runs yet —
it needs one manual trigger from the Actions tab to produce its first
live evidence.

Board: all 50 test files green (full sweep, 15 new in
test_audit10_regressions.py), lint clean 199 files, claims checker
holds, demo / panel / improve / report demos exit 0, identity sweep
clean.

# The engine build (internal cycle — 2026-08-31)

Owner's mandate: build the engine identity for real — verified
connectors, typed verticals, and two new report verticals chosen from
the five named free-data candidates (grants and nonprofits, alongside
the existing deck), at product standard, free-first, with agents that
perform roles rather than scripted lookups. Worked as six gated phases;
every phase's claims were grounded before its code was written.

**Phase 0 — the API record.** Every external claim the new verticals
rest on was captured live before use: ProPublica Nonprofit Explorer v2,
NSF Award Search v1, PubMed E-utilities, USAspending v2 reference
endpoints (recorded/phase0/, verbatim responses with provenance and
quirks). The ProPublica transcription was verified by 990 component
arithmetic — all twelve fiscal years reconcile to the dollar — before
anything was built on it. NIH RePORTER is POST-only and the capture
environment could not POST; the client's docstring says exactly that,
and the weekly canary now performs the live POST rather than anyone
pretending it was captured.

**Phases 1–3 — identity, connectors, typed intake.** README/BUILD/GOALS
lead with the engine; the plugin contract (manifest + sha256-bound
verification marker + AST safety scan + declared-host egress + the
no-key-must-raise law) gates every connector the `connect` verb has a
coding agent write; verticals are frozen declarations with coupling
tests pinning every field to real code, and `deckscope analyze` shows
its cue arithmetic, refuses ties, consults the configured model only to
choose among declared verticals, and writes --propose drafts that are
loudly ungraded ("Nothing runs from a draft").

**Phase 4 — grants.** Three roles: Grant Analyst (model) extracts typed
claims; the Funding Record Checker (deterministic agent) plans which of
NSF / NIH / USAspending / PubMed each checkable claim requires, runs
the plan, registers every hit as a citable primary source with a real
per-award URL, and records outages as outages; the Grants Synthesist
(model) compares under the standard schema and citation audit. The
vertical's law: **the absence cap** — an absence claim is never
"supported"; the ceiling is partially-supported with coverage shown
("a floor, not a census"), while a contradicted absence claim stands,
because counterexamples are proof. The run produces a standard
AnalysisResult, so memo/fix-it/chat/improve work on it unchanged —
the engine thesis, cashed.

**Phase 5 — nonprofits.** The structurally new claim class: the
subject's own filings are public, so claims about the organization
itself are checkable by arithmetic. The Filing Record Checker resolves
the organization (document EIN wins, and a bare 9-digit run needs
EIN/tax-ID wording nearby; otherwise only an unambiguous search top
hit; otherwise refuse to attribute), pulls the IRS extract, reconciles
each dollar claim against the filed figure with the fiscal basis
labeled on every number (tax_prd 202306 is the year ENDING 06/2023),
and volunteers what the filings show that the document omits — the
demo's recorded Feeding America extract shows a $16.8M operating
deficit the sample brief never mentions. **The self-filing law**: where
the reconciliation computed a verdict, it overwrites the synthesist's —
including its commentary, so no row argues with itself — and stamps the
evidence strong, because the subject's sworn filing is the strongest
class this engine holds. Refusal over derivation: program-expense
ratios and individual pay are not in the extract, so those claims are
refused with the filing PDF cited, never approximated. Tolerance is
precision-aware: "$2.8 billion" is held to its own half-ULP, so a true
claim inside its own rounding is never called contradicted.

**The hostile pass on the build's own output** found and fixed, before
any external eyes: a claim-audit row that argued with itself (law
overwrote the verdict but not the commentary); deck vocabulary on
non-deck reports ("Ask the founder" on a nonprofit report, a TAM/SAM
annex of dashes, "Deck vs. Market" framing) — fixed by a per-vertical
vocabulary in the findings spine (deck output byte-compatible); a
footer that read "? / ? (0 sources)" while References counted 2 —
runners now populate stats; headline garble from noun-phrase blind
spots ("the deck omits No prior-support section"); IRS filings listed
at "unknown" reliability; and the --nda skip being reported to the
synthesist as "no checkable claims" instead of the truth (skipped for
privacy).

Honestly open, named here rather than discovered later: the HTML and
DOCX renderers still speak deck vocabulary — they are unreachable from
the vertical runners (which render markdown+json), and the memo is a
deliberately IC-shaped artifact, but running those paths on a grants or
nonprofits record will wear the deck's clothes until they get the same
vocabulary pass. Both new verticals are UNGRADED — no answer-key case
in the evaluation harness yet — and every report they emit says so.
The nonprofits sample is a labeled fictional donor brief about a real
organization whose real filings the demo replays; the brief's claims
are deliberately offset so the checker has something to catch, and the
file's provenance note states all of this.

Board: all 54 test files green — 1138 tests (712 functions + 426 class
methods) under scripts/run_tests.py — lint statute clean, claims
checker holds, deck/grants/nonprofits demos exit 0, identity sweep
clean. This sandbox could not install pytest (no package index), so the
board ran under the repo's canonical zero-dependency runner; the hosted
CI run for the commit remains the status of record, per the standing
rule at the top of this document.
