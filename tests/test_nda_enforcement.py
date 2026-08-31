"""NDA mode must be structurally true — pinned at every hole audit five found.

The fifth external audit's stop-ship finding: the guard was constructed
AFTER the full deck had been sent to the extraction model; deck-derived
search queries went to web search services unguarded; hosted subscription
CLIs counted as "local"; and the endpoint locality check was a substring
regex that localhost.evil.com sailed through. Each hole gets its own pin,
plus the property that matters: with --nda and a hosted model, ZERO
outbound calls happen — the run refuses before the deck is even read.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.config import ProviderConfig
from deckscope.tiering import NDAGuard, is_local


# ------------------------------------------------------------- locality

def test_hostname_lookalikes_are_not_local():
    """The audit's exact spoof set. Substring matching is how
    localhost.evil.com became 'the user's machine'."""
    for base in ("https://localhost.evil.com/v1",
                 "https://127.0.0.1.evil.com/v1",
                 "https://10.example.com/v1",
                 "https://192.168.evil.com/v1"):
        assert not is_local(ProviderConfig(name="openai_compatible",
                                           base_url=base)), base


def test_only_parsed_loopback_counts_as_this_machine():
    for base, want in (("http://localhost:11434/v1", True),
                       ("http://127.0.0.1:11434/v1", True),
                       ("http://[::1]:11434/v1", True),
                       ("http://192.168.1.20:11434/v1", False),
                       ("http://10.0.0.5:11434/v1", False)):
        got = is_local(ProviderConfig(name="openai_compatible",
                                      base_url=base))
        assert got == want, (base, "traffic to a LAN box has left the "
                                   "machine; the promise says nothing does")


def test_hosted_subscription_clis_are_not_local():
    """Sandboxing removes tools; it does not move the model on-device."""
    for preset in ("claude", "codex", "gemini"):
        assert not is_local(ProviderConfig(name="cli",
                                           extra={"preset": preset})), preset
    assert is_local(ProviderConfig(name="cli", extra={"preset": "ollama"}))


def test_a_cli_provider_with_no_preset_is_not_local():
    assert not is_local(ProviderConfig(name="cli"))


# ------------------------------------------- fail-closed, zero outbound

class _SpyProvider:
    """Any call at all is the failure being tested for."""

    name = "anthropic"

    def __init__(self):
        self.calls = 0

    def complete(self, *a, **kw):
        self.calls += 1
        raise AssertionError("an outbound model call happened under --nda "
                             "with a hosted provider")

    complete_json = complete


def test_nda_with_a_hosted_model_refuses_before_the_deck_is_read(tmp_path,
                                                                 monkeypatch):
    """The audit's control-flow finding: extraction used to fire before the
    guard existed. Now the run exits 4 with nothing read and nothing sent."""
    import deckscope.cli as cli

    deck = tmp_path / "secret.md"
    deck.write_text("--- Slide 1 ---\nUltraSecret Corp\nour ARR is $9M",
                    encoding="utf-8")
    spy = _SpyProvider()
    loaded = {"n": 0}

    def _no_load(path):
        loaded["n"] += 1
        raise AssertionError("the deck was read before the NDA refusal")

    monkeypatch.setattr("deckscope.providers.registry.get_provider",
                    lambda cfg: spy)
    monkeypatch.setattr("deckscope.ingest.load_deck", _no_load)
    monkeypatch.setenv("DECKSCOPE_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-real")
    code = cli.main(["research", str(deck), "--nda", "--quiet"])
    assert code == 4, f"expected the NDA refusal exit, got {code}"
    assert spy.calls == 0, "zero outbound calls is the whole promise"
    assert loaded["n"] == 0


def test_the_engine_disables_web_research_under_nda():
    """Library callers get the same gate as the CLI: deck-derived queries
    must not reach a search backend."""
    import inspect

    from deckscope.research import engine

    src = inspect.getsource(engine.run_research)
    assert "NoResearcher" in src
    assert "guard.enabled" in src


def test_the_guard_still_refuses_tainted_payloads_to_hosted_providers():
    guard = NDAGuard(enabled=True)
    try:
        guard.check(ProviderConfig(name="openai"), "deck text",
                    tainted=True, where="test")
    except Exception as exc:
        assert "refusing to send deck content" in str(exc)
    else:
        raise AssertionError("a tainted payload to a hosted provider must "
                             "raise")
