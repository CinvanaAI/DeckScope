"""Agent 2b — map the market cold, without seeing the deck.

The pipeline's market analyst is given the deck's claims, because it has to be:
it is checking them. But that shapes its search. It looks for evidence about the
things the deck raises, which finds *errors* well and finds *omissions* badly —
nobody searches for what they were not prompted to consider. A deck that never
mentions its dominant incumbent produces research that never mentions it either.

This agent is the correction. It receives the category and at most a company name,
and nothing else. It generates its own queries, reads its own sources, and
describes the market as an analyst would who was handed the beat cold.

The value is entirely in the delta. What did the cold pass find that the
claim-directed pass never looked for? That difference is the strongest form of
blind spot available here, because it was produced by a process that could not
have been anchored by the deck.

**The isolation is structural, not a matter of instruction.** `_identity()` builds
the entire payload this agent may see, and a test asserts that no claim text, ask,
traction figure or founder name reaches it. A prompt saying "do not consider the
deck" is worth very little when the deck is in the context window.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..prompts.templates import (DISCOVERY_QUERY_SYSTEM, DISCOVERY_QUERY_USER,
                                 DISCOVERY_SYSTEM, DISCOVERY_USER)
from ..providers.base import Message, extract_json_array
from ..schemas import MARKET_SCHEMA, coerce, schema_block
from ..security.policy import SecurityPolicy
from ..security.sanitizer import fence
from .base import Agent

#: The only fields of the deck extraction this agent is permitted to see.
#:
#: Deliberately minimal, and deliberately a whitelist rather than a blacklist: a
#: blacklist grows a hole every time the deck schema gains a field.
ALLOWED_IDENTITY_FIELDS = ("category", "sub_category", "geography")


class DiscoveryAnalyst(Agent):
    name = "discovery"
    label = "2b/4 Cold Market Discovery"

    def __init__(self, provider, researcher: Any,
                 policy: Optional[SecurityPolicy] = None, **kw: Any) -> None:
        super().__init__(provider, **kw)
        self.researcher = researcher
        self.policy = policy or SecurityPolicy()
        self.corpus = None

    # ------------------------------------------------------------------
    @staticmethod
    def _identity(deck: Dict[str, Any]) -> Dict[str, str]:
        """Everything this agent is allowed to know. Nothing else may pass.

        A company NAME is included because a market cannot be researched without
        knowing which one it is, and the name alone carries no thesis. Everything
        that constitutes a claim — sizing, traction, competitors, the ask, the
        team — is excluded by construction.
        """
        market = deck.get("market") or {}
        company = deck.get("company") or {}
        out = {k: str(market.get(k) or "") for k in ALLOWED_IDENTITY_FIELDS}
        out["company_name"] = str(company.get("name") or "")
        return {k: v for k, v in out.items() if v}

    def _queries(self, identity: Dict[str, str], max_queries: int) -> List[str]:
        category = identity.get("category") or "this market"
        company = identity.get("company_name")
        company_line = f"A company in it is called: {company}" if company else ""
        out = self.provider.complete(
            DISCOVERY_QUERY_SYSTEM,
            [Message("user", DISCOVERY_QUERY_USER.format(
                category=category, company_line=company_line,
                geography=identity.get("geography") or "unspecified",
                max_queries=max_queries))],
            max_tokens=1200, temperature=0.4)
        self.track(out)
        queries = [q for q in (extract_json_array(out.text) or [])
                   if isinstance(q, str) and len(q) > 8]
        if not queries:
            queries = [f"{category} market overview",
                       f"who sells {category} software",
                       f"{category} why projects fail"]
        return queries[:max_queries]

    # ------------------------------------------------------------------
    def run(self, deck: Dict[str, Any], *, max_queries: int = 6,
            max_results: int = 8) -> Dict[str, Any]:
        from ..corpus import gather

        identity = self._identity(deck)
        if not identity.get("category"):
            self.emit("no category identified — skipping cold discovery")
            return {"_meta": {"skipped": "no category available"}}

        self.emit(f"mapping '{identity['category']}' cold, without the deck's claims")
        queries = self._queries(identity, max_queries)
        for q in queries:
            self.emit(f"  · {q}")

        self.corpus = gather(self.researcher, queries, self.policy,
                             max_results=max_results,
                             on_event=lambda m, _d=None: self.emit(m))

        company = identity.get("company_name")
        user = DISCOVERY_USER.format(
            category=identity["category"],
            company_line=(f"A company in this market is called: {company}"
                          if company else "No company name was supplied."),
            geography=identity.get("geography") or "unspecified",
            schema=schema_block(MARKET_SCHEMA, "MarketAnalysis"),
            material=(fence(self.corpus.prompt_block(char_budget=60_000),
                            "RESEARCH MATERIAL")
                      if not self.corpus.empty else
                      "No external research was available. Say so, and set "
                      "sizing_confidence to low."))

        out = self.cached_json(
            self.cache_key(identity=identity, queries=sorted(queries),
                           sources=[{"url": s.url, "title": s.title}
                                    for s in self.corpus.registry.sources]),
            lambda: self.complete_json(DISCOVERY_SYSTEM, user, temperature=0.3))
        out = coerce(out, MARKET_SCHEMA)
        out["_meta"] = {
            "mode": "cold_discovery",
            "identity_shown": identity,
            "queries": queries,
            "backend": self.corpus.backend,
            "corpus_fingerprint": self.corpus.fingerprint(),
            "n_results": self.corpus.kept,
        }
        land = out.get("competitive_landscape") or {}
        self.emit(f"found {len(land.get('incumbents') or [])} incumbent(s), "
                  f"{len(land.get('challengers') or [])} challenger(s) cold")
        return out
