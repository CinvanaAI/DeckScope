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
    default_model = "gpt-5.2"
    default_base = "https://api.openai.com/v1"
    key_env = "OPENAI_API_KEY"
    key_required = True
    #: Only IDs with a first-party model page, and deliberately few.
    #:
    #: This list has now been wrong twice in a row, in both possible directions.
    #: First it kept recommending models the provider had retired. Then, fixing
    #: that, it offered `gpt-5.2-mini` and `gpt-5.2-nano` — names produced by
    #: pattern-matching on `gpt-5.2` rather than read from the docs, where the
    #: small variants are `gpt-5-mini` and `gpt-5-nano`. Two of the three models
    #: the setup wizard offered did not exist, and a retired-model message
    #: helpfully redirected users to one of them.
    #:
    #: The lesson is not "try harder to keep the list current". A hard-coded
    #: catalogue is a maintenance promise nobody keeps, so this one is short,
    #: conservative, and no longer the primary answer: `available_models()` asks
    #: the provider what it actually serves, and `deckscope models --check`
    #: probes before recommending.
    catalog = [
        ("gpt-5.2", "Strong general analysis — recommended"),
        ("gpt-5-mini", "Faster and cheaper"),
        ("gpt-5-nano", "Cheapest, for high-volume work"),
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
        "o4-mini": "gpt-5-mini",       # retired February 2026
        "o3-mini": "gpt-5-mini",
        "o1-mini": "gpt-5-mini",
        "o1-preview": "gpt-5.2",
        "gpt-4.5-preview": "gpt-5.2",  # retired June 2026
        "gpt-4-vision-preview": "gpt-5.2",
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

    def available_models(self) -> Optional[list]:
        """What this endpoint actually serves, asked rather than assumed.

        Every OpenAI-shaped API exposes `GET /v1/models`, so the shipped
        catalogue can stop being the source of truth for anything that has a
        key configured. Returns None when it cannot be determined — no key, no
        network, or an endpoint that does not implement the route — because
        "could not ask" and "serves nothing" are different answers and the
        caller must not confuse them.
        """
        if not self.api_key and self.key_required:
            return None
        try:
            from ._http import get_json

            data = get_json(f"{self.base_url}/models",
                            {"Authorization": f"Bearer {self.api_key}"}
                            if self.api_key else {},
                            timeout=min(self.config.timeout, 20))
        except Exception:  # noqa: BLE001 - an unavailable listing is not an error
            return None
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return None
        return sorted({str(r.get("id")) for r in rows
                       if isinstance(r, dict) and r.get("id")})

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
    default_model = "anthropic/claude-sonnet-5"
    default_base = "https://openrouter.ai/api/v1"
    key_env = "OPENROUTER_API_KEY"
    key_required = True
    catalog = [
        ("anthropic/claude-sonnet-5", "Claude via OpenRouter"),
        ("openai/gpt-5.2", "GPT-5.2 via OpenRouter"),
        ("google/gemini-flash-latest", "Fast and cheap"),
    ]
    catalog_url = "https://openrouter.ai/models"
    retired_models: Dict[str, str] = {}


class GroqProvider(OpenAIProvider):
    name = "groq"
    #: Groq shut down `llama-3.1-8b-instant` and `llama-3.3-70b-versatile` for
    #: free and developer tiers on 16 August 2026, and recommended GPT-OSS or
    #: Qwen as the replacements. `llama-3.3-70b-versatile` was this backend's
    #: only catalogue entry *and* its default, so a new user following the setup
    #: wizard was pointed at a model that no longer answers.
    default_model = "openai/gpt-oss-120b"
    default_base = "https://api.groq.com/openai/v1"
    key_env = "GROQ_API_KEY"
    key_required = True
    catalog = [
        ("openai/gpt-oss-120b", "Very fast open model — recommended"),
        ("qwen/qwen3.6-27b", "Smaller and cheaper"),
    ]
    catalog_url = "https://console.groq.com/docs/models"
    retired_models = {
        "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
        "llama-3.1-8b-instant": "qwen/qwen3.6-27b",
    }


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
