"""OpenAI and anything that speaks the OpenAI chat-completions shape."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ..config import ProviderConfig
from ._http import post_json
from .base import Completion, LLMProvider, ProviderError


class OpenAIProvider(LLMProvider):
    """OpenAI, and anything speaking its chat-completions shape.

    Subclasses declare which of their models reject sampling parameters. Several
    vendors now ship reasoning-first models where sending `temperature` at all —
    even at its default value — is an error rather than a no-op, so the request
    has to be built per model rather than uniformly.
    """

    name = "openai"
    default_model = "gpt-4o"
    default_base = "https://api.openai.com/v1"
    key_env = "OPENAI_API_KEY"
    key_required = True
    catalog = [
        ("gpt-4o", "Strong general analysis — recommended"),
        ("gpt-4o-mini", "Fast and cheap"),
        ("o4-mini", "Reasoning-heavy, slower"),
    ]
    #: Model-name prefixes that reject temperature/top_p. The reasoning families
    #: run their own sampling policy and return an error if one is supplied.
    no_sampling_prefixes: tuple = ("o1", "o3", "o4", "gpt-5")
    #: Prefixes for the reasoning families, which differ from the chat models in
    #: two ways that both produce hard 400s rather than degraded output: they
    #: count budget as `max_completion_tokens` (`max_tokens` is rejected), and
    #: they take instructions in a `developer` message rather than a `system`
    #: one. Sending the chat shape to them fails every request.
    reasoning_prefixes: tuple = ("o1", "o3", "o4", "gpt-5")
    #: Names OpenAI has withdrawn. Saying so beats a raw 404 from the API, and
    #: `o3-mini` in particular was in this catalogue and in the docs long after
    #: it stopped answering.
    retired_models = {
        "o3-mini": "o4-mini",
        "o1-mini": "o4-mini",
        "o1-preview": "o4-mini",
        "gpt-4-vision-preview": "gpt-4o",
    }
    catalog_url = "https://platform.openai.com/docs/models"

    def accepts_sampling(self) -> bool:
        model = (self.model or "").lower()
        return not any(model.startswith(p) for p in self.no_sampling_prefixes)

    def is_reasoning_model(self) -> bool:
        model = (self.model or "").lower()
        return any(model.startswith(p) for p in self.reasoning_prefixes)

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        env = self.config.api_key_env or self.key_env
        self.api_key = os.getenv(env) or self.config.extra.get("api_key")
        if self.key_required and not self.api_key:
            raise ProviderError(
                f"No API key found for {self.name}. Set {env}, or run `deckscope setup`."
            )
        self.base_url = (self.config.base_url or self.default_base).rstrip("/")
        retired = getattr(self, "retired_models", {})
        if self.model in retired:
            raise ProviderError(
                f"{self.name}: '{self.model}' has been retired by the provider and no "
                f"longer answers. Use '{retired[self.model]}' instead, or pick a current "
                f"model from {getattr(self, 'catalog_url', 'the provider docs')}.")

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        reasoning = self.is_reasoning_model()
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "developer" if reasoning else "system",
                          "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        }
        # The reasoning models bill hidden reasoning tokens against the same
        # budget and expose it under a different name; `max_tokens` is not
        # accepted and the request 400s.
        budget = max_tokens or self.config.max_tokens
        payload["max_completion_tokens" if reasoning else "max_tokens"] = budget
        # Sending temperature to a model that rejects it fails the request
        # outright — omitting the field is the supported way to get default
        # behaviour, not passing the default value.
        if self.accepts_sampling():
            payload["temperature"] = (self.config.temperature
                                      if temperature is None else temperature)
        if tools:
            payload["tools"] = tools
        payload.update(self.config.extra.get("body", {}))
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        headers.update(self.config.extra.get("headers", {}))
        try:
            data = post_json(f"{self.base_url}/chat/completions", payload, headers,
                             timeout=self.config.timeout)
        except RuntimeError as exc:
            raise ProviderError(str(exc)) from None
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderError(f"Unexpected response shape from {self.name}: "
                                f"{str(data)[:300]}") from None
        u = data.get("usage", {}) or {}
        return Completion(text=text, raw=data, model=data.get("model"),
                          usage={"input": u.get("prompt_tokens", 0),
                                 "output": u.get("completion_tokens", 0)})


class OpenAICompatibleProvider(OpenAIProvider):
    """Ollama, LM Studio, vLLM, OpenRouter, Together, Groq, Azure-style gateways.

    Point `base_url` at the server; set `api_key_env` if it wants a key.
    """

    name = "openai_compatible"
    default_model = "llama3.1:8b"
    default_base = "http://localhost:11434/v1"
    key_env = "OPENAI_COMPATIBLE_API_KEY"
    key_required = False
    catalog = [
        ("llama3.1:8b", "Local via Ollama — free, needs a decent machine"),
        ("qwen2.5:14b", "Local, stronger reasoning"),
    ]


class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"
    default_model = "anthropic/claude-sonnet-4.5"
    default_base = "https://openrouter.ai/api/v1"
    key_env = "OPENROUTER_API_KEY"
    key_required = True
    catalog = [
        ("anthropic/claude-sonnet-4.5", "Claude via OpenRouter"),
        ("openai/gpt-4o", "GPT-4o via OpenRouter"),
        ("google/gemini-2.0-flash-001", "Fast and cheap"),
    ]


class GroqProvider(OpenAIProvider):
    name = "groq"
    default_model = "llama-3.3-70b-versatile"
    default_base = "https://api.groq.com/openai/v1"
    key_env = "GROQ_API_KEY"
    key_required = True
    catalog = [("llama-3.3-70b-versatile", "Very fast open model")]


class GeminiProvider(OpenAIProvider):
    """Google Gemini through its OpenAI-compatible endpoint."""

    name = "gemini"
    #: gemini-2.0-flash was the default here until it reached its shutdown date,
    #: at which point DeckScope's out-of-the-box Gemini configuration stopped
    #: working. Google retires model IDs on a published schedule, so treat any
    #: name in this file as perishable and check `catalog_url` when one fails.
    default_model = "gemini-flash-latest"
    default_base = "https://generativelanguage.googleapis.com/v1beta/openai"
    key_env = "GEMINI_API_KEY"
    key_required = True
    catalog = [
        ("gemini-flash-latest", "Fast and cheap, always the current Flash — recommended"),
        ("gemini-pro-latest", "Deeper analysis, always the current Pro"),
        ("gemini-2.5-flash", "Pinned version, if you need reproducibility"),
    ]
    catalog_url = "https://ai.google.dev/gemini-api/docs/models"
    #: Google's current generation does not accept sampling controls, and the
    #: `-latest` aliases track that generation — so the default configuration
    #: would have failed on its first call while sending temperature.
    no_sampling_prefixes = ("gemini-flash-latest", "gemini-pro-latest",
                            "gemini-3", "gemini-4")

    #: Names Google has retired. Naming them beats a raw 404 from the API.
    retired_models = {
        "gemini-2.0-flash": "gemini-flash-latest",
        "gemini-2.0-flash-001": "gemini-flash-latest",
        "gemini-1.5-flash": "gemini-flash-latest",
        "gemini-1.5-pro": "gemini-pro-latest",
    }
