# Build requirements

What has to exist, in what order, and how each piece is known to be done.
[GOALS.md](GOALS.md) says why. This says what.

Status marks: **DONE** shipped and tested · **PART** partly built · **TODO** not
started. A piece is only DONE when something outside my own judgment says so.

---

## Stage 0 — Foundations (DONE)

| | |
|---|---|
| Provenance-carrying arithmetic | `marketreport/sizing.py` — Term / Ring / Sizing |
| Concentric narrowing | national → state → county, each sized |
| Refusal over degradation | every backend raises `Unavailable` with a remedy |
| Packaging | `marketreport` ships; acceptance gate imports it |
| Entry point | `deckscope size <naics> --state --county` |

Done because agilon's three published rings reproduce exactly from its own
stated operands, and the value term is reported as uncheckable on all three.

---

## Stage 1 — Sourcing the terms (PART)

The count is solved. The value is the product's central problem.

### 1a. COUNT backends — PART

| Source | Answers | Status |
|---|---|---|
| County Business Patterns | establishments by NAICS × geography × size band | DONE |
| Economic Census | receipts by NAICS → revenue per establishment | DONE |
| BLS OEWS | wages by occupation × metro | TODO |
| BLS BED | firm survival rates | PART (`research/datasets.py`) |
| CMS | Medicare enrollment and spend per beneficiary | TODO |
| ACS | population, households, income by geography | TODO |
| Consumer Expenditure Survey | household spend by category | TODO |

**Done when:** each returns a `Term` with source, vintage and geography, refuses
without its key, and is exercised by a test with a recorded fixture.

### 1b. The VALUE problem — PART

Three routes, in descending order of defensibility. Option 1 is built; the
others are not.

1. **Industry average revenue per establishment** (Economic Census) — DONE.
2. **Per-capita or per-beneficiary spend** (CMS, CEX, OEWS) — TODO.
3. **A stated assumption with a range**, flagged as an assumption — DONE
   (`Term(method=ASSUMED)` requires `low`/`high` or it self-annotates).

**Done when:** a market can be sized by whichever of the three archetypes fits,
and the report says which one it used and what that makes the number mean.

### 1c. Archetype routing — TODO

Pick the sizing method from the market definition:

- **B2B** → establishments × ARPU by size band
- **B2C / professional** → population or workforce × incidence × annual spend
- **Programme-funded** → national spending account, narrowed

**Done when:** three markets of different archetypes size correctly without the
caller choosing the method.

---

## Stage 2 — The rest of the report (PART)

Twelve standing questions, from the intersection of the S-1 and IBISWorld
formats. `marketreport/questions.py` is the definition; `report.py` walks them
in dependency order; `render.py` is the view.

| # | Section | Live source | Demo | Status |
|---|---|---|---|---|
| Q1 | Market definition | user input | yes | DONE |
| Q2 | Size, top-down | Economic Census receipts, narrowed by establishment share | yes | DONE |
| Q3 | Size, bottom-up | CBP × Economic Census | yes | DONE |
| Q4 | Growth | two CBP vintages | yes | PART — needs vintage-addressable CBP |
| Q5 | Concentration | CBP size bands | yes | DONE |
| Q6 | Who competes | EDGAR, registries | yes | PART — fixtures only |
| Q7 | Operating economics | Economic Census | yes | DONE |
| Q8 | Regulation | state licensing | yes | PART — fixtures only |
| Q9 | Barriers, graded and trended | derived | yes | DONE |
| Q10 | Life cycle and saturation | derived | yes | DONE |
| Q11 | What could not be established | the run's own record | yes | DONE |
| Q12 | Do the two sizings converge | derived from Q2 and Q3 | yes | DONE |

**Done when:** every question answers from a live source, not a fixture. Today
`--demo` answers twelve of twelve and reports that **eleven of them are demo**;
live answers two, because the Census key is not set and three sources are
unwired. The split is printed in `coverage()` as `answered_live` /
`answered_from_demo` and stated in the report header above the first number,
so the gap is visible in the artifact rather than only in a planning file.

**Demo taints downstream.** An answer derived from a demo answer is a demo
answer. Without that rule the barriers, life-cycle and convergence sections
read a made-up concentration figure and came out labelled live — invented
numbers acquiring a provenance badge by passing through one more function. The
inheritance is enforced in `report.build()` against each question's declared
`needs`, so it cannot be forgotten by a new agent.

### Completeness is checked, not claimed

Each section declares the follow-ups a reader will immediately have, and
`closure()` verifies something in the report answers them. **Structurally**:
a follow-up names the field that must be populated to close it
(`"Q5.detail.concentration.basis"`), and closure reads that field. The earlier
version counted content-word overlap against our own prose, which meant a
section using the right vocabulary passed without answering anything. A reader who
finishes with questions has been failed by the report, so an open follow-up is
a defect rather than further reading. Currently one standing question and one
follow-up remain open on the demo run, and the report says so at the top and
lists them at the bottom.

