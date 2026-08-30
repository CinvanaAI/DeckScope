# FAQ

## Cost and access

**What does it cost to run?**
DeckScope is free and MIT-licensed. You pay whatever your AI provider charges. A single
analysis is typically a few cents on a mid-tier model. A three-model panel is
substantially more than three times that: the current fixture measures roughly
11× the single-run input tokens, because every review round carries the other
panelists' full analyses inside each prompt. Treat the panel as an expensive
advanced mode, and check the cost receipt the terminal prints after every run. Search backends have free tiers that cover
hundreds of decks.

**Can I use it with no API key at all?**
Yes, three ways. `--provider cli` uses an agent CLI you already have signed in (Claude
Code, Ollama). `--provider openai_compatible` uses a local model. `--provider manual`
writes each prompt to your clipboard so you can paste it into any chat AI and paste the
answer back. And `deckscope demo` runs the whole pipeline offline with built-in answers.

**Do I need to know how to code?**
No. Double-click the installer, answer six questions, drag a deck onto a window.

---

## Privacy

**Where does my deck go?**
To the AI provider you configured, and nowhere else. DeckScope has no servers. The app
window binds to `127.0.0.1` and is unreachable from your network. Reports are written to
your own disk.

**Can I keep everything on my machine?**
Yes:

```yaml
provider: {name: openai_compatible, base_url: http://localhost:11434/v1, model: llama3.1:8b}
research: {name: none}
```

Nothing leaves your computer. The report will state that no external sources were
consulted.

**Where are my API keys stored?**
In `~/.deckscope/.env` (or `%APPDATA%\DeckScope\.env`), mode 0600, never in the settings
file — so `config.yaml` is safe to share or commit.

**Does search send my deck anywhere?**
No. Only short search queries derived from the deck's category and claims. Those queries
are printed in the report so you can see exactly what was sent.

---

## Accuracy

**How accurate is it?**
It is an AI analysis. Treat it as a well-prepared first pass by a diligent junior analyst:
useful for surfacing questions and finding things you'd have missed, not a substitute for
your own judgment. A figure is either traceable to a cited source or shown as unsourced —
the report never presents one as the other, and the citation audit removes any reference
that does not resolve. Check the ones your decision turns on.

One boundary worth knowing: with a provider's *native* search, the provider's own model
reads the page and DeckScope receives its summary. DeckScope screens what it receives, but
cannot claim to have screened the original page before any model saw it. Local search
backends are screened before anything reaches a model.

**Does it hallucinate numbers?**
It can. The mitigations are structural: the market agent may only use the research
material it was given, it must cite by ID from a supplied bibliography (so invented URLs
are much harder), and an uncited claim is displayed as *"none cited — this assessment
rests on no source"* rather than passing as supported.

**Why does market sizing come out as a range?**
Because that's usually the truth. The agent is instructed to report the range and explain
the divergence rather than averaging credible estimates into a single number that no
source supports.

**Two runs gave different answers.**
Expected. Lower `temperature` for consistency, or run a panel — where two independent
models disagree is precisely where the evidence is thin.

---

## Scope

**What file types can it read?**
`.pdf` `.pptx` `.docx` `.md` `.txt` `.html` `.json`, and URLs. Not `.ppt` (save as
`.pptx`), and not Google Slides directly (export to PDF or PPTX).

**Can it read the charts in my deck?**
Only their category labels in PPTX. Numbers that exist solely inside a chart *image* are
invisible to it, and it tells you when a deck is mostly graphics.

**Does it work on scanned PDFs?**
Not without OCR first. It detects and reports the problem rather than returning an empty
analysis.

**Can it analyze several decks at once?**
Not built in. Loop over them:

```bash
for f in decks/*.pdf; do deckscope run "$f" --out ./reports --quiet; done
```

The `xlsx` output is designed for exactly this — the sheets stack cleanly into a pipeline
tracker.

**Can it compare two companies?**
Not directly. Run each, then compare the JSON, or use the spreadsheet output.

---

## Security

**What is the security layer actually for?**
Both of DeckScope's inputs are written by other people, and both can carry text meant to
steer an AI rather than inform you — white text on a white slide, hidden speaker notes,
a web page seeded with fake instructions. DeckScope screens both before analyzing.
[Full details](SECURITY.md).

**Is this a real threat or theoretical?**
Prompt injection through documents is well documented and cheap to attempt. Whether any
particular founder has tried it, you can't know without checking — which is the point.
Run `deckscope demo --injected` to see it caught.

**What if a deck legitimately discusses AI instructions?**
It may trip the detector. The report shows the excerpt so you can judge, and
`--security permissive` reports without changing anything.

**Can I turn it off?**
`--security off`. Not recommended, and the report will say the screen wasn't run.

---

## The panel

**Why not just average several models?**
Averaging destroys the only genuinely new information a panel produces — where competent
analysts disagree — and rewards hedging. DeckScope has them argue instead, and the
revision prompt explicitly forbids drifting toward the group.

**Does agreement between models mean it's right?**
No, and the report says so. Models with overlapping training data reading the same sources
agree for correlated reasons. Agreement raises confidence; it does not establish fact.
The consensus report includes a section naming blind spots the whole panel may share.

**How many models should be on a panel?**
Two is useful; three is the sweet spot. Diversity of *provider* matters more than number —
`anthropic openai gemini` beats three Claude variants.

**What if one fails mid-run?**
The run continues and the failure is reported. If only one survives, the report says
"single panelist — no cross-check was possible" rather than presenting it as corroborated.

---

## Using it in a team

**Can we share a configuration?**
Yes — keys are never in `config.yaml`, so it's safe to commit. Point at it with
`--config ./team-config.yaml`.

**Can it run in CI?**
Yes. Set the key as a secret environment variable and use `--config` with a checked-in
file. `--quiet` and the JSON output are made for this.

**Can our AI assistant drive it?**
Yes — register the MCP server and Claude Desktop, Claude Code, Cursor or Zed can call it.
See [MCP.md](MCP.md). There is also a portable skill in `skill/`.

**Can we point it at our own research corpus?**
Yes — write a research backend, about twenty lines, and your internal notes get cited
alongside public sources with the same reliability labelling. See
[EXTENDING.md](EXTENDING.md).

---

## Project

**Why is it called DeckScope?**
It puts a deck under a microscope, and it scopes the market around it.

**Is this investment advice?**
No. It is a research tool that helps you ask better questions. Every report says so.

**Can I use it commercially?**
Yes — MIT licensed. Your AI provider's terms still apply to your usage of their models.

**How do I contribute?**
See [CONTRIBUTING.md](../CONTRIBUTING.md). New detections for the security layer and new
provider backends are especially welcome.
