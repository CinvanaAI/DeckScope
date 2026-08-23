# DeckScope

**The adversarial second opinion for a pitch deck. It separates persuasion from
evidence, finds what the deck leaves out, and gives you the questions worth asking
next.**

Not an AI that tells you whether to invest. Every report answers four questions, in
this order:

1. **What did the deck claim that the evidence does not support?**
2. **What did the deck leave out?**
3. **What could not be established either way?**
4. **What should you go and find out next?**

The headline is assembled in Python from those counts, not written by a model, so it
cannot claim more than the evidence holds. A run that retrieved no sources says so in
its first line rather than listing confident findings. See
[deckscope/findings.py](deckscope/findings.py).

> ### Status: unreleased, and honest about it
>
> DeckScope has an architecture that works end to end and a test suite that runs
> offline. It has **not** been shown to produce better analysis than a simpler tool,
> and several of its guarantees are newer than its ideas.
>
> **Reasonable to use it for:** exploring a deck you already have context on,
> generating questions to ask, structuring your own diligence, screening a deck for
> hidden instructions.
>
> **Not yet reasonable:** unattended analysis, decks from strangers treated as
> trusted input, or any figure relied on without opening the source it cites.
>
> An external audit in August 2026 found a remote-code-execution path in the local
> web server, several places where the security layer detected more than it enforced,
> a panel citation-collision bug, and a broken Windows console path. Those are fixed
> and covered by tests. What has **not** been done is the evaluation that would show
> the three-agent design beats a single good prompt. Until that exists, treat the
> architecture as a well-tested hypothesis. See [Limitations](#limitations).

Most deck-analysis tools ask one model to read a deck and give an opinion. That opinion
inherits the deck's own framing: if the deck says the market is $47B, the model reasons
about a $47B market. DeckScope is built to avoid that. It runs three agents in sequence,
deliberately isolated from each other, and it can run the whole thing across several AI
services that then argue with each other.

```
  ┌────────────────┐     ┌──────────────────┐     ┌────────────────────┐
  │ 1. Deck Analyst│ ──▶ │ 2. Market Analyst│ ──▶ │ 3. Comparison      │
  │ extract claims │     │ research the     │     │ claim-by-claim     │
  │ never judge    │     │ on its own terms │     │ deck vs. evidence  │
  └────────────────┘     └──────────────────┘     └────────────────────┘
        │                        │                          │
        └──── screened for prompt injection before either runs ────┘
```

The deck agent extracts and never evaluates. The market agent researches the category and
is instructed to describe it on its own terms. Only the third agent sees both artifacts,
and only it is allowed to draw conclusions.

**Being precise about what that isolation buys**, because it is easy to overstate: the
market agent *is* given the deck's claims and a deck-derived research agenda — it has to
be, or it would not know what to research. So it is **claim-directed falsification**, not
deck-blind discovery. That reduces anchoring in the *conclusions* and leaves it in the
*search*: a category the deck never mentions is one the market agent is unlikely to
look for.

Which is why `--cold-discovery` exists. It adds a second pass that receives only the
category and a company name — never a claim, enforced by a whitelist and a test that
asserts on the payload rather than the prompt.

**It is claim-blind, not deck-blind, and the distinction matters.** The category it
researches is itself read out of the deck. If a deck frames itself as "workflow
automation" when a fairer framing is "RPA", the cold pass inherits the wrong framing and
researches the wrong market — thoroughly and without ever citing the deck. Isolation
removes the deck's *arguments* from this pass; it does not remove the deck's *framing*,
and no amount of prompt hygiene can, because the pass has to be pointed somewhere. Read
its output as "what an analyst who was told only the category would find", which is a
real and useful counterweight, rather than as an independent check on whether the
category is the right one. Naming it deck-blind overstated it; the flag keeps its name
for compatibility, but this is what it does.

The pass reports what researching the market
from scratch found that the claim-directed pass never looked for. On the sample deck the
two routes overlap on 29% of the competitors they name.
[How it works.](docs/EVIDENCE.md)

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
recover what rendering hid, screens every retrieved snippet, drops sources that behave
like an attack, neutralizes the exact spans it detected, and reports all of it.

It screens **the text it is given**, which for most search backends is a snippet rather
than the whole page — DeckScope does not fetch and scan every source document. An
injection placed below the fold of a page whose snippet looks clean would not be seen.
[Details and limits.](#the-security-layer)

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
cd DeckScope
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

Pick any combination. All formats carry the analysis, the bibliography and the security
screen — except `pptx`, which is deliberately a curated summary and caps the claim, risk
and action lists to what fits on slides.

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
deckscope run deck.pdf --provider gemini --model gemini-flash-latest
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

**In every retrieved snippet**, the same text screening, plus URL checks: punycode
domains, embedded credentials, `data:` and `javascript:` schemes, shorteners, unusual
TLDs. A source that trips any of these is dropped rather than cleaned, and the drop is
recorded in the bibliography with its reason.

What this does *not* cover: the full page behind a search result. Tavily and Exa return
substantial page content, so those are screened in depth; Serper and Brave return short
snippets, and DeckScope screens what it receives rather than fetching the page itself.

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

## Compared to what?

The question an investor actually faces is not "is this deck any good" but "against
what alternative". When a named competitor is publicly traded, that alternative is
concrete — you could simply buy it.

```bash
deckscope run deck.pdf --opportunity
deckscope demo --opportunity          # see it, free
```

DeckScope checks which named competitors are listed, pulls their actual historical
returns, and then **inverts the question**. Instead of predicting a return it computes
the outcome that would be *required*:

> To match holding Microsoft (MSFT) over 5 years, this company would need to reach
> roughly $27M in revenue — about 80x its current $340k — after typical dilution.

Alongside it: sourced base rates for how companies at this stage in this category have
historically done, so the requirement has a denominator.

**It does not forecast returns, deliberately.** No model knows what a seed-stage company
will be worth in five years, and "estimated return 3.2x, confidence medium" is a guess
wearing the clothes of an analysis — it would be the least supportable number in a
project that spends most of its effort refusing to state things it cannot cite. Every
figure here is either arithmetic you can check by hand or an input that arrived with a
citation, and the assumptions are printed with the result:

| Assumption | Default | Flag |
|---|---|---|
| Future dilution before exit | 50% | `--dilution 0.6` |
| Exit revenue multiple | 6x | `--exit-multiple 8` |
| Horizon | 5 years | `--horizon 7` |

Change any of them and every number changes. That is the point — it is a model you drive,
not an answer you receive. *Not investment advice.*

## Is this a product, or a feature?

Categories get built out by startups, proven useful, and then bundled into a platform that
already owns the customer. Antivirus, file sync, VPN, screen sharing, password management —
the companies in those markets were not out-competed so much as made redundant.

So the market analysis reports **absorption risk** explicitly: who could bundle this away,
by what mechanism, what signals are *already visible* (shipped features, acquisitions, job
postings), and which precedents genuinely match. Plus **saturation** with numbers behind
it — how many funded competitors, whether new ones are still arriving, whether pricing is
compressing, whether anyone is being acquired — because "concentrated" alone cannot
distinguish a wide-open wedge from a played-out category.

And **adjacent markets**: what this category is converging with, what substitutes it, and
where it could expand.

### Open source is the leading indicator

Where a category has an open-source dimension, it predicts absorption better than market
size, growth or funding do — and the mechanism is specific:

> While an open-source alternative is meaningfully behind, commercial products compete on
> capability and customers pay for something they cannot get free. Once open source reaches
> rough parity, capability stops being the differentiator, and what remains is packaging,
> operations, support and distribution — **which is precisely what a platform vendor
> already owns.** It only has to be good enough and free, and the mid-market has nowhere
> to stand.

But parity alone does not decide it, and treating it as though it does gets the answer
wrong in both directions. Kubernetes reached parity and Docker Inc. could not monetize,
because the residual differentiation was distribution. Credible open-source warehouses
existed throughout Snowflake's rise, because the residual differentiation was operational
burden at scale — expensive to give away even if you are Amazon.

So DeckScope records **both**: how close the closest project is, and what specifically the
commercial offering still provides once it arrives — classifying each remainder by whether
a platform vendor could reproduce it cheaply. The resulting bundling risk is derived in
Python rather than asked of a model, so the same inputs always give the same reading and
the reasoning is inspectable:

| Open source is… | What's left is… | Reading |
|---|---|---|
| far behind | anything | **low** — customers are paying for capability |
| at parity | packaging, distribution | **severe** — defending the hill the giant occupies |
| at parity | operations, support | **elevated** — buys time, not safety |
| at parity | compliance, data effects, workflow depth | **moderate** — slow and expensive to reproduce |

A narrowing gap raises the reading; a widening one lowers it. Where the derived signal
disagrees with the market agent's own product-or-feature verdict, the report says so
rather than quietly picking one.

## Is any of it actually any good?

```bash
deckscope eval                            # score the shipped suite, free
deckscope eval --mode pipeline baseline   # compare the two architectures
deckscope eval --trials 3                 # measure stability
```

Every audit of this project said the same thing: plausible and unproven. That was
right, and it was not fixable by argument — "was the analysis good?" has no mechanical
answer for a real deck, because nobody knows the true TAM of a real market.

The way around it is to **author both sides**. If the deck claims $88B and the frozen
corpus says $6-8B, then "contradicted" is correct and "supported" is wrong — not as a
matter of taste, but because the evidence in front of the model says so. Ground truth
exists because it was planted.

Five cases ship: an inflated market, an omitted incumbent, evidence too thin to
conclude from, a planted injection, and **an honest deck whose claims the evidence
supports**. That last one matters most — a system that calls everything contradicted
scores well on the other four, and the control is what stops the suite rewarding pure
cynicism.

Eight dimensions are scored, all computed in Python rather than judged by a model, and
**never averaged into one number** — because a system scores perfectly on fabrication
by saying nothing, and perfectly on recall by saying everything.

Exits non-zero on any failure, so it can gate a release.
[What it does and does not establish.](docs/EVALUATION.md)

## The panel: several AIs that review each other

One model gives you one model's blind spots. A panel gives you something better — but
only if the panelists actually engage rather than being averaged together.

```bash
deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-4o gemini
deckscope panel deck.pdf --panel anthropic openai --rounds 2 --format html pdf
deckscope demo --panel                       # see it work, free
```

Five rounds:

1. **Independent.** Each panelist runs the full three-agent pipeline alone, in parallel,
   with no knowledge of the others.
2. **Cross-review.** Each reads every other panelist's deck extraction, market analysis
   and comparison — **anonymized as "Panelist B", so it judges the work and not the
   brand** — and records what it concedes, what it holds and why, and what errors it
   found.
3. **Revise.** Each rewrites its own analysis to reflect what it conceded. A panelist
   that was right and challenged badly should barely change; the prompt explicitly
   forbids averaging toward the group.
4. **Vote.** Each panelist ranks the others' finished reports — on whether the reasoning
   holds, not on whether they agree. Nobody ranks themselves. A preference cycle
   (A > B > C > A) is reported as a cycle rather than broken arbitrarily.
5. **Consensus.** A chair reports where the panel agreed, where it split, what changed,
   and how much the agreement is worth — and each panelist's own report is kept intact
   beside it, ordered by the vote, because a synthesis can smooth away the disagreement
   that is the point.

**When it stops is a choice, not a constant.** `--strategy convergence` skips review
entirely when the panel already agreed independently; `--strategy confidence_floor` keeps
going while anyone is low-confidence and says so plainly if it hits the cap anyway;
`adaptive` picks from how the panel actually behaved. Every stopping decision is logged in
the report, so the run explains its own cost.

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

```bash
deckscope run deck.pdf --mode both     # three agents vs. one prompt, same evidence
deckscope run deck.pdf --cold-discovery --opportunity
deckscope run deck.pdf --save-corpus evidence.json   # replay it later with --corpus
```

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
| [docs/OPPORTUNITY.md](docs/OPPORTUNITY.md) | Opportunity cost, absorption risk, and why there are no forecasts |
| [docs/EVIDENCE.md](docs/EVIDENCE.md) | Frozen corpora, claim-blind discovery, and comparing two modes fairly |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Scoring DeckScope against decks with planted, known-correct answers |
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
- **The security screen is heuristic.** It catches the known families of injection well,
  and there are tests for each. A novel technique may pass. Treat it as defence in
  depth, not a guarantee.
- **It screens snippets, not whole pages.** For search backends that return short
  snippets, an injection further down the page is not seen.
- **It cannot see injections inside images.** Text rendered into a picture is never
  extracted, so it is never scanned.
- **The three-agent design is measurable now, and still unproven.** `deckscope eval`
  scores it against decks whose correct answers are known, because the decks and their
  evidence were authored together. But five constructed cases is a smoke test, not a
  benchmark: a high score means "does not fail in the ways we know how to check", which
  is a floor. The planted answers are also one author's judgement, so a second
  contributor would improve the suite more than a hundred more cases from the same one.
- **The panel is not fully independent.** Panelists use separate models and separate
  research calls, but the research agenda is derived from one deck-extraction pass and
  they often retrieve overlapping sources. It is role-separated analysis with model
  diversity, not independent market discovery.
- **Citation resolution is not entailment checking.** DeckScope verifies that a cited
  source exists and was supplied. It does not verify that the source actually contains
  the figure attributed to it.
- **Panel agreement is not proof.** Models with overlapping training data reading the same
  sources will share blind spots.
- **Not investment advice.** It is a research tool that helps you ask better questions.

---

## License

MIT — see [LICENSE](LICENSE).
