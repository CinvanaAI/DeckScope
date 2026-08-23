# Citations and the bibliography

## The problem this solves

A report that cites four URLs out of forty consulted is not auditable. You cannot tell
whether the other thirty-six contradicted the conclusion, said nothing useful, or were
never really read. And a model asked to "cite your sources" will happily attach a
plausible URL to a figure that URL does not contain.

DeckScope handles this structurally rather than by asking nicely.

---

## How it works

**1. Every result is registered, before screening.**

The moment the research backend returns anything, each result gets a stable ID — `S1`,
`S2`, `S3` — in a `SourceRegistry`. Registration happens *before* the security screen, so
a source later dropped as hostile still appears in the bibliography with the reason it
was dropped. Nothing disappears silently.

**2. The model is given a numbered bibliography, not a pile of text.**

```
[S1] Independent analyst composite on workflow automation
      url: https://research.example.org/6555
      date: 2026-03
      found via query: workflow automation market size 2026 independent estimate
      content: Mid-market serviceable slice estimated at $3-5B in 2026…
```

with explicit instructions: cite by ID, fill the `source_ids` array on every object that
has one, cite inline in prose, and **never cite an ID you were not given**.

Quarantined sources are excluded from this block, so a hostile page cannot be cited even
by accident. IDs stay stable and therefore non-contiguous — if `S2` was dropped, the model
sees `S1, S3, S4`, and the report explains why.

**3. Citation is structural, not decorative.**

The schemas carry `source_ids` on TAM estimates, competitors, funding rounds, scorecard
rows and every claim in the audit. An empty array is meaningful: it is a statement that
the assessment rests on no source. The prompt says so directly:

> An honest "no source supports this" is worth more than a decorative citation.

Claims also carry `evidence_quality`: `strong` / `moderate` / `weak` / `none`.

**4. Citations are resolved after the run.**

`resolve_citations()` walks the finished result and attributes every `source_ids` entry
and every inline `[S3]` back to the registry — by ID, by URL, or by title fragment. Each
source ends up with a status and a list of what it supports.

A quarantined source can never be promoted to `cited`, even if a model references it.

**5. The whole registry is printed.**

Not just the cited part.

---

## What the References section looks like

> 14 sources were retrieved and screened. 6 are cited in the analysis above; 7 were
> consulted without being cited; 1 was dropped by the security screen.
>
> Every source retrieved is listed here, including the ones that did not support a
> conclusion — so the absence of evidence is as visible as its presence.

**Cited in this analysis**

| ID | Source | Published | Reliability | Supports |
|---|---|---|---|---|
| S1 | Independent analyst composite | 2026-03 | secondary | TAM estimate $18-24B; investor: claim C1 |
| S7 | Regulator filing | 2026-01 | primary | competitor: UiPath |

**Consulted, not cited** — retrieved by the research queries but did not end up
supporting any specific conclusion.

**Dropped by the security screen**

| ID | Source | Reason |
|---|---|---|
| S2 | https://evil.example.xyz/seo | The page contained text addressed to the AI rather than reporting facts. |

Plus a collapsed block listing every search query that produced them.

---

## Where citations appear

- **In the claim audit** — each claim shows its source IDs as links, or says *"none cited
  — this assessment rests on no source"*.
- **Inline in prose** — the summary cites `[S3]` where a figure comes from a source.
- **In the market annex** — every TAM estimate, competitor and funding round.
- **In the scorecard** — per-dimension source IDs.
- **In HTML** — source IDs are internal links; clicking `[S3]` jumps to the entry.
- **In XLSX** — a References sheet with status, reliability, the query that found it, and
  what it supports.
- **In JSON** — the complete registry under `references`.

---

## When there is no research

The References section does not go quiet. It says:

> No external sources were retrieved for this analysis (research backend: `none`). Every
> statement above therefore rests on the model's training knowledge and on the deck
> itself, and should be treated as unverified.

The market agent is separately instructed to set `sizing_confidence: low` and record the
limitation in `research_gaps`.

---

## From Python

```python
result = analyze("deck.pdf")

for s in result.sources:
    print(s.sid, s.status, s.reliability, s.url)
    print("   supports:", "; ".join(s.cited_by))

print(result.registry.stats())
# {'total': 14, 'cited': 6, 'consulted_uncited': 7, 'quarantined': 1}

print(result.registry.find("S3").title)
print([s.url for s in result.registry.quarantined])
```

---

## What this does not do

It does not verify that a cited source **actually contains** the figure attributed to it.
That would require fetching and re-reading every page, which DeckScope does not do.

The mitigations are: sources are ranked by reliability and labelled; the ID must come from
the supplied bibliography, so fabricated URLs are much harder; the snippet the model saw is
retained; and every source is printed with its URL so a reader can check in one click.

Check the citations behind any figure your decision actually turns on. The bibliography
exists to make that a ten-second task rather than an afternoon.
