# The research engine

> Search *backends* — Tavily, Serper, Brave, and how to add your own — are in
> [RESEARCH.md](RESEARCH.md). This page is about the loop that drives them.

`deckscope run` and `deckscope research` do different things, and the difference
is not a feature list.

`run` writes its search queries before it has read anything, retrieves once, and
reports. Every conclusion it draws is downstream of one guess made at the start,
and nothing it learns along the way can change what it looks up next.

`research` posts a queue of open questions, works the highest-priority one,
reads what comes back, and lets that reading add questions — to any beat. A
regulation page can put a question on the economics queue. Questions close only
when a stated rule fires. Nothing closes because a model felt finished.

```
deck → claims → framing → LOOP → comparison
```

The stages are a data dependency, not a division of labour. You cannot research
a market before deciding which market. You cannot compare a claim against
evidence that does not exist yet.

## Try it with nothing installed

```
deckscope research path/to/deck.pdf --demo
```

No AI connection, no search key. Fixed sample evidence, so every figure is
illustrative — what is real is the loop, and you can watch it work.

## The loop

```
while budget remains and open questions exist:
    q       = highest-priority open question
    route   = classify(q)          # search | dataset | filing | fetch
    results = retrieve(q, route)   # screened and registered on the way in
    read   -> findings, and NEW questions
    post the new questions, to any beat
    close q when a stated rule fires
```

### Routing: a database question never goes to web search

"How many landscaping businesses operate in Maricopa County?" is a query against
County Business Patterns. Sending it to a web search returns a directory listing
that says 193 when the census says 71, and nothing downstream can tell which is
right.

`research/router.py` classifies each question and sends it to a backend that can
actually answer it. **A dataset backend refuses rather than degrading to search.**
Without a NAICS code, `census_cbp` raises `Unavailable` and the question closes
as unanswerable with the reason attached. That is a worse-looking report and a
better one: a confident wrong number is the failure that matters.

### Closing rules

Four outcomes, and two of them are results rather than failures.

| Outcome | Fires when |
|---|---|
| `confirmed` | two findings agree within tolerance **from independent publishers** |
| `contested` | grounded sources disagree and further research did not settle it |
| `unanswerable` | attempts or budget exhausted, or research established nobody publishes it |
| *(stays open)* | none of the above yet |

The rules are in `research/closing.py`, deliberately separate, because this is
the part most likely to be quietly weakened. "One good source is enough" turns
the loop back into the lookup it replaced, and does so invisibly — the output
still looks like research.

Agreement is counted by **publisher**, not by source. Four pages from one
content farm is one source quoted four times, and calling it corroboration is
the specific mistake that rule exists to prevent.

### Budget

Enforced in the scheduler, not requested in a prompt. A loop that can spawn its
own work will spend everything on the first interesting thread.

```
--max-iterations 24     questions the loop may work
--max-retrievals 40     retrievals across the whole run
--max-seconds 600       wall clock
```

One slot in every three is reserved for a question attached to a claim the deck
actually makes. Without that reservation, generic market questions — which carry
the same priority and are queued first — eat the entire budget, and every claim
comes back "unverifiable". That reads like a finding about the deck and is
actually a finding about the scheduler.

## Findings, not a report

The primary artifact is a set of findings, each with a value, a unit, an `as_of`
date, a method and its sources. The written report is one *view* over that set.

A finding with no source behind it is **deleted**, not softened. Same invariant
as the citation audit, one layer down.

`as_of` is the date the fact is true *of*, not the date it was retrieved. A 2019
market size found today is a 2019 market size.

## Comparison

Per claim, over the records rather than a summary — which is the change that
matters most. The three-agent pipeline lost to a single prompt because each
hand-off was a summary, and summarising is lossy in a direction you cannot
recover from: nothing downstream could ask a question the summary had already
answered away.

Three passes the old report schema could not express at all:

**Omission.** Findings the research established that no claim addresses. The
deck is silent and the market is not. Missing sections count too — a deck with
no team slide, no pricing and no retention figure has told you three things.

**Contested.** Where two grounded sources disagree and nothing settled it,
promoted into the output rather than resolved by picking a side.

**Ask versus requirement.** When a deck asks for $5,000 and the evidence says
the requirement is nearer $10,000, the *gap* is the finding, and it is about the
person who wrote the deck rather than the industry. Under-asking by half means
they did not research the cost or expect you not to check. Either reading
decides how much to give and on what terms.

Above 25× the gap is reported as a **unit mismatch** instead, with no conclusion
drawn. A $4M seed round measured against a $10,000 owner-operator setup cost is
not a 400× over-ask; it is two different kinds of number, and saying otherwise
would be exactly the confident-and-wrong failure this engine exists to avoid.

## Cost and confidentiality

