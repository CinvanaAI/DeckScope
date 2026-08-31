"""Research backend registry, with an `auto` mode that picks whatever is available."""
from __future__ import annotations

import threading
import os
from typing import Dict, List, Optional, Type

from ..config import ResearchConfig
from .base import Researcher

_REGISTRY: Dict[str, Type[Researcher]] = {}
_BOOTSTRAPPED = False
#: The panel runs backends in parallel threads; registration must be atomic.
_LOCK = threading.RLock()


def register_researcher(cls: Type[Researcher], name: Optional[str] = None) -> Type[Researcher]:
    # Load the built-ins first, so registering a custom backend early never
    # shadows them.
    _bootstrap()
    key = (name or getattr(cls, "name", "")).strip().lower()
    if not key:
        raise ValueError("Researcher class needs a `name` attribute.")
    with _LOCK:
        _REGISTRY[key] = cls
    return cls


def _bootstrap() -> None:
    global _BOOTSTRAPPED
    with _LOCK:
        if _BOOTSTRAPPED:
            return
        # Set the flag first: _do_bootstrap registers through register_*, which
        # calls back into here. The lock is reentrant, so only the flag stops it.
        _BOOTSTRAPPED = True
        _do_bootstrap()


def _do_bootstrap() -> None:
    from .web_backends import (BraveResearcher, ExaResearcher, MCPResearcher,
                               NoResearcher, ProviderNativeResearcher,
                               SerperResearcher, TavilyResearcher)

    for cls in (TavilyResearcher, SerperResearcher, BraveResearcher, ExaResearcher,
                ProviderNativeResearcher, MCPResearcher, NoResearcher):
        register_researcher(cls)


def list_researchers() -> List[str]:
    _bootstrap()
    return sorted(_REGISTRY)


def researcher_class(name: str) -> Type[Researcher]:
    _bootstrap()
    key = (name or "").strip().lower()
    if key not in _REGISTRY:
        # Verified connector plugins are the fallback namespace: a backend
        # the operator installed and the conformance harness approved. The
        # loader refuses anything unverified or edited-since-verification,
        # so an unknown name either resolves to approved code or fails
        # with the exact remedy.
        from ..plugins import PluginError, load_researcher_class

        try:
            cls = load_researcher_class(key)
        except PluginError as exc:
            raise ValueError(str(exc)) from exc
        if cls is not None:
            register_researcher(cls, name=key)
            return _REGISTRY[key]
        raise ValueError(f"Unknown research backend {name!r}. "
                         f"Available: {', '.join(list_researchers())}, auto "
                         f"— or a verified plugin name (deckscope plugins "
                         f"list)")
    return _REGISTRY[key]


#: Tried in order when research.name == "auto".
AUTO_ORDER = ["tavily", "serper", "brave", "exa"]


def get_researcher(config: ResearchConfig, provider=None) -> Researcher:
    """Build the configured backend. `auto` falls back gracefully to `none`."""
    _bootstrap()
    name = (config.name or "auto").lower()

    if name == "auto":
        for candidate in AUTO_ORDER:
            cls = _REGISTRY[candidate]
            if os.getenv(cls.key_env):
                cfg = ResearchConfig(**{**config.__dict__, "name": candidate})
                try:
                    return cls(cfg)
                except Exception:  # noqa: BLE001
                    continue
        if provider is not None and getattr(provider, "supports_native_search", False):
            from .web_backends import ProviderNativeResearcher
            return ProviderNativeResearcher(
                ResearchConfig(**{**config.__dict__, "name": "provider_native"}), provider)
        from .web_backends import NoResearcher
        return NoResearcher(ResearchConfig(**{**config.__dict__, "name": "none"}))

    cls = researcher_class(name)
    if name == "provider_native":
        return cls(config, provider)  # type: ignore[call-arg]
    return cls(config)
