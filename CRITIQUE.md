# What is wrong with what I built

Written after the fact, against the code as it stands at `260220e`. Ordered by
how much damage each does, not by how hard it is to fix. Every claim here is
something I checked rather than something I suspect.

---

## 1. The demo is doing the persuading, and it runs on numbers I made up

**Evidence.** `--demo` answers 10 of 11 questions. Live answers 3. The demo's
establishment counts, revenue per establishment and prior-year vintages in
`marketreport/fixtures.py` are figures I invented to be plausible.

**Why it matters.** This is the fixture-maturity trap in a new costume — the
exact failure that fooled me this morning, when three rounds of improving a mock
moved a score from 8% to 62% while the architecture never changed. A stranger
running the demo would conclude the product works. It does not yet; it produces
a well-shaped document over data that has no source.

The labelling helps and does not fix it. `$42.7B` for US landscaping is probably
low by a factor of two or three against the figures the trade press quotes, so
the demo is also teaching a wrong intuition about the market it demonstrates.

**Fix.** Replace every fixture with a recorded real Census response, fetched
once with a key and committed with its request URL and retrieval date, the way
`market-corpus/meta/sources.md` already treats the S-1 excerpts. Then the demo
teaches true things and the arithmetic is validated against real inputs. Until
then the demo should probably print its coverage as `3/11 live · 10/11 demo` so
the gap is visible in the artifact rather than only in this file.

---

## 2. I built the same thing twice and the two halves do not share a line

**Evidence.**

| `deckscope/research/` | `marketreport/` | Same idea |
|---|---|---|
| `Question` | `StandingQuestion` | a thing to answer |
| `Finding` | `Answer` | a thing established, with sources |
| `closing.decide()` | `closure()` | when is it settled |
| `metrics.classify()` | — | what a number is about |
| `judge.py` | `render.py` | the conclusion |

Shared symbol names between `deckscope/research/questions.py` and
`marketreport/questions.py`: **none**. They were written a day apart by me, for
the same purpose, and share no code.

**Why it matters more than tidiness.** `research/metrics.py` is the module I
built to fix the seventh audit's most important finding — that "the market is
$7B" and "a competitor raised $7.2B" confirmed each other. **The market report
does not use it.** So the newer system can compare two figures that measure
different things, and the fix does not protect it. The bug is fixed in one half
of a repository that has two.

This is also the "four products in one package" finding from the audit, and I
made it five. `deckscope --help` now lists fourteen commands.

**Fix.** `Answer` should be a `Finding` with a question id. `closure()` should
use `relation()`. The market report's sizing comparison should go through
`comparable()`. One question type, one answer type, one comparison rule.

---

## 3. The architectural insight I claimed to have found is not exercised

**Evidence.** `RESEARCH_NOTES.md` says the profession's advice to run top-down
and bottom-up independently and read convergence as a reliability signal is "the
single most useful thing in this research, because it is an architecture rather
than a technique". `AGENTS.md` builds Q2 and Q3 as mutually blind agents.

`sizing_top_down()` returns `unanswered` unconditionally. Q2 is the one question
the demo cannot answer.

**Why it matters.** The convergence check is the entire justification for the
two-agent design. Without it the report ships one sizing method and calls the
absence of the second a limitation — which is honest, and also means the design's
central claim has never once run. I have no evidence the two methods diverge in
practice, or by how much, or whether the divergence is informative.

**Fix.** Build Q2 from something defensible. The Economic Census national
receipts total for the NAICS code, narrowed by the geography's share of
establishments, is a genuine top-down path using data already retrieved — it
starts from an aggregate and narrows, which is what top-down means. It would
disagree with the bottom-up figure in exactly the places where the county's
revenue per establishment differs from the national average, which is
information.

---

## 4. `closure()` grades its own homework

**Evidence.** `AnswerSet._addressed()` decides whether a follow-up question is
answered by counting content-word overlap against the concatenated text of our
own answers. A section that happens to use the right vocabulary passes without
answering anything.

**Why it matters.** This is the completeness check — the mechanism behind the
claim that a reader will not finish with questions. It is checked by us, over
our own prose, with a rule we chose. It is better than nothing and it is not
evidence.

**Fix.** Follow-ups should be answerable structurally rather than lexically:
each one names the field or the section that must exist for it to be closed
(`"Is that concentration measured or estimated?"` → closed iff
`detail.concentration.basis` is set). That is checkable without reading prose.

---

## 5. HHI on establishment size bands is close to vacuous for the markets we care about

**Evidence**, computed:

| Market | N | HHI | reading |
|---|---|---|---|
| 1,422 establishments, realistic skew | 1,422 | 55 | unconcentrated |
| 1,422 establishments, all tiny | 1,422 | 7 | unconcentrated |
| 1,422 establishments, all huge | 1,422 | 7 | unconcentrated |
| 1,422, barbell (1,421 tiny + 1 giant) | 1,422 | 885 | unconcentrated |

