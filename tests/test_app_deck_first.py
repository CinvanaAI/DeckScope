"""The app's deck-first pass: card order, the two checkboxes, and the shared
deck→reports engine behind them.

Each test pins a decision from the driver's-seat redesign:

- The deck card comes FIRST. The primary persona arrives holding a deck; a
  page that greets them with a market-report form is a page about the
  builder's newest feature, not the visitor's task.
- ``market_reports`` and ``opportunity`` in the /api/run payload thread into
  the same engines the CLI flags use — `dispatch_for_deck` and
  `OpportunityConfig` — so the app and the CLI cannot drift into producing
  different things under the same name.
- A refusal is returned, not swallowed. The scoper saying "I could not scope
  this" must reach the job result, because a checkbox that silently does
  nothing teaches the user the product is decorative.
"""
from __future__ import annotations

import re


# --------------------------------------------------------------------- page

def _flat_page() -> str:
    from deckscope import webapp

    return re.sub(r"\s+", " ", webapp.PAGE)


def test_deck_card_precedes_the_market_card():
    flat = _flat_page()
    assert flat.index('id="drop"') < flat.index("Report a market</h2>"), (
        "the deck-drop card must come before the market-report card: the "
        "primary persona arrives holding a deck")


def test_page_offers_both_go_deeper_checkboxes():
    flat = _flat_page()
    assert 'id="opt-reports"' in flat
    assert 'id="opt-opp"' in flat
    # and the submit JS actually sends them — a checkbox that renders but
    # never reaches the payload is UI theater
    assert "market_reports: $('#opt-reports').checked" in _raw_page()
    assert "opportunity: $('#opt-opp').checked" in _raw_page()


def _raw_page() -> str:
    from deckscope import webapp

    return webapp.PAGE


def test_page_states_where_the_deck_goes():
    assert "never leaves this machine" in _flat_page(), (
        "a guest dropping a confidential deck must be told, at the drop "
        "zone, where its bytes travel")


def test_page_teaches_the_three_marks():
    flat = _flat_page()
    assert "How to read the report" in flat
    for mark in ("source ID", "no source", "Could not be checked"):
        assert mark in flat, f"the help block must teach the {mark!r} mark"


# ------------------------------------------------------- the host boundary

def _serve():
    import threading
    from http.server import ThreadingHTTPServer

    from deckscope import webapp

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), webapp.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1], webapp.SESSION_TOKEN


def _get(port, path, host=None):
    import urllib.error
    import urllib.request

    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if host:
        req.add_header("Host", host)
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code


def test_the_token_bearing_page_requires_the_token():
    """The root page embeds the session token in its JavaScript, so serving
    it unauthenticated hands the key to whoever asks — a DNS-rebinding page
    could read it and then hold every token-gated endpoint (external audit
    finding #7). The launch URL printed at startup carries the token, so the
    legitimate user pays nothing."""
    httpd, port, tok = _serve()
    try:
        assert _get(port, "/") == 403
        assert _get(port, f"/?token={tok}") == 200
    finally:
        httpd.shutdown()


def test_a_rebound_host_is_refused():
    """DNS rebinding sends requests with the attacker's hostname in the Host
    header. Only this loopback's own names are served."""
    httpd, port, tok = _serve()
    try:
        assert _get(port, f"/?token={tok}",
                    host=f"evil.attacker.net:{port}") == 403
        assert _get(port, f"/?token={tok}", host=f"localhost:{port}") == 200
    finally:
        httpd.shutdown()


# ------------------------------------------------------------------ run job

class _FakeResult:
    company = "TestCo"
    deck = {"company": {"name": "TestCo"}}
    security = {"overall_risk": "clean"}
    registry = None
    comparisons = {}


class _FakePipeline:
    def __init__(self, cfg, on_event=None):
        self.cfg = cfg

    def run(self):
        return _FakeResult()

    def render(self, result):
        return []

    def close(self):
        pass


