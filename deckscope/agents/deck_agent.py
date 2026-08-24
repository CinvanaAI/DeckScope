"""Agent 1 — reads the deck, extracts claims, sets the research agenda."""
from __future__ import annotations

from pathlib import PurePath

from typing import Any, Dict

from ..ingest.loader import DeckDocument
from ..prompts.templates import DECK_SYSTEM, DECK_USER
from ..schemas import DECK_SCHEMA, coerce, schema_block
from .base import Agent

MAX_DECK_CHARS = 120_000


class DeckAnalyst(Agent):
    name = "deck"
    label = "1/3 Deck Analyst"

    def run(self, doc: DeckDocument, *, company_hint: str | None = None,
            max_queries: int = 10) -> Dict[str, Any]:
        text = doc.text
        truncated = False
        if len(text) > MAX_DECK_CHARS:
            text = text[:MAX_DECK_CHARS] + "\n\n[... deck truncated for length ...]"
            truncated = True

        hint = (f"The company is believed to be: {company_hint}."
                if company_hint else
                "The company name is not supplied — take it from the deck.")
        user = DECK_USER.format(
            # The file's name, never its path. A model has no use for the
            # operator's directory layout, and putting it in the prompt made
            # every prompt machine-specific — which broke prompt-keyed caching
            # across machines and, more visibly, made the committed benchmark
            # prompts unreplayable anywhere but the machine that produced them.
            company_hint=hint, source=_source_label(doc.source),
            n_slides=doc.n_slides,
            max_queries=max_queries, schema=schema_block(DECK_SCHEMA, "DeckExtraction"),
            deck_text=text,
        )
        self.emit(f"reading {doc.n_slides} slide(s) from {doc.fmt.upper()}")
        # doc.text has already been screened and fenced by security.screen_deck.
        for w in doc.warnings:
            self.emit(f"warning: {w}")

        result = self.cached_json(
            self.cache_key(deck=text, hint=company_hint, queries=max_queries),
            lambda: self.complete_json(DECK_SYSTEM, user),
        )
        result = coerce(result, DECK_SCHEMA)
        result["_meta"] = {
            "source": doc.source, "format": doc.fmt, "slides": doc.n_slides,
            "truncated": truncated, "loader_warnings": doc.warnings,
        }
        claims = result.get("claims") or []
        self.emit(f"extracted {len(claims)} claims "
                  f"({sum(1 for c in claims if c.get('load_bearing') == 'high')} load-bearing)")
        return result


def _source_label(source: str) -> str:
    """The deck's name, with any local directory removed.

    A URL keeps its whole address — that is the identity of a remote deck and it
    is not machine-specific. A local path is reduced to its file name, because
    everything to the left of it describes the operator's machine rather than
    the deck: it is useless to the model, it leaks directory layout into a
    third-party prompt, and it makes the prompt itself unportable. That last one
    is not hypothetical — it is what stopped the committed benchmark prompts
    from replaying anywhere except the machine that generated them.
    """
    text = str(source or "").strip()
    if not text:
        return "unknown"
    if "://" in text:
        return text
    return PurePath(text.replace("\\", "/")).name or text
