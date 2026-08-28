# Trying DeckScope on your pitch deck

Written for someone sitting down with a deck and thirty minutes. Every command
on this page was executed, in order, on 2026-08-28, before being written down
here — a command this project recommends is a claim like any other it makes.

## 1. See it work before setting anything up

No account, no key, no network. The analysis below is a built-in sample, but
the machinery running it is the real thing:

```bash
deckscope demo
```

Two more minutes well spent:

```bash
deckscope demo --panel        # three simulated analysts who disagree
deckscope demo --injected     # a deck with a hidden instruction, caught
```

## 2. Connect an AI and a search backend

```bash
deckscope setup
```

Seven questions, each answer tested as you go, all changeable later by running
it again. You need two things: an AI service you already use, and a web-search
key (the wizard shows where the free ones are). DeckScope has not compared the
AI providers on quality and makes no recommendation — pick the one you pay for.

## 3. Run your deck

```bash
deckscope run yourdeck.pdf
deckscope run yourdeck.pdf --format html md      # choose output formats
deckscope run yourdeck.pdf --with-market-reports # also build the market
                                                 # reports the deck's claims
                                                 # depend on (costs more)
```

PDF, PPTX, DOCX, and Markdown decks all work. Prefer the window to a terminal?

```bash
deckscope app
```

opens a drag-and-drop page in your browser, running entirely on your machine.

## 4. How to read what you get

The report answers four questions, in this order: what the deck claims that
the evidence does not support, what the deck leaves out, what could not be
established either way, and what to go find out next. The headline is
assembled by code from those counts — a model does not get to write it.

Three marks matter more than anything else on the page:

- **A source ID after a figure** (like `S3`) means you can open the
  bibliography, click the URL, and check it yourself. Do that for anything you
  intend to rely on.
- **"_no source_"** after a statement means the analysis asserted it without
  evidence. It is printed on the page precisely so you discount it.
- **"Could not be checked"** is a research task, not a red flag. The report
  will not convert its own gaps into a verdict against the company.

## 5. What this is not

It is not an AI that tells you whether to invest, and nothing in it is
investment advice. It has real, documented limits — the README's Status
section lists them without varnish, including the parts of the system that
have not yet been proven better than a simpler tool. If a figure matters to a
decision, open the source it cites. That is what the citation is for.

## If something goes wrong

```bash
deckscope doctor      # checks every connection and says which one is broken
deckscope models      # which AI backends actually respond right now
```

An error message in DeckScope is supposed to name the actual problem and the
fix. If one sends you somewhere unhelpful, that is a bug in the message —
please report the exact text.