def _job_after(monkeypatch, payload, dispatch=None):
    """Run _run_job with the pipeline stubbed out, return the job dict."""
    from deckscope import webapp

    monkeypatch.setattr("deckscope.orchestrator.Pipeline", _FakePipeline)
    calls = []
    if dispatch is None:
        def dispatch(deck, cfg, on_event=None):  # noqa: ANN001
            calls.append(deck)
            return {"stored": ["ps_test1", "ps_test2"],
                    "lines": ["  Scoped to: test market",
                              "  stored as ps_test1"],
                    "document": None, "entries": []}
    monkeypatch.setattr("marketreport.scoping.dispatch_for_deck", dispatch)

    job_id = "t-" + payload.get("deck", "x")[:8]
    with webapp.JOBS_LOCK:
        webapp.JOBS[job_id] = {"id": job_id, "status": "running", "log": [],
                               "files": [], "result": None, "error": None,
                               "started": 0}
    try:
        webapp._run_job(job_id, payload)
        with webapp.JOBS_LOCK:
            return dict(webapp.JOBS[job_id]), calls
    finally:
        with webapp.JOBS_LOCK:
            webapp.JOBS.pop(job_id, None)


def test_market_reports_checkbox_reaches_the_shared_engine(monkeypatch, tmp_path):
    deck = tmp_path / "d.md"
    deck.write_text("# Deck", encoding="utf-8")
    job, calls = _job_after(monkeypatch, {"deck": str(deck), "demo": True,
                                          "market_reports": True})
    assert job["status"] == "done"
    assert calls, "dispatch_for_deck was never called for a checked box"
    assert job["result"]["market_reports"]["stored"] == ["ps_test1", "ps_test2"]


def test_unchecked_box_calls_nothing(monkeypatch, tmp_path):
    deck = tmp_path / "d.md"
    deck.write_text("# Deck", encoding="utf-8")
    job, calls = _job_after(monkeypatch, {"deck": str(deck), "demo": True})
    assert job["status"] == "done"
    assert not calls, "no checkbox, no research spend"
    assert job["result"]["market_reports"] == {}


def test_scoper_refusal_reaches_the_result(monkeypatch, tmp_path):
    """The refusal is the product working, and it must be visible."""
    deck = tmp_path / "d.md"
    deck.write_text("# Deck", encoding="utf-8")

    def refusing(deck_dict, cfg, on_event=None):  # noqa: ANN001
        return {"stored": [], "document": None, "entries": [],
                "lines": ["    note: the scoper could not scope this deck"]}

    job, _ = _job_after(monkeypatch, {"deck": str(deck), "demo": True,
                                      "market_reports": True},
                        dispatch=refusing)
    mr = job["result"]["market_reports"]
    assert mr["stored"] == []
    assert any("could not scope" in n for n in mr["notes"])


def test_dead_specialists_do_not_sink_the_deck_report(monkeypatch, tmp_path):
    """The deck analysis is already rendered when reports run; a scoping
    crash must degrade to a note, never to a failed job."""
    deck = tmp_path / "d.md"
    deck.write_text("# Deck", encoding="utf-8")

    def exploding(deck_dict, cfg, on_event=None):  # noqa: ANN001
        raise RuntimeError("specialist meltdown")

    job, _ = _job_after(monkeypatch, {"deck": str(deck), "demo": True,
                                      "market_reports": True},
                        dispatch=exploding)
    assert job["status"] == "done", "the deck report survived; the job must too"
    assert any("meltdown" in n for n in job["result"]["market_reports"]["notes"])


