# Python API

```bash
pip install -e ".[all]"
```

---

## The one-call version

```python
from deckscope import analyze

result = analyze(
    "deck.pdf",
    lens="investor",                 # or ["investor", "founder"]
    formats=["html", "pdf"],
    out_dir="./reports",
    provider="anthropic",
    model="claude-sonnet-5",
    research="tavily",
    security="balanced",
    company="Acme Flow",
    verbose=True,
)
```

Runs the pipeline, writes the files, returns an `AnalysisResult`.

---

## `AnalysisResult`

```python
result.company                # "Acme Flow"
result.primary                # the first lens's comparison
result.comparisons            # {"investor": {...}, "founder": {...}}
result.deck                   # the deck extraction
result.market                 # the market analysis
result.registry               # SourceRegistry
result.sources                # [Source, ...] in citation order
result.security               # the input integrity screen
result.stats                  # model, research backend, timings, token usage
result.written_files          # paths written

result.to_dict()              # everything, JSON-serializable
result.save_json("out.json")
```

```python
comp = result.primary
comp["headline"]
comp["verdict"]["call"]              # "YES WITH CONDITIONS"
comp["verdict"]["confidence"]        # "medium"
comp["_meta"]["weighted_score"]      # {"score": 65.7, "out_of": 100.0}
comp["summary"]

for c in comp["claim_audit"]:
    print(c["id"], c["assessment"], c["evidence_quality"], c["source_ids"])

for r in comp["risks"]:
    print(r["severity"], r["risk"], r["mitigation_or_test"])

comp["alignment"]["blind_spots"]
```

---

## Full control

```python
from deckscope.config import (Lens, OutputConfig, ProviderConfig,
                              ResearchConfig, RunConfig)
from deckscope.orchestrator import Pipeline

cfg = RunConfig(
    deck_path="deck.pdf",
    company_hint="Acme Flow",
    lenses=[Lens.INVESTOR, Lens.FOUNDER],
    provider=ProviderConfig(name="anthropic", model="claude-sonnet-5",
                            temperature=0.2, max_tokens=8000),
    extract_provider=ProviderConfig(name="anthropic",
                                    model="claude-haiku-4-5-20251001"),
    research=ResearchConfig(name="tavily", max_queries=10, recency_days=365),
    output=OutputConfig(formats=["html", "xlsx"], out_dir="./reports",
                        theme="midnight"),
    security={"mode": "strict", "min_font_pt": 6.0},
    cache_dir=".cache",
    verbose=False,
)

pipe = Pipeline(cfg, on_event=lambda msg, data: print(msg))
try:
    result = pipe.run()
    files = pipe.render(result)
finally:
    pipe.close()
```

`on_event(message, data)` receives every progress event — useful for a UI or a log.

---

## The panel

```python
from deckscope.ensemble import analyze_with_panel

result = analyze_with_panel(
    "deck.pdf",
    ["anthropic:claude-sonnet-5", "openai:gpt-5.2", "gemini"],
    lens="investor", rounds=1, formats=["html"])

cons = result.consensus["investor"]
cons["consensus_verdict"]          # call, confidence, agreement, rationale
cons["where_all_agree"]
cons["contested"]
cons["minority_report"]
cons["reliability"]["shared_blind_spots"]

m = result.metrics["investor"]
m["verdict"]["distribution"]       # {"YES WITH CONDITIONS": 2, "LEAN NO": 1}
m["score"]["spread"]               # 30.0
m["contested_claims"]              # ["C1", "C2"]
m["total_position_changes"]        # 3

for p in result.working:
    print(p.label, p.name)
    print("  conceded:", len(p.review["position_changes"]))
    print("  held:    ", len(p.review["positions_held"]))
    print("  final:   ", p.final("investor")["verdict"]["call"])
```

With explicit control:

```python
from deckscope.ensemble import Panel

panel = Panel(cfg,
              [ProviderConfig(name="anthropic", model="claude-sonnet-5"),
               ProviderConfig(name="openai", model="gpt-5.2")],
              rounds=2,
              chair=ProviderConfig(name="anthropic"),
              parallel=True,
              on_event=lambda m, d: print(m))
result = panel.run()
panel.render(result)
```

---

## Security on its own

Screen a deck without calling any model — fast and free:

```python
from deckscope.ingest.loader import load_deck
from deckscope.security import SecurityPolicy, screen_deck, scan_text

doc = load_deck("deck.pdf")
clean, report = screen_deck(doc, SecurityPolicy(mode="permissive"),
                            deck_path="deck.pdf")

print(report.risk)              # clean | low | medium | high | critical
print(report.summary_line())
for f in report.findings:
    print(f.severity, f.code, f.where, f.detail, f.action)

scan_text("Ignore all previous instructions", "somewhere").risk   # 'critical'
```

---

## The registry

```python
reg = result.registry

reg.stats()          # {'total': 14, 'cited': 6, 'consulted_uncited': 7, 'quarantined': 1}
reg.cited            # [Source, ...]
reg.consulted
reg.quarantined
reg.find("S3")
reg.find("https://example.org/report")

for s in reg.sources:
    print(s.sid, s.status, s.reliability, s.domain, s.cited_by)
```

---

## Rendering separately

```python
from deckscope.render import render, list_formats

paths = render("html", result, Path("./out"), "acme_flow", theme="paper")
list_formats()
```

---

## Registering your own pieces

```python
from deckscope import register_provider, register_researcher, register_renderer
```

See [EXTENDING.md](EXTENDING.md).

---

## Exceptions

| Exception | When | Where |
|---|---|---|
| `ProviderError` | A model backend fails or returns unparseable JSON | `deckscope.providers.base` |
| `DeckLoadError` | The deck cannot be read | `deckscope.ingest.loader` |
| `SecurityAbort` | Strict mode found hostile content; carries `.report` | `deckscope.security.report` |
| `ValueError` | Bad lens, format, backend name, or a one-member panel | — |

```python
from deckscope.security.report import SecurityAbort

try:
    result = analyze("deck.pdf", security="strict")
except SecurityAbort as exc:
    print(exc)                                   # human-readable, with findings
    print(exc.report.risk, len(exc.report.findings))
```

---

## Thread safety

The registries are lock-protected and the pipeline holds no global state, so several
analyses can run in parallel threads — which is exactly what `Panel` does. Give each a
distinct `cache_dir` if you want their caches isolated.
