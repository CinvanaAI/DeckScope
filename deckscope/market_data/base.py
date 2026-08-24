"""Interface for looking up whether a competitor is publicly traded, and what it did.

Deliberately narrow. This answers two factual questions — is there a ticker, and
what has it actually done — and nothing else. It does not forecast, because the
module that consumes it does not forecast either.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Listing:
    """What a market-data backend can tell us about one company."""

    name: str
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    market_cap: Optional[float] = None
    revenue: Optional[float] = None
    revenue_growth: Optional[float] = None
    #: Total return as a MULTIPLE (2.4 = the holding is worth 2.4x what it was).
    total_return_1y: Optional[float] = None
    total_return_5y: Optional[float] = None
    as_of: Optional[str] = None
    #: Where each figure came from. Empty means unsourced, which the renderer says.
    source_ids: List[str] = field(default_factory=list)
    #: "api" when it came from a market-data service, "search" when it was read
    #: out of research results, so the report can weight it accordingly.
    provenance: str = "unknown"
    note: str = ""

    @property
    def is_listed(self) -> bool:
        return bool(self.ticker)

    @property
    def has_returns(self) -> bool:
        return self.total_return_5y is not None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["is_listed"] = self.is_listed
        return d


class MarketDataProvider(ABC):
    """Implement `lookup` and DeckScope can price the alternative.

        from deckscope.market_data import register_market_data
        from deckscope.market_data.base import MarketDataProvider, Listing

        class MyFeed(MarketDataProvider):
            name = "my_feed"
            def lookup(self, company, **kw):
                row = my_api.quote(company)
                return Listing(name=company, ticker=row["symbol"], ...)

        register_market_data(MyFeed)
    """

    name: str = "base"
    needs_key: bool = False
    key_env: str = ""
    signup_url: str = ""
    blurb: str = ""
    #: Backends that read numbers out of prose are less reliable than an API, and
    #: the report says which was used.
    precision: str = "approximate"

    def __init__(self, config: Any = None, researcher: Any = None,
                 provider: Any = None, policy: Any = None,
                 registry: Any = None) -> None:
        self.config = config
        self.researcher = researcher
        self.provider = provider
        #: The same screening policy the main research uses. A backend that
        #: fetches pages and hands them to a model without this is a second,
        #: quieter door into the prompt.
        self.policy = policy
        #: The run's bibliography, so sources this backend retrieves get
        #: canonical IDs and appear in the final References section.
        self.registry = registry
        #: What the screen found here, so the run's security report can include
        #: it rather than describing only the market pass.
        self.security_reports: List[Any] = []

    @abstractmethod
    def lookup(self, company: str, *, context: str = "") -> Listing:
        """Find out whether `company` is listed, and what it has done.

        Must never raise for an unknown company — return a Listing with no ticker
        and a note. "Not listed" and "could not tell" are both real answers and
        the report distinguishes them.
        """

    def lookup_many(self, companies: List[str], *, context: str = "") -> List[Listing]:
        out = []
        for c in companies:
            try:
                out.append(self.lookup(c, context=context))
            except Exception as exc:  # noqa: BLE001 - one failure is survivable
                out.append(Listing(name=c, note=f"lookup failed: {exc}",
                                   provenance=self.name))
        return out

    def health_check(self) -> Dict[str, Any]:
        try:
            listing = self.lookup("Microsoft")
            return {"ok": True, "backend": self.name,
                    "found_ticker": listing.ticker or "none"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "backend": self.name, "error": str(exc)}
