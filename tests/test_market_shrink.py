"""The MarketAnalyst shrink: with specialist reports running inside the
pipeline, the lightweight analyst stops researching the same quantities in
parallel — the "two partially parallel systems" gap, closed at the query
level and in the prompt.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.agents.market_agent import (_COVERED_VOCAB, MarketAnalyst,
                                           covered_note)


def _agent():
    a = MarketAnalyst.__new__(MarketAnalyst)  # built bare: no model calls
    a.events = []
    a.emit = a.events.append
    a.track = lambda *_a, **_k: None

    class _P:  # the top-up pass returns nothing extra
        def complete(self, *a, **k):
            return type("C", (), {"text": "[]"})()

    a.provider = _P()
    return a


_DECK = {"company": {"name": "Acme Flow"},
         "market": {"category": "workflow automation"},
         "research_agenda": {"search_queries": [
             "workflow automation market size 2026 independent estimate",
             "Zapier Make n8n pricing comparison mid-market",
             "workflow automation CAGR growth rate forecast",
             "RPA vendor consolidation 2026 funding rounds"]}}


def test_covered_queries_are_dropped_and_the_drop_is_announced():
    a = _agent()
    out = a.build_queries(_DECK, 8, covered=["market-size", "growth"])
    assert out == ["Zapier Make n8n pricing comparison mid-market",
                   "RPA vendor consolidation 2026 funding rounds"], (
        "size and growth queries are the specialists' job now")
    assert any("skipped 2" in e for e in a.events), (
        "a silently narrowed search would be a hidden behavior change")


def test_nothing_is_dropped_when_no_specialist_ran():
    a = _agent()
    out = a.build_queries(_DECK, 8, covered=[])
    assert len(out) == 4, "the un-staged pipeline is untouched"


def test_all_covered_falls_back_to_a_boundary_query():
    a = _agent()
    deck = {"company": {"name": "Acme"},
            "market": {"category": "workflow automation"},
            "research_agenda": {"search_queries": [
                "workflow automation market size 2026"]}}
    out = a.build_queries(deck, 8, covered=["market-size"])
    assert len(out) == 1
    assert "boundary" in out[0], (
        "with the quantities covered, what remains is the boundary itself")
    assert "market size" not in out[0]


def test_covered_note_names_reports_and_forbids_parallel_estimates():
    note = covered_note(["market-size", "regulation"])
    assert "market-size, regulation" in note
    assert "Do NOT produce your own parallel estimates" in note
    assert "boundary" in note
    assert covered_note([]) == "", "empty when nothing ran — prompt unchanged"


def test_vocab_covers_every_report_type_key():
    # reports.py keys — a new report type must add its vocabulary or the
    # shrink silently does nothing for it.
    import re

    src = (Path(__file__).resolve().parent.parent
           / "marketreport" / "reports.py").read_text(encoding="utf-8")
    keys = set(re.findall(r'^    key="([a-z-]+)"', src, re.M))
    assert keys, "report type keys should be discoverable"
    missing = keys - set(_COVERED_VOCAB)
    assert not missing, f"no covered-vocabulary for report type(s): {missing}"


def test_the_prompt_template_has_the_covered_slot():
    from deckscope.prompts.templates import MARKET_USER

    assert "{covered_note}" in MARKET_USER
