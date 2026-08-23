"""Market-data backend registry, mirroring the provider and research registries."""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Type

from .base import MarketDataProvider

_REGISTRY: Dict[str, Type[MarketDataProvider]] = {}
_BOOTSTRAPPED = False
_LOCK = threading.RLock()


def register_market_data(cls: Type[MarketDataProvider],
                         name: Optional[str] = None) -> Type[MarketDataProvider]:
    _bootstrap()
    key = (name or getattr(cls, "name", "")).strip().lower()
    if not key:
        raise ValueError("Market-data class needs a `name` attribute.")
    with _LOCK:
        _REGISTRY[key] = cls
    return cls


def _bootstrap() -> None:
    global _BOOTSTRAPPED
    with _LOCK:
        if _BOOTSTRAPPED:
            return
        _BOOTSTRAPPED = True
        _do_bootstrap()


def _do_bootstrap() -> None:
    from .search_backend import SearchMarketData
    from .none_backend import NoMarketData

    register_market_data(SearchMarketData)
    register_market_data(NoMarketData)


def list_market_data() -> List[str]:
    _bootstrap()
    return sorted(_REGISTRY)


def get_market_data(name: str = "auto", *, config: Any = None,
                    researcher: Any = None, provider: Any = None
                    ) -> MarketDataProvider:
    """Build a backend. `auto` uses search when research is available, else none."""
    _bootstrap()
    key = (name or "auto").strip().lower()
    if key == "auto":
        key = "search" if (researcher is not None
                           and getattr(researcher, "name", "none") != "none") else "none"
    if key not in _REGISTRY:
        raise ValueError(f"Unknown market-data backend {name!r}. "
                         f"Available: {', '.join(list_market_data())}, auto")
    return _REGISTRY[key](config=config, researcher=researcher, provider=provider)