---

## Stage 3 — Evaluation against filings (TODO)

The only loss signal that counts.

- **3a. Corpus.** ~20 real underwritten IPO S-1 industry sections, filtered from
  the ~90% that are shell filings. PART — 5 collected, filter not built.
- **3b. Structural parity scorer.** Does our section contain what theirs does?
  Scored per schema row, not by text similarity. TODO.
- **3c. Backtest.** Freeze the clock at the filing date; reproduce from
  contemporaneous data. Requires every source to be vintage-addressable. TODO.

**Done when:** a score exists that moves for reasons in the code rather than
reasons in a fixture.

### Known obstacle

`web_fetch` truncates at ~142KB; Klaviyo's S-1 is 3.3MB. Reliably in range: the
Prospectus Summary and the Risk Factors Summary. Out of range: rivals named
individually. Recorded in SCHEMA.md §4 with what it costs.

---

## Stage 3.5 — The request flow (DONE)

    deckscope market "landscaping in Phoenix"
    deckscope market "gyms" --in Seattle
    deckscope market 561730 --state 04 --county 013   # still exact, if you like
    deckscope market "landscaping" --demo             # no key, no network

The plain-language door is the point. Asking for `--state 04 --county 013` is a
question only somebody who already does this work can answer, which made the
product useless to the person it was built for — the client's first question was
"landscaping in Phoenix" and nothing in it could take that.

**The resolver asks rather than guesses**, and this is the one place where that
rule matters most. Everything else here fails loudly: a missing term is `None`,
an unavailable source raises. A market resolved to the wrong NAICS code fails
*silently* — the report is internally consistent, every figure traces to a real
Census response, the arithmetic is right, and it is about a different industry.
Nothing downstream can detect it. So:

- an ambiguous phrase returns a ranked list and exit code 7, never a pick
- a city spanning counties (New York, Houston, Kansas City) is named and refused
- a sector code (`56`) is refused with the reason, because a sector figure is
  real, sourced, and about landscaping *and* landfills at once
- no place given means a national report, not a silently narrowed one

**The NAICS index is fetched, never typed.** 1,012 codes whose titles carry
legal precision; a table written from memory would be wrong where nobody would
look. A 32-entry starter set ships for offline use and says so on every use.
**County FIPS are fetched too** — 3,143 of them. State codes are typed, because
there are 52, they are ANSI, and the set has a checkable shape that a test
asserts.

Plus `/api/market` and a panel in the app window. Exit 6 means "ran correctly,
report incomplete", which is distinct from a crash and scriptable.

## Stage 3.6 — The report as a document (DONE)

Text in a terminal is the developer's view. The goal is *"output an S-1
report"*, and a filed industry section is a document people read, print,
forward and argue with.

    deckscope market "landscaping in Phoenix" --save report.html
    deckscope market "gyms" --in Seattle --save notes.md

Four formats behind one table (`marketreport/document.FORMATS`), so the CLI,
the web app and the tests cannot disagree about what exists. The extension
decides; `--format` overrides it; an unknown format **raises** rather than
falling back to text, because a caller who asked for `--format pdf` and
silently received plain text has been handed something that looks like it
worked.

**Provenance is visible, not available.** Three states are distinct at a
glance: a sourced figure with its dataset named beneath it, an unchecked one
with no source to go and read, and a demo figure in a warning block that
*replaces* the source line rather than sitting beside it — listing a dataset
that was never queried is the provenance badge over invented numbers, one
layer further out.

**No PDF writer, on purpose.** The HTML has a `@media print` block with page
margins and `page-break-inside: avoid`, so any browser prints it correctly. A
second layout would be a second thing to keep in step with the first, and the
first would win.

The web panel hands over the document the run already produced, held in memory.
Re-fetching would re-query the Census and could return a different report under
the same heading — two artifacts, one label, no way to tell them apart.

---

## Stage 4 — DeckScope as a consumer (PART)

Deck analysis becomes: generate the market report, diff the deck against it.

**Staged (2026-08-29):** with `market_reports` on, the pipeline now scopes
and runs the specialist reports BEFORE the comparison, merges their sources
into the run's single registry (remap applied per `merge_into`'s contract),
and hands their findings into the comparison prompt as `specialist_reports`
— each tagged with the deck claim it was dispatched to check. The verdict is
derived with them, not despite them, and the per-claim reconciliation is
computed once, in memory, on the result. The mechanical join is DONE
(sixth cycle): the scoper declares `checks_claim_ids` per report, and
`_join_reports_to_claims` in the orchestrator attaches each report's
finding, stored id, and remapped sources to the matching audit rows by
code — rendered beside the row, never counted as the model's own
citations. The MarketAnalyst shrink is DONE (ninth cycle): when
specialists produced reports, their keys are passed as `covered` — the
analyst's queries about those quantities are dropped (announced, never
silent), its prompt forbids parallel estimates and redirects effort to
boundary/framing/buyers/funding/regulation, the all-covered fallback
query asks about the boundary itself, and the cache key carries the
covered set. A vocabulary-coverage test fails if a new report type
ships without shrink vocabulary. The un-staged pipeline is untouched
and pinned so.

