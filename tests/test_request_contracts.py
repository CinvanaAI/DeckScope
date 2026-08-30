"""Pin what each HTTP integration actually SENDS, not just what it parses.

The Economic Census bug's shape, generalized: every existing test of an
external integration stubbed the transport and asserted on the parsed reply,
so a request built against the wrong contract — wrong variable name, wrong
auth header, wrong endpoint — passed forever and failed only live. These
tests capture the request at the transport seam and assert the parts each
vendor's documented contract fixes: the endpoint, where the credential goes
(header vs body, and under which name), and the parameter names the service
keys on. A refactor that moves any of those now fails here instead of in a
user's first live run.

The four search backends had ZERO tests of any kind before this file — four
keyed integrations relying entirely on being read carefully.
"""
from __future__ import annotations

from typing import Any, Dict

from deckscope.providers.base import Message

from deckscope.config import ResearchConfig


class _Capture:
    """Stands in for _http.post_json/get_json and records the request."""

    def __init__(self, reply: Dict[str, Any]):
        self.reply = reply
        self.url = self.payload = self.headers = None

    def post(self, url, payload, headers, timeout=180):
        self.url, self.payload, self.headers = url, payload, headers
        return self.reply

    def get(self, url, headers=None, timeout=60):
        self.url, self.headers = url, headers
        return self.reply


def _config(**extra) -> ResearchConfig:
    return ResearchConfig(extra={"api_key": "test-key", **extra})


# ------------------------------------------------------- search backends

def test_tavily_request_matches_its_documented_contract(monkeypatch):
    """Tavily: POST /search, key in the JSON body as api_key, query/
    max_results/search_depth in the body."""
    import deckscope.research.web_backends as wb

    cap = _Capture({"results": [{"title": "t", "url": "u", "content": "c"}]})
    monkeypatch.setattr(wb, "post_json", cap.post)
    out = wb.TavilyResearcher(_config()).search("hearing aids", max_results=3)
    assert cap.url == "https://api.tavily.com/search"
    assert cap.payload["api_key"] == "test-key", (
        "Tavily authenticates in the body — moving the key would 401 live "
        "while every parse-side test stayed green")
    assert cap.payload["query"] == "hearing aids"
    assert cap.payload["max_results"] == 3
    assert out and out[0].url == "u"


def test_serper_request_matches_its_documented_contract(monkeypatch):
    """Serper: POST google.serper.dev/search, key in X-API-KEY header,
    body keys q and num."""
    import deckscope.research.web_backends as wb

    cap = _Capture({"organic": [{"title": "t", "link": "u", "snippet": "s"}]})
    monkeypatch.setattr(wb, "post_json", cap.post)
    out = wb.SerperResearcher(_config()).search("tam", max_results=5)
    assert cap.url == "https://google.serper.dev/search"
    assert cap.headers.get("X-API-KEY") == "test-key"
    assert "api_key" not in cap.payload, "Serper keys go in the header only"
    assert cap.payload == {"q": "tam", "num": 5}
    assert out and out[0].url == "u"


def test_brave_request_matches_its_documented_contract(monkeypatch):
    """Brave: GET with q/count in the query string, key in
    X-Subscription-Token."""
    import deckscope.research.web_backends as wb

    cap = _Capture({"web": {"results": [
        {"title": "t", "url": "u", "description": "d"}]}})
    monkeypatch.setattr(wb, "get_json", cap.get)
    out = wb.BraveResearcher(_config()).search("market size", max_results=4)
    assert cap.url.startswith("https://api.search.brave.com/res/v1/web/search?")
    assert "q=market+size" in cap.url and "count=4" in cap.url
    assert cap.headers.get("X-Subscription-Token") == "test-key"
    assert "test-key" not in cap.url, (
        "the credential must never ride in the URL — it would land in "
        "server logs and referrer headers")
    assert out and out[0].url == "u"


def test_exa_request_matches_its_documented_contract(monkeypatch):
    """Exa: POST /search, key in x-api-key header, numResults (camelCase —
    the exact kind of detail a rename silently breaks)."""
    import deckscope.research.web_backends as wb

    cap = _Capture({"results": [{"title": "t", "url": "u", "text": "x"}]})
    monkeypatch.setattr(wb, "post_json", cap.post)
    out = wb.ExaResearcher(_config()).search("competitors", max_results=6)
    assert cap.url == "https://api.exa.ai/search"
    assert cap.headers.get("x-api-key") == "test-key"
    assert cap.payload["numResults"] == 6, (
        "Exa's contract is camelCase numResults; num_results would be "
        "ignored and the service would default — a silently wrong request")
    assert out and out[0].url == "u"


def test_no_search_backend_leaks_its_key_into_the_url(monkeypatch):
    """Cross-cutting: whatever else changes, credentials stay out of URLs."""
    import deckscope.research.web_backends as wb

    for cls, reply in ((wb.TavilyResearcher, {"results": []}),
                       (wb.SerperResearcher, {"organic": []}),
                       (wb.BraveResearcher, {"web": {"results": []}}),
                       (wb.ExaResearcher, {"results": []})):
        cap = _Capture(reply)
        monkeypatch.setattr(wb, "post_json", cap.post)
        monkeypatch.setattr(wb, "get_json", cap.get)
        cls(_config()).search("q")
        assert "test-key" not in (cap.url or ""), cls.name


# ------------------------------------------------------ provider adapters

def test_anthropic_request_carries_the_documented_auth_headers(monkeypatch):
    """Anthropic: x-api-key + anthropic-version headers on /v1/messages.
    An SDK-style Authorization: Bearer would 401 live."""
    import deckscope.providers.anthropic_provider as ap
    from deckscope.config import ProviderConfig

    cap = _Capture({"content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "stop_reason": "end_turn"})
    monkeypatch.setattr(ap, "post_json", cap.post)
    provider = ap.AnthropicProvider(
        ProviderConfig(name="anthropic", model="claude-sonnet-5",
                       extra={"api_key": "test-key"}))
    provider.complete("sys", [Message("user", "hi")])
    assert cap.url == "https://api.anthropic.com/v1/messages"
    assert cap.headers.get("x-api-key") == "test-key"
    assert cap.headers.get("anthropic-version"), (
        "the version header is mandatory on the Messages API — dropping "
        "it is a live 400 that no parse-side test would see")
    assert "Authorization" not in cap.headers
    assert cap.payload["model"] == "claude-sonnet-5"
    assert cap.payload["messages"][0]["role"] == "user"


def test_openai_request_carries_the_documented_auth_headers(monkeypatch):
    """OpenAI-compatible: Authorization: Bearer on /chat/completions."""
    import deckscope.providers.openai_provider as op
    from deckscope.config import ProviderConfig

    cap = _Capture({"choices": [{"message": {"content": "ok"},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    monkeypatch.setattr(op, "post_json", cap.post)
    provider = op.OpenAIProvider(
        ProviderConfig(name="openai", model="gpt-test",
                       extra={"api_key": "test-key"}))
    provider.complete("sys", [Message("user", "hi")])
    assert cap.url.endswith("/chat/completions")
    assert cap.headers.get("Authorization") == "Bearer test-key"
    assert "x-api-key" not in cap.headers
    assert cap.payload["model"] == "gpt-test"
