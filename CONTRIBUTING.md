# Contributing

Thanks for looking. This project is small enough that a good pull request lands quickly.

---

## Get set up

```bash
git clone https://github.com/CinvanaAI/DeckScope.git
cd deckscope
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all,dev]"
```

Run the tests:

```bash
pytest tests/                 # if you have pytest
python tests/run_tests.py     # zero dependencies — works anywhere
```

Everything is testable offline. The `mock` provider drives the whole pipeline — including
a panel that genuinely disagrees with itself — so **you never need an API key to develop
or test DeckScope**. Please use it rather than mocking HTTP.

---

## Especially welcome

**New injection detections.** If you find a technique the security layer misses, that's
the most valuable contribution here. Add the pattern, add a test, and add a test proving
it doesn't fire on ordinary business language.

**New provider backends.** About thirty lines — see [docs/EXTENDING.md](docs/EXTENDING.md).

**New research backends.** Internal corpora, sector-specific indexes, anything with an
API.

**Prompt improvements.** With a concrete before/after on a real deck. Prompt changes are
the highest-leverage and highest-risk edits in the project, so evidence matters.

**Documentation.** Especially anywhere the plain-language path assumes too much.

---

## House style

**Errors name the fix.** Not `"auth failed"` but
`"No Anthropic API key found. Set ANTHROPIC_API_KEY, or run deckscope setup."`

**Never silently degrade.** If a capability is missing, the output says so. A report that
looks complete but rests on nothing is worse than one that admits a gap. This applies to
missing research backends, missing forensics libraries, dropped sources, and failed
panelists.

**Standard library first.** Every third-party import is optional and wrapped in `try`.
The core has exactly one dependency.

**Comments explain *why*.** The reader can see what the code does.

```python
# Register every source BEFORE screening, so anything dropped still appears in the
# bibliography with the reason it was dropped. A source removed for hostility is
# evidence about the research environment, not something to hide.
```

**Line length 92.** `ruff check .` — config is in `pyproject.toml`.

---

## Adding a security detection

1. Add the pattern to `INTENT_PATTERNS` in `deckscope/security/text_scanner.py`, with a
   severity and a plain-language explanation a non-technical reader will understand.
2. If it's a *concealment* signal rather than an *intent* signal, add its code to
   `CONCEALMENT_CODES` — concealment escalates the severity of co-occurring intent.
3. Add a test in `tests/test_security.py`.
4. **Check `test_clean_deck_is_clean` still passes.** A detection that fires on normal
   language is worse than no detection — false positives train people to ignore the
   screen.

---

## Changing prompts

Two hard rules:

1. **`_TRUST_RULES` stays in every system prompt.** It's the backstop behind the security
   screen.
2. **The agents stay isolated.** The market agent may see the deck's *claims*; it must
   never see the deck's *conclusions*. That isolation is the main design property of this
   project.

Include in the PR: what you changed, why, and an example of the output before and after.

---

## Pull requests

- One concern per PR.
- Tests for new behaviour.
- Update the relevant page in `docs/` — an undocumented feature effectively doesn't exist.
- Note anything user-visible in `CHANGELOG.md` under *Unreleased*.
- If you touched a schema, say which renderers you checked.

---

## Reporting bugs

Include: the exact command, the full error, `deckscope doctor` output, your OS and Python
version, and — if you can share it — a redacted deck that reproduces it.

**Security bypasses:** please open a private security advisory rather than a public issue,
and include the deck or page that demonstrates it.

---

## Not in scope

A few deliberate omissions, so nobody spends a weekend on something that won't be merged:

- **Hosting or a web service.** DeckScope runs on your machine. That's the privacy model.
- **Storing API keys in the config file.** Keys stay in a separate 0600 file so configs
  can be shared.
- **Averaging panel results into a single score.** The disagreement is the product.
- **Scoring a deck without market research and presenting it confidently.** Running with
  `--research none` is fine; presenting the result as verified is not.

---

## Code of conduct

Be decent. Assume good faith. Critique the work, not the person — which is, not
coincidentally, exactly what we ask the panel agents to do.
