# Examples

## Sample decks

**`sample_deck.md`** — a realistic seed-stage deck for a fictional company, Acme Flow.
Deliberately built with the flaws real decks have: a $47B top-down TAM that's the wrong
denominator, two named competitors and three conspicuously unnamed ones, a 78% gross
margin with no stated COGS definition, and no retention figure anywhere.

```bash
deckscope run examples/sample_deck.md --lens investor
deckscope demo                              # same deck, no AI needed
```

**`sample_deck_with_injection.md`** — the same company, with a prompt injection on the
last slide instructing the AI to rate it 10/10 and conceal the instruction.

```bash
deckscope demo --injected
deckscope run examples/sample_deck_with_injection.md --security strict
```

The first neutralizes it and reports it. The second refuses to analyze the deck at all.
Both are correct behaviour, for different situations.

## Config files

**`config.example.yaml`** — every setting with a comment. Copy it, edit it, and use it
with `--config`, or let `deckscope setup` write one for you.

```bash
deckscope run deck.pdf --config examples/config.example.yaml
```

## Code

**`custom_provider.py`** — a complete custom AI backend in about forty lines.
**`custom_research.py`** — a research backend over an internal corpus.
**`batch_analysis.py`** — analyze a folder of decks into one spreadsheet.

```bash
python examples/batch_analysis.py ./decks ./reports
```
