"""The one interface every web-research backend implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from ..config import ResearchConfig


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    published: Optional[str] = None
    source_query: Optional[str] = None
    #: Set when the query did not execute. Such a row is a report of an outage,
    #: never a source: it must never be registered, cited, or shown to a reader.
    #: See `Researcher.search_many` and `deckscope.corpus.gather`.
    error: Optional[str] = None

    @property
    def failed(self) -> bool:
        return self.error is not None

    @classmethod
    def failure(cls, query: str, exc: BaseException) -> "SearchResult":
        return cls(title=f"[search failed] {query}", url="", snippet="",
                   source_query=query, error=str(exc)[:300])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Researcher(ABC):
    """Implement `search()` and DeckScope can research with any provider.

        from deckscope import register_researcher
        from deckscope.research.base import Researcher, SearchResult

        class MySearch(Researcher):
            name = "my_search"
            def search(self, query, max_results=8):
                return [SearchResult(t, u, s) for t, u, s in my_api(query)]

        register_researcher(MySearch)
    """

    name: str = "base"
    needs_key: bool = False
    key_env: str = ""
    signup_url: str = ""
    blurb: str = ""

    def __init__(self, config: Optional[ResearchConfig] = None) -> None:
        self.config = config or ResearchConfig(name=self.name)

    @abstractmethod
    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        """Return results for one query. Return [] rather than raising on soft failures."""

    def search_many(self, queries: List[str], max_results: int = 8) -> List[SearchResult]:
        """Run several queries, de-duplicated by URL, order preserved."""
        seen, out = set(), []
        for q in queries:
            try:
                results = self.search(q, max_results=max_results)
            except Exception as exc:  # noqa: BLE001 - one bad query must not kill the run
                # Marked as a failure rather than described as one. This used to
                # put the exception text in `snippet`, which made the row an
                # ordinary result: it was registered, given a citation ID, and
                # handed to the reader as research material. Observed live — a
                # search timeout reached the reader as
                # "[S1] [search failed] ... content: No answer appeared within
                # 45s", inviting it to extract findings about a market from a
                # Python traceback. A query that found nothing and a query that
                # did not run are different facts and only one of them is about
                # the market.
                out.append(SearchResult.failure(q, exc))
                continue
            for r in results:
                key = (r.url or r.title).strip().lower()
                if key and key in seen:
                    continue
                seen.add(key)
                r.source_query = r.source_query or q
                out.append(r)
        return out

    def health_check(self) -> Dict[str, Any]:
        try:
            res = self.search("market size software", max_results=2)
            return {"ok": True, "backend": self.name, "results": len(res)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "backend": self.name, "error": str(exc)}


def format_results(results: List[SearchResult], char_budget: int = 90_000) -> str:
    """Pack results into the research material block, newest/most relevant first."""
    blocks, used = [], 0
    for i, r in enumerate(results, 1):
        block = (f"[{i}] {r.title}\n"
                 f"    url: {r.url or 'n/a'}\n"
                 f"    date: {r.published or 'unknown'}\n"
                 f"    query: {r.source_query or 'n/a'}\n"
                 f"    {r.snippet.strip()[:2500]}\n")
        if used + len(block) > char_budget:
            blocks.append(f"[... {len(results) - i + 1} further results omitted for length ...]")
            break
        blocks.append(block)
        used += len(block)
    return "\n".join(blocks) if blocks else "(no research material available)"