def test_opportunity_checkbox_enables_the_config(monkeypatch, tmp_path):
    """payload.opportunity → cfg.opportunity.enabled, via the same override
    key the CLI's --opportunity flag uses."""
    from deckscope import settings, webapp

    deck = tmp_path / "d.md"
    deck.write_text("# Deck", encoding="utf-8")
    seen = {}
    real = settings.settings_to_runconfig

    def spy(overrides=None):
        seen.update(overrides or {})
        return real(overrides)

    # webapp calls settings.settings_to_runconfig through the shared module
    # object, so patching the settings module is patching what webapp sees
    monkeypatch.setattr("deckscope.settings.settings_to_runconfig", spy)
    monkeypatch.setattr("deckscope.orchestrator.Pipeline", _FakePipeline)
    job_id = "t-opp"
    with webapp.JOBS_LOCK:
        webapp.JOBS[job_id] = {"id": job_id, "status": "running", "log": [],
                               "files": [], "result": None, "error": None,
                               "started": 0}
    try:
        webapp._run_job(job_id, {"deck": str(deck), "demo": True,
                                 "opportunity": True})
    finally:
        with webapp.JOBS_LOCK:
            webapp.JOBS.pop(job_id, None)
    assert seen.get("opportunity") == {"enabled": True}


def test_panel_run_says_reports_are_not_produced(monkeypatch, tmp_path):
    """A checked box on a panel run must be declined out loud, not dropped."""
    from deckscope import webapp

    class _FakePanelResult:
        company = "TestCo"
        security = {"overall_risk": "clean"}
        registry = None
        panelists = []
        consensus = {}
        metrics = {}

    class _FakePanel:
        def __init__(self, cfg, members, rounds=1, on_event=None):
            self.log = on_event

        def run(self):
            return _FakePanelResult()

        def render(self, result):
            return []

    monkeypatch.setattr("deckscope.ensemble.Panel", _FakePanel)
    monkeypatch.setattr("deckscope.ensemble.parse_panelist", lambda s: s)
    deck = tmp_path / "d.md"
    deck.write_text("# Deck", encoding="utf-8")
    job_id = "t-panel"
    with webapp.JOBS_LOCK:
        webapp.JOBS[job_id] = {"id": job_id, "status": "running", "log": [],
                               "files": [], "result": None, "error": None,
                               "started": 0}
    try:
        webapp._run_job(job_id, {"deck": str(deck), "demo": True,
                                 "market_reports": True,
                                 "panel": ["mock:a", "mock:b"]})
        with webapp.JOBS_LOCK:
            job = dict(webapp.JOBS[job_id])
    finally:
        with webapp.JOBS_LOCK:
            webapp.JOBS.pop(job_id, None)
    assert job["status"] == "done"
    assert any("not produced on panel runs" in line for line in job["log"]), (
        "the six-of-seven-arrived lesson: an ignored request must say so")


# ----------------------------------------------------------- shared engine

def _engine_cfg(tmp_path):
    class _Cfg:
        provider = type("P", (), {"name": "mock", "model": None,
                                  "temperature": 0.0})()
        research = type("R", (), {"name": "none"})()
        output = type("O", (), {"out_dir": str(tmp_path)})()
    return _Cfg()


def test_dispatch_for_deck_stores_narrates_and_reconciles(monkeypatch, tmp_path):
    """The positive path of the shared engine: briefs run, panels stored,
    ids returned, progress narrated — and the reports are read back against
    the claim that dispatched them, in a document beside the outputs."""
    from marketreport import scoping
    from marketreport.handoff import Brief

    brief = Brief(market="test market", measures=["units"],
                  specialist="market-share",
                  because="the deck claims 40% unit share")
    monkeypatch.setattr("marketreport.scoping.briefs_from_deck",
                        lambda deck, provider: ([brief], []))
    monkeypatch.setattr("marketreport.handoff.run_brief",
                        lambda b, **kw: {"panels": ["fake-panel"],
                                         "unknown": [], "failed": []})

    class _Ref:
        id = "ps_fake"

    class _FakeLibrary:
        def save_all(self, panels, market="", place="", request=""):
            return [_Ref()]

    monkeypatch.setattr("marketreport.library.Library", _FakeLibrary)

    out = scoping.dispatch_for_deck({}, _engine_cfg(tmp_path))
    assert out["stored"] == ["ps_fake"]
    assert any("stored as ps_fake" in ln for ln in out["lines"])
    assert any("producing market-share" in ln for ln in out["lines"])
    # The loop is closed: the claim travels into the reconciliation.
    assert out["entries"] and out["entries"][0]["claim"] == \
        "the deck claims 40% unit share"
    assert out["document"] and out["document"].endswith("_market_reports.md")
    body = open(out["document"], encoding="utf-8").read()
    assert "the deck claims 40% unit share" in body
    assert "ps_fake" in body
    assert "Bearing on the claim" in body


