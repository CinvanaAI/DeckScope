# Command reference

```
deckscope <command> [options]
```

Run `deckscope` with no arguments for help, or `deckscope <command> --help` for one
command.

---

## `setup`

Guided configuration. Six plain-language questions, each answer tested as you go. Writes
`~/.deckscope/config.yaml` and stores keys in a sibling `.env` readable only by you.

```bash
deckscope setup
```

Safe to re-run — it offers to keep your existing settings.

---

## `app`

Opens a drag-and-drop window in your browser. Binds to `127.0.0.1` only; nothing is
exposed to your network, and no file leaves your machine except to the AI service you
configured.

```bash
deckscope app
deckscope app --port 9000 --no-browser
```

---

## `run`

Analyze one deck.

```bash
deckscope run DECK [options]
```

`DECK` is a path or a URL. Supported: `.pdf` `.pptx` `.docx` `.md` `.txt` `.html` `.json`.

| Option | Default | Meaning |
|---|---|---|
| `--lens, -l` | from settings | `investor` `founder` `neutral`, several, or `all` |
| `--format, -f` | from settings | `md html pdf docx pptx xlsx json txt` |
| `--out, -o` | from settings | Output folder |
| `--company` | — | Company name, if the deck omits it |
| `--provider` | from settings | Override the AI backend |
| `--model` | from settings | Override the model |
| `--research` | `auto` | `auto tavily serper brave exa provider_native mcp none` |
| `--security` | `balanced` | `strict balanced permissive off` |
| `--theme` | `slate` | `slate midnight paper` |
| `--max-queries` | 8 | Search queries to run |
| `--no-cache` | off | Ignore cached agent results |
| `--quiet, -q` | off | Suppress progress output |
| `--mode` | `pipeline` | `pipeline` (three isolated agents), `baseline` (one prompt), or `both` |
| `--config` | — | Use a specific config file instead of your settings |

```bash
deckscope run deck.pdf
deckscope run deck.pdf --lens founder --format html pdf
deckscope run deck.pdf --lens all --research tavily --security strict
deckscope run deck.pptx --provider gemini --model gemini-2.0-flash --theme midnight
deckscope run https://example.com/deck.pdf --company "Acme Flow" --out ./reports
```

**Exit codes:** `0` success · `1` failure · `2` bad input · `3` blocked by the security
screen in strict mode.

---

## `panel`

Analyze with several AI connections that then review each other and revise. See
[PANEL.md](PANEL.md).

```bash
deckscope panel DECK --panel PROVIDER[:MODEL] PROVIDER[:MODEL] ... [options]
```

| Option | Default | Meaning |
|---|---|---|
| `--panel, -p` | from settings | Two or more connections |
| `--rounds, -r` | 3 | Maximum cross-review rounds; `0` skips review entirely |
| `--strategy, -s` | `adaptive` | When to stop: `adaptive` `convergence` `confidence_floor` `fixed` |
| `--no-vote` | off | Skip the round where panelists rank each other's reports |
| `--chair` | first panelist | Which connection writes the consensus |
| `--sequential` | off | Run panelists one at a time instead of in parallel |

Plus every option `run` accepts.

```bash
deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-4o
deckscope panel deck.pdf --panel anthropic openai gemini --rounds 2 --format html pdf
deckscope panel deck.pdf --panel anthropic:claude-opus-5 anthropic:claude-haiku-4-5-20251001 \
                         --chair openai:gpt-4o --lens all
deckscope panel deck.pdf            # uses the panel saved by `deckscope setup`
deckscope panel deck.pdf --panel anthropic openai --strategy convergence
deckscope panel deck.pdf --panel anthropic openai gemini --strategy confidence_floor -r 4
```

**Comparing the architecture against a single prompt:**

```bash
deckscope run deck.pdf --mode baseline    # one call per lens, ~a third of the cost
deckscope run deck.pdf --mode both        # both, plus mode_comparison.json
```

---

## `demo`

A full run against a built-in sample deck, using built-in model answers. No AI account,
no key, no network, no cost.

```bash
deckscope demo
deckscope demo --panel                    # three simulated analysts who disagree
deckscope demo --injected                 # a deck with a hidden injection
deckscope demo --lens all --format html pdf --out ./demo
```

`--injected` is worth running once: it shows exactly what DeckScope does when a deck
contains hidden text telling the AI to score it 10/10.

---

## `doctor`

Tests everything and names the fix for anything broken: the AI connection (a real
round-trip), the research backend (a real search), the packages your output formats need,
and whether the reports folder is writable.

```bash
deckscope doctor
```

Exit code `0` means healthy.

---

## `providers`

Lists every AI backend and its suggested models.

```bash
deckscope providers
```

---

## `formats`

Lists every output format with a description.

```bash
deckscope formats
```

---

## `config`

Prints your current settings and the names of saved keys, masked.

```bash
deckscope config
```

---

## Environment variables

| Variable | Effect |
|---|---|
| `DECKSCOPE_HOME` | Where settings and keys live. Useful for multiple profiles. |
| `DECKSCOPE_PROVIDER` | Default provider, overridden by config and flags |
| `DECKSCOPE_MODEL` | Default model |
| `DECKSCOPE_RESEARCH` | Default research backend |
| `ANTHROPIC_API_KEY` etc. | Provider keys. An existing environment variable always wins over the saved one. |
| `NO_COLOR` | Disable coloured output |

Precedence, highest first: **command-line flags → config file → environment → defaults**.

---

## As a module

Everything also works without the `deckscope` script on your PATH:

```bash
python -m deckscope run deck.pdf
python -m deckscope demo --panel
python -m deckscope.mcp_server          # the MCP server
```