It does discriminate — the barbell case is 885 against 7, so my first suspicion
that it merely restates `10000/N` was wrong. But note rows two and three: a
market of 1,422 sole traders and one of 1,422 large firms produce **the same
number and the same reading**, because HHI measures share equality and says
nothing about scale.

And every genuinely fragmented trade lands far below the 1,500 threshold, so the
reading is always "unconcentrated" — true, and carrying almost no information
beyond the establishment count the reader already has.

**Why it matters.** HHI is built for firm-level revenue shares in markets with
few players. Most markets a user of this tool will ask about are fragmented
local trades. The measure is being applied where it has least to say.

**Fix.** Keep HHI for the concentrated cases, and add the measures that actually
discriminate among fragmented ones: establishments per capita against a national
baseline (is this county over-served?), the share of employment in the largest
decile, and — most useful — whether concentration is rising, which needs the
second vintage that Q4 already wants.

---

## 6. Nothing checks that the numbers are right

**Evidence.** `marketreport/cases/agilon_2021.py` validates the sizing *engine*
against agilon's published operands. No case validates an *agent*. If
`sizing_bottom_up` multiplied by the wrong ring, or `growth` inverted its CAGR,
every test would still pass — they check shape, provenance and refusal, never
correctness against a known answer.

**Fix.** One end-to-end case per archetype with an externally known answer.
The Economic Census publishes total receipts by NAICS; our bottom-up national
figure should reproduce it within rounding, and that is a real check because the
answer comes from outside.

---

## 7. Smaller things

- **`answers()` and `classify()` are regex over prose.** They work on the cases
  I wrote and will mis-classify constantly on real sources. Acceptable as a
  guard that fails permissive; not acceptable as the basis of anything decided.
- **Growth measures firm counts, not revenue.** The report says so, which is
  right, but it means the "growth" section does not answer the question a reader
  is asking. Revenue growth needs two Economic Census vintages.
- **Fourteen CLI commands.** `market`, `size` and `research` overlap heavily.
  `size` is a strict subset of `market` and should probably go.
- **No HTML/PDF output for the market report.** It is text and JSON only, while
  the deck report has eight renderers. The renderers are built around
  `AnswerSet`'s predecessor and do not read it.

---

## What I would do next, in order

1. **Merge the two systems.** One question, one answer, one comparison rule.
   Nothing else on this list is safe while the semantic-comparison fix protects
   only half the codebase.
2. **Build Q2** so the convergence check runs at least once and I can say
   whether it does anything.
3. **Replace the invented fixtures with recorded real responses**, which needs
   the Census key and takes an hour.
4. **Make `closure()` structural** rather than lexical.
5. **Add the fragmented-market measures** alongside HHI.
6. **One correctness case per archetype**, checked against a published total.


---

# Status, after the fixes

Written against the code as it stands now. Each item below is marked with what
closed it and what is still open. **Marked done only where something outside my
own judgment says so.**

| # | Problem | Status |
|---|---|---|
| 1 | The demo persuades with invented numbers | **PART** — labelling now propagates and coverage splits live from demo; the fixtures are still invented |
| 2 | Two systems, no shared line | **DONE** — one `Answer`, one `relation()`, one metric identity |
| 3 | Convergence never ran | **DONE** — Q2 built, Q12 compares, disagreement is a reported finding |
| 4 | `closure()` graded its own homework | **DONE** — follow-ups name a field, not a vocabulary |
| 5 | HHI near-vacuous on fragmented markets | **DONE** — `shape()` adds per-capita density, top-decile share, average size |
| 6 | Nothing checks the numbers are right | **DONE** — `tests/test_published_totals.py` |
| 7 | `size` was a subset of `market` | **DONE** — retired to a hidden alias; `market --sizing-only` is the door |

## What #1 still needs, exactly

The fix is not more code. It is a `CENSUS_API_KEY`, one afternoon of recording
real County Business Patterns and Economic Census responses, and committing each
with its request URL and retrieval date the way `market-corpus/meta/sources.md`
already treats the S-1 excerpts. Until that happens the demo is *honest* —
it says on every line and in its header that the figures are illustrative and
that none of them is checkable — but it still teaches a wrong intuition about
the size of the market it demonstrates.

The distinction matters: the demo no longer *claims* anything it cannot support.
It just cannot yet support very much.

## What is still open beyond the six

- **Growth measures firm counts, not revenue.** Needs two Economic Census
  vintages. The report says which one it measured, which is right and is not the
  question a reader is asking.
- **Q6 competitors and Q8 regulation are fixtures only.** EDGAR full-text search
  and state licensing registries are the two free routes; neither is wired.
- **No direct PDF for the market report.** HTML now exists (the app serves it and the reconciliation ships as a styled page); PDF still does not, while the deck
  report has eight renderers built around `AnswerSet`'s predecessor.
- **`classify()` is regex over prose.** Fine as a guard that fails permissive.
  Not a basis for anything decided.
