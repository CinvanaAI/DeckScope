# Extending DeckScope

Four layers are registries. Adding to any of them is one function call, and everything
downstream — CLI, config, app window, MCP, panel — picks it up automatically.

---

## A model backend

Implement one method.

```python
from deckscope import register_provider
from deckscope.providers.base import LLMProvider, Completion, Message, ProviderError

class MyProvider(LLMProvider):
    name = "my_backend"                 # what --provider expects
    default_model = "my-model-v1"
    supports_native_search = False      # True if you implement native_search()
    catalog = [                         # shown by `deckscope providers` and the wizard
        ("my-model-v1", "Balanced — recommended"),
        ("my-model-mini", "Fast and cheap"),
    ]

    def __init__(self, config=None):
        super().__init__(config)
        import os
        key = os.getenv(self.config.api_key_env or "MY_BACKEND_KEY")
        if not key:
            raise ProviderError("Set MY_BACKEND_KEY, or run `deckscope setup`.")
        self.client = MyClient(key, timeout=self.config.timeout)

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None):
        try:
            text = self.client.chat(
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                max_tokens=max_tokens or self.config.max_tokens,
                temperature=self.config.temperature if temperature is None else temperature)
        except Exception as exc:
            raise ProviderError(f"my_backend call failed: {exc}") from None
        return Completion(text=text, model=self.model,
                          usage={"input": 0, "output": 0})

register_provider(MyProvider)
```

You get `complete_json()` free, including two rounds of JSON self-repair, plus
`health_check()` used by `deckscope doctor` and the wizard.

**Contract:**

- raise `ProviderError` on failure, with a message a user can act on
- return the text only — no fences, no wrapper
- honour `max_tokens` and `temperature` when the backend supports them
- override `close()` if you hold sockets or subprocesses
- implement `native_search(query, max_results)` if your backend can search the web, and
  set `supports_native_search = True`

Use it:

```python
import my_module          # the import runs register_provider
from deckscope import analyze
analyze("deck.pdf", provider="my_backend")
```

---

## A research backend

```python
from deckscope import register_researcher
from deckscope.research.base import Researcher, SearchResult

class MySearch(Researcher):
    name = "my_search"
    needs_key = True
    key_env = "MY_SEARCH_KEY"
    signup_url = "https://example.com/api"
    blurb = "Our internal market-research index"

    def search(self, query, max_results=8):
        return [SearchResult(title=r["title"], url=r["url"], snippet=r["text"],
                             published=r.get("date"))
                for r in my_client.search(query, limit=max_results)]

register_researcher(MySearch)
```

`search_many()`, de-duplication by URL, security screening, source registration and
citation resolution all come from the base class.

**Contract:** return `[]` on a soft failure rather than raising — one bad query must not
end a run. Fill `published` when you can; recency matters to the market agent.

An internal corpus is a good fit: point DeckScope at your own research notes and they get
cited alongside public sources, with the same reliability labelling.

---

## An output format

```python
from deckscope import register_renderer

def render_email(result, out_dir, base, **kw):
    comp = result.primary
    body = [comp.get("headline", ""), "", comp.get("summary", ""), "", "Sources:"]
    for s in result.registry.cited:
        body.append(f"  [{s.sid}] {s.url}")
    p = out_dir / f"{base}_email.txt"
    p.write_text("\n".join(body), encoding="utf-8")
    return [str(p)]

register_renderer("email", render_email, "A short email body")
```

**Contract:** signature `(result, out_dir: Path, base: str, **kw) -> List[str]`, returning
the paths written. `kw` may include `theme`. Write one file per lens if the format is
per-lens; a single file otherwise.

What's on `result`:

```python
result.company                  # str
result.deck                     # DECK_SCHEMA
result.market                   # MARKET_SCHEMA
result.comparisons              # {lens: COMPARISON_SCHEMA}
result.primary                  # the first lens's comparison
result.registry                 # SourceRegistry — .cited .consulted .quarantined
result.sources                  # every Source, in citation order
result.security                 # the screen results
result.stats                    # model, research backend, timings, version
```

