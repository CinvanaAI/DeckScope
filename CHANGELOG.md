# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Panel — added

- **Stopping is now a strategy, not a constant.** `adaptive` (default), `convergence`,
  `confidence_floor` and `fixed`. Convergence can skip cross-review entirely when the
  panel already agreed independently; confidence_floor refuses to present a
  low-confidence result as settled and says so when it hits the cap. Every decision is
  logged, and the report shows the spread, agreement, position changes and contested
  claims after each round with the reason it continued or stopped.
- **Panelists rank each other's finished reports.** Borda count, self-votes structurally
  impossible, reasons required, and a preference cycle (A > B > C > A) reported as a
  cycle rather than broken arbitrarily. The chair's synthesis is still the headline, but
  each panelist's own report is kept intact beside it, ordered by the vote — a synthesis
  can smooth away the disagreement that is the point.
- The round sequence is driven by the strategy rather than hardcoded, so new stopping
  rules are a subclass rather than an edit to `Panel.run()`.

### Evaluation — added

- **Single-prompt baseline mode** (`--mode baseline`), and `--mode both` to run it
  alongside the pipeline on the same deck with identical screening and identical sources.
  Writes `mode_comparison.json` and prints verdict agreement, score gap, claims examined,
  claims carrying a citation, blind spots named, and cost in tokens and seconds.
  Deliberately declines to name a winner: whether the extra passes bought anything is a
  judgement about reasoning quality that a count cannot make.
- This is the control the architecture never had. The README no longer says the design is
  unmeasured; it says how to measure it.

### Security — fixed

- **Local web server could execute arbitrary files.** `GET /api/open` passed any
  path to the OS handler; on Windows that means running an executable. Any web page
  open in your browser could trigger it. Now: per-launch token, Origin validation,
  POST only, and restricted to files DeckScope itself produced. Body size, concurrent
  jobs and job retention are also capped.
- **Enforcement now follows detection.** Redaction is driven by the findings and
  their exact character spans, so a detected base64 payload is removed rather than
  reported and left in place, and `redact_on: high` redacts high-severity findings
  instead of silently only doing `critical`.
- **Dangerous-scheme URLs quarantine their source.** Previously a `javascript:` or
  `data:` result was flagged and then kept.
- **Concealment escalation is span-local.** One zero-width character no longer
  upgrades the severity of every later match in the document.
- **Unsafe URLs cannot become live links.** All hrefs pass through `safe_url`;
  anything that is not http(s)/mailto renders as inert text.
- **Remote deck fetching is SSRF-guarded.** Private, loopback and link-local
  addresses are refused, redirects are revalidated, downloads are size- and
  time-capped, and temporary files are uniquely named.
- **CLI providers are sandboxed.** Minimal environment, empty temporary working
  directory, and no-tool flags where the CLI supports them.
- **`get_settings` no longer returns secrets over MCP.**
- **API keys are genuinely owner-only on Windows**, via a real ACL rather than a
  `chmod` that does nothing there. `doctor` reports whether it worked.
- **Encoded-payload detection no longer rests on a length threshold.** It was 80
  characters, then 32, and both let real payloads through: `"ignore instructions"`
  encodes to 28 characters and `"you are now a promoter"` to 32 including padding the
  regex did not count. Length is now only a cheap pre-filter; the decode does the work,
  across both base64 alphabets and all padding lengths. Zero false positives on git
  SHAs, embedded images and tenant IDs.
- **The instruction-override pattern required a qualifier.** `"ignore all instructions"`
  matched; plain `"ignore instructions"` did not. Split into two forms so the
  unqualified case is caught without flagging "our rules engine lets admins override
  rules".

### Correctness — fixed

- **Panel citations could point at the wrong source.** Each panelist numbered its
  own bibliography from S1, and only one registry survived, so Panelist B's `S1`
  resolved against Panelist A's document. Registries are now merged into one global
  namespace before any cross-review, with every panelist's citations rewritten.
- **Claim agreement compared unrelated claims.** The matrix grouped by each
  panelist's own C-numbering. It now matches on content — quoted figures and
  significant words — and reports single-panelist claims as silence rather than
  disagreement.
- **The cache never actually hit.** Keys used `hash()`, which is randomized per
  process. Now SHA-256 over canonicalized inputs, bound to the exact sources, the
  security policy and a prompt epoch, with a TTL and owner-only permissions.
- **Token accounting was always zero**, because `complete_json` discarded the
  provider's response object. Usage is now tracked, including JSON-repair retries.
- **`--research none` fabricated a source.** It registered its own "no research was
  performed" notice as a cited bibliography entry. The registry now stays empty and
  the report says so plainly.
- **Model output is validated**, not merely coerced: enums, numeric ranges, row
  shapes, and citations to sources that were never supplied. Every repair is
  recorded in the report.

### Platform — fixed

- **Windows console output crashed all three demos.** Box-drawing characters cannot
  be encoded on a CP-1252 console. Output now goes through `deckscope.console`,
  which requests UTF-8 and transliterates when it cannot get it. A test forbids bare
  `print()` in the package.
- **Anthropic defaults returned HTTP 400.** `temperature` is rejected on Claude 4.7
  and later; it is now omitted for those models.
- **The default Gemini model was past its shutdown date.** Refreshed, with retired
  names mapped to an actionable error.
- **The test suite required optional packages**, so it failed on the minimal install
  the README recommends. It now skips formats whose dependency is absent.
- MCP client: enforced timeouts, drained stderr (a chatty server could deadlock),
  and out-of-order responses are buffered rather than discarded.

### Documentation

- Version dropped. This is unreleased software and now says so.
- Claims narrowed to what the code enforces: DeckScope screens **retrieved
  snippets**, not whole source pages; the panel is **role-separated analysis with
  model diversity**, not independent market discovery; citation resolution checks
  that a source exists, **not** that it supports the claim.
- Added a threat model, and a limitations section that states the three-agent design
  is unproven rather than merely unmeasured.

### Testing

- 99 tests, up from 42, including one regression test per audit finding and full
  coverage of the stopping strategies, voting maths and baseline mode.
- The suite passes on a minimal install and on a legacy Windows console.

---

## Earlier

Initial implementation, before external audit.

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
