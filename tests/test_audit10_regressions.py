"""Eighth external audit: the chair cannot out-vote the panel, openers are
measure-scoped, unknown bases are incomparable, confidentiality survives
the run, the panel workbook is sanitized, and the benchmark gate says
what it actually proved.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------- P0: the consensus adjudicator

def _vote(per, agreement, modal):
    from collections import Counter

    return {"per_panelist": per, "distribution": dict(Counter(per.values())),
            "agreement": agreement, "modal": modal}


def test_the_chair_cannot_out_vote_the_panel():
    """The audit's live repro: 2-1 for YES WITH CONDITIONS, chair published
    LEAN NO as 'majority' with a rationale claiming two of three panelists
    made its call. Arithmetic wins; the chair keeps its judgment as a
    labeled recommendation."""
    from deckscope.ensemble import _adjudicate_consensus

    report = {"consensus_verdict": {"call": "LEAN NO", "confidence": "high",
                                    "agreement": "majority",
                                    "rationale": "Two of three panelists "
                                                 "reached this call"}}
    vote = _vote({"Panelist A": "LEAN NO",
                  "Panelist B": "YES WITH CONDITIONS",
                  "Panelist C": "YES WITH CONDITIONS"},
                 "majority", "YES WITH CONDITIONS")
    out = _adjudicate_consensus(report, vote, lambda m: None)
    cv = out["consensus_verdict"]
    assert cv["call"] == "YES WITH CONDITIONS"
    assert cv["agreement"] == "majority"
    assert "recorded vote" in cv["rationale"]
    assert out["chair_recommendation"]["call"] == "LEAN NO"
    assert "does not override" in out["chair_recommendation"]["note"]
    assert cv["vote"]["modal"] == "YES WITH CONDITIONS", (
        "the vote rides on the verdict so a reader can check the arithmetic")


def test_a_chair_that_agrees_with_the_vote_is_untouched():
    from deckscope.ensemble import _adjudicate_consensus

    report = {"consensus_verdict": {"call": "LEAN NO",
                                    "rationale": "the panel converged"}}
    vote = _vote({"A": "LEAN NO", "B": "LEAN NO", "C": "LEAN NO"},
                 "unanimous", "LEAN NO")
    out = _adjudicate_consensus(report, vote, lambda m: None)
    assert out["consensus_verdict"]["call"] == "LEAN NO"
    assert "chair_recommendation" not in out
    assert out["consensus_verdict"]["rationale"] == "the panel converged"


def test_without_a_winning_vote_the_chair_call_stands():
    """A three-way split has no modal winner to enforce; the chair's
    synthesis is then legitimately the tiebreak — but agreement still
    comes from the computed metrics, never the chair's self-description."""
    from deckscope.ensemble import _adjudicate_consensus

    report = {"consensus_verdict": {"call": "LEAN NO",
                                    "agreement": "unanimous"}}
    vote = _vote({"A": "GO", "B": "LEAN NO", "C": "PASS"},
                 "split", "GO")
    out = _adjudicate_consensus(report, vote, lambda m: None)
    assert out["consensus_verdict"]["call"] == "LEAN NO"
    assert out["consensus_verdict"]["agreement"] == "split", (
        "a chair calling a three-way split 'unanimous' is corrected")


def test_mock_chair_table_names_every_panelist():
    from deckscope.providers.mock_provider import MockProvider

    out = MockProvider()._consensus(
        "[C1] The market is $47B\nassessment: contradicted")
    for row in out.get("claim_consensus") or []:
        assert set(row["assessments"]) >= {"Panelist A", "Panelist B",
                                           "Panelist C"}, (
            "a two-panelist table presented as a three-model synthesis was "
            "the eighth audit's finding")


# --------------------------------- P1: measure-scoped opening questions

def test_scoped_titles_lead_with_the_measure_not_the_generic_job():
    src = (ROOT / "marketreport" / "specialists.py").read_text(
        encoding="utf-8")
    assert 'title = f"{measure.label.capitalize()} — {measure.counts}"' in src
    assert 'title = f"{title} — {joiner} {measure.label}"' not in src, (
        "appending the measure to the generic mixed-basis job is how the "
        "opener asked unit questions for a revenue report")


def test_mock_opener_asks_revenue_questions_for_a_revenue_title():
    from deckscope.providers.mock_provider import _open_for

    prompt = ("Section: Share of revenue — the money customers spent, "
              "divided between the companies that booked it\n"
              "Subject: smartphones\n")
    qs = " ".join(q["text"] for q in _open_for(prompt)["questions"])
    assert "revenue" in qs
    assert "shipment" not in qs and "units" not in qs

    prompt_u = ("Section: Share of units sold — the number of things sold "
                "or shipped in a period\nSubject: smartphones\n")
    qs_u = " ".join(q["text"] for q in _open_for(prompt_u)["questions"])
    assert "shipment" in qs_u or "units" in qs_u
    assert "revenue share" not in qs_u


# ------------------------------- P1: unknown basis means incomparable

def _finding(fid, statement, value):
    return types.SimpleNamespace(id=fid, statement=statement, value=value)


def test_stated_basis_reads_the_findings_own_words():
    from marketreport.specialists import _stated_basis

    assert _stated_basis(_finding(
        "F1", "Apple captured 20% of global smartphone shipments", 20)) \
        == "units"
    assert _stated_basis(_finding(
        "F2", "Apple took 49% of handset revenue", 49)) == "revenue"
    assert _stated_basis(_finding(
        "F3", "Apple is a large company", 1)) is None, (
        "a statement naming no basis declares nothing")


