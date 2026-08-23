"""OpenAI and anything that speaks the OpenAI chat-completions shape."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ..config import ProviderConfig
from ._http import post_json
from .base import Completion, LLMProvider, ProviderError


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o"
    default_base = "https://api.openai.com/v1"
    key_env = "OPENAI_API_KEY"
    key_required = True
    catalog = [
        ("gpt-4o", "Strong general analysis — recommended"),
        ("gpt-4o-mini", "Fast and cheap"),
        ("o3-mini", "Reasoning-heavy, slower"),
    ]

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        env = self.config.api_key_env or self.key_env
        self.api_key = os.getenv(env) or self.config.extra.get("api_key")
        if self.key_required and not self.api_key:
            raise ProviderError(
                f"No API key found for {self.name}. Set {env}, or run `deckscope setup`."
            )
        self.base_url = (self.config.base_url or self.default_base).rstrip("/")

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": self.config.temperature if temperature is None else temperature,
        }
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
    default_model = "gemini-2.0-flash"
    default_base = "https://generativelanguage.googleapis.com/v1beta/openai"
    key_env = "GEMINI_API_KEY"
    key_required = True
    catalog = [
        ("gemini-2.0-flash", "Fast, large context — recommended"),
        ("gemini-2.5-pro", "Deeper analysis"),
    ]