def test_html_runs_get_an_html_reconciliation(monkeypatch, tmp_path):
    """A guest's click should land on a document, not raw markdown — when
    the run produces HTML, the reconciliation matches it (md still written
    beside it for the terminal reader)."""
    from marketreport import scoping
    from marketreport.handoff import Brief

    brief = Brief(market="m", measures=["units"], specialist="market-share",
                  because="claim under test")
    monkeypatch.setattr("marketreport.scoping.briefs_from_deck",
                        lambda deck, provider: ([brief], []))
    monkeypatch.setattr("marketreport.handoff.run_brief",
                        lambda b, **kw: {"panels": ["p"], "unknown": [],
                                         "failed": []})

    class _Ref:
        id = "ps_h"

    class _FakeLibrary:
        def save_all(self, panels, market="", place="", request=""):
            return [_Ref()]

    monkeypatch.setattr("marketreport.library.Library", _FakeLibrary)
    cfg = _engine_cfg(tmp_path)
    cfg.output.formats = ["html", "md"]

    out = scoping.dispatch_for_deck({}, cfg)
    assert out["document"].endswith(".html")
    body = open(out["document"], encoding="utf-8").read()
    assert "claim under test" in body and "<!doctype html>" in body
    assert (tmp_path / "deck_market_reports.md").exists(), (
        "markdown still written beside the page")


def test_one_dead_brief_does_not_sink_the_rest(monkeypatch, tmp_path):
    from marketreport import scoping
    from marketreport.handoff import Brief

    briefs = [Brief(market="m", measures=["units"], specialist="market-share"),
              Brief(market="m", measures=["revenue"], specialist="market-share")]
    monkeypatch.setattr("marketreport.scoping.briefs_from_deck",
                        lambda deck, provider: (briefs, []))
    calls = []

    def flaky(b, **kw):
        calls.append(b)
        if len(calls) == 1:
            raise RuntimeError("first brief dies")
        return {"panels": ["p"], "unknown": [], "failed": []}

    monkeypatch.setattr("marketreport.handoff.run_brief", flaky)

    class _Ref:
        id = "ps_second"

    class _FakeLibrary:
        def save_all(self, panels, market="", place="", request=""):
            return [_Ref()]

    monkeypatch.setattr("marketreport.library.Library", _FakeLibrary)

    out = scoping.dispatch_for_deck({}, _engine_cfg(tmp_path))
    assert out["stored"] == ["ps_second"], "the second brief must still produce"
    assert any("failed: first brief dies" in ln for ln in out["lines"])


def test_mock_demo_summary_makes_no_comps_claim():
    """The demo's canned summary once said the traction figure 'is above the
    median seed comp in this category' — a capability claim about a comps
    engine this product does not have. The demo must only demonstrate things
    the real system can do."""
    import inspect

    from deckscope.providers import mock_provider

    source = inspect.getsource(mock_provider)
    assert "median seed comp" not in source


if __name__ == "__main__":  # pragma: no cover
    import runpy
    import sys
    from pathlib import Path

    sys.argv = [sys.argv[0], "--only", Path(__file__).stem]
    runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts"
                       / "run_tests.py"), run_name="__main__")