---

## A lens

Two edits in `deckscope/prompts/lenses.py`:

```python
class Lens(str, Enum):          # in config.py
    ...
    ACQUIRER = "acquirer"

LENS_PROFILES[Lens.ACQUIRER] = {
    "label": "Strategic acquirer",
    "reader": "a corp-dev team assessing a tuck-in acquisition",
    "question": "Would owning this be worth more to us than building it?",
    "stance": "You are a corp-dev lead. You care about integration cost, customer "
              "overlap, whether the team stays, and what this closes that we cannot "
              "close ourselves. Standalone growth matters less to you than strategic "
              "fit and the cost of the alternative.",
    "verdict_rule": "The verdict `call` must be one of: ACQUIRE, ACQUIRE IF PRICED "
                    "RIGHT, PARTNER INSTEAD, BUILD INSTEAD, PASS.",
    "emphasis": "Weight integration risk and build-versus-buy most heavily.",
}
```

It is then available in the CLI, config, app window, MCP and panel. Keep `stance`
concrete — the difference between a useful lens and a tone knob is whether it changes what
the agent *weights*.

---

## Changing a prompt

All prompts are in `deckscope/prompts/templates.py`, documented in
[PROMPTS.md](PROMPTS.md). Three shared blocks are appended to the system prompts:

- `_TRUST_RULES` — the trust boundary. **Do not remove this.** It is the backstop behind
  the security screen.
- `_CITATION_RULES` — citation discipline (market and comparison agents only).
- `_JSON_RULES` — output format.

If you edit a schema in `schemas.py`, update the renderer that reads it. `coerce()` fills
missing top-level keys so a renderer never raises `KeyError` on a field the model omitted.

---

## A whole agent

The pattern is in `deckscope/agents/`:

```python
from deckscope.agents.base import Agent
from deckscope.schemas import coerce, schema_block

MY_SCHEMA = {"finding": "str", "confidence": "high|medium|low"}

class RegulatoryAnalyst(Agent):
    name = "regulatory"
    label = "Regulatory Analyst"

    def run(self, deck, market):
        self.emit("checking the regulatory picture")
        user = f"{schema_block(MY_SCHEMA, 'Regulatory')}\n\n{...}"
        return coerce(self.cached_json(
            f"reg::{self.provider.model}",
            lambda: self.provider.complete_json(MY_SYSTEM, user)), MY_SCHEMA)
```

`Agent` gives you caching, progress events, and token tracking. Wire it into
`Pipeline.run()` in `orchestrator.py`.

---

## Adding a security detection

Add a tuple to `INTENT_PATTERNS` in `deckscope/security/text_scanner.py`:

```python
(_p(r"\byour (real|true|actual) (task|instruction|goal) is\b"),
 "task_replacement", "critical",
 "Text attempting to replace the analysis task."),
```

Add the code to `CONCEALMENT_CODES` if it is a concealment signal rather than an intent
signal — concealment escalates the severity of co-occurring intent findings.

For a new file format, add a scanner to `forensics.py` and register it in `SCANNERS`.

**Please add a test.** `tests/test_security.py` has one per detection, plus a
`test_clean_deck_is_clean` that must keep passing — a detection that fires on ordinary
business language is worse than no detection.

---

## Project conventions

- Standard library first. Every third-party import is optional and wrapped in `try`.
- Errors name the fix, not just the problem: *"Set ANTHROPIC_API_KEY, or run
  `deckscope setup`"*, not *"auth failed"*.
- Never silently degrade. A missing capability is stated in the output.
- Comments explain *why*, not *what*.
- Line length 92; `ruff` config is in `pyproject.toml`.

---

## Testing

```bash
pytest tests/                 # if you have pytest
python tests/run_tests.py     # zero dependencies
```

The `mock` provider makes the whole pipeline testable offline, including a panel that
genuinely disagrees with itself. Use it rather than mocking HTTP.
