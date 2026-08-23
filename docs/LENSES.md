# The three lenses

A lens is not a tone setting. It changes what the agent weights, what it treats as a
problem, and what it is allowed to recommend.

```bash
deckscope run deck.pdf --lens investor
deckscope run deck.pdf --lens founder neutral
deckscope run deck.pdf --lens all
```

Each lens produces its own report file. The deck extraction and market research are shared
across lenses, so `--lens all` costs far less than three separate runs.

---

## Investor — diligence

**Written for:** an investment committee deciding whether to take a first meeting or write
a check.

**The question:** is this worth funding at the stage and terms implied by the ask?

**Stance.** A partner who has seen several thousand decks: constructive but unsentimental.
Cares whether the market is big enough and growing fast enough to return the fund, whether
this team can win a defensible position in it, and whether the traction is real for the
stage. Distrusts top-down TAM arithmetic, vendor-marketing market reports, and any metric
presented without a denominator. Names the specific thing that would have to be true.

**Weights most heavily:** market timing, defensibility, traction-for-stage.

**Verdict scale:** `STRONG YES` · `YES WITH CONDITIONS` · `LEAN NO` · `PASS` — with the
single biggest reason, and the single condition that would flip the answer.

---

## Founder — self-critique

**Written for:** the founding team preparing to raise, who need to know what breaks in the
room.

**The question:** where will this deck lose the room, and what should we fix before the
next pitch?

**Stance.** An experienced operator-coach: direct and warm. Tells you exactly what an
investor will attack, without hedging and without discouraging you. Every criticism comes
with a concrete fix — a specific number to find, a slide to add, a claim to soften, a
competitor to address head-on.

The distinction this lens is built around, and the reason it exists separately:

> *"The market says you are wrong"* and *"the market agrees but your deck fails to prove
> it"* need opposite responses. One means change the business. The other means change the
> slide.

**Weights most heavily:** fixability. Findings are ranked by return on effort.

**Verdict scale:** `RAISE-READY` · `NEEDS TIGHTENING` · `NEEDS REPOSITIONING` ·
`NEEDS A DIFFERENT STORY` — with the one change that has the highest return.

---

## Neutral — analyst

**Written for:** a reader who wants the facts lined up and will draw their own conclusion.

**The question:** where do the deck's claims and the market evidence agree, and where do
they diverge?

**Stance.** A research analyst. Makes **no recommendation** and does not editorialize.
Lines up each material claim beside the best available evidence and characterizes the gap
precisely and quantitatively where possible. Explicit about the reliability of each source
and about what could not be verified. Where evidence is genuinely mixed, presents both
readings rather than picking one.

**Weights most heavily:** evidence quality and traceability. Every assessment cites its
basis.

**Verdict scale:** characterizes alignment only —
`CLAIMS LARGELY ALIGN WITH MARKET EVIDENCE` · `MIXED ALIGNMENT` · `MATERIAL DIVERGENCE` ·
`INSUFFICIENT EVIDENCE`. The prompt forbids recommending any action.

---

## The same deck, three ways

A deck claiming a $47B TAM where independent estimates put the serviceable slice at $3–5B:

| Lens | How it reports the same finding |
|---|---|
| Investor | "Roughly an order of magnitude overstatement of the addressable denominator. The $400M SOM survives the correction; the framing does not. Weighs against the team's diligence habits more than against the opportunity." |
| Founder | "An investor will check this in the first ten minutes and you will lose credibility for a number you didn't need. Your own SOM is unaffected — reframe slide 5 around the $3–5B serviceable slice and the story gets *stronger*, not weaker." |
| Neutral | "Deck claims $47B (2030, vendor-sponsored roll-up spanning iPaaS, RPA and agent platforms, [S3]). Independent 2026 estimates for the category: $18–24B [S1][S2]; for the mid-market slice: $3–5B [S1]. Divergence is a function of category boundary, not of arithmetic." |

Same evidence. Same numbers. Three different useful outputs.

---

## Choosing

- Evaluating someone else's company → **investor**
- Preparing your own raise → **founder**
- Building a file others will read, or you don't want the AI's opinion → **neutral**
- Not sure, or the stakes are high → **all three**. Reading the investor and founder
  versions side by side is unusually clarifying: one tells you what's wrong, the other
  tells you whether it's fixable.

---

## Lenses and the panel

The panel runs each lens separately, with its own consensus report and its own agreement
metrics. Panelists review each other within a lens, never across.

```bash
deckscope panel deck.pdf --panel anthropic openai --lens investor founder
```

---

## Adding a lens

Lenses live in `deckscope/prompts/lenses.py` as a `Lens` enum member and a profile with
five fields: `label`, `reader`, `question`, `stance`, `verdict_rule`, `emphasis`. Add both
and it becomes available everywhere — CLI, API, app window, MCP. See
[EXTENDING.md](EXTENDING.md).
