## What this changes

<!-- One or two sentences. -->

## Why

<!-- The problem it solves. If it's a prompt change, show output before and after. -->

## Checklist

- [ ] Tests pass — `pytest tests/` **and** `python tests/run_tests.py`
- [ ] New behaviour has a test
- [ ] `ruff check .` is clean
- [ ] The relevant page in `docs/` is updated
- [ ] User-visible changes noted in `CHANGELOG.md` under *Unreleased*

### If you touched the security layer

- [ ] `test_clean_deck_is_clean` still passes — a detection that fires on ordinary
      business language is worse than no detection
- [ ] The finding's `detail` text is readable by a non-technical person

### If you touched prompts

- [ ] `_TRUST_RULES` is still in every system prompt
- [ ] The market agent still sees only the deck's *claims*, never its *conclusions*

### If you touched a schema

- [ ] Every renderer that reads it was checked (md, html, pdf, docx, pptx, xlsx, json)
