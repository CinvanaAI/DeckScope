"""Search backends. Each is ~30 lines; add your own the same way."""
from __future__ import annotations

import json
import os
import urllib.parse
from typing import List, Optional

from ..config import ResearchConfig
from ..providers._http import get_json, post_json
from .base import Researcher, SearchResult


class _KeyedResearcher(Researcher):
    needs_key = True

    def __init__(self, config: Optional[ResearchConfig] = None) -> None:
        super().__init__(config)
        env = self.config.api_key_env or self.key_env
        self.api_key = os.getenv(env) or self.config.extra.get("api_key")
        if self.needs_key and not self.api_key:
            raise RuntimeError(
                f"{self.name} needs an API key. Set {env} (free tier at {self.signup_url}), "
                f"or run `deckscope setup` to pick a different research backend."
            )


class TavilyResearcher(_KeyedResearcher):
    name = "tavily"
    key_env = "TAVILY_API_KEY"
    signup_url = "https://tavily.com"
    blurb = "Built for AI research. Generous free tier. Recommended."

    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        payload = {"api_key": self.api_key, "query": query,
                   "max_results": max_results, "search_depth": "advanced",
                   "include_answer": True}
        if self.config.recency_days:
            payload["days"] = self.config.recency_days
        data = post_json("https://api.tavily.com/search", payload, {})
        out = []
        if data.get("answer"):
            out.append(SearchResult(f"Synthesized answer: {query}", "",
                                    data["answer"], source_query=query))
        for r in data.get("results", []):
            out.append(SearchResult(r.get("title", ""), r.get("url", ""),
                                    r.get("content", ""), r.get("published_date"), query))
        return out


class SerperResearcher(_KeyedResearcher):
    name = "serper"
    key_env = "SERPER_API_KEY"
    signup_url = "https://serper.dev"
    blurb = "Google results via API. 2,500 free queries."

    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        data = post_json("https://google.serper.dev/search",
                         {"q": query, "num": max_results},
                         {"X-API-KEY": self.api_key})
        out = []
        if data.get("answerBox", {}).get("snippet"):
            out.append(SearchResult("Answer box", data["answerBox"].get("link", ""),
                                    data["answerBox"]["snippet"], source_query=query))
        for r in data.get("organic", []):
            out.append(SearchResult(r.get("title", ""), r.get("link", ""),
                                    r.get("snippet", ""), r.get("date"), query))
        return out


class BraveResearcher(_KeyedResearcher):
    name = "brave"
    key_env = "BRAVE_API_KEY"
    signup_url = "https://brave.com/search/api"
    blurb = "Independent index. Free tier available."

    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        url = ("https://api.search.brave.com/res/v1/web/search?"
               + urllib.parse.urlencode({"q": query, "count": max_results}))
        data = get_json(url, {"X-Subscription-Token": self.api_key,
                              "Accept": "application/json"})
        return [SearchResult(r.get("title", ""), r.get("url", ""),
                             r.get("description", ""), r.get("age"), query)
                for r in data.get("web", {}).get("results", [])]


class ExaResearcher(_KeyedResearcher):
    name = "exa"
    key_env = "EXA_API_KEY"
    signup_url = "https://exa.ai"
    blurb = "Semantic search over high-quality pages. Good for market reports."

    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        payload = {"query": query, "numResults": max_results,
                   "contents": {"text": {"maxCharacters": 2000}}}
        data = post_json("https://api.exa.ai/search", payload,
                         {"x-api-key": self.api_key})
        return [SearchResult(r.get("title", ""), r.get("url", ""),
                             (r.get("text") or r.get("snippet") or ""),
                             r.get("publishedDate"), query)
                for r in data.get("results", [])]


class ProviderNativeResearcher(Researcher):
    """Use the model provider's own server-side web search (e.g. Anthropic's).

    No separate search key needed — the model does the searching.
    """

    name = "provider_native"
    needs_key = False
    blurb = "Let the AI provider search the web itself. No extra key needed."

    def __init__(self, config: Optional[ResearchConfig] = None, provider=None) -> None:
        super().__init__(config)
        self.provider = provider

    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        if self.provider is None or not hasattr(self.provider, "native_search"):
            raise RuntimeError(
                "The configured AI provider has no built-in web search. "
                "Run `deckscope setup` and choose a search backend such as Tavily."
            )
        out = []
        for item in self.provider.native_search(query, max_results):
            out.append(SearchResult(item.get("title", ""), item.get("url", ""),
                                    item.get("snippet", ""), None, query))
            for s in item.get("sources", []) or []:
                out.append(SearchResult(s.get("title", ""), s.get("url", ""),
                                        s.get("snippet", ""), None, query))
        return out


class MCPResearcher(Researcher):
    """Search through an MCP server that exposes a search tool."""

    name = "mcp"
    needs_key = False
    blurb = "Route search through an MCP server you already run."

    def __init__(self, config: Optional[ResearchConfig] = None) -> None:
        super().__init__(config)
        from ..providers.mcp_provider import MCPStdioClient

        cmd = self.config.extra.get("command")
        if not cmd:
            raise RuntimeError("MCP research backend needs extra.command in your config.")
        if isinstance(cmd, str):
            import shlex
            cmd = shlex.split(cmd)
        self.tool = self.config.extra.get("tool_name", "search")
        self.arg = self.config.extra.get("query_arg", "query")
        self.client = MCPStdioClient(cmd, self.config.extra.get("env"))

    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        text = self.client.call_tool(self.tool, {self.arg: query})
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [SearchResult(d.get("title", ""), d.get("url", ""),
                                     d.get("snippet") or d.get("content", ""),
                                     d.get("date"), query) for d in data][:max_results]
        except Exception:  # noqa: BLE001 - plain text is fine too
            pass
        return [SearchResult(f"MCP search: {query}", "", text[:6000], None, query)]


class NoResearcher(Researcher):
    """Model-knowledge-only mode. Honest about its own limits."""

    name = "none"
    needs_key = False
    blurb = "Skip web search. Fastest, free, but the market view can be out of date."

    #: Told to the model in place of a bibliography. It is an instruction about
    #: the run, not a source — an earlier version returned it AS a SearchResult,
    #: which meant the report claimed one source consulted and one cited, both of
    #: them this notice. A bibliography that cites its own absence is worse than
    #: an empty one.
    NOTICE = ("NO WEB RESEARCH WAS PERFORMED FOR THIS RUN.\n\n"
              "No search backend was configured, so there is no external evidence "
              "below. Everything you conclude about the market must come from your "
              "training knowledge, which has a cutoff date and cannot see recent "
              "funding rounds, pricing changes, or new entrants.\n\n"
              "Therefore: set sizing_confidence to 'low', cite no source IDs at all "
              "(there are none — do not invent any), and state this limitation "
              "prominently in research_gaps.")

    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        return []

    def search_many(self, queries, max_results: int = 8) -> List[SearchResult]:
        return []

    def health_check(self):
        return {"ok": True, "backend": self.name, "results": 0}
