"""Agent 4 (optional) — what else could you do with the money?

Runs after the market analysis, because it needs the competitor list. Its job is
to turn "here are the incumbents" into "here is what buying one of them instead
would look like", which is the comparison an investor is actually making and which
nothing else in DeckScope was measuring.

It contributes facts, not forecasts. The model is asked only for things that can
be sourced — is this company listed, what did it actually return, what do published
base rates say — and the arithmetic that turns those into a comparison happens in
`deckscope/opportunity.py`, in Python, where it can be checked by hand.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..market_data.base import Listing, MarketDataProvider
from ..opportunity import (Assumptions, ComparableReturn, build_comparison,
                           parse_money, parse_percent)
from ..prompts.templates import BASERATE_SYSTEM, BASERATE_USER
from ..security.sanitizer import fence
from .base import Agent


class OpportunityAnalyst(Agent):
    name = "opportunity"
    label = "4/4 Opportunity Cost"

    def __init__(self, provider, market_data: MarketDataProvider,
                 researcher: Any = None, assumptions: Optional[Assumptions] = None,
                 **kw: Any) -> None:
        super().__init__(provider, **kw)
        self.market_data = market_data
        self.researcher = researcher
        self.assumptions = assumptions or Assumptions()

    # ------------------------------------------------------------------
    def run(self, deck: Dict[str, Any], market: Dict[str, Any],
            registry: Any = None) -> Dict[str, Any]:
        company = (deck.get("company") or {}).get("name") or "this company"
        names = self._competitor_names(market)
        if not names:
            self.emit("no named competitors to price against")

        self.emit(f"checking whether {len(names)} competitor(s) are publicly traded")
        listings = self.market_data.lookup_many(
            names, context=(market.get("market_definition") or {}).get("category", ""))
        listed = [x for x in listings if x.is_listed]
        self.emit(f"{len(listed)} of {len(listings)} appear to be listed"
                  + (f" ({', '.join(x.ticker for x in listed if x.ticker)})"
                     if listed else ""))

        base_rates = self._base_rates(deck, market, registry)

        ask = deck.get("ask") or {}
        traction = deck.get("traction") or {}
        comparison = build_comparison(
            company=company,
            ask=parse_money(ask.get("amount")),
            post_money=parse_money(ask.get("valuation")),
            current_arr=parse_money(traction.get("revenue")),
            current_growth_monthly=parse_percent(traction.get("growth")),
            comparables=[_to_comparable(x) for x in listings],
            assumptions=self.assumptions,
            base_rates=base_rates,
        )

        out = comparison.to_dict()
        out["_meta"] = {
            "market_data_backend": self.market_data.name,
            "precision": self.market_data.precision,
            "competitors_checked": len(listings),
            "competitors_listed": len(listed),
        }
        if comparison.headline:
            self.emit(comparison.headline[:120])
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _competitor_names(market: Dict[str, Any]) -> List[str]:
        land = market.get("competitive_landscape") or {}
        names: List[str] = []
        for group in ("incumbents", "challengers"):
            for c in land.get(group) or []:
                name = (c or {}).get("name")
                if name and name not in names:
                    names.append(str(name))
        return names[:8]

    def _base_rates(self, deck: Dict[str, Any], market: Dict[str, Any],
                    registry: Any) -> List[Dict[str, Any]]:
        """Published outcome rates, cited. An empty list is an honest answer."""
        if not self.researcher or getattr(self.researcher, "name", "none") == "none":
            self.emit("no research backend — base rates unavailable")
            return []

        category = (market.get("market_definition") or {}).get("category") or "software"
        stage = (deck.get("company") or {}).get("stage") or "seed"
        try:
            results = self.researcher.search_many([
                f"{stage} stage startup outcomes what percentage return capital study",
                f"{category} startup exit multiples revenue acquisition data",
                f"{stage} to exit dilution typical percentage venture",
            ], max_results=5)
        except Exception as exc:  # noqa: BLE001
            self.emit(f"base-rate research failed: {exc}")
            return []
        if not results:
            return []

        if registry is not None:
            registry.add_results(results, backend=getattr(self.researcher, "name", ""))

        material = "\n\n".join(
            f"[{i}] {r.title}\n    {r.url}\n    {(r.snippet or '')[:1500]}"
            for i, r in enumerate(results[:12], 1))
        ask = deck.get("ask") or {}
        traction = deck.get("traction") or {}
        try:
            data = self.complete_json(
                BASERATE_SYSTEM,
                BASERATE_USER.format(
                    stage=stage, category=category,
                    ask=ask.get("amount") or "unstated",
                    valuation=ask.get("valuation") or "unstated",
                    traction=traction.get("revenue") or "unstated",
                    schema_note="Cite every rate by its source ID.",
                    material=fence(material, "RESEARCH MATERIAL")),
                temperature=0.1)
        except Exception as exc:  # noqa: BLE001
            self.emit(f"base rates unavailable: {exc}")
            return []

        rates = [r for r in (data.get("base_rates") or []) if isinstance(r, dict)]
        # A rate with no source is exactly the kind of authoritative-sounding
        # number this project exists to refuse.
        cited = [r for r in rates if r.get("source_ids")]
        dropped = len(rates) - len(cited)
        if dropped:
            self.emit(f"dropped {dropped} uncited base rate(s)")
        self.emit(f"{len(cited)} sourced base rate(s)")
        return cited


def _to_comparable(listing: Listing) -> ComparableReturn:
    return ComparableReturn(
        name=listing.name, ticker=listing.ticker, exchange=listing.exchange,
        market_cap=listing.market_cap, revenue=listing.revenue,
        revenue_growth=listing.revenue_growth,
        total_return_5y=listing.total_return_5y,
        total_return_1y=listing.total_return_1y,
        source_ids=list(listing.source_ids), as_of=listing.as_of,
        note=listing.note)
