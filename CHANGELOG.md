# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

Nothing yet.

## [1.0.0] — 2026-08-23

First release.

### The pipeline

- Three isolated agents — **DeckAnalyst**, **MarketAnalyst**, **ComparisonSynthesist** —
  so the market view is never anchored on the deck's own framing. The extraction agent is
  forbidden from evaluating; the market agent researches the category without being told
  what the deck claims about it; only the third agent sees both.
- Three analytical lenses: **investor**, **founder**, **neutral**, each with its own
  stance, weighting and verdict scale.
- Deck ingestion for `.pptx` `.pdf` `.docx` `.md` `.txt` `.html` `.json` and URLs, with
  slide numbering, table and chart-category extraction, speaker notes, and detection of
  image-only PDFs.

### AI connections

- Nine backends behind one interface: `anthropic`, `openai`, `gemini`, `openrouter`,
  `groq`, `bedrock`, `openai_compatible` (Ollama, LM Studio, vLLM), `cli` (an agent CLI
  already signed in), `mcp`, `manual` (copy-and-paste, works with any chat AI), and `mock`
  for offline demos.
- Anthropic works through the official SDK when installed and plain HTTP otherwise.
- Optional `extract_provider` so a cheap model can do extraction and a strong one the
  reasoning.
- JSON self-repair with two retry rounds, and `health_check()` on every provider.

### Research

- Seven research backends: `tavily`, `serper`, `brave`, `exa`, `provider_native`, `mcp`,
  `none`, plus `auto` which picks whatever is available and degrades honestly.
- Search queries are generated from the deck's load-bearing claims and printed in the
  report.
- Running without research is supported and clearly labelled as unverified throughout.

### Security

- **Deck forensics**: re-opens the original file to recover text hidden by rendering —
  colour-matched to background, sub-point fonts, off-page and off-slide positioning,
  hidden slides, speaker notes, document metadata, PDF render mode 3.
- **Text screening**: fourteen intent patterns (instruction override, role hijack, fake
  system messages, chat-template delimiter spoofing, conceal directives, score and verdict
  manipulation, exfiltration, authority spoofing, fence-breaking) and five concealment
  signals (zero-width and bidi characters, Unicode tag-block smuggling with payload
  decoding, homoglyph evasion, base64 payloads).
- Severity escalates when intent and concealment co-occur.
- **Web source screening** with URL checks; hostile sources are dropped rather than
  sanitized, and the drop is recorded in the bibliography.
- Layered sanitization: strip → fold homoglyphs → redact visibly → fence with an in-band
  trust boundary.
- Four modes: `strict`, `balanced`, `permissive`, `off`.
- Every report carries an **Input integrity screen** section, including when clean.

### Citations

- `SourceRegistry` assigns stable IDs (`S1`, `S2`, …) at retrieval, before screening.
- Agents cite by ID; citations are resolved after the run by ID, URL or title.
- The complete bibliography is printed in every format, in three groups: cited, consulted
  but uncited, and dropped by the security screen — so absence of evidence is as visible
  as its presence.
- Quarantined sources can never be promoted to cited.

### The panel

- Several AI connections analyze the same deck independently and in parallel, then read
  each other's work **anonymized**, concede or hold each position with reasons, and revise.
- Agreement is **measured in Python** — verdict distribution, score spread and standard
  deviation, per-dimension contestedness, a claim × panelist agreement matrix, per-panelist
  movement — and handed to the chair as input.
- Consensus report leads with the disagreements, includes a minority report, and names
  blind spots the whole panel may share.
- Graceful degradation: a failed panelist is reported and the run continues; a lone
  survivor is labelled "single panelist — no cross-check was possible".

### Output

- Eight formats: `md`, `html`, `pdf`, `docx`, `pptx`, `xlsx`, `json`, `txt`, plus dedicated
  panel reports.
- Three themes: `slate`, `midnight`, `paper`.
- Self-contained HTML with no external assets; PDF via WeasyPrint, headless Chrome, or
  ReportLab.

### Interfaces

- Double-click installers for Windows, macOS and Linux that check Python, create a private
  environment, add Desktop shortcuts, and launch setup.
- Six-question guided setup wizard that tests every answer, plus `deckscope doctor`.
- A local drag-and-drop app window built on the standard library alone.
- Full CLI: `setup`, `app`, `run`, `panel`, `demo`, `doctor`, `providers`, `formats`,
  `config`.
- Python API: `analyze()` and `analyze_with_panel()`, plus `Pipeline` and `Panel`.
- An MCP server exposing `analyze_deck`, `analyze_deck_panel`, `scan_deck_security`,
  `list_capabilities`, `get_settings`.
- A portable skill for skill-aware assistants.

### Extensibility

- Thread-safe, lazily bootstrapped registries for providers, research backends and
  renderers. Adding to any of them is one call.

### Testing

- 42 tests covering the security layer, the pipeline, the registries and the panel — all
  runnable offline with no API key, via `pytest` or a zero-dependency runner.
