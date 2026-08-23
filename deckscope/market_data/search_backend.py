"""Read listing facts out of ordinary research results.

Needs no new API key: it reuses whichever research backend is already configured,
and asks the model to extract the figures — with the same rule as everywhere else,
that a number not present in the material must come back as null rather than as a
guess.

Less precise than a market-data API, and says so: every Listing it produces is
marked `provenance="search"` and `precision="approximate"`, and the report carries
that through so a reader knows whether a market cap was quoted from a filing or
lifted from a news sentence.
"""
from __future__ import annotations

from typing import Any, Optional

from ..security.sanitizer import fence
from .base import Listing, MarketDataProvider

EXTRACT_SYSTEM = """You extract listing facts about a company from research material.

Return ONE JSON object and nothing else:

{"listed": true|false|null,
 "ticker": "MSFT"|null,
 "exchange": "NASDAQ"|null,
 "market_cap_usd": number|null,
 "revenue_usd": number|null,
 "revenue_growth_pct": number|null,
 "total_return_5y_multiple": number|null,
 "total_return_1y_multiple": number|null,
 "as_of": "2026-08"|null,
 "note": "anything a reader should know, including what was missing"}

Rules that matter more than completeness:
- A figure not present in the material is null. Never estimate, never recall from
  memory, never infer a market cap from a valuation mentioned in passing.
- `total_return_5y_multiple` is a MULTIPLE, not a percentage: a holding worth 2.4x
  what it was five years ago is 2.4. If the material gives a percentage, convert
  it. If it gives a share price without a comparison point, that is null.
- `listed: false` means you found positive evidence it is private. If you simply
  found nothing, that is null, and say so in the note. Those are different answers
  and the report treats them differently.
- Subsidiaries: report the PARENT's ticker and say so in the note. A product line
  is not separately investable."""


class SearchMarketData(MarketDataProvider):
    """Extract listing facts from the configured research backend's results."""

    name = "search"
    needs_key = False
    precision = "approximate"
    blurb = ("Reads listing facts out of ordinary web research. No extra key, "
             "less precise than a market-data API.")

    def lookup(self, company: str, *, context: str = "") -> Listing:
        listing = Listing(name=company, provenance="search")
        if not self.researcher or not self.provider:
            listing.note = "no research backend configured, so nothing could be checked"
            return listing

        queries = [
            f"{company} stock ticker symbol exchange",
            f"{company} market cap revenue latest quarter",
            f"{company} stock price 5 year total return performance",
        ]
        try:
            results = self.researcher.search_many(queries, max_results=4)
        except Exception as exc:  # noqa: BLE001
            listing.note = f"research failed: {exc}"
            return listing
        if not results:
            listing.note = "no research results returned for this company"
            return listing

        material = "\n\n".join(
            f"[{i}] {r.title}\n    {r.url}\n    {(r.snippet or '')[:1200]}"
            for i, r in enumerate(results[:12], 1))

        try:
            data = self.provider.complete_json(
                EXTRACT_SYSTEM,
                f"Company: {company}\n"
                + (f"Context: {context}\n" if context else "")
                + "\n" + fence(material, "RESEARCH MATERIAL"),
                temperature=0)
        except Exception as exc:  # noqa: BLE001
            listing.note = f"extraction failed: {exc}"
            return listing

        listing.ticker = _clean_ticker(data.get("ticker"))
        listing.exchange = data.get("exchange") or None
        listing.market_cap = _num(data.get("market_cap_usd"))
        listing.revenue = _num(data.get("revenue_usd"))
        growth = _num(data.get("revenue_growth_pct"))
        listing.revenue_growth = growth / 100.0 if growth is not None else None
        listing.total_return_5y = _multiple(data.get("total_return_5y_multiple"))
        listing.total_return_1y = _multiple(data.get("total_return_1y_multiple"))
        listing.as_of = data.get("as_of") or None
        listing.note = str(data.get("note") or "")

        if listing.ticker is None and data.get("listed") is False:
            listing.note = (listing.note
                            or "appears to be privately held — not investable directly")
        elif listing.ticker is None:
            listing.note = (listing.note
                            or "could not determine whether this company is publicly "
                               "traded from the available material")
        return listing


def _clean_ticker(value: Any) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    t = value.strip().upper().replace("$", "")
    # Reject prose that slipped into the field.
    if not t or len(t) > 8 or " " in t or not t.replace(".", "").replace("-", "").isalnum():
        return None
    return t


def _num(value: Any) -> Optional[float]:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _multiple(value: Any) -> Optional[float]:
    """Reject implausible multiples rather than letting them into the arithmetic."""
    n = _num(value)
    if n is None:
        return None
    # A five-year total return outside this band is almost certainly a unit error
    # — a percentage that was not converted, or a share price.
    if not (0.01 <= n <= 100):
        return None
    return n
