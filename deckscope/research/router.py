"""Deciding *where* a question should be asked, not just what to ask.

A live test of the old engine asked how many landscaping firms operate in
Phoenix. It got two SEO directories claiming 193 and 71, both lead-generation
listicles, neither a business census. That was not a research failure. It was a
**source-type failure**: a question whose answer sits in a government database
was sent to a web search, and web search returned what web search returns.

Firm counts, survival rates, wages, and public-company financials are all
published as structured data by people whose job is counting. A research engine
that only knows how to search will answer those questions with a blog post every
time, and — worse — the blog post will arrive with a citation, which makes the
wrong answer look better evidenced than an honest "unknown".

Routing is rules-first on purpose. A regex table is inspectable, free,
deterministic, and testable offline; a model classifier is none of those and adds
a call to every question. The model is only consulted when the rules abstain.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

#: Where a question can be sent.
SEARCH = "search"      # general web search — context, leads, qualitative
DATASET = "dataset"    # a structured statistical source
FILING = "filing"      # regulatory filings and registries
FETCH = "fetch"        # retrieve a specific page in full, not a snippet
KINDS = (SEARCH, DATASET, FILING, FETCH)


@dataclass
class Route:
    kind: str
    #: A dataset/filing backend name, when the kind implies one.
    backend: Optional[str] = None
    #: Why this route was chosen, kept so a wrong answer can be traced to a
    #: wrong routing decision rather than blamed on the model.
    because: str = ""
    #: Structured parameters a dataset backend needs (industry, geography, …).
    params: Dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.params is None:
            self.params = {}


#: (pattern, kind, backend, why). Order matters — first match wins, so the most
#: specific patterns come first.
RULES: List[Tuple[str, str, Optional[str], str]] = [
    (r"\b(how many|number of|count of)\b.*\b(business|businesses|firms?|companies|"
     r"establishments?|providers?|vendors?|competitors?)\b",
     DATASET, "census_cbp",
     "a count of businesses is published by the business census, not by blogs"),

    (r"\b(survival|survive|still (in business|operating)|fail(ure)? rate|"
     r"how many last|make it to \d+ years?)\b",
     DATASET, "bls_bed",
     "firm survival by age is measured by business employment dynamics data"),

    (r"\b(wage|wages|salary|salaries|pay|hourly rate|labou?r cost)\b",
     DATASET, "bls_oes",
     "occupational wages by metro are published as structured data"),

    # Market-wide questions are excluded before the filing rule sees them.
    # "What share of smartphone revenue does each company hold in Ireland?"
    # matched on `revenue` and went to EDGAR full-text search, which indexes
    # what individual filers say about themselves and cannot answer a question
    # about a market. The whole revenue half of a market-share panel vanished
    # into a backend that was never going to have it — and it vanished as
    # "no backend could answer this", which reads as an absent fact rather than
    # as the misrouting it was. A wrong route is the most expensive kind of
    # wrong answer here, because it looks like evidence of a gap.
    (r"\b(market share|share of (the )?(market|revenue|units|shipments)|"
     r"market size|industry (revenue|size)|each (company|vendor|brand)|"
     r"by (vendor|brand|manufacturer))\b",
     SEARCH, None,
     "a question about a whole market's revenue is answered by the firms who "
     "track markets, not by any one company's own filings"),

    (r"\b(revenue|earnings|market cap|10-?k|10-?q|annual report|filing|"
     r"public company financials?)\b",
     FILING, "edgar",
     "public company financials come from filings, not from summaries of them"),

    (r"\b(licen[cs]e|licencing|licensing|permit|regulat|statute|legal requirement|"
     r"certification|bond|exempt)\b",
     FETCH, None,
     "the decisive detail in a regulation is usually below the fold, so the page "
     "must be read rather than snippeted"),

    (r"\b(pricing|price list|how much does .* charge|subscription cost|"
     r"job posting|careers page|roadmap|changelog|release notes)\b",
     FETCH, None,
     "what a vendor actually does is on their own pages, not in commentary"),

    (r"\b(market size|tam|sam|som|industry size|market value|cagr|growth rate)\b",
     SEARCH, None,
     "sizing needs several independent estimates, which search is good at "
     "surfacing and a single dataset is not"),
]

_COMPILED = [(re.compile(p, re.I), k, b, why) for p, k, b, why in RULES]


def classify(text: str, *, params: Optional[Dict[str, Any]] = None) -> Route:
    """Route a question by its shape. Falls back to search, which is honest.

    Search is the fallback rather than the default: everything with a better
    home should have been claimed by a rule above, and anything that reaches the
    bottom genuinely is a qualitative question.
    """
    question = (text or "").strip()
    for pattern, kind, backend, why in _COMPILED:
        if pattern.search(question):
            return Route(kind=kind, backend=backend, because=why,
                         params=dict(params or {}))
    return Route(kind=SEARCH, because="no structured source covers this kind of "
                                      "question; general search is appropriate",
                 params=dict(params or {}))


def route_all(questions) -> Dict[str, Route]:
    """Convenience for reporting: how the whole queue was routed."""
    return {q.id: classify(q.text) for q in questions}


def routing_report(questions) -> Dict[str, Any]:
    """A summary the UI can show, so routing is visible rather than implicit."""
    routes = route_all(questions)
    counts: Dict[str, int] = {}
    for r in routes.values():
        counts[r.kind] = counts.get(r.kind, 0) + 1
    return {
        "by_kind": counts,
        "questions": [{"id": qid, "kind": r.kind, "backend": r.backend,
                       "because": r.because}
                      for qid, r in routes.items()],
    }
