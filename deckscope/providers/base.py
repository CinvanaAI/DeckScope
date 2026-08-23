"""The one interface every model backend implements."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..config import ProviderConfig


class ProviderError(RuntimeError):
    """Raised when a backend cannot be reached or refuses the request."""


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class Completion:
    text: str
    raw: Any = None
    usage: Optional[Dict[str, int]] = None
    model: Optional[str] = None


class LLMProvider(ABC):
    """Implement two methods and DeckScope can drive any model.

    Subclass this to add a backend that ships with no adapter:

        from deckscope import register_provider
        from deckscope.providers.base import LLMProvider, Completion

        class MyProvider(LLMProvider):
            name = "my_backend"
            def complete(self, system, messages, **kw):
                return Completion(text=my_client.chat(system, messages))

        register_provider(MyProvider)
    """

    name: str = "base"
    default_model: str = ""
    supports_native_search: bool = False
    supports_vision: bool = False

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        self.config = config or ProviderConfig(name=self.name)
        self.model = self.config.model or self.default_model

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: List[Message],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Completion:
        """Single-turn completion. Must raise ProviderError on failure."""

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        retries: int = 2,
        on_usage: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Completion that must parse as a JSON object, with self-repair.

        `on_usage` receives every Completion, including the ones consumed by a
        JSON-repair retry. Those retries cost real tokens; an earlier version
        discarded the Completion here and reported usage as zero, which made the
        cost figures in a panel report meaningless.
        """
        messages = [Message("user", user)]
        last_text = ""
        for attempt in range(retries + 1):
            out = self.complete(
                system, messages, max_tokens=max_tokens, temperature=temperature
            )
            if on_usage is not None:
                on_usage(out)
            last_text = out.text
            parsed = extract_json(out.text)
            if parsed is not None:
                return parsed
            messages = [
                Message("user", user),
                Message("assistant", out.text[:4000]),
                Message(
                    "user",
                    "That was not parseable JSON. Return the same content as ONE valid "
                    "JSON object, no fence, no commentary.",
                ),
            ]
        raise ProviderError(
            f"{self.name} did not return parseable JSON after {retries + 1} attempts. "
            f"Last output began: {last_text[:300]!r}"
        )

    def health_check(self) -> Dict[str, Any]:
        """Cheap round-trip used by `deckscope doctor` and the setup wizard."""
        try:
            out = self.complete(
                "Reply with the single word: ok",
                [Message("user", "ping")],
                max_tokens=16,
                temperature=0,
            )
            return {"ok": True, "provider": self.name, "model": self.model,
                    "reply": out.text.strip()[:40]}
        except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
            return {"ok": False, "provider": self.name, "model": self.model,
                    "error": str(exc)}

    def close(self) -> None:
        """Release sockets/subprocesses. Safe to call twice."""


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON object recovery from a model's reply."""
    if not text:
        return None
    candidates: List[str] = []
    stripped = text.strip()
    candidates.append(stripped)
    for m in _FENCE.finditer(text):
        candidates.append(m.group(1).strip())
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    for cand in candidates:
        for attempt in (cand, _repair(cand)):
            try:
                obj = json.loads(attempt)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                return obj
            if isinstance(obj, list):
                return {"items": obj}
    return None


def extract_json_array(text: str) -> Optional[List[Any]]:
    if not text:
        return None
    stripped = text.strip()
    for m in _FENCE.finditer(text):
        stripped = m.group(1).strip()
        break
    s, e = stripped.find("["), stripped.rfind("]")
    if s == -1 or e <= s:
        return None
    try:
        val = json.loads(stripped[s : e + 1])
        return val if isinstance(val, list) else None
    except Exception:  # noqa: BLE001
        return None


def _repair(s: str) -> str:
    """Fix the two mistakes models actually make: trailing commas, smart quotes."""
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s
