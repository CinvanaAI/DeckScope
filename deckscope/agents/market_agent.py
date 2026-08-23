"""Agent 2 — researches the market independently of the deck's claims."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from ..prompts.templates import (MARKET_SYSTEM, MARKET_USER, QUERY_SYSTEM,
                                 QUERY_USER)
from ..research.base import Researcher, format_results
from ..security.policy import SecurityPolicy
from ..security.screening import screen_sources
from ..sources import SourceRegistry
from ..providers.base import Message, extract_json_array
from ..schemas import MARKET_SCHEMA, coerce, schema_block
from ..security.sanitizer import fence
from .base import Agent


class MarketAnalyst(Agent):
    name = "market"
    label = "2/3 Market Analyst"

    def __init__(self, provider, researcher: Researcher,
                 policy: SecurityPolicy | None = None, **kw: Any) -> None:
        super().__init__(provider, **kw)
        self.researcher = researcher
        self.policy = policy or SecurityPolicy()
        self.registry = SourceRegistry()
        self.security_report = None

    # ------------------------------------------------------------------
    def build_queries(self, deck: Dict[str, Any], max_queries: int) -> List[str]:
        """Prefer the deck agent's agenda; top it up with a dedicated pass."""
        agenda = (deck.get("research_agenda") or {}).get("search_queries") or []
        queries = [q for q in agenda if isinstance(q, str) and len(q) > 8]
        if len(queries) >= max_queries:
            return queries[:max_queries]

        company = (deck.get("company") or {}).get("name") or "the company"
        category = (deck.get("market") or {}).get("category") or "its market"
        claims = "\n".join(
            f"- {c.get('claim')}" for c in (deck.get("claims") or [])
            if c.get("load_bearing") in ("high", "medium")
        ) or "- (none extracted)"
        out = self.provider.complete(
            QUERY_SYSTEM,
            [Message("user", QUERY_USER.format(category=category, company=company,
                                               claims=claims, max_queries=max_queries))],
            max_tokens=1200, temperature=0.3,
        )
        self.track(out)
        extra = extract_json_array(out.text) or []
        for q in extra:
            if isinstance(q, str) and q not in queries:
                queries.append(q)
        return queries[:max_queries] or [f"{category} market size competitors {company}"]

    # ------------------------------------------------------------------
    def run(self, deck: Dict[str, Any], *, max_queries: int = 8,
            max_results: int = 8) -> Dict[str, Any]:
        queries = self.build_queries(deck, max_queries)
        self.emit(f"researching with {self.researcher.name}: {len(queries)} queries")
        for q in queries:
            self.emit(f"  · {q}")

        results = self.researcher.search_many(queries, max_results=max_results)
        self.emit(f"gathered {len(results)} sources")

        # Register every source BEFORE screening, so anything dropped still appears
        # in the bibliography with the reason it was dropped. A source removed for
        # hostility is evidence about the research environment, not something to hide.
        self.registry.add_results(results, backend=self.researcher.name)
        raw_count = len(results)

        # Screen every source before a single word of it reaches the model. Web pages
        # are the softest target in this pipeline: anyone can publish one.
        results, self.security_report = screen_sources(results, self.policy)
        kept_keys = {(getattr(r, "url", "") or getattr(r, "title", "")).lower()
                     for r in results}
        reasons = {f.get("excerpt", ""): f.get("detail", "")
                   for f in [x.to_dict() for x in self.security_report.findings]
                   if f.get("action") == "quarantined"}
        for src in self.registry.sources:
            key = (src.url or src.title).lower()
            if key not in kept_keys:
                src.status = "quarantined"
                src.note = next(
                    (d for e, d in reasons.items() if e and src.url and e in src.url),
                    "Dropped by the security screen: the page contained text addressed "
                    "to the AI rather than reporting facts.")
        if self.security_report.findings:
            self.emit(f"security: {self.security_report.summary_line()}")
        if raw_count != len(results):
            self.emit(f"dropped {raw_count - len(results)} untrustworthy source(s)")

        market = deck.get("market") or {}
        company = (deck.get("company") or {}).get("name") or "the company"
        claims = "\n".join(
            f"- [{c.get('id')}] {c.get('claim')} ({c.get('type')})"
            for c in (deck.get("claims") or [])
        ) or "- (none extracted)"

        research_note = (
            "The numbered bibliography follows. Cite every figure by its source ID."
            if results and self.researcher.name != "none" else
            "NO web research was available for this run. Rely on training knowledge "
            "only, set sizing_confidence to 'low', and state this limitation "
            "prominently in research_gaps."
        )

        user = MARKET_USER.format(
            company=company,
            category=market.get("category") or "unspecified",
            geography=market.get("geography") or "unspecified",
            segments=", ".join(market.get("customer_segments") or []) or "unspecified",
            claims=claims, research_note=research_note,
            schema=schema_block(MARKET_SCHEMA, "MarketAnalysis"),
            research_material=fence(self.registry.prompt_block(),
                                    "RESEARCH MATERIAL"),
        )
        out = self.cached_json(
            f"market::{self.provider.model}:{hash(tuple(queries))}:{len(results)}",
            lambda: self.provider.complete_json(MARKET_SYSTEM, user),
        )
        out = coerce(out, MARKET_SCHEMA)
        out["_meta"] = {
            "queries": queries, "backend": self.researcher.name,
            "n_results": len(results), "n_results_before_screening": raw_count,
            "registry": self.registry.to_dict(),
            "security": (self.security_report.to_dict()
                         if self.security_report else None),
        }
        landscape = out.get("competitive_landscape") or {}
        self.emit(f"mapped {len(landscape.get('incumbents') or [])} incumbents, "
                  f"{len(landscape.get('challengers') or [])} challengers")
        return out
