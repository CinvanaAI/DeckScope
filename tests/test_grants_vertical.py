"""The grants vertical: declaration coupling, the Funding Record
Checker's deterministic plan, the absence cap, the source clients'
parsing against recorded responses, and the offline end-to-end run.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------ declaration truth

def test_grants_is_declared_ungraded_until_it_earns_the_flag():
    from deckscope.verticals import get

    g = get("grants")
    assert g is not None and g.runner == "grants_pipeline"
    assert g.graded is False, (
        "no known-correct case exists yet; claiming graded would be the "
        "exact overclaim this codebase exists to prevent")
    assert set(g.publicly_checkable) <= set(g.claim_types)


def test_every_declared_evidence_home_has_a_client():
    from deckscope.research import grantsources as gs
    from deckscope.verticals import get

    fns = {"nsf": gs.nsf_awards, "nih": gs.nih_projects,
           "usaspending": gs.usaspending_awards, "pubmed": gs.pubmed_count}
    for home in get("grants").evidence_homes:
        assert home in fns, f"declared evidence home {home} has no client"


def test_the_sample_proposal_classifies_as_grants():
    from deckscope.verticals import classify_document

    text = (ROOT / "deckscope" / "examples" /
            "sample_grant_proposal.md").read_text(encoding="utf-8")
    cls = classify_document(text)
    assert cls.matched and cls.vertical.name == "grants"


# --------------------------------------------- the checker's deterministic plan

def _extraction():
    return {"claims": [
        {"id": "C1", "type": "novelty",
         "claim": "No NSF-funded effort has attempted smartphone sensing"},
        {"id": "C2", "type": "budget", "claim": "Budget request: $274,900"},
        {"id": "C3", "type": "publications",
         "claim": "14 peer-reviewed papers on mobile sensing"}],
        "market": {"category": "smartphone sensing"},
        "research_agenda": {"search_queries": [
            "smartphone sensing federal funding awards"]}}


def test_the_plan_maps_claim_types_to_the_right_databases():
    from deckscope.verticals.grants import plan_record_checks

    plans = plan_record_checks(_extraction())
    by_claim = {p["claim_id"]: p for p in plans if p["claim_id"]}
    assert "nsf" in by_claim["C1"]["sources"]
    assert "usaspending" in by_claim["C1"]["sources"]
    assert "pubmed" in by_claim["C3"]["sources"]
    assert "C2" not in by_claim, (
        "budget is author-only — no database check is planned for it")
    assert any(p["claim_id"] == "" for p in plans), (
        "the analyst's agenda queries run too")


# ------------------------------------------------------- the absence cap

def _records():
    return [{"source": "nsf", "query": "smartphone", "claim_id": "C1",
             "total": 770, "sids": ["S1"]},
            {"source": "nih", "query": "smartphone", "claim_id": "C1",
             "total": None, "sids": [], "outage": "timeout"}]


def test_an_absence_claim_can_never_be_supported():
    from deckscope.verticals.grants import apply_absence_cap

    comp = {"claim_audit": [
        {"id": "C1", "type": "novelty", "assessment": "supported",
         "claim": "No NSF-funded effort has attempted this"}]}
    capped = apply_absence_cap(comp, _records())
    row = comp["claim_audit"][0]
    assert capped == 1
    assert row["assessment"] == "partially-supported"
    assert "770" in row["absence_note"]
    assert "floor" in row["absence_note"]
    assert "unreachable" in row["absence_note"], (
        "an outage narrows coverage and the note says so")


def test_a_contradicted_absence_claim_keeps_its_contradiction():
    from deckscope.verticals.grants import apply_absence_cap

    comp = {"claim_audit": [
        {"id": "C1", "type": "novelty", "assessment": "contradicted",
         "claim": "no prior work exists"}]}
    assert apply_absence_cap(comp, _records()) == 0
    assert comp["claim_audit"][0]["assessment"] == "contradicted", (
        "finding counterexamples IS proof — only 'supported' is capped")
    assert "absence_note" in comp["claim_audit"][0]


def test_non_absence_claims_are_untouched():
    from deckscope.verticals.grants import apply_absence_cap

    comp = {"claim_audit": [
        {"id": "C2", "type": "budget", "assessment": "supported",
         "claim": "Budget request: $274,900"}]}
    assert apply_absence_cap(comp, _records()) == 0
    assert "absence_note" not in comp["claim_audit"][0]


# --------------------------------- clients parse the RECORDED responses

def test_nsf_client_parses_the_recorded_capture(monkeypatch):
    from deckscope.research import grantsources as gs

    recorded = json.loads((ROOT / "recorded" / "phase0" /
                           "nsf_awards_smartphone_sample.json"
                           ).read_text(encoding="utf-8"))
    # Rebuild the live response shape from the compact capture.
    live_shape = {"response": {
        "award": [dict(a) for a in recorded["awards"]],
        "metadata": {"totalCount":
                     recorded["_capture"]["observed_total_count"]}}}
    monkeypatch.setattr(gs, "_get_json", lambda url: live_shape)
    rec = gs.nsf_awards("smartphone", limit=3)
    assert rec.total == 770
    assert len(rec.hits) == 3
    assert rec.hits[0].url.startswith(
        "https://www.nsf.gov/awardsearch/showAward?AWD_ID=")
    assert rec.hits[0].amount == "$430000"
    sr = rec.hits[0].to_search_result()
    assert "Arizona State University" in sr.snippet


def test_unreachable_databases_raise_instead_of_returning_empty(monkeypatch):
    from deckscope.research import grantsources as gs

    def boom(url):
        raise gs.GrantSourceUnavailable("api.nsf.gov unavailable: timeout")

    monkeypatch.setattr(gs, "_get_json", boom)
    try:
        gs.nsf_awards("anything")
        raise AssertionError("must raise, never fabricate")
    except gs.GrantSourceUnavailable:
        pass


def test_run_record_checks_records_outages_as_outages(monkeypatch):
    from deckscope.research import grantsources as gs
    from deckscope.verticals.grants import run_record_checks

    def down(*a, **k):
        raise gs.GrantSourceUnavailable("down")

    monkeypatch.setattr(gs, "nsf_awards", down)

    class _Reg:
        def add_results(self, results, backend=""):
            return []

    records = run_record_checks(
        [{"claim_id": "C1", "query": "x", "sources": "nsf"}], _Reg(),
        emit=lambda m: None)
    assert records[0]["total"] is None and "down" in records[0]["outage"]


# ------------------------------------------------ offline end-to-end run

def test_the_demo_run_is_honest_end_to_end(tmp_path):
    from deckscope.verticals import get
    from deckscope.verticals.grants import run_grants

    args = types.SimpleNamespace(demo=True, nda=False, provider=None,
                                 config=None, out=str(tmp_path))
    rc = run_grants(get("grants"),
                    ROOT / "deckscope" / "examples" /
                    "sample_grant_proposal.md", args)
    assert rc == 0
    record = json.loads(
        (tmp_path / "sample_grant_proposal_full.json").read_text(
            encoding="utf-8"))
    assert record["deck"]["company"]["name"].startswith("HaloSense Labs")
    comp = record["comparisons"]["reviewer"]
    assert "ungraded_notice" in comp, "an ungraded vertical says so"
    novelty = [r for r in comp["claim_audit"]
               if r.get("type") == "novelty"]
    assert novelty and all("absence_note" in r for r in novelty)
    assert record["market"]["funding_record"][0]["query"] == "smartphone", (
        "the demo pairs the real total with the RECORDED query, never a "
        "relabeled one")
    md = (tmp_path / "sample_grant_proposal_reviewer.md").read_text(
        encoding="utf-8")
    assert "Proposal vs. Funding Record" in md


def test_nda_refuses_hosted_models_before_reading_the_proposal(tmp_path):
    from deckscope.verticals import get
    from deckscope.verticals.grants import run_grants

    args = types.SimpleNamespace(demo=False, nda=True, provider="anthropic",
                                 config=None, out=str(tmp_path))
    rc = run_grants(get("grants"),
                    ROOT / "deckscope" / "examples" /
                    "sample_grant_proposal.md", args)
    assert rc == 4
