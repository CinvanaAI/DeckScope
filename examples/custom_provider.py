"""A complete custom AI backend.

Implement one method and DeckScope can drive any model. Run this file directly to
see it work:

    python examples/custom_provider.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope import register_provider
from deckscope.providers.base import Completion, LLMProvider, Message, ProviderError


class EchoProvider(LLMProvider):
    """A toy backend that returns canned JSON.

    Replace `complete()` with a call to whatever service you use. Everything else —
    JSON repair, retries, health checks, caching, the panel — comes for free.
    """

    name = "echo"
    default_model = "echo-1"

    #: Shown by `deckscope providers` and offered in the setup wizard.
    catalog = [("echo-1", "A toy backend that returns canned answers")]

    def __init__(self, config=None) -> None:
        super().__init__(config)
        # Real backends set up a client here and fail loudly if they can't:
        #
        #   key = os.getenv(self.config.api_key_env or "ECHO_API_KEY")
        #   if not key:
        #       raise ProviderError("Set ECHO_API_KEY, or run `deckscope setup`.")
        #   self.client = EchoClient(key, timeout=self.config.timeout)
        self.calls = 0

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        """The only method you must implement.

        Return the model's text. Raise ProviderError with an actionable message on
        failure — the wizard and `deckscope doctor` surface it verbatim.
        """
        self.calls += 1
        try:
            text = json.dumps({
                "note": "replace this with a real API call",
                "system_chars": len(system),
                "turns": len(messages),
                "max_tokens": max_tokens or self.config.max_tokens,
            })
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"echo backend failed: {exc}") from None

        return Completion(text=text, model=self.model,
                          usage={"input": 0, "output": 0})

    # Optional. Implement this and set supports_native_search = True if your backend
    # can search the web itself; then `research: provider_native` works.
    #
    # def native_search(self, query, max_results=8):
    #     return [{"title": ..., "url": ..., "snippet": ...}]

    # Optional. Override if you hold sockets or subprocesses.
    # def close(self):
    #     self.client.close()


register_provider(EchoProvider)


if __name__ == "__main__":
    from deckscope.config import ProviderConfig
    from deckscope.providers.registry import get_provider, list_providers

    print("registered backends:", ", ".join(list_providers()))

    provider = get_provider(ProviderConfig(name="echo"))
    print("health check:", provider.health_check())

    out = provider.complete("You are a test.", [Message("user", "hello")])
    print("completion:", out.text)

    # complete_json() comes from the base class, including JSON self-repair.
    print("json:", provider.complete_json("You are a test.", "return some json"))

    print("\nTo use it in a real run:")
    print("  import examples.custom_provider        # registers it")
    print("  analyze('deck.pdf', provider='echo')")
