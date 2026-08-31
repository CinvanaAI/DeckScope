"""Agent 2 — researches the market independently of the deck's claims."""
from __future__ import annotations

from typing import Sequence, Any, Dict, List

from ..prompts.templates import (MARKET_SYSTEM, MARKET_USER, QUERY_SYSTEM,
                                 QUERY_USER)
from ..research.base import Researcher
from ..security.policy import SecurityPolicy
from ..sources import SourceRegistry
from ..providers.base import Message, extract_json_array
from ..bundling import assess as assess_bundling
from ..schemas import MARKET_SCHEMA, coerce, schema_block
from ..validate import validate_market
from ..security.sanitizer import fence
from .base import Agent


#: Query vocabulary per specialist report key. A query containing any of
#: these terms is asking for a quantity the named specialist already
#: established with its own citations.
_COVERED_VOCAB: Dict[str, tuple] = {
    "market-size": ("market size", "market sizing", "tam", "total addressable",
                    "industry size", "market worth", "market value"),
    "market-share": ("market share", "concentration", "hhi",
                     "share of market"),
    "growth": ("growth rate", "cagr", "market growth", "growth forecast"),
    "demographics": ("demographics", "population count", "household count"),
    "competitive-landscape": ("competitive landscape", "top competitors",
                              "leading vendors", "top companies in"),
    "regulation": ("regulation", "regulatory requirements", "licensing "
                   "requirements", "compliance requirements"),
}


