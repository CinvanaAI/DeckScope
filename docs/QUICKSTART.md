# Quick start

Fifteen minutes, no jargon. If you've already installed DeckScope, start at step 2.

---

## 1. Install

Download the repository, unzip it, and double-click `install.bat` (Windows),
`install.command` (Mac) or `install.sh` (Linux). It handles the rest.

Stuck? [docs/INSTALL.md](INSTALL.md) covers every case.

---

## 2. See what it does — before setting anything up

```bash
deckscope demo
```

No AI account, no API key, no cost. It analyzes a built-in sample deck with built-in
answers and writes real report files, so you can see the shape of the output before
deciding whether to configure anything.

Two more worth running:

```bash
deckscope demo --panel      # three simulated analysts who disagree with each other
deckscope demo --injected   # a deck with hidden instructions, caught and reported
```

The second one is worth thirty seconds of your time. It shows what DeckScope does when a
deck contains white-on-white text telling the AI to score it 10/10.

---

## 3. Set it up

```bash
deckscope setup
```

Six questions:

1. **Which AI should do the analysis?** If unsure, pick Claude. If you'd rather not
   create an account, pick the copy-paste option or an AI app already on your computer.
2. **Which model?** The middle option is right for almost everyone.
3. **How should it research the market?** Tavily's free tier takes about a minute to set
   up and is what makes the market half of the report worth reading.
4. **Whose point of view?** Investor, founder, or neutral analyst. You can change this
   per run.
5. **Which files should it produce?** Type numbers separated by commas.
6. **How strict should security be?** Balanced is the right default.

Then it tests everything and tells you what, if anything, is broken.

**About API keys.** These are the passwords that let DeckScope use an AI service. You
create one on the provider's website, paste it once, and DeckScope stores it in a file
only you can read. It never goes into the settings file, so you can share that safely.
Costs are usually a few cents per deck.

---

## 4. Analyze a real deck

The easy way:

```bash
deckscope app
```

A window opens in your browser. Drag your deck onto it, choose what you want, press
**Analyze this deck**. Everything runs on your own computer.

The command line way:

```bash
deckscope run "path/to/deck.pdf"
```

It prints its progress as it goes — reading the deck, running searches, comparing — and
finishes with the verdict and a list of the files it wrote.

---

## 5. Read the report

Open the HTML or PDF file it produced. Sections, in order:

| Section | What it tells you |
|---|---|
| **Headline** | One sentence a partner could read aloud in a meeting. |
| **Verdict and confidence** | The call, and how sure the analysis is — with the reason for that confidence. |
| **Summary** | Several paragraphs of prose. If you read nothing else, read this. |
| **Scorecard** | Seven dimensions, scored and weighted for this company at this stage. |
| **Claim-by-claim audit** | Each deck claim beside the market evidence, with the size of the gap. **This is the core of the report.** |
| **Alignment** | Where the deck matches, overstates, understates — and its blind spots. |
| **Risks** | Severity, likelihood, and the specific test that would resolve each one. |
| **Questions and actions** | What to ask, what to do. |
| **Annex A** | What the market evidence shows, independently of the deck. |
| **Annex B** | What the deck claims, extracted verbatim. |
| **References** | Every source retrieved — cited, uncited, and dropped. |
| **Input integrity screen** | What the security screen found. Present even when clean. |

Read the **blind spots** first. What the market shows and the deck never mentions is
usually more informative than anything the deck got wrong.

---

## 6. Useful next steps

**Get all three points of view at once:**

```bash
deckscope run deck.pdf --lens all
```

**Get a Word document and a PDF instead:**

```bash
deckscope run deck.pdf --format docx pdf
```

**Run a panel of AIs that argue with each other:**

```bash
deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-4o
```

Where two independent models disagree is where your own diligence should start.

**Check everything still works:**

```bash
deckscope doctor
```

---

## If something goes wrong

```bash
deckscope doctor
```

It tests your AI connection, your search backend, your output formats and your reports
folder, and names the specific fix for anything broken.
[docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) covers the rest.