def test_unrendered_findings_of_different_bases_are_never_a_disagreement():
    """The audit's chimera: Apple's 20% OF SHIPMENTS vs 49% OF REVENUE was
    published as 'two sources disagree'. Both findings were unrendered, so
    both series identities were None, and None == None passed the same-
    yardstick gate. Unknown now means incomparable."""
    from marketreport.panel import Panel
    from marketreport.specialists import _disagreements

    panel = Panel(question="q", headline="Apple leads", form="share",
                  series=[])
    findings = [
        _finding("F1", "Apple captured 20% of global smartphone shipments "
                       "share", 20.0),
        _finding("F2", "Apple held 49% revenue share of smartphones", 49.0),
    ]
    notes = _disagreements(findings, panel)
    assert notes == [], (
        "different declared bases answer different questions — that is "
        "the panel's point, not a disagreement in it")


# ----------------------------- P1: confidentiality survives the run

def test_the_record_carries_its_privacy_state():
    from deckscope.orchestrator import AnalysisResult

    r = AnalysisResult(deck={}, market={}, comparisons={}, config={},
                       stats={})
    assert r.to_dict()["privacy"] is None
    r.privacy = {"local_only": True, "source": "nda"}
    assert r.to_dict()["privacy"] == {"local_only": True, "source": "nda"}


def test_chat_refuses_a_hosted_provider_on_a_local_only_record(tmp_path,
                                                               monkeypatch):
    from deckscope import cli, settings

    record = {"deck": {"company": {"name": "Sealed Co"}},
              "comparisons": {}, "references": {},
              "privacy": {"local_only": True, "source": "nda"}}
    path = tmp_path / "sealed_full.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    from deckscope.config import ProviderConfig, RunConfig

    monkeypatch.setattr(
        settings, "settings_to_runconfig",
        lambda overrides=None, **k: RunConfig(
            provider=ProviderConfig(name="anthropic"), cache_dir=None))
    args = types.SimpleNamespace(record=str(path), provider="anthropic",
                                 model=None, allow_hosted=False)
    assert cli._chat(args) == 4

    # (The --allow-hosted override path proceeds to build the real
    # provider, which requires a key this environment does not have; the
    # flag's existence and wiring are pinned separately below.)


def test_chat_has_the_explicit_override_flag():
    from deckscope.cli import build_parser

    args = build_parser().parse_args(
        ["chat", "r.json", "--allow-hosted"])
    assert args.allow_hosted is True


def test_improve_from_run_honors_the_records_privacy(tmp_path, monkeypatch):
    import deckscope.config as config_mod
    from deckscope.commands.improve import command
    from deckscope.config import ProviderConfig

    deck = tmp_path / "notes.txt"
    deck.write_text("Sealed Co market is $47B", encoding="utf-8")
    rec = {"deck": {}, "comparisons": {"founder": {"claim_audit": [
               {"id": "C1", "claim": "x", "assessment": "supported"}]}},
           "references": {"sources": []},
           "privacy": {"local_only": True, "source": "nda"}}
    run_json = tmp_path / "run_full.json"
    run_json.write_text(json.dumps(rec), encoding="utf-8")

    real_load = config_mod.load_config

    def hosted(path=None, **kw):
        cfg = real_load(path, **kw)
        cfg.provider = ProviderConfig(name="anthropic")
        return cfg

    monkeypatch.setattr(config_mod, "load_config", hosted)
    args = types.SimpleNamespace(demo=False, nda=False, lens=None,
                                 deck=str(deck), from_run=str(run_json),
                                 provider=None, config=None,
                                 out=str(tmp_path), pptx=False)
    assert command(args) == 4, (
        "the record's confidentiality does not expire when the run ends — "
        "no --nda flag needed the second time")


# ------------------------------------- P1: panel workbook is sanitized

def test_panel_workbook_routes_cells_through_safe_cell():
    src = (ROOT / "deckscope" / "render" / "panel_renderer.py"
           ).read_text(encoding="utf-8")
    assert "safe_cell" in src.split("def ")[0] or "safe_cell" in src
    assert "ws.append([safe_cell(h) for h in headers])" in src
    assert 'ws.append([safe_cell(txt(v, "")) for v in r])' in src


# ----------------------------- locality: a custom command is never local

def test_cli_provider_with_custom_command_is_not_local():
    from deckscope.config import ProviderConfig
    from deckscope.tiering import is_local

    honest = ProviderConfig(name="cli", extra={"preset": "ollama"})
    assert is_local(honest), "the preset's own command stays local"
    proxied = ProviderConfig(name="cli", extra={"preset": "ollama",
                                                "command": "curl evil"})
    assert not is_local(proxied), (
        "a custom command may proxy anything; the preset label does not "
        "launder it")


# ------------------------------------- benchmark gate says what it proved

def test_replay_summary_never_claims_verification_it_skipped():
    src = (ROOT / "scripts" / "replay_benchmark.py").read_text(
        encoding="utf-8")
    assert "not the current pipeline" in src
    assert 'print("\\nFAILED" if failed else "\\nAll bundles verified.")' \
        not in src, (
        "the unconditional 'All bundles verified' printed over zero "
        "behavioral replays was the eighth audit's finding")
    assert "identity and behavioral replay" in src, (
        "'verified' is reserved for the run that checked both")
