# Panels — the unit of work

Written after Von asked for something the existing system could not do:

> Show me a market share pie graph of cell phones — and the breakdown, so I can
> look at it and say "oh, that is the cell phone market, Samsung and Apple have
> that much, the whole market is worth this much."

I produced that in about six minutes, by hand, with four web searches. Then we
looked at how I did it, and the gap became the design.

---

## 1. What I actually did, and why the code could not

The chain was not a checklist. It was a search, and every link came from being
surprised by the previous one:

    how big is it
      → who is in it
        → these two sources disagree about who leads
          → why do they disagree
            → one counts phones, the other counts dollars
              → how big is that gap
                → 3.5x on price
                  → and Samsung is losing money while ranked first

Four things happened there that `marketreport/` structurally cannot do.

**A disagreement redirected the work.** IDC said Samsung led, Counterpoint said
Apple. That contradiction was not noise to be resolved — it was the doorway to
the actual finding. `marketreport` has twelve standing questions in a fixed
dependency order. A fixed list cannot be surprised.

**The finding chose the form.** I drew two pies because the finding *was* that
there are two pies. `render.py` has a static `HEADINGS` dict and walks
`STANDING` in order regardless of what the run found. It has no representation
of "the shape of this answer is X", so the shape can never depend on the answer.

**I reported around the holes instead of refusing.** I had no per-vendor revenue
split for 65% of the market and no ASP for three vendors. I showed what I had,
named the hole, and still answered the question. `marketreport`'s central
principle is refuse-rather-than-degrade — which is *correct for arithmetic over
a government dataset* and wrong here. A function that cannot find a Census row
has nothing else to try. An agent goes and looks somewhere else.

**The sources were found, not configured.** I did not know before I started that
Counterpoint publishes a quarterly share table. `marketreport` has a fixed
backend registry of two datasets.

The honest summary: **the things in `marketreport/agents.py` are not agents.**
They are deterministic functions that call the Census API and do arithmetic. No
model, no search, no judgment, nothing that can change its mind. `AGENTS.md`
describes mutually blind agents with enforced denials, and the "denial" is a
restricted function signature. That is a fine property for arithmetic. It is not
intelligence, and refuse-rather-than-degrade was compensating for its absence.

## 2. Why this is not a second system

The temptation is a new package. The critique's finding #2 was that I had
already built the same thing twice, so: no.

Everything the panel agent needs **already exists in this repository**, wired to
the wrong caller:

| Piece | Where | Currently used for |
|---|---|---|
| Question-driven loop with a budget | `deckscope/research/loop.py` | deck research |
| Source-type routing (search / dataset / filing / fetch) | `research/router.py` | deck research |
| The reader — findings + follow-ups from screened evidence | `research/reader.py` | deck research |
| Metric identity, so agreement is semantic | `research/metrics.py` | deck research |
| Model providers, tiering, NDA mode | `providers/`, `tiering.py` | deck research |
| Screening, quarantine, citable source IDs | `security/`, `sources.py` | everything |
| Report structure and provenance discipline | `marketreport/` | Census arithmetic |

`ResearchLoop` takes a question queue, a researcher, a reader and a registry. It
knows nothing about decks. It is already the engine a panel agent needs.

So the work is a **join**, not a rebuild. The Census path stays — for a US
industry question it is genuinely better than searching, which is exactly what
`router.py` was built to know. It stops being the only thing that can happen.

## 3. What a panel is

> A panel is one question, answered well enough that a reader does not need to
> ask a follow-up, carrying the form it should be drawn in.

    Panel
      question    what was asked, in the words a person would use
      headline    the finding, in one sentence
      figures     the numbers, each with its own provenance state
      series      the data to draw, structured
      form        WHICH visual — chosen by the agent, not by the renderer
      caveats     the holes, named
      sources     what was read
      coverage    how much of this could be established

`form` is the load-bearing field. It is the thing the current system cannot
express, and it is why the cell-phone answer worked.

### Panels compose; they are not an alternative to the report

Von's question, which settles the architecture:

> How you gonna make a market report if you don't/can't make the market share
> report you just made?

Q5 ("how concentrated is it") and Q6 ("who competes") **are** the market-share
question. The Census HHI answer is a weak proxy that only works for fragmented
US trades — and returns `unconcentrated` for essentially all of them, which the
critique already found carries almost no information.

So a panel is not a rival unit to the market report. It is what a section of the
market report *is*, once the section can actually answer its question. The
report becomes an arrangement of panels; the panel is the atom.

## 4. The shaper — the one genuinely new stage

    question → route → retrieve → read → findings → SHAPE → panel

The reader says what the sources establish. The shaper says what the answer's
shape is. It is the only stage that gets to decide the form, and it is the stage
that had no equivalent in the code.

