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

    deckscope market 561730 --state 04 --county 013
    deckscope market 561730 --state 04 --demo        # no key, no network

Plus `/api/market` and a panel in the app window. Exit 6 means "ran correctly,
report incomplete", which is distinct from a crash and scriptable.

## Stage 4 — DeckScope as a consumer (TODO)

Deck analysis becomes: generate the market report, diff the deck against it.

**Done when:** the claim audit, blind spots and the ask-versus-requirement gap
are all derived from that diff rather than computed separately.

---

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
9. **Correctness needs an answer from outside.** `tests/test_published_totals.py`
   checks our arithmetic against filings that publish both their operands and
   their result — FIGS' 146% revenue CAGR, Cricut's 4% penetration, agilon's
   three rings. A test whose expected value I chose grades my own homework.
