# The agent team

Derived from [RESEARCH_NOTES.md](RESEARCH_NOTES.md) — from what the profession
actually does — rather than from a division of labour I invented. Read
[GOALS.md](GOALS.md) first for why.

---

## The organising idea: agents are questions, not roles

The earlier version of this system split work by *role* — deck analyst, market
analyst, synthesist — and it never beat a single prompt. The reason is now
clear: roles were labels on the same undifferentiated work, so each hand-off was
a summary of the last, and summarising is lossy in a direction nothing
downstream can recover from.

The fix is not better roles. It is that **an agent owns a question**.

A question gives an agent three things a role never did:

- **a distinct retrieval target** — the question decides which dataset answers
  it, and a database question must never go to a web search
- **a closing rule** — a question is answered or it is not, and it says which
- **a place in the report** — the answer is the section

This also settles what the report *is*. A report is not a document with
sections; it is **a set of questions with their answers, their sources, and an
honest record of the ones nobody could answer.** The document is a view over
that set. Which means the user can add a question, and the same machinery
answers it — the report is a starting position rather than a fixed artifact.

---

## The standing questions

Every market report answers these. They come from the intersection of the two
professional schemas — S-1 industry sections and IBISWorld reports — because
where two independent formats agree, the question is load-bearing.

| # | Question | Answered by | Method |
|---|---|---|---|
| Q1 | What market is this, exactly? | framing | user input, then NAICS resolution |
| Q2 | How big is it, top-down? | sizing-td | published aggregate, narrowed |
| Q3 | How big is it, bottom-up? | sizing-bu | count × rate × value |
| Q4 | How fast is it growing? | growth | the official series' own projection |
| Q5 | How concentrated is it? | structure | HHI and CR4 from CBP size bands |
| Q6 | Who competes in it? | competitors | EDGAR, registries, filings |
| Q7 | What does it cost to operate? | economics | Economic Census, OEWS |
| Q8 | What are the rules? | regulation | licensing, CFR, agency filings |
| Q9 | How hard is it to enter? | barriers | derived from Q5, Q7, Q8 |
| Q10 | Where is it in its life cycle? | lifecycle | derived from Q4, Q5 |
| Q11 | What could not be established? | the loop itself | its own record |

**Q2 and Q3 are deliberately the same question asked twice.** The profession's
own advice is to run top-down and bottom-up independently and treat convergence
as a reliability signal. So they are two agents that do not see each other's
work, and their disagreement is a reported finding rather than something to
reconcile. We already have `relation()` for exactly this.

**Q11 is ours.** Neither profession writes it, for the same reason: both are
paid to produce an answer.

---

## What each agent is given, and what it is denied

Specialization is only real if the context differs. Each agent gets a different
slice, and the denials matter as much as the grants.

| Agent | Given | Denied | Why the denial |
|---|---|---|---|
| framing | the user's description | any market size | so the boundary is not chosen to flatter a number |
| sizing-td | the resolved market, published aggregates | the bottom-up result | independence is the entire point |
| sizing-bu | the resolved market, unit counts | the top-down result | same |
| growth | official series | any company's own projection | a filer's forecast is not a market forecast |
| structure | establishment counts by size band | prose about competition | HHI is arithmetic, not opinion |
| competitors | filings, registries | market-size findings | so a big number does not become evidence of who is in it |
| economics | Economic Census, wage data | any single firm's economics | the corpus constraint: nobody publishes ARPU |
| regulation | statute, licensing bodies | everything else | narrow context, cheap model |
| barriers | Q5, Q7, Q8 answers only | raw sources | it reasons over findings, not evidence |
| lifecycle | Q4, Q5 answers only | raw sources | same |

The last two are the only agents that read other agents' output, and they read
**findings**, never prose. That is the hand-off that killed the old pipeline.

---

## Model tiering

Most of this is not judgment.

| Work | Tier | Why |
|---|---|---|
| classify a question, resolve an entity, read a page | small | mechanical; a local 7-14B model does it |
| framing, contradiction | mid | bounded judgment |
| the concluding call | best | happens once |
| **HHI, CR4, penetration, growth, barriers grading** | **none** | arithmetic — no model at all |

The fourth row is the interesting one. Everything the profession computes with a
formula, we compute with a formula. A model that is asked to "consider the
concentration" will produce a plausible adjective; `sum(share**2)` produces a
number with a published threshold attached.

---

## Answering rules

Inherited from the research loop and unchanged, because they are the part most
likely to be quietly weakened:

1. A question closes on a stated rule, never on a model's satisfaction.
2. Two sources agree only if they measure the same thing — `INCOMPARABLE` is a
   third outcome and it settles nothing.
3. Agreement counts by publisher, not by source.
4. Quarantined evidence grounds nothing.
5. A finding must answer the question it was retrieved for.
6. Unanswerable is a result. It gets a section.

---

## What we do not do, permanently

**Primary research.** Expert-network calls and commissioned surveys are how a
research firm establishes the RATE term — "85% of medical professionals buy
their own uniforms" came from a study FIGS paid for. We cannot originate that.

Where a question needs primary data, the answer is a public substitute, or a
stated assumption with a range, or nothing. Never a number that looks measured.
And it is said **in the section where it matters**, not in a footnote, because a
reader deciding something needs to know which part of the answer is thin.