It is model-facing, like the reader, and it is bounded the same way:

- **It may only use findings that exist.** Every number in a series must name
  the finding it came from, checked structurally after the call — not requested
  in the prompt. Anything unmatched is dropped and reported.
- **It may not compute.** Derived numbers (a share from a count, a total from
  a share) are produced by code from findings, so the arithmetic is inspectable
  and a wrong multiplication is a code bug rather than a model mood.
- **It must name what it could not get.** The caveats are part of the answer.
  "The two pies come from different trackers" is information; hiding it is the
  failure the whole provenance apparatus exists to prevent.

### Forms, and refusing to draw what we cannot

A form registry maps a form name to a renderer. A panel naming a form nothing
can draw **raises** — it does not silently degrade to a table, because a caller
who asked for a comparison and received a list has been handed something that
looks like it worked.

Starting set, each with a stated job:

| Form | For | Example |
|---|---|---|
| `share` | one part-to-whole split | who ships the phones |
| `share_pair` | the same population split two ways | units vs revenue |
| `ranking` | ordered magnitudes | top vendors by shipments |
| `trend` | one measure over time | share by quarter |
| `stat` | a single number that is the answer | total market value |
| `table` | more classes than a chart can carry | the full breakdown |

`share_pair` exists because the cell-phone answer needed it and no single pie
could have carried the finding. That is the test for adding a form: a real
question needed it.

## 5. Provenance, and the mistake I made by hand

In the cell-phone table I put a column headed "Est. revenue" containing `~$17B`
and `~$53B`. Those are **my multiplications**, not published figures, and they
sat in the same table, in the same formatting, as the sourced numbers.

That is exactly the failure the three-state rendering exists to prevent, and I
committed it about an hour after committing the fix for it. So a panel figure
carries its state explicitly and the renderer must distinguish them visually:

- **sourced** — a source ID to go and read
- **derived** — computed by us from other figures; the operands are shown
- **estimated** — a figure we inferred, with the reasoning stated
- **absent** — asked for and not established, with the reason

`derived` is new. It did not exist because the old system only had arithmetic it
performed itself over data it fetched itself, and never mixed the two in one
view. A panel mixes them constantly, so the distinction has to be visible.

## 6. Reproducibility, which is what determinism was buying

The real cost of putting a model in the loop: run it twice, get two slightly
different answers. `marketreport` was auditable because it could not drift.

Three mechanisms, none of which is "ask the model to be consistent":

**The panel is a record, not a rendering.** It stores the findings, the source
IDs, the series and the form. Re-rendering does not re-run anything. Two people
looking at the same panel see the same panel, forever.

**Re-running produces a new panel, and they can be diffed.** A panel is stamped
with what it read and when. Two runs of the same question are comparable
*because* both are records — which is more useful than determinism, since the
market genuinely changes and a report that cannot change with it is wrong in a
quieter way.

**The arithmetic is ours.** Every derived figure is computed in code from
findings. The model chooses what to show; it never chooses what a number is.

## 6a. How a panel becomes a section

`build(market, ask=...)` is the door. A specialist declares which standing
questions it answers — `MARKET_SHARE.answers = ("Q5", "Q6")` — and `build()`
gives it first refusal on those.

Four properties, each one load-bearing:

**It falls back.** A specialist that fails, or that establishes nothing, costs
nothing: the Census agent runs as it always did. A failed search must never lose
an answer the arithmetic could have given.

**It runs once.** Q5 and Q6 are both claimed by market-share. Without a cache
the loop researched the same market twice and spent two budgets on two identical
panels.

**It satisfies the same follow-ups.** `_from_panel` populates
`detail.concentration.basis` and `detail.cr4` from the panel's own series, so
`closure()` closes structurally exactly as it does for a Census answer. A
section answered by a specialist must clear the same bar, or the completeness
check quietly stops applying to half the report.

**The declaration lives on the specialist.** A new specialist claims a section
without anyone editing the report's spine.

Without `ask`, nothing changes at all. For a US establishment count, County
Business Patterns still beats searching — `router.py` has encoded that judgment
since long before any of this, and it is not being thrown away.

## 7. What this does not change

Worth stating, because "adapt" is not "replace":

- The deck-analysis path stays. It becomes a **consumer** of panels rather than
  a parallel product — the claim audit is a diff against what the panels found.
- The Census backends stay, and stay preferred where they are right. A US
  establishment count should come from County Business Patterns, not a blog.
  `router.py` already encodes that judgment.
- Security, screening, quarantine, citable IDs — unchanged, and every panel
  retrieval goes through them, because the fifth audit's lesson was that the
  exempted path is the one that gets exploited.
- The twelve standing questions stay as the report's spine. What changes is that
  a section can now be answered by an agent rather than only by a lookup.
