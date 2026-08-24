# Configuration

Settings live in one file, written by `deckscope setup` and editable by hand.

| System | Location |
|---|---|
| Windows | `%APPDATA%\DeckScope\config.yaml` |
| macOS / Linux | `~/.config/deckscope/config.yaml` (or `~/.deckscope/` if it exists) |

Override with the `DECKSCOPE_HOME` environment variable.

**Keys are never stored in this file.** They go in a sibling `.env` with mode 0600, so
`config.yaml` is safe to share, commit, or send to a colleague.

```bash
deckscope config     # show current settings and masked key names
```

---

## A complete file

Every field, with its default. You only need the ones you want to change.

```yaml
# ------------------------------------------------------------------ AI
provider:
  name: anthropic              # anthropic | openai | gemini | openrouter | groq |
                               # bedrock | openai_compatible | cli | mcp | manual | mock
  model: claude-sonnet-5       # null uses the provider's default
  api_key_env: ANTHROPIC_API_KEY
  base_url: null               # for self-hosted, proxies, Ollama, LM Studio
  temperature: 0.2
  max_tokens: 8000
  timeout: 180                 # seconds
  extra: {}                    # provider-specific — see below

# Optional: a cheaper model for extraction, the good one for reasoning.
# Same fields as `provider`. Omit to use `provider` for everything.
extract_provider:
  name: anthropic
  model: claude-haiku-4-5-20251001

# -------------------------------------------------------------- research
research:
  name: auto                   # auto | tavily | serper | brave | exa |
                               # provider_native | mcp | none
  max_results: 8               # results per query
  max_queries: 8               # queries per analysis
  api_key_env: TAVILY_API_KEY
  recency_days: 540            # bias toward recent sources; null = no limit
  extra: {}

# ----------------------------------------------------------------- lens
lenses: [investor]             # investor | founder | neutral, one or more

# --------------------------------------------------------------- output
output:
  formats: [html, pdf]         # md html pdf docx pptx xlsx json txt
  out_dir: ~/Documents/DeckScope Reports
  basename: null               # defaults to a slug of the company name
  include_raw_json: true       # always also write the full JSON
  theme: slate                 # slate | midnight | paper

# ------------------------------------------------------------- security
security:
  mode: balanced               # strict | balanced | permissive | off
  scan_deck_forensics: true    # invisible text, tiny fonts, off-slide shapes
  min_font_pt: 4.0
  contrast_threshold: 0.12
  scan_speaker_notes: true
  scan_metadata: true
  scan_web_sources: true
  max_source_chars: 6000
  block_untrusted_domains: []
  strip_invisible_chars: true
  normalize_homoglyphs: true
  redact_on: high              # minimum severity redacted in balanced mode
  abort_on: critical           # minimum severity that aborts in strict mode

# ---------------------------------------------------------------- panel
panel:
  members: [anthropic:claude-sonnet-5, openai:gpt-5.2]
  rounds: 1

# ----------------------------------------------------------------- misc
cache_dir: null               # null disables caching; omit for the
                              # per-user application-data directory
verbose: true
```

---

## Provider `extra` fields

**Local / self-hosted** (`openai_compatible`):

```yaml
provider:
  name: openai_compatible
  base_url: http://localhost:11434/v1     # Ollama
  model: llama3.1:8b
  extra:
    headers: {}       # merged into every request
    body: {}          # merged into the JSON payload
```

**MCP** (`mcp`):

```yaml
provider:
  name: mcp
  extra:
    command: ["npx", "-y", "my-mcp-server"]   # string or list
    mode: sampling                             # sampling | tool
    tool_name: chat                            # when mode: tool
    prompt_arg: prompt
    env: {MY_VAR: value}
```

**An agent CLI you already have** (`cli`):

```yaml
provider:
  name: cli
  model: claude                     # claude | ollama | codex | gemini
  extra:
    preset: claude
    ollama_model: llama3.1:8b       # when preset is ollama
    command: ["my-cli", "--flag"]   # or override entirely
```

**Copy-and-paste** (`manual`):

```yaml
provider:
  name: manual
  extra:
    exchange_dir: ~/.deckscope/exchange
```

**AWS Bedrock:**

```yaml
provider:
  name: bedrock
  model: anthropic.claude-sonnet-4-5-20250929-v1:0
  extra:
    region: us-east-1
```

---

## Research `extra` fields

**MCP search server:**

```yaml
research:
  name: mcp
  extra:
    command: ["npx", "-y", "some-search-mcp"]
    tool_name: search
    query_arg: query
```

**The provider's own web search** — no extra key; only some providers support it. If
yours doesn't, DeckScope says so rather than silently returning nothing:

```yaml
research:
  name: provider_native
```

---

## Precedence

Highest wins:

1. Command-line flags
2. `--config FILE`, if given
3. Your settings file
4. Environment variables (`DECKSCOPE_PROVIDER`, `DECKSCOPE_MODEL`, `DECKSCOPE_RESEARCH`)
5. Built-in defaults

For API keys specifically, an existing environment variable always beats the saved one —
so a CI environment can supply keys without touching the user's file.

---

## Per-project configs

Keep a config in a project folder and point at it:

```bash
deckscope run deck.pdf --config ./team-config.yaml
```

Useful for a shared house style — a fixed lens, format set, and security mode — checked
into a repo. Since keys never live in the config, it is safe to commit.

---

## Multiple profiles

```bash
DECKSCOPE_HOME=~/.deckscope-work    deckscope setup
DECKSCOPE_HOME=~/.deckscope-work    deckscope run deck.pdf

DECKSCOPE_HOME=~/.deckscope-personal deckscope run other.pdf
```

Each profile gets its own settings, keys, and defaults.

---

## Tuning cost

| Change | Effect |
|---|---|
| `extract_provider` → a cheap model | Extraction is the longest prompt; this is the biggest single saving |
| `research.max_queries` → 4 | Fewer searches, smaller research prompt |
| `research.max_results` → 5 | Smaller prompt per query |
| `provider.max_tokens` → 5000 | Shorter reports |
| `lenses: [investor]` | Each extra lens is one more comparison call |
| Keep `cache_dir` enabled | Re-running a deck with a new lens reuses extraction and research |
| `panel.rounds: 0` | Parallel independent analyses with measured agreement, no review calls |

## Tuning quality

| Change | Effect |
|---|---|
| A stronger model | The largest single factor |
| `research.max_queries` → 12 | Broader evidence base |
| `research.name: exa` | Semantic search finds analyst pages rather than listicles |
| `research.recency_days: 365` | Tighter recency for fast-moving categories |
| `provider.temperature: 0.1` | More consistent, less exploratory |
| A panel | Catches what any single model misses |
