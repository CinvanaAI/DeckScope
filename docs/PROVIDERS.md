# AI connections

DeckScope talks to any model behind one interface. Nine backends ship with it; adding a
tenth is about thirty lines ([EXTENDING.md](EXTENDING.md)).

```bash
deckscope providers      # list them with suggested models
```

---

## Choosing

| If you… | Use |
|---|---|
| want the best analysis and don't mind a few cents per deck | `anthropic` |
| already pay for OpenAI | `openai` |
| want cheap with a very large context | `gemini` |
| want one key for many models | `openrouter` |
| need speed above all | `groq` |
| run on AWS with existing governance | `bedrock` |
| need everything to stay on your machine | `openai_compatible` (Ollama) |
| already have Claude Code or Ollama signed in | `cli` — no key at all |
| have a chat subscription but no API | `manual` — copy and paste |
| just want to see what it does | `mock` — `deckscope demo` |

---

## anthropic — Claude

The strongest analysis, and the only backend with built-in web search.

```yaml
provider:
  name: anthropic
  model: claude-sonnet-5
  api_key_env: ANTHROPIC_API_KEY
```

Key: [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)

| Model | Notes |
|---|---|
| `claude-opus-5` | Deepest analysis, slowest, priciest |
| `claude-sonnet-5` | Best balance — the default |
| `claude-haiku-4-5-20251001` | Fast and cheap; good as an `extract_provider` |

Uses the official SDK if `anthropic` is installed, and plain HTTP against the Messages
API otherwise. Both work; the SDK adds better retries.

Because it supports server-side search, you can skip a separate search key:

```yaml
research:
  name: provider_native
```

---

## openai — ChatGPT

```yaml
provider:
  name: openai
  model: gpt-4o
  api_key_env: OPENAI_API_KEY
```

Key: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

`gpt-4o` for balance, `gpt-4o-mini` for cost, `o4-mini` for reasoning-heavy work at the
cost of speed.

---

## gemini — Google

Speaks OpenAI's shape through Google's compatible endpoint.

```yaml
provider:
  name: gemini
  model: gemini-flash-latest
  api_key_env: GEMINI_API_KEY
```

