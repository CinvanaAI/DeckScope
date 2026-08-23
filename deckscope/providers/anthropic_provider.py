"""Anthropic — via the official SDK when installed, raw Messages API otherwise."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..config import ProviderConfig
from ._http import post_json
from .base import Completion, LLMProvider, Message, ProviderError

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-sonnet-5"
    supports_native_search = True
    supports_vision = True

    #: Models the setup wizard offers, cheapest last.
    catalog = [
        ("claude-opus-5", "Deepest analysis, slowest, priciest"),
        ("claude-sonnet-5", "Best balance — recommended"),
        ("claude-haiku-4-5-20251001", "Fast and cheap, lighter analysis"),
    ]

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        env = self.config.api_key_env or "ANTHROPIC_API_KEY"
        self.api_key = os.getenv(env) or self.config.extra.get("api_key")
        if not self.api_key:
            raise ProviderError(
                f"No Anthropic API key found. Set {env}, or run `deckscope setup`."
            )
        self.base_url = (self.config.base_url or API_URL).rstrip("/")
        if not self.base_url.endswith("/v1/messages"):
            self.base_url = self.base_url + "/v1/messages"
        self._sdk = None
        try:  # SDK path: better retries, streaming, beta headers
            import anthropic  # type: ignore

            self._sdk = anthropic.Anthropic(
                api_key=self.api_key,
                timeout=self.config.timeout,
                **({"base_url": self.config.base_url} if self.config.base_url else {}),
            )
        except Exception:  # noqa: BLE001 - HTTP fallback is fine
            self._sdk = None

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": self.config.temperature if temperature is None else temperature,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if tools:
            payload["tools"] = tools

        if self._sdk is not None:
            try:
                resp = self._sdk.messages.create(**payload)
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"Anthropic SDK call failed: {exc}") from None
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
            return Completion(
                text=text, raw=resp, model=getattr(resp, "model", self.model),
                usage={"input": resp.usage.input_tokens, "output": resp.usage.output_tokens},
            )

        try:
            data = post_json(
                self.base_url, payload,
                {"x-api-key": self.api_key, "anthropic-version": API_VERSION},
                timeout=self.config.timeout,
            )
        except RuntimeError as exc:
            raise ProviderError(str(exc)) from None
        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")
        u = data.get("usage", {})
        return Completion(text=text, raw=data, model=data.get("model"),
                          usage={"input": u.get("input_tokens", 0),
                                 "output": u.get("output_tokens", 0)})

    def native_search(self, query: str, max_results: int = 8) -> List[Dict[str, Any]]:
        """Use Anthropic's server-side web search tool as a research backend."""
        payload = {
            "model": self.model,
            "max_tokens": 4000,
            "messages": [{"role": "user", "content":
                          f"Search the web for: {query}\n\nSummarize the findings and list "
                          f"every source URL you used."}],
            "tools": [{"type": "web_search_20250305", "name": "web_search",
                       "max_uses": max(1, min(max_results, 10))}],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": API_VERSION}
        data = post_json(self.base_url, payload, headers, timeout=self.config.timeout)
        text, urls = [], []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text.append(block.get("text", ""))
            if block.get("type") == "web_search_tool_result":
                for item in block.get("content", []) or []:
                    if item.get("url"):
                        urls.append({"title": item.get("title", ""), "url": item["url"],
                                     "snippet": (item.get("page_age") or "")})
        return [{"title": f"Anthropic web search: {query}", "url": "",
                 "snippet": "\n".join(text)[:6000], "sources": urls}]