def covered_note(covered: Sequence[str]) -> str:
    """The prompt's covered block — empty when nothing ran."""
    if not covered:
        return ""
    names = ", ".join(sorted(str(c) for c in covered))
    return (
        "\nALREADY ESTABLISHED BY SPECIALIST REPORTS: " + names + ". Their "
        "findings and citations are merged into this run and will sit beside "
        "your analysis. Do NOT produce your own parallel estimates for those "
        "quantities — where your schema asks for one, state that the "
        "specialist report establishes it. Spend your effort on what they do "
        "not cover: the market boundary and framing, buyers and their "
        "alternatives, competitive dynamics, funding environment, and "
        "regulatory context.\n")


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
        self.corpus = None

    # ------------------------------------------------------------------
    def build_queries(self, deck: Dict[str, Any], max_queries: int,
                      covered: Sequence[str] = ()) -> List[str]:
        """Prefer the deck agent's agenda; top it up with a dedicated pass.

        `covered` names the specialist reports that already ran: queries
        about their quantities are dropped, because researching them again
        in parallel is what the external audit called "two partially
        parallel systems" — the specialists' figures arrive with their own
        citations, and a second, looser search for the same number can only
        muddy the evidence."""
        agenda = (deck.get("research_agenda") or {}).get("search_queries") or []
        queries = [q for q in agenda if isinstance(q, str) and len(q) > 8]
        queries = self._drop_covered(queries, covered, deck)
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
        queries = self._drop_covered(queries, covered, deck)
        return queries[:max_queries] or [self._fallback_query(deck, covered)]

    @staticmethod
    def _fallback_query(deck: Dict[str, Any], covered: Sequence[str]) -> str:
        company = (deck.get("company") or {}).get("name") or "the company"
        category = (deck.get("market") or {}).get("category") or "its market"
        if covered:
            # The sized quantities are the specialists' job now; what is
            # left to establish is the boundary itself.
            return (f"{category} market boundary adjacent segments "
                    f"buyer alternatives {company}")
        return f"{category} market size competitors {company}"

    def _drop_covered(self, queries: List[str],
                      covered: Sequence[str],
                      deck: Dict[str, Any]) -> List[str]:
        if not covered:
            return queries
        vocab: List[str] = []
        for key in covered:
            vocab.extend(_COVERED_VOCAB.get(str(key).strip().lower(), ()))
        if not vocab:
            return queries
        kept, dropped = [], []
        for q in queries:
            (dropped if any(w in q.lower() for w in vocab) else kept).append(q)
        if dropped:
            self.emit(f"skipped {len(dropped)} quer(y/ies) already covered "
                      f"by specialist reports: "
                      + "; ".join(d[:60] for d in dropped))
        return kept

    # ------------------------------------------------------------------
    def run(self, deck: Dict[str, Any], *, max_queries: int = 8,
            max_results: int = 8, corpus: Any = None,
            covered: Sequence[str] = ()) -> Dict[str, Any]:
        """Analyze the market.

        When `corpus` is supplied the research phase is skipped entirely and that
        frozen evidence is used instead — which is what lets two modes be compared
        on identical sources rather than on whatever each happened to retrieve.
        """
        from ..corpus import gather

        if corpus is None:
            queries = self.build_queries(deck, max_queries, covered=covered)
            self.emit(f"researching with {self.researcher.name}: "
                      f"{len(queries)} queries")
            for q in queries:
                self.emit(f"  · {q}")
            corpus = gather(self.researcher, queries, self.policy,
                            max_results=max_results,
                            on_event=lambda m, _d=None: self.emit(m))
        else:
            queries = list(corpus.queries)
            self.emit(f"using frozen corpus {corpus.fingerprint()} "
                      f"({corpus.kept} source(s), backend {corpus.backend})")

        self.registry = corpus.registry
        self.security_report = corpus.security
        self.corpus = corpus
        raw_count = corpus.retrieved

        if corpus.empty:
            self.emit("no external sources — the market view will be unverified "
                      "and the report will say so")
        if self.security_report and self.security_report.findings:
            self.emit(f"security: {self.security_report.summary_line()}")
        if raw_count and raw_count != corpus.kept:
            self.emit(f"dropped {raw_count - corpus.kept} untrustworthy source(s)")

        market = deck.get("market") or {}
        company = (deck.get("company") or {}).get("name") or "the company"
        claims = "\n".join(
            f"- [{c.get('id')}] {c.get('claim')} ({c.get('type')})"
            for c in (deck.get("claims") or [])
        ) or "- (none extracted)"

        have_evidence = bool(self.registry.citable)
        research_note = (
            "The numbered bibliography follows. Cite every figure by its source ID."
            if have_evidence else
            "NO external evidence is available for this run."
        )

        user = MARKET_USER.format(
            covered_note=covered_note(covered),
            company=company,
            category=market.get("category") or "unspecified",
            geography=market.get("geography") or "unspecified",
            segments=", ".join(market.get("customer_segments") or []) or "unspecified",
            claims=claims, research_note=research_note,
            schema=schema_block(MARKET_SCHEMA, "MarketAnalysis"),
            research_material=(
                fence(self.registry.prompt_block(), "RESEARCH MATERIAL")
                if have_evidence
                else getattr(self.researcher, "NOTICE",
                             "No external evidence was retrieved for this run.")),
        )
        # Bound to the EXACT evidence, not just the query list and a count.
        # Two searches returning the same number of different results must not
        # replay each other's market analysis.
        out = self.cached_json(
            self.cache_key(
                covered=sorted(str(c) for c in covered),
                queries=sorted(queries),
                backend=self.researcher.name,
                security=self.policy.mode.value,
                sources=[{"url": s.url, "title": s.title,
                          "snippet": s.snippet[:500]} for s in self.registry.sources],
                claims=claims,
            ),
            lambda: self.complete_json(MARKET_SYSTEM, user),
        )
        out = coerce(out, MARKET_SCHEMA)
        validation = validate_market(
            out, valid_source_ids=self.registry.citable_ids)
        if not validation.ok:
            self.emit(f"validation: {validation.summary()}")

        # Derived in Python rather than asked of the model, so the same inputs
        # always give the same reading and the reasoning can be inspected.
        bundling = assess_bundling(out.get("open_source_landscape"),
                                   out.get("absorption_risk"))
        out["bundling_assessment"] = bundling.to_dict()
        if bundling.applicable:
            self.emit(f"open-source signal: bundling risk {bundling.level}"
                      + (f" ({bundling.closest_project} is {bundling.gap})"
                         if bundling.closest_project and bundling.gap else ""))
        out["_meta"] = {
            "queries": queries, "backend": self.researcher.name,
            "n_results": corpus.kept, "n_results_before_screening": raw_count,
            "corpus_fingerprint": corpus.fingerprint(),
            "registry": self.registry.to_dict(),
            "security": (self.security_report.to_dict()
                         if self.security_report else None),
            "validation": validation.to_dict(),
        }
        landscape = out.get("competitive_landscape") or {}
        self.emit(f"mapped {len(landscape.get('incumbents') or [])} incumbents, "
                  f"{len(landscape.get('challengers') or [])} challengers")
        return out
