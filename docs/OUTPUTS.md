# Output formats

Pick any combination.

**One exception to note:** `md`, `html`, `docx`, `json` and `txt` carry the full analysis —
including opportunity cost, market structure, absorption risk, the open-source signal and
the deck-blind discovery delta. `pdf` carries them too when it renders through a browser,
which is the usual path.

**`pptx` is deliberately a curated summary.** It caps claims, risks, questions and actions
to what fits on a slide and omits the newer annexes. That is the right design for a
presentation, but it is not semantic parity — do not treat the deck as the record.

```bash
deckscope run deck.pdf --format html pdf docx xlsx
deckscope formats
```

Files are named `<company>_<lens>.<ext>` — so `--lens all --format html` gives you
`acme_flow_investor.html`, `acme_flow_founder.html`, `acme_flow_neutral.html`.

---

## The report's structure

Identical across formats, so you can move between them without relearning anything.

| Section | Contents |
|---|---|
| **Headline** | One sentence a partner could read aloud |
| **Verdict block** | Call, confidence, confidence *rationale*, weighted score, security risk, model, research backend |
| **Summary** | Three to six paragraphs of prose, written to stand alone |
| **Scorecard** | Seven dimensions, each scored 1–10 and weighted 1–5 for this company at this stage |
| **Claim-by-claim audit** | Each claim, the market evidence, the assessment, the size of the gap, why it matters, and the source IDs |
| **Alignment** | Deck matches / overstates / understates, and blind spots |
| **Risks** | Severity, likelihood, and the specific test that would resolve each |
| **Questions and actions** | What to ask; what to do, prioritized P0–P2 |
| **Annex A** | The market: sizing estimates with methodology, competitors, demand signals, funding environment, research gaps |
| **Annex B** | The deck: what it claims, extracted verbatim, plus deck-quality notes |
| **References** | Every source — cited, consulted-but-uncited, and dropped |
| **Input integrity screen** | What the security screen found, present even when clean |

The scorecard weights are the thing people miss. A pre-seed deck is not penalized for thin
revenue; it is penalized for thin evidence of demand. The agent sets both the score and
its weight for *this* company at *this* stage.

---

## `md` — Markdown

The canonical text. Everything else is derived from or parallel to it.

Good for: pasting into Notion, Slack or a doc; diffing two analyses of the same company
over time; feeding into another tool.

Tables render everywhere. Long source lists and search queries sit in `<details>` blocks
so they collapse on GitHub.

## `html` — self-contained web page

One file, no external assets, no CDN. Adapts to the reader's light or dark preference.
Prints cleanly to PDF from any browser, with page breaks that don't split a claim in half.
Source IDs are internal links — click `[S3]` in a claim and land on the entry.

Good for: emailing, sharing, reading. Usually the best default.

## `pdf` — print-ready

Tries hardest first: WeasyPrint if installed, then headless Chrome or Edge — both of which
render the HTML report, so typography is identical. Falls back to a native ReportLab
layout that needs nothing but `reportlab`, with running footers and page numbers.

Good for: attaching to an IC memo; anything that needs to look the same everywhere.

## `docx` — Word

Real Word styles, so your organization's template applies cleanly. Headings, tables and a
proper numbered reference list. The References section is on its own page.

Good for: circulating to people who will comment or edit.

## `pptx` — slides

A presentation, not a dump. Title, headline, scorecard with drawn bars, one slide per
major claim, divergence, risks, next steps, references (paginated, with cited/consulted/
dropped markers), the security screen, and a method-and-caveats slide.

Good for: presenting the analysis back to a partnership or a founding team.

## `xlsx` — spreadsheet

Seven sheets, each frozen and auto-filtered:

| Sheet | Contents |
|---|---|
| Overview | Company, run stats, verdict per lens |
| Scorecard | Dimension, score, weight, rationale, sources |
| Claim audit | Every claim with assessment, evidence quality, gap, and source IDs |
| Risks | Severity, likelihood, mitigation |
| Competitors | Incumbents and challengers with threat level and sources |
| Market sizing | Every estimate with methodology and source |
| References | The full bibliography with status and what each supports |
| Security | Every finding with severity, location and action |

Good for: comparing many decks; building a pipeline tracker; anyone who thinks in rows.

## `json` — everything

The complete run: deck extraction, market analysis, every lens's comparison, the config,
run stats, the security report, and the full source registry.

Always written unless `include_raw_json: false`.

Good for: pipelines, dashboards, storing analyses in a database.

```python
import json
d = json.load(open("acme_flow_full.json"))
d["comparisons"]["investor"]["verdict"]["call"]
d["references"]["sources"]
d["security"]["overall_risk"]
```

## `txt` — plain text

Markdown flattened: tables become aligned rows, links become `text (url)`.

Good for: email bodies, terminals, systems that reject formatting.

---

## Panel output

A panel run writes a **panel report** per lens plus **each panelist's own final report**.

```
acme_flow_panel_investor.html      the consensus, disagreements and metrics
acme_flow_panel_investor.md
acme_flow_panel.xlsx               panel, claim agreement, score spread, cross-review
acme_flow_panel_full.json          everything, including each review
acme_flow_anthropic_claude_sonnet_5_investor.html
acme_flow_openai_gpt_4o_investor.html
```

The panel `.xlsx` adds sheets the single-run one doesn't have: per-panelist movement,
the claim × panelist agreement matrix, per-dimension score spread, and every concession
and held position from the cross-review round. See [PANEL.md](PANEL.md).

---

## Themes

```bash
deckscope run deck.pdf --theme midnight
```

`slate` (default, professional), `midnight` (dark), `paper` (warm, print-oriented).
Applies to HTML, PDF, DOCX and PPTX.

---

## Adding a format

```python
from deckscope import register_renderer

def render_email(result, out_dir, base, **kw):
    comp = result.primary
    body = f"{comp['headline']}\n\n{comp['summary']}"
    p = out_dir / f"{base}_email.txt"
    p.write_text(body, encoding="utf-8")
    return [str(p)]

register_renderer("email", render_email, "A short email body")
```

Then `--format email` works everywhere. See [EXTENDING.md](EXTENDING.md).
