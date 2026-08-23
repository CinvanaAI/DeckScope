"""No market-data lookup. Reports absence rather than guessing."""
from __future__ import annotations

from .base import Listing, MarketDataProvider


class NoMarketData(MarketDataProvider):
    name = "none"
    needs_key = False
    precision = "none"
    blurb = "Skip the listing lookup entirely."

    def lookup(self, company: str, *, context: str = "") -> Listing:
        return Listing(
            name=company, provenance="none",
            note="No market-data lookup was performed for this run, so whether this "
                 "company is publicly traded is unknown — not 'no'.")

    def health_check(self):
        return {"ok": True, "backend": self.name, "found_ticker": "n/a"}