Most of the work in a research loop is small and mechanical — read this page,
pull the figure, classify this question. Sending all of it to a frontier model is
how a per-deck cost becomes absurd.

`tiering.py` routes by **task**, not by agent:

| Task | Tier | Why |
|---|---|---|
| `extract`, `route`, `resolve` | small | mechanical; a 7-14B local model does it reliably |
| `contradict`, `frame` | mid | judgment, but bounded |
| `judge` | best | the one call that concludes |

Tiers degrade **upward**. If no small model is configured, the work runs on a
bigger one: expensive but correct. Judgment on a model too weak for it is cheap
and wrong.

### NDA mode

```
deckscope research deck.pdf --nda
```

Structurally enforced, not documented politely. `NDAGuard` refuses any outbound
call carrying deck-derived text to a provider that is not running on your
machine — the call **raises**; it is not logged and downgraded.

Two independent checks, because a privacy control that depends on every future
caller remembering something is not a control:

1. an explicit taint flag on the call
2. a content fingerprint of the deck as a backstop for when somebody forgets

`openai_compatible` counts as local **only** when pointed at a loopback or
private address. It is the backend people use for Ollama and LM Studio, and also
the one they use for hosted gateways, so the name alone proves nothing.

## Extending it

Everything is a registry, so nothing here requires forking.

```python
from deckscope.research.datasets import DatasetBackend, register_backend

class MyStatsOffice(DatasetBackend):
    name = "my_stats_office"
    def answer(self, question, params):
        ...   # return a DatasetAnswer, or raise Unavailable
```

Add a routing rule in `research/router.py` and questions of that shape go there
instead of to a search engine.

## Invariants under test

`tests/test_research_loop.py`. Each one corresponds to something that either
went wrong on the first end-to-end run or would have gone unnoticed.

| | |
|---|---|
| I1 | a question closes only on a stated rule |
| I2 | agreement from one publisher is not corroboration |
| I3 | a database question never goes to web search |
| I4 | reading raises new questions, and they may land on another beat |
| I5 | an unsourced finding never reaches the output |
| I6 | NDA mode refuses, it does not warn |
| I7 | claim-bound questions cannot be starved by generic ones |
| I8 | the same query is never run twice |
| I9 | the closing note says what actually stopped the research |

## What the evaluation says, and what it cannot say

```bash
deckscope eval --mode research pipeline baseline --provider mock
```

Nine cases, one trial, identical frozen corpus per case:

| dimension | research | pipeline | baseline |
|---|---|---|---|
| claim_accuracy | 28% | 33% | 33% |
| claim_citation | **71%** | 59% | 67% |
| blind_spot_recall | 62% | 100% | 100% |
| no_fabrication | 100% | 100% | 100% |
| citation_integrity | 100% | 100% | 100% |
| calibration | 100% | 100% | 100% |
| verdict | 100% | 100% | 100% |
| injection_detection | 100% | 100% | 100% |

Total tokens across nine cases: research 158k, pipeline 144k, baseline 34k.

**Do not read this table as "the research engine is worse."** Read it as: this
harness cannot answer the question.

The provider is `mock`. Every mode's answers come from a hand-written fixture,
and the pipeline's fixture has been refined against these exact nine cases
across many sessions while the research engine's was written the same day the
engine was. Its 62% blind-spot recall is mostly the fixture extracting fewer
phrases from the corpus than `_market_analysis` does — not the loop finding
less. Three rounds of "improving" that fixture moved the number from 8% to 31%
to 62% and changed nothing about the architecture, which is the tell: **the
measurement was tracking fixture maturity, and continuing would have been
fitting the mock to the benchmark.** The suite's own caveat warns about exactly
this.

The comparison that would answer the question needs a real model on both sides,
the way the earlier pipeline-versus-baseline runs did.

### What the evaluation did establish

It found two real defects in the comparison stage that no unit test had, and
both were the same mistake: **comparing two numbers because they were both
numbers.**

1. `$28,000 average contract value` was measured against `104-112%` net revenue
   retention. Ratio ~270, reported as `contradicted` with a confident gap line.
   There was no unit check at all.
2. `$520k ARR` was measured against the `$2.6-3.0B` size of the whole market —
   both dollars, so matching units did not save it — and reported as
   "roughly 5384.6x below". The honest-control case exists to catch a system
   that calls everything contradicted, and this is what it caught.

Both now require matching units *and* a ratio under `MISMATCH_CEILING`; past
that the claim is reported as not checked rather than judged. Fixing them also
took the verdict dimension from 50% to 100%, because a wrong contradiction was
driving a wrong call — the two failures were one failure.

A confidently wrong contradiction is worse than a missed one. It is the product
failing in precisely the way it accuses decks of failing, and it would have
shipped without the control case.