Key: [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

Very large context and low cost make it a good fit for long decks. `gemini-2.5-pro` for
deeper analysis.

---

## openrouter — many models, one key

```yaml
provider:
  name: openrouter
  model: anthropic/claude-sonnet-4.5
  api_key_env: OPENROUTER_API_KEY
```

Key: [openrouter.ai/keys](https://openrouter.ai/keys)

The simplest way to assemble a diverse panel without collecting several accounts:

```bash
deckscope panel deck.pdf --panel \
  openrouter:anthropic/claude-sonnet-4.5 \
  openrouter:openai/gpt-4o \
  openrouter:google/gemini-flash-latest
```

---

## groq — very fast

```yaml
provider:
  name: groq
  model: llama-3.3-70b-versatile
  api_key_env: GROQ_API_KEY
```

Fast enough that a three-round panel finishes while you're still reading the first
report. Analysis quality is below the frontier models; good as a panel member, less good
alone.

---

## bedrock — AWS

```yaml
provider:
  name: bedrock
  model: anthropic.claude-sonnet-4-5-20250929-v1:0
  extra:
    region: us-east-1
```

Needs `pip install boto3` and standard AWS credentials. Uses the Converse API, which
normalizes across model families, so Llama and Mistral model IDs work unchanged.

For organizations where data must stay inside an existing AWS account and governance
boundary.

---

## openai_compatible — local and self-hosted

Anything speaking the OpenAI chat-completions shape: **Ollama**, **LM Studio**, **vLLM**,
**llama.cpp server**, **Together**, **Fireworks**, or a company gateway.

```yaml
provider:
  name: openai_compatible
  base_url: http://localhost:11434/v1     # Ollama's default
  model: llama3.1:8b
```

```bash
# Ollama
ollama serve
ollama pull llama3.1:8b
deckscope run deck.pdf --provider openai_compatible

# LM Studio: start the local server, then
#   base_url: http://localhost:1234/v1
```

Free, private, and offline-capable. Pair with `research: none` for a fully air-gapped
run — the report will state clearly that no external sources were consulted.

A caution worth stating: small local models produce noticeably weaker analysis, and are
more likely to fail JSON validation. DeckScope retries and repairs, but a 7B model will
not match a frontier model on a task this structured. Use 14B or larger where you can.

---

## cli — an AI app already on your computer

Zero keys, zero extra cost: DeckScope shells out to an agent CLI you already have signed
in.

```yaml
provider:
  name: cli
  model: claude          # claude | ollama | codex | gemini
```

The setup wizard detects which of these are on your PATH and offers them.

| Preset | Requires |
|---|---|
| `claude` | Claude Code, signed in — uses your existing subscription |
| `ollama` | Ollama installed; set `extra.ollama_model` |
| `codex` | OpenAI Codex CLI |
| `gemini` | Google Gemini CLI |

Override entirely with `extra.command` for any CLI that reads a prompt on stdin and
prints a reply.

---

## mcp — through an MCP server

For a model exposed by an MCP server rather than an HTTP API.

```yaml
provider:
  name: mcp
  extra:
    command: ["npx", "-y", "my-mcp-server"]
    mode: sampling          # sampling | tool
```

`sampling` uses the MCP standard `sampling/createMessage`. `tool` calls a named tool —
set `tool_name` and `prompt_arg`. Transport is stdio, spoken directly; no MCP SDK needed.

---

## manual — copy and paste

For people with a chat subscription and no API access at all.

```yaml
provider:
  name: manual
  extra:
    exchange_dir: ~/.deckscope/exchange
```

At each step DeckScope writes the prompt to a file, puts it on your clipboard, and waits.
You paste it into ChatGPT, Claude, Gemini — whatever you use — save the reply into the
named file, and press Enter.

Slow, and it needs you present for three to five steps. But it costs nothing beyond a
subscription you already have, and it works with assistants that have no API.

**Answers are cached by prompt content.** Close the terminal halfway through and run the
same command tomorrow: every prompt you already answered replays instantly and DeckScope
stops at the first genuinely new one. Identity comes from a hash of the prompt text
rather than a step counter, so an identical prompt issued twice — which happens whenever
a panel convenes several panelists on the same deck — is only asked of you once. Answers
live in `<exchange_dir>/answers/`; delete one to be asked again.

### Spool mode — driving DeckScope from a script or an agent

The same mechanism without the prompts to press Enter. DeckScope writes
`asked/<hash>.prompt.txt`, blocks until `answers/<hash>.txt` appears, and continues.
Anything that can watch a directory can drive the entire pipeline this way with no API
key at all.

```bash
export DECKSCOPE_MANUAL_DIR=/tmp/spool
export DECKSCOPE_MANUAL_INTERACTIVE=0      # no keyboard at the other end
export DECKSCOPE_MANUAL_TIMEOUT=3600       # how long to wait for each answer
export DECKSCOPE_MANUAL_TAG=run-1          # labels files when several runs share a spool
deckscope eval --provider manual --mode pipeline baseline
```

The environment is read as well as the config because `deckscope eval` builds its own
provider configuration and has nowhere to thread `extra` through.

An unanswered prompt is an error, never an empty completion — an empty string would flow
into the JSON repair loop and surface three retries later as a parse failure, which
describes the wrong problem. Token counts in this mode are character-based estimates and
are labelled `estimated`; every mode is estimated the same way, so cost comparisons
between modes hold, but nobody should quote them as billing figures.

This mode is how the real-model evaluation in [PANEL.md](PANEL.md) was run.

---

## mock — the offline demo

Deterministic, schema-shaped sample output. Powers `deckscope demo` and the test suite,
so a new user can see the whole pipeline before configuring anything.

Model names seed a small deterministic divergence, which is why `deckscope demo --panel`
produces a panel that genuinely disagrees with itself.

---

## Mixing models in one run

Use a cheap model for extraction — the longest prompt — and a strong one for reasoning:

```yaml
provider:
  name: anthropic
  model: claude-sonnet-5
extract_provider:
  name: anthropic
  model: claude-haiku-4-5-20251001
```

Typically cuts cost meaningfully with little quality loss, because extraction is a
mechanical task and comparison is not.

---

## Health checks

`deckscope doctor` makes a real round-trip to your provider and a real search against
your research backend, and reports the actual error when either fails.

```python
from deckscope.config import ProviderConfig
from deckscope.providers.registry import get_provider

print(get_provider(ProviderConfig(name="anthropic")).health_check())
# {'ok': True, 'provider': 'anthropic', 'model': 'claude-sonnet-5', 'reply': 'ok'}
```
