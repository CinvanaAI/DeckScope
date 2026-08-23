"""Provider registry. Adding a backend is one `register_provider()` call."""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Type

from ..config import ProviderConfig
from .base import LLMProvider, ProviderError

_REGISTRY: Dict[str, Type[LLMProvider]] = {}
_BOOTSTRAPPED = False
#: The panel runs backends in parallel threads; registration must be atomic.
_LOCK = threading.RLock()


def register_provider(cls: Type[LLMProvider], name: Optional[str] = None) -> Type[LLMProvider]:
    """Register a provider class. Usable as a decorator."""
    # Load the built-ins first, so registering a custom backend early never
    # shadows them.
    _bootstrap()
    key = (name or getattr(cls, "name", "")).strip().lower()
    if not key:
        raise ValueError("Provider class needs a `name` attribute.")
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
    from .mock_provider import MockProvider
    from .manual_provider import ManualProvider

    register_provider(MockProvider)
    register_provider(ManualProvider)

    # Optional backends: registered lazily so a missing SDK never breaks import.
    lazy = [
        ("anthropic", ".anthropic_provider", "AnthropicProvider"),
        ("openai", ".openai_provider", "OpenAIProvider"),
        ("openai_compatible", ".openai_provider", "OpenAICompatibleProvider"),
        ("openrouter", ".openai_provider", "OpenRouterProvider"),
        ("groq", ".openai_provider", "GroqProvider"),
        ("gemini", ".openai_provider", "GeminiProvider"),
        ("bedrock", ".bedrock_provider", "BedrockProvider"),
        ("mcp", ".mcp_provider", "MCPProvider"),
        ("cli", ".cli_provider", "CLIProvider"),
    ]
    import importlib

    for key, module, attr in lazy:
        try:
            mod = importlib.import_module(module, __package__)
            register_provider(getattr(mod, attr), key)
        except Exception:  # noqa: BLE001 - backend simply unavailable here
            continue


def list_providers() -> List[str]:
    _bootstrap()
    return sorted(_REGISTRY)


def provider_class(name: str) -> Type[LLMProvider]:
    _bootstrap()
    key = (name or "").strip().lower()
    if key not in _REGISTRY:
        raise ProviderError(
            f"Unknown provider {name!r}. Available: {', '.join(list_providers())}"
        )
    return _REGISTRY[key]


def get_provider(config: ProviderConfig) -> LLMProvider:
    """Instantiate the configured backend."""
    return provider_class(config.name)(config)


def catalog(name: str) -> List[Any]:
    """Model menu the setup wizard shows for a provider."""
    try:
        return list(getattr(provider_class(name), "catalog", []))
    except ProviderError:
        return []
