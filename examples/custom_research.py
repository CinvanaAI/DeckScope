"""A research backend over your own corpus.

Point DeckScope at internal market notes and they get cited alongside public
sources, with the same reliability labelling and the same security screening.

    python examples/custom_research.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope import register_researcher
from deckscope.research.base import Researcher, SearchResult


class LocalNotesResearcher(Researcher):
    """Naive keyword search over a folder of markdown notes.

    A real implementation would hit your internal search API or a vector store.
    The contract is the same either way: return SearchResult objects, and return
    an empty list on a soft failure rather than raising — one bad query must not
    end a run.
    """

    name = "local_notes"
    needs_key = False
    blurb = "Our internal market-research notes"

    def __init__(self, config=None) -> None:
        super().__init__(config)
        folder = (self.config.extra or {}).get("folder", "./research_notes")
        self.folder = Path(folder).expanduser()

    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        if not self.folder.exists():
            return []

        terms = [t.lower() for t in query.split() if len(t) > 3]
        scored = []

        for path in self.folder.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            lowered = text.lower()
            score = sum(lowered.count(t) for t in terms)
            if score:
                scored.append((score, path, text))

        scored.sort(key=lambda x: -x[0])
        results = []
        for score, path, text in scored[:max_results]:
            results.append(SearchResult(
                title=path.stem.replace("_", " ").title(),
                url=path.as_uri(),
                snippet=self._excerpt(text, terms),
                published=None,
                source_query=query))
        return results

    @staticmethod
    def _excerpt(text: str, terms: List[str], window: int = 1200) -> str:
        lowered = text.lower()
        for t in terms:
            i = lowered.find(t)
            if i != -1:
                start = max(0, i - window // 3)
                return text[start:start + window]
        return text[:window]


register_researcher(LocalNotesResearcher)


if __name__ == "__main__":
    from deckscope.config import ResearchConfig
    from deckscope.research.registry import get_researcher, list_researchers

    print("registered backends:", ", ".join(list_researchers()))

    r = get_researcher(ResearchConfig(name="local_notes",
                                      extra={"folder": "./research_notes"}))
    print("health check:", r.health_check())

    print("\nUse it with:")
    print("  deckscope run deck.pdf --research local_notes")
    print("or in config:")
    print("  research: {name: local_notes, extra: {folder: ~/notes}}")
