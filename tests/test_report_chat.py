"""The post-report chat: grounded in the run record, honest about its edges.

The feature exists because a reader's first instinct after a report is a
question — "where did that come from?", "go deeper on X". The tests pin the
three properties that make the answers worth having: provenance lookups are
deterministic (no model gets to misremember a URL), the model path is
grounded in the record and nothing else, and the web surface never ships the
multi-hundred-KB record to a polling client.
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.interrogate import (answer, briefing, load_record,
                                   provenance_shortcut, source_card)
from deckscope.providers.base import Completion, Message


def _record(sources=None):
    return {
        "deck": {"company": {"name": "Acme Flow"},
                 "market": {"tam_claimed": "$47B"},
                 "_consistency": {"conflicts": 1}},
        "market": {"sizing": {"consensus_view": "smaller than claimed"}},
        "comparisons": {"investor": {
            "headline": "TAM overstated",
            "claim_audit": [{"id": "C1", "claim": "TAM is $47B",
                             "assessment": "contradicted",
                             "source_ids": ["S1"]}]}},
        "references": {"sources": sources if sources is not None else [
            {"sid": "S1", "title": "Independent sizing composite",
             "url": "https://research.example.org/sizing",
             "retrieved": "2026-08-01",
             "snippet": "Estimates cluster at $18-24B."}]},
        "stats": {"provider": "mock", "sources_found": 1},
    }


# ------------------------------------------------ deterministic provenance

def test_provenance_questions_skip_the_model_entirely():
    """"Where is S1 from?" is a lookup. A model paraphrasing a URL wrong
    would be strictly worse than reading the bibliography."""
    rec = _record()
    for q in ("where is S1 from?", "S1", "source S1",
              "Where does S1 come from"):
        out = provenance_shortcut(rec, q)
        assert out is not None, q
        assert "https://research.example.org/sizing" in out
        assert "Estimates cluster at $18-24B." in out
        assert "may have changed since retrieval" in out


def test_a_substantive_question_goes_to_the_model():
    assert provenance_shortcut(_record(), "what does S1 say about growth "
                                          "and do you believe it?") is None


def test_an_unknown_source_id_lists_what_exists():
    out = provenance_shortcut(_record(), "where is S9 from?")
    assert "no S9" in out and "S1" in out


def test_a_sourceless_record_says_so():
    out = provenance_shortcut(_record(sources=[]), "S1")
    assert "none" in out


def test_source_card_survives_missing_fields():
    card = source_card({"references": {"sources": [{"sid": "S2"}]}}, "s2")
    assert card.startswith("S2:")


# --------------------------------------------------------- the grounding

def test_the_briefing_carries_bibliography_audit_and_arithmetic():
    text = briefing(_record())
    assert "BIBLIOGRAPHY" in text
    assert "Estimates cluster at $18-24B." in text
    assert "claim_audit" in text
    assert "_consistency" in text, (
        "the deterministic arithmetic is exactly what a reader asks about")


def test_the_briefing_respects_its_budget():
    text = briefing(_record(), budget=500)
    assert len(text) < 1200
    assert "TRUNCATED" in text


def test_a_zero_source_record_briefs_the_absence():
    assert "No external sources were retrieved" in briefing(_record(sources=[]))


class _FakeProvider:
    def __init__(self):
        self.calls = []

    def complete(self, system, messages, **kw):
        self.calls.append((system, messages))
        return Completion(text="grounded reply",
                          usage={"input_tokens": 10, "output_tokens": 5})


def test_answer_grounds_the_model_in_the_record():
    fake = _FakeProvider()
    history = [Message("user", "earlier q"), Message("assistant", "earlier a")]
    counted = {}
    out = answer(_record(), "compare the TAM claims", provider=fake,
                 history=history,
                 on_usage=lambda u: counted.update(u))
    assert out == "grounded reply"
    system, messages = fake.calls[0]
    assert "Answer FROM THE RECORD" in system
    assert "Estimates cluster at $18-24B." in system, (
        "the record must ride in the system prompt — grounding by promise "
        "alone is no grounding")
    assert [m.content for m in messages] == \
        ["earlier q", "earlier a", "compare the TAM claims"]
    assert counted.get("input_tokens") == 10


def test_answer_never_spends_a_model_call_on_a_lookup():
    fake = _FakeProvider()
    out = answer(_record(), "where is S1 from?", provider=fake)
    assert "research.example.org" in out
    assert fake.calls == [], "the shortcut must not also hit the provider"


def test_load_record_refuses_a_non_record(tmp_path):
    bogus = tmp_path / "x.json"
    bogus.write_text('{"hello": 1}', encoding="utf-8")
    try:
        load_record(bogus)
    except ValueError as exc:
        assert "run record" in str(exc)
    else:
        raise AssertionError("a random JSON must not pass as a run record")


# ------------------------------------------------------------ web surface

def test_polling_a_job_never_ships_the_record(monkeypatch):
    """The record can be hundreds of KB; the poller asks every 700ms. The
    client gets a can_ask flag, the record stays server-side for /api/ask."""
    import deckscope.webapp as webapp
    from http.server import ThreadingHTTPServer

    job_id = "testjob123"
    with webapp.JOBS_LOCK:
        webapp.JOBS[job_id] = {"id": job_id, "status": "done", "log": [],
                               "files": [], "result": {"company": "X"},
                               "error": None, "started": 1e12,
                               "record": _record(),
                               "chat_provider": {"name": "mock"}}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), webapp.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/job/{job_id}",
            headers={"X-DeckScope-Token": webapp.SESSION_TOKEN})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
        assert body["can_ask"] is True
        assert "record" not in body
        assert "chat_provider" not in body

        ask = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/ask",
            data=json.dumps({"job": job_id,
                             "question": "where is S1 from?"}).encode(),
            headers={"X-DeckScope-Token": webapp.SESSION_TOKEN,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(ask, timeout=30) as resp:
            body = json.loads(resp.read())
        assert "research.example.org" in body["answer"], (
            "the deterministic provenance path must work over HTTP too")
    finally:
        httpd.shutdown()
        with webapp.JOBS_LOCK:
            webapp.JOBS.pop(job_id, None)


def test_asking_about_an_unknown_job_is_a_polite_404(monkeypatch):
    import deckscope.webapp as webapp
    from http.server import ThreadingHTTPServer

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), webapp.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        ask = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/ask",
            data=json.dumps({"job": "nope", "question": "hi"}).encode(),
            headers={"X-DeckScope-Token": webapp.SESSION_TOKEN,
                     "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(ask, timeout=10)
            raise AssertionError("expected 404")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        httpd.shutdown()
