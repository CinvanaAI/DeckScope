"""Forward-motion features: the structural claim-report join and the
question pack. Built between audits, from the product's own head rather
than an auditor's list.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.orchestrator import _join_reports_to_claims


# ------------------------------------------------------ the structural join

def _rows():
    return [{"checks_claim_ids": ["C1"], "specialist": "market-size",
             "measure": "retail", "finding": "The category is $18-24B",
             "stored_as": "20260830-x-1",
             "figures": [{"source_ids": ["S3", "S4"]},
                         {"source_ids": ["S3"]}]},
            {"checks_claim_ids": [], "specialist": "growth",
             "measure": "", "finding": "n/a", "stored_as": "",
             "figures": []}]


def test_reports_attach_to_the_rows_they_declared():
    """Two audits called the claim-to-report link model-mediated: the
    synthesist was ASKED to notice which report checked which claim.
    Noticing is now irrelevant — the scoper's declared ids join by code."""
    comp = {"claim_audit": [{"id": "C1", "assessment": "unverifiable"},
                            {"id": "C2", "assessment": "supported"}]}
    _join_reports_to_claims(comp, _rows())
    row = comp["claim_audit"][0]
    assert row["checked_by_reports"][0]["specialist"] == "market-size"
    assert row["checked_by_reports"][0]["source_ids"] == ["S3", "S4"]
    assert "checked_by_reports" not in comp["claim_audit"][1], (
        "a report attaches only to the claims it declared")


def test_the_join_never_touches_the_models_own_assessment():
    comp = {"claim_audit": [{"id": "C1", "assessment": "contradicted",
                             "source_ids": ["S9"]}]}
    _join_reports_to_claims(comp, _rows())
    row = comp["claim_audit"][0]
    assert row["assessment"] == "contradicted"
    assert row["source_ids"] == ["S9"], (
        "report sources render beside the row; they are not smuggled into "
        "the row's own citations, so the cited/uncited stats stay honest")


def test_the_join_survives_malformed_rows():
    comp = {"claim_audit": [{"id": "C1"}]}
    _join_reports_to_claims(comp, ["not a dict", None,
                                   {"checks_claim_ids": ["C1"],
                                    "figures": None}])
    assert comp["claim_audit"][0]["checked_by_reports"][0]["source_ids"] == []
    _join_reports_to_claims(comp, "not a list")  # no raise


def test_the_join_renders_in_the_markdown_row(tmp_path):
    from deckscope.render.markdown_renderer import build_markdown

    class _Reg:
        sources = []

        def stats(self):
            return {"cited": 1, "total": 1, "quarantined": 0}

        def find(self, sid):
            return None

    class _Result:
        company = "TestCo"
        stats = {}
        registry = _Reg()
        deck = {"company": {"name": "TestCo"}}
        market = {}
        security = None
        market_reports = None
        opportunity = None
        discovery_delta = None
        cold_market = None
        comparisons = {"investor": {
            "headline": "h",
            "verdict": {"call": "LEAN NO", "confidence": "low"},
            "claim_audit": [{
                "id": "C1", "claim": "TAM is $47B",
                "assessment": "contradicted", "source_ids": ["S1"],
                "checked_by_reports": [{
                    "specialist": "market-size", "measure": "retail",
                    "finding": "The category is $18-24B",
                    "stored_as": "x-1", "source_ids": ["S3"]}],
            }],
        }}

    body = build_markdown(_Result(), "investor")
    assert "Independently checked by the market-size report" in body
    assert "[S3]" in body
    assert "stored as `x-1`" in body


# ---------------------------------------------------------- question pack

def _result(questions, claims=()):
    class _Reg:
        def stats(self):
            return {"cited": 1, "total": 1, "quarantined": 0}

    class _Result:
        company = "Acme Flow"
        registry = _Reg()
        comparisons = {"investor": {
            "questions": list(questions),
            "claim_audit": [{"id": f"C{i}", "claim": c,
                             "assessment": "unverifiable"}
                            for i, c in enumerate(claims, 1)],
        }}

    return _Result()


def test_every_question_ships_with_its_answer_standard():
    from deckscope.render.questions_renderer import build_question_pack

    pack = build_question_pack(_result(
        ["What is net revenue retention on the first 11 customers?",
         "Is inference cost inside the 78% margin?"]), "investor")
    assert "## 1. What is net revenue retention" in pack
    assert "'Strong' is not a number." in pack
    assert "reconciles the specific figures" in pack


def test_unverified_claims_become_questions_for_the_room():
    from deckscope.render.questions_renderer import build_question_pack

    pack = build_question_pack(
        _result([], claims=["SAM: $6B (mid-market North America)"]),
        "investor")
    assert "Claims only the founder can settle" in pack
    assert "SAM: $6B" in pack
    assert "not marks against the company" in pack


def test_no_questions_is_itself_flagged():
    from deckscope.render.questions_renderer import build_question_pack

    pack = build_question_pack(_result([]), "investor")
    assert "no open questions" in pack


def test_the_format_is_registered_and_writes_files(tmp_path):
    from deckscope.render.registry import list_formats, render

    assert "questions" in list_formats()
    paths = render("questions", _result(["A question?"]), tmp_path, "acme")
    assert len(paths) == 1
    text = Path(paths[0]).read_text(encoding="utf-8")
    assert "Question pack — Acme Flow" in text
    assert "no additional AI call" in text
