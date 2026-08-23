# DeckScope

**An agentic framework that reads a pitch deck, researches the market it competes in,
and tells you where the two agree — and where they don't.**

Most deck-analysis tools ask one model to read a deck and give an opinion. That opinion
inherits the deck's own framing: if the deck says the market is $47B, the model reasons
about a $47B market. DeckScope is built to avoid that. It runs three agents in sequence,
deliberately isolated from each other, and it can run the whole thing across several AI
services that then argue with each other.

```
  ┌────────────────┐     ┌──────────────────┐     ┌────────────────────┐
  │ 1. Deck Analyst│ ──▶ │ 2. Market Analyst│ ──▶ │ 3. Comparison      │
  │ extract claims │     │ research the     │     │ claim-by-claim     │
  │ never judge    │     │ market alone     │     │ deck vs. evidence  │
  └────────────────┘     └──────────────────┘     └────────────────────┘
        │                        │                          │
        └──── screened for prompt injection before either runs ────┘
```

The deck agent extracts and never evaluates. The market agent researches the category
without being told what the deck claims about it. Only the third agent sees both, and
only it is allowed to draw conclusions.

---

## Contents

- [What makes it different](#what-makes-it-different)
- [Install](#install)
- [Quick start](#quick-start)
- [The three lenses](#the-three-lenses)
- [Output formats](#output-formats)
- [AI connections](#ai-connections)
- [Web research](#web-research)
- [The security layer](#the-security-layer)
- [Citations](#citations)
- [The panel: several AIs that review each other](#the-panel-several-ais-that-review-each-other)
- [Four ways to use it](#four-ways-to-use-it)
- [Configuration](#configuration)
- [Extending it](#extending-it)
- [Documentation](#documentation)
- [Limitations](#limitations)

---

## What makes it different

**It is provider-agnostic by design.** Claude, GPT, Gemini, Llama on your own machine,
an MCP server, an agent CLI you already have signed in, or copy-and-paste into whatever
chat app you use. One interface, nine backends, and adding a tenth is about thirty lines.

**It screens its inputs for prompt injection.** Both of DeckScope's inputs are written
by other people. A founder can put white text on a white slide. Anyone can publish a web
page hoping a research agent retrieves it. DeckScope re-opens the original file to
recover what rendering hid, screens every web source, neutralizes what it finds, and
reports all of it. [Details below.](#the-security-layer)

**Every source is listed, cited or not.** A report that cites four URLs out of forty
consulted is not auditable. DeckScope assigns every retrieved source a stable ID, has the
agents cite by ID, and prints the complete bibliography — including the sources that
supported nothing and the ones dropped as hostile.

**A panel can disagree.** Run the same deck through several AI services. They analyze it
independently, then read each other's work anonymized, concede what they got wrong, hold
what they got right, and revise. A chair reports where they agreed, where they split, and
how much the agreement is actually worth. [Details below.](#the-panel-several-ais-that-review-each-other)

**A non-technical person can install it.** Double-click an installer, answer six
questions in plain language, drag a deck onto a window.

---

## Install

### The easy way

1. Download or clone this repository.
2. Double-click the installer for your system:

   | System | File |
   |---|---|
   | Windows | `install.bat` |
   | macOS | `install.command` |
   | Linux | `install.sh` |

The installer checks for Python, creates a private environment so nothing on your
machine is disturbed, installs everything, puts a **DeckScope** shortcut on your
Desktop, and walks you through setup.

If Python is missing it opens the download page and tells you exactly which box to tick.

### The developer way

```bash
git clone https://github.com/CinvanaAI/DeckScope.git
cd deckscope
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[all]"
deckscope setup
```

Full details, including offline and locked-down environments, in
**[docs/INSTALL.md](docs/INSTALL.md)**.

---

## Quick start

**See what it does before configuring anything.** No AI account, no key, no cost —
the model's answers are built in:

```bash
deckscope demo                    # a full single-model report
deckscope demo --panel            # three simulated analysts who disagree
deckscope demo --injected         # a deck with a hidden injection, caught and reported
```

**Set it up** — six plain-language questions, each answer tested as you go:

```bash
deckscope setup
```

**Analyze a real deck:**

```bash
deckscope run deck.pdf
deckscope run deck.pdf --lens founder --format html pdf
deckscope run deck.pdf --lens all --research tavily --security strict
deckscope run https://example.com/deck.pdf --company "Acme Flow"
```

**Or never touch a terminal:**

```bash
deckscope app
```

Opens a window in your browser. Drag a deck in, pick what you want, press the button.
It runs entirely on your own machine — nothing is uploaded anywhere except to the AI
service you configured.

---

## The three lenses

Same evidence, different question. Pick one, or produce all three.

| Lens | The question | Verdict scale |
|---|---|---|
| `investor` | Is this worth funding at this ask? | STRONG YES · YES WITH CONDITIONS · LEAN NO · PASS |
| `founder` | Where will this deck lose the room, and how do I fix it? | RAISE-READY · NEEDS TIGHTENING · NEEDS REPOSITIONING · NEEDS A DIFFERENT STORY |
| `neutral` | Where do the claims and the evidence diverge? | *(no recommendation — characterizes alignment only)* |

The lens is not a tone setting. It changes what the agent weights, what it treats as a
problem, and what it recommends. The founder lens separates "the market says you're
wrong" from "the market agrees but your deck fails to prove it", because those need
opposite responses. The neutral lens is forbidden from recommending anything.

```bash
deckscope run deck.pdf --lens investor founder
deckscope run deck.pdf --lens all
```

More in **[docs/LENSES.md](docs/LENSES.md)**.

---

## Output formats

Pick any combination. Every format contains the full analysis, the complete
bibliography, and the security screen result.

| Format | Flag | What it's for |
|---|---|---|
| Markdown | `md` | The canonical text. Diff-able, pasteable. |
| Web page | `html` | Self-contained, dark-mode aware, prints cleanly. |
| PDF | `pdf` | Print-ready. Uses your HTML report if a browser is available, ReportLab otherwise. |
| Word | `docx` | The format most people actually circulate. |
| Slides | `pptx` | A summary deck to present back. |
| Spreadsheet | `xlsx` | Scorecard, claim audit, competitors, references, security findings — each on its own filterable sheet. |
| JSON | `json` | Everything, machine-readable. Always written unless you disable it. |
| Plain text | `txt` | Email bodies and terminals. |

```bash
deckscope run deck.pdf --format html pdf docx xlsx
deckscope formats          # list them with descriptions
```

More in **[docs/OUTPUTS.md](docs/OUTPUTS.md)**.

---

## AI connections

| Backend | `--provider` | Needs | Notes |
|---|---|---|---|
| Claude | `anthropic` | API key | Strongest analysis. Also supports server-side web search. |
| ChatGPT | `openai` | API key | |
| Gemini | `gemini` | API key | Large context, cheap |
| OpenRouter | `openrouter` | API key | One key, many models |
| Groq | `groq` | API key | Very fast |
| AWS Bedrock | `bedrock` | AWS creds | Enterprise deployments |
| Local / self-hosted | `openai_compatible` | nothing | Ollama, LM Studio, vLLM, any OpenAI-shaped server |
| An agent CLI you have | `cli` | nothing | Uses Claude Code, Ollama, Codex or Gemini CLI already signed in |
| An MCP server | `mcp` | nothing | Sampling or a chat tool over stdio |
| Copy and paste | `manual` | nothing | Works with any chat AI, including ones with no API |
| Offline demo | `mock` | nothing | Deterministic sample output |

```bash
deckscope providers                                   # list with models
deckscope run deck.pdf --provider gemini --model gemini-2.0-flash
deckscope run deck.pdf --provider openai_compatible   # your own Ollama
```

You can also use a cheap model for extraction and an expensive one for the reasoning —
see `extract_provider` in **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**.

---

## Web research

This is the half that makes the analysis worth reading. Without it, the "market" view is
the model's memory, which has a cutoff date and cannot see recent funding, pricing, or
new entrants. DeckScope says so loudly in the report when research is unavailable, rather
than quietly producing a confident-looking answer.

| Backend | `--research` | Free tier |
|---|---|---|
| Tavily | `tavily` | Generous — recommended |
| Serper (Google) | `serper` | 2,500 searches |
| Brave | `brave` | Yes |
| Exa (semantic) | `exa` | Yes |
| The provider's own search | `provider_native` | No extra key |
| An MCP search server | `mcp` | — |
| Skip research | `none` | Free, and clearly labelled as unverified |
| Pick whatever is available | `auto` *(default)* | — |

---

## The security layer

Both of DeckScope's inputs are attacker-controllable, and the attack is cheap: put
instructions in a place a human reader never looks but a text extractor always finds.

**In the deck**, DeckScope re-opens the original file — the plain text extraction has
already thrown away what makes hidden text hidden — and looks for:

- text whose colour matches its background (white on white, and every near-miss)
- fonts below 4pt
- text boxes positioned outside the slide or page
- slides marked hidden
- speaker notes, which no audience ever sees
- document metadata fields, invisible in every viewer
- PDF text in render mode 3 (the "invisible" mode)
- zero-width characters, bidi overrides, and Unicode tag-block smuggling
- Cyrillic and Greek homoglyphs mixed into Latin words to dodge keyword filters
- base64 blobs that decode to instructions

**In every web source**, the same text screening, plus URL checks: punycode domains,
embedded credentials, `data:` and `javascript:` schemes, shorteners, unusual TLDs.

**On top of that**, DeckScope looks for *intent*: text ordering the model to ignore its
instructions, reassign its role, dictate a score or verdict, conceal something from you,
or exfiltrate its own prompt. Severity escalates when intent and concealment appear
together — because a founder writing the word "instructions" on a slide is not an attack,
and the same sentence in 1pt white text is.

Four postures:

| Mode | Behaviour |
|---|---|
| `strict` | Refuses to analyze a deck or source containing hidden instructions |
| `balanced` *(default)* | Neutralizes what it finds, continues, reports everything |
| `permissive` | Changes nothing, reports what it found |
| `off` | No screening (not recommended) |

```bash
deckscope run deck.pdf --security strict
deckscope demo --injected              # see it catch a real injection
```

Hostile web sources are **dropped, not sanitized** — a page behaving that way is not
trustworthy evidence regardless of what else it says — and the drop is recorded in the
bibliography with the reason.

A deck that tries to manipulate its own analysis is reported as a finding about the
company. Every report carries an **Input integrity screen** section, even when it is clean.

Full threat model and detection details in **[docs/SECURITY.md](docs/SECURITY.md)**.

---

## Citations

Every source retrieved gets a stable ID (`S1`, `S2`, …) before screening. Agents cite by
ID. The report ends with the complete bibliography in three groups:

- **Cited in this analysis** — with what each one supports
- **Consulted, not cited** — retrieved but supported no conclusion
- **Dropped by the security screen** — with the reason

A claim with no supporting source says so plainly rather than borrowing a citation that
does not actually contain the figure. When no research backend was available at all, the
References section says that in place of a list, and the market analysis is flagged as
unverified throughout.

---

## The panel: several AIs that review each other

One model gives you one model's blind spots. A panel gives you something better — but
only if the panelists actually engage rather than being averaged together.

```bash
deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-4o gemini
deckscope panel deck.pdf --panel anthropic openai --rounds 2 --format html pdf
deckscope demo --panel                       # see it work, free
```

Four rounds:

1. **Independent.** Each panelist runs the full three-agent pipeline alone, in parallel,
   with no knowledge of the others.
2. **Cross-review.** Each reads every other panelist's deck extraction, market analysis
   and comparison — **anonymized as "Panelist B", so it judges the work and not the
   brand** — and records what it concedes, what it holds and why, and what errors it
   found.
3. **Revise.** Each rewrites its own analysis to reflect what it conceded. A panelist
   that was right and challenged badly should barely change; the prompt explicitly
   forbids averaging toward the group.
4. **Consensus.** A chair reports where the panel agreed, where it split, what changed,
   and how much the agreement is worth.

Agreement is **measured in code, not asked of a model**: verdict distribution, score
spread and standard deviation, per-dimension contestedness, a claim-by-claim agreement
matrix, and how many positions each panelist actually changed. The chair receives those
numbers as input.

The panel report leads with the disagreements, because that is the useful part — a split
panel marks exactly where the evidence is thin enough that competent analysts diverge.
It also includes a **minority report** stating each dissent at its strongest, and a
reliability section naming blind spots the whole panel may share. Models trained on
overlapping data reading the same sources agree for correlated reasons; the report says
so rather than presenting consensus as proof.

If a panelist fails, the run continues and the failure is reported. If only one survives,
the report says "single panelist — no cross-check was possible" rather than pretending to
be corroborated.

More in **[docs/PANEL.md](docs/PANEL.md)**.

---

## Four ways to use it

**1. The app window** — for people who never want a terminal.

```bash
deckscope app
```

**2. The command line** — see `deckscope --help`, or **[docs/CLI.md](docs/CLI.md)**.

**3. The Python API:**

```python
from deckscope import analyze

result = analyze("deck.pdf", lens="investor", formats=["html", "pdf"],
                 provider="anthropic", research="tavily", security="strict")

print(result.primary["headline"])
print(result.security["overall_risk"])
for s in result.sources:
    print(s.sid, s.status, s.url)
```

```python
from deckscope.ensemble import analyze_with_panel

panel = analyze_with_panel("deck.pdf",
                           ["anthropic:claude-sonnet-5", "openai:gpt-4o"],
                           rounds=1, formats=["html"])
print(panel.consensus["investor"]["consensus_verdict"])
print(panel.metrics["investor"]["contested_claims"])
```

**4. As an MCP server** — so Claude Desktop, Claude Code, Cursor or Zed can drive it:

```json
{"mcpServers": {"deckscope": {"command": "python", "args": ["-m", "deckscope.mcp_server"]}}}
```

Exposes `analyze_deck`, `analyze_deck_panel`, `scan_deck_security`, `list_capabilities`
and `get_settings`. There is also a portable **skill** in [`skill/`](skill/) that teaches
any skill-aware assistant the same method, with or without the package installed.

---

## Configuration

`deckscope setup` writes `~/.deckscope/config.yaml` (or `%APPDATA%\DeckScope` on
Windows). Keys go in a sibling `.env` with owner-only permissions — never in the config
file, so the config is safe to share or commit.

```yaml
provider:
  name: anthropic
  model: claude-sonnet-5
  api_key_env: ANTHROPIC_API_KEY

research:
  name: tavily
  max_queries: 8
  recency_days: 540

lenses: [investor]

output:
  formats: [html, pdf]
  out_dir: ~/Documents/DeckScope Reports
  theme: slate            # slate | midnight | paper

security:
  mode: balanced          # strict | balanced | permissive | off
  min_font_pt: 4.0

panel:
  members: [anthropic:claude-sonnet-5, openai:gpt-4o]
  rounds: 1
```

Every field is documented in **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**.

```bash
deckscope config     # show current settings
deckscope doctor     # test every connection and report what's broken
```

---

## Extending it

Every layer is a registry. Adding to one is a single call.

```python
from deckscope import register_provider, register_researcher, register_renderer
from deckscope.providers.base import LLMProvider, Completion

class MyProvider(LLMProvider):
    name = "my_backend"
    def complete(self, system, messages, **kw):
        return Completion(text=my_client.chat(system, messages))

register_provider(MyProvider)
```

The same pattern works for research backends and output formats. See
**[docs/EXTENDING.md](docs/EXTENDING.md)**.

---

## Documentation

| Document | What's in it |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | Every install path, including offline and corporate networks |
| [docs/QUICKSTART.md](docs/QUICKSTART.md) | First fifteen minutes, no jargon |
| [docs/CLI.md](docs/CLI.md) | Every command and flag |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every config field |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the pieces fit, and why |
| [docs/PROVIDERS.md](docs/PROVIDERS.md) | Each AI backend, setup and trade-offs |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Search backends and how queries are built |
| [docs/LENSES.md](docs/LENSES.md) | What each lens changes |
| [docs/OUTPUTS.md](docs/OUTPUTS.md) | Every format, with samples |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, detections, limits |
| [docs/PANEL.md](docs/PANEL.md) | The multi-model panel in depth |
| [docs/CITATIONS.md](docs/CITATIONS.md) | How sources are tracked and resolved |
| [docs/PROMPTS.md](docs/PROMPTS.md) | Every prompt, and the reasoning behind it |
| [docs/EXTENDING.md](docs/EXTENDING.md) | Adding backends, formats, agents |
| [docs/API.md](docs/API.md) | Python API reference |
| [docs/MCP.md](docs/MCP.md) | Using DeckScope from an AI assistant |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Errors, causes, fixes |
| [docs/FAQ.md](docs/FAQ.md) | Cost, privacy, accuracy, scope |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

---

## Limitations

Worth reading before you trust anything it produces.

- **It is an AI analysis, not a fact.** Every figure should be checked against its cited
  source before anyone relies on it. The reports say so on every page.
- **It cannot see images.** Numbers that exist only inside a chart image are invisible to
  it. It tells you when a deck is mostly graphics.
- **Scanned PDFs need OCR first.** It detects and reports this rather than returning an
  empty analysis.
- **Market sizing is genuinely hard.** Where credible estimates diverge, DeckScope reports
  the range and the reason rather than inventing a midpoint. Sometimes the honest answer
  is "confidence: low".
- **The security screen is heuristic.** It catches the known families of injection well.
  A novel technique may pass. Treat it as defence in depth, not a guarantee.
- **Panel agreement is not proof.** Models with overlapping training data reading the same
  sources will share blind spots.
- **Not investment advice.** It is a research tool that helps you ask better questions.

---

## License

MIT — see [LICENSE](LICENSE).
