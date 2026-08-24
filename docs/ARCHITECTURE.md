# Architecture

How the pieces fit, and — more usefully — why they fit that way.

---

## The central design decision: isolation

The obvious way to build this is one prompt: "here is a deck, analyze it and research
the market". That produces a report that inherits the deck's framing. If the deck says
the market is $47B, the model reasons about a $47B market, searches for evidence about a
$47B market, and concludes that the market is large.

DeckScope splits the work across three agents that cannot contaminate each other:

```
   deck file
      │
      ▼
 ┌─────────────────┐
 │ SECURITY SCREEN │  file forensics + text scan + sanitize + fence
 └─────────────────┘
      │
      ▼
 ┌──────────────────┐        extraction only. Forbidden from evaluating.
 │ 1. DeckAnalyst   │        Output: structured claims + a research agenda.
 └──────────────────┘
      │  claims, category, research queries
      ▼
 ┌──────────────────┐        searches the web, screens every result,
 │ 2. MarketAnalyst │        describes the market on its own terms.
 └──────────────────┘        Never told to compare.
      │  market picture + numbered bibliography
      ▼
 ┌──────────────────┐        the only agent that sees both.
 │ 3. Comparison    │        The only one allowed to conclude anything.
 └──────────────────┘
      │
      ▼
  citation resolution → renderers → md / html / pdf / docx / pptx / xlsx / json / txt
```

The market agent receives the deck's *claims* — it has to, or it cannot know what to
research — but its instructions are explicit: describe the territory, not the map the
founders drew. It is told to find competitors the deck never mentions and to report where
credible estimates diverge rather than converging on the deck's number.

---

## Module map

```
deckscope/
├── config.py            RunConfig, ProviderConfig, ResearchConfig, OutputConfig, Lens
├── settings.py          per-user settings and key storage (~/.deckscope)
├── schemas.py           the JSON contracts between agents
├── sources.py           SourceRegistry — S-IDs, citation resolution, bibliography
├── orchestrator.py      Pipeline — wires the three agents, owns the run
├── ensemble.py          Panel — several pipelines + cross-review + consensus
├── wizard.py            the guided setup and `doctor`
├── cli.py               argparse entry point
├── webapp.py            stdlib-only local app window
├── mcp_server.py        JSON-RPC MCP server
│
├── ingest/loader.py     pptx / pdf / docx / md / txt / html / json / URL → text
│
├── security/
│   ├── policy.py        SecurityPolicy and the four modes
│   ├── text_scanner.py  intent + concealment detection
│   ├── forensics.py     re-opens the original file for hidden-by-rendering text
│   ├── sanitizer.py     strip, fold, redact, fence
│   ├── screening.py     screen_deck() and screen_sources()
│   └── report.py        Finding, ScanReport, SecurityAbort
│
├── providers/           anthropic, openai(+compat), bedrock, mcp, cli, manual, mock
├── research/            tavily, serper, brave, exa, provider_native, mcp, none
├── agents/              deck_agent, market_agent, synthesis_agent
├── prompts/             templates.py + lenses.py
└── render/              markdown, html, pdf, docx, pptx, xlsx, json, text, panel
```

---

## The registries

Providers, research backends and renderers all live behind a registry with the same
shape:

```python
register_provider(MyProvider)
register_researcher(MySearch)
register_renderer("myfmt", my_render_fn)
```

Three properties matter:

**Lazy.** Optional backends are imported inside a `try`, so a missing SDK removes one
backend rather than breaking the import.

**Bootstrap-safe.** Built-ins load on first access, guarded by a flag set *before*
bootstrapping runs — because `_do_bootstrap` registers through `register_*`, which calls
back in. Registering a custom backend before the built-ins load no longer shadows them.

**Thread-safe.** The panel runs backends in parallel threads. Registration takes a
reentrant lock.

---

## Data flow, concretely

**1. Load.** `ingest/loader.py` turns any supported file into slide-numbered text. It
detects `--- Slide N ---` markers, extracts tables and chart categories from PPTX, pulls
speaker notes, and flags image-only PDFs rather than returning nothing.

**2. Screen.** `security/screening.screen_deck()` runs three passes: file forensics on
the *original* file (plain-text extraction has already discarded what makes hidden text
hidden), a text scan of the extracted content, then sanitization. The cleaned text is
wrapped in an explicit trust-boundary fence before any model sees it.

**3. Extract.** `DeckAnalyst` returns `DECK_SCHEMA`: company, problem, solution, market
sizing with methodology, business model, traction, competition, team, ask, a list of
claims each marked load-bearing or not, deck-quality notes, and a research agenda of
specific search queries.

**4. Research.** `MarketAnalyst` takes the agenda, tops it up with a dedicated
query-generation pass if it is thin, runs the searches, registers **every** result in the
`SourceRegistry` with a stable ID, screens them, drops hostile ones, and hands the
numbered bibliography to the model.

**5. Compare.** `ComparisonSynthesist` receives both artifacts with internals stripped,
plus the lens block, and returns `COMPARISON_SCHEMA`.

**6. Resolve citations.** `sources.resolve_citations()` walks the finished result,
attributes every `source_ids` array and every inline `[S3]` reference back to the
registry, and marks each source cited / consulted / quarantined.

**7. Render.** Each renderer reads the same `AnalysisResult`.

---

## The panel

`ensemble.Panel` runs step 1–6 once per panelist, in parallel threads, each with its own
cache namespace so they cannot share answers. Then:

- **Cross-review.** Each panelist sees the others' artifacts under anonymous labels
  (`Panelist B`), and returns `REVIEW_SCHEMA`: per-peer agreements, disagreements typed as
  evidence/interpretation/weighting, errors found, blind spots caught, positions changed,
  positions held with reasons.
- **Revise.** Each rewrites its own comparison, with a `revision_log`. The prompt
  explicitly forbids averaging toward the group.
- **Measure.** `measure_agreement()` computes — in Python, not in a prompt — the verdict
  distribution, score spread and standard deviation, per-dimension contestedness, a
  claim-by-claim agreement matrix, and per-panelist movement.
- **Consensus.** A chair receives every final analysis, every revision log, and the
  measured numbers, and returns `CONSENSUS_SCHEMA`.

A panelist that fails is recorded and the run continues. If only one survives, the
consensus explicitly reports "single panelist — no cross-check was possible".

---

## Failure behaviour

Deliberate, throughout:

| Failure | Behaviour |
|---|---|
| Model returns non-JSON | Two self-repair rounds, then a clear error naming the provider |
| One search query fails | Recorded as a failed-search entry; the others continue |
| No research backend available | Run continues; the market analysis is flagged unverified everywhere and References says so instead of listing sources |
| Optional package missing | That format or reader is unavailable; the rest works; the wizard names the fix |
| One output format fails | The other formats are still written |
| One panelist fails | Reported; the panel continues with the rest |
| Hostile deck, `strict` | `SecurityAbort` with the findings and the exact flag to override |
| Hostile web source | Dropped, not sanitized, and recorded in the bibliography with the reason |

The principle: never silently degrade. A missing capability is stated in the output, not
hidden behind a confident-looking report.

---

## Caching

Keyed on agent + provider + model + a hash of the input. Lives in the per-user
application-data directory, not the working folder — a cache of extracted deck
text is confidential, and the working folder gets committed and cloud-synced.
Panelists get separate namespaces. Disable with `--no-cache` or `cache_dir: null`.

Re-running the same deck with a different lens reuses the deck extraction and market
research and only re-runs the comparison — which is why `--lens all` costs far less than
three separate runs.