**Done when:** the claim audit, blind spots and the ask-versus-requirement gap
are all derived from that diff rather than computed separately.

---

## The deliverables slate (2026-08-30) — DONE

Five features shipped in one pass, all deterministic on top of the audited
result (zero new model calls except `diff`/`batch` claim extraction, which
reuses the pipeline's own DeckAnalyst under the same gates):

- **`--format memo` (alias `ic`)** — the one-page deal memo: verdict via
  `header_block` (withheld stays withheld), the three decisive claims by
  materiality, blind spots, one paragraph of the advisor's read, five
  questions.
- **`--format fixit` (alias `founder`)** — the founder's fix-it list from
  the same audit rows, worst first, with what the investor side will be
  holding when they find each item.
- **`deckscope diff old new`** — claim-by-claim change log between deck
  versions: figure changes with ratios, dropped/added claims, moved claims.
  Pairing is same-type token overlap; the header declares extraction
  nondeterminism honestly.
- **`deckscope batch <dir>`** — every deck in a folder, continue-on-error,
  ranked screening table (verdict rank with withheld in the middle, then
  fewest contested) as summary.md + xlsx-or-csv.
- **`deckscope audit-report <doc> --sources <json>`** — the citation-audit
  layer unbundled: any document plus a source list, dangling/quarantined
  [S#]s and unsourced-figure sentences flagged, caller S-IDs preserved.

The refactor beachhead came with it: `deckscope/commands/` — new verbs are
born there (diff, batch, audit-report live in it), cli.py keeps parsing and
dispatch, and existing commands migrate out as they are next touched. The
package docstring states the rule; a test pins it.

## The reverse flow (2026-08-30) — DONE

`deckscope improve`: the audit run backwards — deck (or raw `.txt`/`.md`
notes: the loader already ingests them, so build-from-scratch is the same
command) in, the strongest audit-surviving version out. One model call (the
Deck Reviser, schema-validated); everything else is code. The enforcement
layer is the feature: `validate_revision` strips citations outside the
run's bibliography via the same `audit_fragment` the pipeline trusts,
demotes any new/revised figure line with no surviving source to a visible
founder-input slot (DeckScope invents nothing in either direction), and
flags kept lines that token-match contested claims as "kept against the
evidence". Blueprint markdown always; `--pptx` writes an editable starting
deck; `--demo` runs the whole flow offline on the packaged sample with a
fixture deliberately authored to trip both guards. `--nda` fails closed
exactly like run/research. Declared open: the web app exposes analysis
only — improve is CLI-only until the app grows a founder mode.

**Declared open — mock reader recall on 4 graded cases.** `check --demo`
passes 2 of 6 cases with 6 of 6 inventing nothing, and the banner
correctly says those scores measure the fixture. Raising the other four
honestly means making the mock's generic reading less lossy — legal
instruments (21 CFR 800.30) are not "figures" so never surface; age
bands separate from their rates across clause boundaries; demographics
recalls 0% for a reason not yet diagnosed. `_read_for` is deliberately
generic and sits upstream of the research-loop, evidence-design and
mode-comparison pins, so this is an investigation, not a patch; it must
not be closed by teaching the fixture the test answers.

## Standing constraints

These are not features. Breaking one is a defect regardless of what it buys.

1. **Never a bare number.** Operands, sources, dates — or "not established".
2. **A missing term is `None`, never zero**, and never a partial answer dressed
   as a whole one.
3. **Rules that decide anything are code**, not prompt text. Anything a model is
   asked to "consider carefully" will drift.
4. **Refuse rather than degrade.** A census question answered from a web search
   is how you report 193 competitors when there are 71.
5. **Quarantined evidence grounds nothing.**
6. **NDA mode raises**, it does not warn.
7. **Every gate is as wide as the surfaces it touches.** Every failure the
   seventh audit found in new code was outside the acceptance gate. That is the
   pattern, not a coincidence — extend the gate with the surface.
8. **No score from our own fixtures counts as evidence.** It measures fixture
   maturity. It has already fooled me once.
9. **A defect must never render as a finding.** `build()` with no agents
   registered used to produce a full twelve-section report: Q1 read "no agent
   is registered" and eleven more read "needs Q1, which was not established".
   Eleven honest-looking limits of the evidence, all caused by a missing
   import. It raises now. This is the recurring shape here — the fix is always
   to make the impossible state loud rather than plausible.
10. **Correctness needs an answer from outside.** `tests/test_published_totals.py`
   checks our arithmetic against filings that publish both their operands and
   their result — FIGS' 146% revenue CAGR, Cricut's 4% penetration, agilon's
   three rings. A test whose expected value I chose grades my own homework.
