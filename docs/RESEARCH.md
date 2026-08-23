# Web research

This is the half that makes the analysis worth reading. Without it, the "market" view is
the model's memory — which has a cutoff date, cannot see recent funding rounds, pricing
changes or new entrants, and cannot be cited.

```bash
deckscope run deck.pdf --research tavily
```

---

## Backends

| Backend | Key | Free tier | Best for |
|---|---|---|---|
| `tavily` | `TAVILY_API_KEY` | generous | **Recommended.** Built for AI research; returns a synthesized answer plus sources |
| `serper` | `SERPER_API_KEY` | 2,500 searches | Google's index, including answer boxes |
| `brave` | `BRAVE_API_KEY` | yes | An index independent of Google |
| `exa` | `EXA_API_KEY` | yes | Semantic search — finds analyst pages rather than listicles |
| `provider_native` | none | — | The AI provider searches for itself (Anthropic supports this) |
| `mcp` | none | — | Route through an MCP search server you already run |
| `none` | none | — | No research. Clearly labelled as unverified throughout the report |
| `auto` *(default)* | — | — | Uses whichever key it finds, then provider-native, then `none` |

Sign-up links appear in the setup wizard.

---

## How `auto` decides

1. Try `tavily`, `serper`, `brave`, `exa` in that order — the first whose key is present.
2. If none, and the provider supports server-side search, use `provider_native`.
3. Otherwise fall back to `none` — and say so, loudly, in the report.

---

## How queries are built

The deck agent produces a research agenda as part of extraction: specific queries that
would verify the load-bearing claims. It is instructed to write the queries a skeptical
analyst would actually run — naming the category, the competitors, and the metric — and
explicitly told to avoid generic ones like "AI market size".

If that agenda is thin, the market agent runs a dedicated query-generation pass covering
independent sizing, the named and unnamed competitors, recent funding, pricing and
unit-economics norms, and regulatory factors.

Every query used appears in the report, in a collapsed block under References. You can
see exactly what was searched.

```bash
deckscope run deck.pdf --max-queries 12      # broader evidence base
```

---

## What happens to results

1. **Registered.** Every result gets a stable ID (`S1`, `S2`, …) *before* screening, so
   anything later dropped still appears in the bibliography with the reason.
2. **Screened.** Text scanned for injection; URLs checked for punycode, embedded
   credentials, dangerous schemes, shorteners, unusual TLDs. Hostile sources are **dropped,
   not sanitized** — a page behaving that way is not trustworthy evidence.
3. **Capped.** Snippets are truncated so a wall of text cannot bury a payload.
4. **Fenced.** The whole bibliography is wrapped in an explicit trust boundary.
5. **Cited.** The market agent must cite by ID; every citation is resolved back to the
   registry after the run.

See [SECURITY.md](SECURITY.md) and [CITATIONS.md](CITATIONS.md).

---

## Source reliability

The market agent is instructed to rank sources rather than treat them equally:

> A regulator filing or a public company's disclosure beats an analyst house press
> release, which beats a vendor's own "market report", which beats a listicle.

Each source is labelled `primary` / `secondary` / `vendor-marketing` / `unknown` in the
References table, and that label is folded back onto the registry.

Where credible estimates diverge widely, the agent is told to report the range and explain
the divergence rather than averaging it into a single fake number — which is why market
sizing in a DeckScope report often reads "$18–24B, and here is why the estimates differ"
rather than a tidy single figure.

---

## Recency

```yaml
research:
  recency_days: 540     # ~18 months; null for no limit
```

Tighten it for fast-moving categories, loosen it for structural markets where a 2023
regulator filing is still the best available source.

---

## Running without research

Legitimate for a quick pass, an offline machine, or a category you know well:

```bash
deckscope run deck.pdf --research none
```

DeckScope will not pretend. The market agent is told explicitly that no research was
available, instructed to set `sizing_confidence` to `low` and to list the limitation in
`research_gaps`. The References section says, in place of a list:

> No external sources were retrieved for this analysis. Every statement above therefore
> rests on the model's training knowledge and on the deck itself, and should be treated
> as unverified.

---

## Adding a backend

```python
from deckscope import register_researcher
from deckscope.research.base import Researcher, SearchResult

class MySearch(Researcher):
    name = "my_search"
    needs_key = True
    key_env = "MY_SEARCH_KEY"
    blurb = "Our internal research index"

    def search(self, query, max_results=8):
        return [SearchResult(title=r["title"], url=r["url"], snippet=r["text"],
                             published=r.get("date"))
                for r in my_client.search(query, max_results)]

register_researcher(MySearch)
```

`search_many()`, de-duplication, screening, registration and citation all come from the
base class. Return `[]` on a soft failure rather than raising — one bad query should not
end a run.

Internal research repositories are a good fit here: point DeckScope at your own corpus of
market notes and it will cite them alongside public sources.
