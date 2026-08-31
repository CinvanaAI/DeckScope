"""The five-feature slate: IC memo, founder fix-it list, deck diff, batch
screening, and the standalone citation audit — plus the commands/ package
they establish. Everything here is deterministic: the model contributes
nothing to any assertion in this file.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _reg(cited=1):
    class _Reg:
        sources = []

        def stats(self):
            return {"cited": cited, "total": max(cited, 1), "quarantined": 0}

        def find(self, sid):
            return None

    return _Reg()


def _result(comp, lens="investor", cited=1):
    class _Result:
        company = "Acme Flow"
        registry = _reg(cited)
        stats = {}
        comparisons = {lens: comp}

    return _Result()


_AUDIT = [
    {"id": "C1", "claim": "TAM is $47B", "assessment": "contradicted",
     "materiality": "damaging", "source_ids": ["S1"],
     "delta": "independent estimates say $18-24B",
     "checked_by_reports": [{"specialist": "market-size", "measure": "retail",
                             "finding": "the category is $18-24B",
                             "stored_as": "x-1", "source_ids": ["S3"]}]},
    {"id": "C2", "claim": "Churn is zero", "assessment": "contradicted",
     "materiality": "fatal", "source_ids": [],
     "delta": "cohort math in the deck itself implies 8% monthly"},
    {"id": "C3", "claim": "Pricing is $2k/mo", "assessment": "supported",
     "materiality": "cosmetic", "source_ids": ["S2"]},
    {"id": "C4", "claim": "NRR is 140%", "assessment": "unverifiable",
     "materiality": "damaging"},
]

_COMP = {
    "verdict": {"call": "LEAN NO", "confidence": "low"},
    "claim_audit": _AUDIT,
    "alignment": {"blind_spots": [
        {"what": "Power Automate is free in E5",
         "why_it_matters": "the bundled option costs zero"},
        {"what": "No security posture slide",
         "why_it_matters": "enterprise buyers gate on it"},
        {"what": "third spot", "why_it_matters": "should be cut to two"},
    ]},
    "advisor_read": "First paragraph of judgment.\n\nSecond paragraph.",
    "questions": ["Q one?", "Q two?", "Q three?", "Q four?", "Q five?",
                  "Q six should be cut?"],
}


# ------------------------------------------------------------------ memo

def test_memo_leads_with_fatal_contested_and_marks_uncited():
    from deckscope.render.memo_renderer import build_memo

    memo = build_memo(_result(dict(_COMP)), "investor")
    body = memo[memo.index("## The claims that decide it"):]
    assert body.index("Churn is zero") < body.index("TAM is $47B"), (
        "fatal outranks damaging among contested claims")
    assert "*(no source — a reading, not a finding)*" in memo
    assert "independently checked by the market-size report" in memo
    assert "[S3]" in memo


def test_memo_is_one_page_shaped():
    from deckscope.render.memo_renderer import build_memo

    memo = build_memo(_result(dict(_COMP)), "investor")
    assert "First paragraph of judgment." in memo
    assert "Second paragraph." not in memo, "memo takes one paragraph only"
    assert "Q five?" in memo and "Q six should be cut?" not in memo
    assert "third spot" not in memo, "two blind spots only"
    assert "not investment advice" in memo


def test_memo_honors_a_withheld_verdict():
    """A zero-evidence run withholds its verdict in the report; the memo
    must not resurrect it."""
    from deckscope.render.memo_renderer import build_memo

    memo = build_memo(_result(dict(_COMP), cited=0), "investor")
    assert "LEAN NO" not in memo.split("\n")[2]
    assert "No verdict" in memo


def test_memo_and_fixit_are_registered_with_aliases(tmp_path):
    from deckscope.render.registry import list_formats, render

    fmts = list_formats()
    assert "memo" in fmts and "fixit" in fmts
    for name in ("memo", "ic"):
        paths = render(name, _result(dict(_COMP)), tmp_path, "acme")
        assert Path(paths[0]).name == "acme_investor_memo.md"
    for name in ("fixit", "founder"):
        paths = render(name, _result(dict(_COMP)), tmp_path, "acme")
        assert Path(paths[0]).name == "acme_investor_fixit.md"


# ----------------------------------------------------------------- fix-it

def test_fixit_orders_by_materiality_with_labels():
    from deckscope.render.fixit_renderer import build_fixit

    body = build_fixit(_result(dict(_COMP)), "investor")
    assert body.index("Churn is zero") < body.index("TAM is $47B")
    assert "FIX BEFORE SENDING" in body
    assert "expect it as a question rather than a finding" in body, (
        "uncited contested items are labelled as readings")
    assert "Add a slide (or a line) on:" in body
    assert "NRR is 140%" in body, "unverifiable claims become preemptions"
    assert "no additional AI call" in body


def test_fixit_prefers_the_founder_lens_when_present(tmp_path):
    from deckscope.render.fixit_renderer import render

    class _Result:
        company = "Acme Flow"
        registry = _reg()
        stats = {}
        comparisons = {"investor": dict(_COMP), "founder": dict(_COMP)}

    paths = render(_Result(), tmp_path, "acme")
    assert [Path(p).name for p in paths] == ["acme_founder_fixit.md"]


def test_fixit_on_an_empty_run_says_so():
    from deckscope.render.fixit_renderer import build_fixit

    body = build_fixit(_result({"claim_audit": []}), "investor")
    assert "Nothing to fix from this run" in body
    assert "no evidence to check against" in body


# ------------------------------------------------------------------- diff

def _claims(*texts, type="market-size", **kw):
    return [dict(text=t, type=type, location=kw.get("location", ""),
                 value_text=kw.get("value_text", "")) for t in texts]


def test_diff_detects_a_figure_change_with_ratio():
    from deckscope.commands.diff import diff_claims

    old = [{"text": "The workflow market is $47B", "type": "market-size",
            "value_text": "$47B", "location": "slide 3"}]
    new = [{"text": "The workflow market is $24B", "type": "market-size",
            "value_text": "$24B", "location": "slide 3"}]
    d = diff_claims(old, new)
    assert len(d["changed"]) == 1
    row = d["changed"][0]
    assert row["old_figure"] == 47e9 and row["new_figure"] == 24e9
    assert row["ratio"] == 0.51
    assert not d["dropped"] and not d["added"]


def test_diff_reports_dropped_added_and_moved():
    from deckscope.commands.diff import diff_claims

    old = [{"text": "We have zero churn across all cohorts",
            "type": "traction", "location": "slide 5"},
           {"text": "Gross margin is 78% at scale", "type": "financial",
            "location": "slide 7"}]
    new = [{"text": "Gross margin is 78% at scale", "type": "financial",
            "location": "slide 4"},
           {"text": "Pipeline includes three Fortune 500 pilots",
            "type": "traction", "location": "slide 5"}]
    d = diff_claims(old, new)
    assert [c["text"] for c in d["dropped"]] == [
        "We have zero churn across all cohorts"]
    assert [c["text"] for c in d["added"]] == [
        "Pipeline includes three Fortune 500 pilots"]
    assert d["moved"] == [{"claim": "Gross margin is 78% at scale",
                           "from": "slide 7", "to": "slide 4"}]


def test_diff_never_pairs_across_types_on_shared_digits():
    """$47B market and $47K contract share tokens; they are different
    claims, and pairing them would report a 1,000,000x 'change'."""
    from deckscope.commands.diff import diff_claims

    old = [{"text": "The market is $47B", "type": "market-size"}]
    new = [{"text": "Average contract is $47K", "type": "financial"}]
    d = diff_claims(old, new)
    assert not d["changed"]
    assert len(d["dropped"]) == 1 and len(d["added"]) == 1


def test_diff_render_declares_extraction_nondeterminism():
    from deckscope.commands.diff import diff_claims, render_diff

    d = diff_claims(_claims("The market is $47B"),
                    _claims("The market is $24B"))
    body = render_diff(d, "old.pdf", "new.pdf", "Acme")
    assert "leads, not verdicts" in body
    assert "47,000,000,000 → 24,000,000,000" in body
    assert "a change log, not an audit" in body


def test_diff_nda_refuses_a_hosted_extraction_model(tmp_path, monkeypatch):
    """Both decks go to the extraction model; --nda must fail closed
    before either deck is read, exactly like run/research."""
    from deckscope.commands.diff import command

    deck = tmp_path / "d.txt"
    deck.write_text("Our market is $47B", encoding="utf-8")
    args = types.SimpleNamespace(old_deck=str(deck), new_deck=str(deck),
                                 provider="anthropic", config=None,
                                 out=str(tmp_path), nda=True)
    calls = []
    import deckscope.commands.diff as mod
    monkeypatch.setattr("deckscope.providers.registry.get_provider",
                        lambda cfg: calls.append(cfg))
    assert command(args) == 4
    assert calls == [], "refusal happens before any provider is built"
    assert mod is not None


# ------------------------------------------------------------------ batch

def test_verdict_rank_orders_calls_and_no_go_is_not_go():
    from deckscope.commands.batch import verdict_rank

    assert verdict_rank("GO") < verdict_rank("LEAN YES") \
        < verdict_rank("No verdict") < verdict_rank("LEAN NO") \
        < verdict_rank("NO GO")
    assert verdict_rank("NO GO") > verdict_rank("GO"), (
        "'NO GO' contains 'GO' and must still rank as a decline")
    assert verdict_rank("") == verdict_rank("No verdict") == 2, (
        "a withheld verdict is unknown, not bad — it sits in the middle")


def test_rank_rows_puts_failures_last_and_contested_within_verdict():
    from deckscope.commands.batch import rank_rows

    rows = [
        {"company": "b", "deck": "b.pdf", "verdict": "LEAN NO",
         "contested": 1, "error": ""},
        {"company": "dead", "deck": "x.pdf", "verdict": "",
         "contested": 0, "error": "boom"},
        {"company": "a", "deck": "a.pdf", "verdict": "LEAN YES",
         "contested": 3, "error": ""},
        {"company": "c", "deck": "c.pdf", "verdict": "LEAN YES",
         "contested": 0, "error": ""},
    ]
    ranked = rank_rows(rows)
    assert [r["company"] for r in ranked] == ["c", "a", "b", "dead"]


def test_batch_summary_renders_ok_and_failed_sections(tmp_path):
    from deckscope.commands.batch import render_summary, write_table

    rows = [{"company": "Acme", "deck": "a.pdf", "verdict": "LEAN NO",
             "confidence": "low", "contested": 2, "supported": 1,
             "unverifiable": 1, "questions": 8, "sources_cited": 6,
             "out_dir": "out/a", "error": ""},
            {"company": "?", "deck": "bad.pdf", "verdict": "",
             "confidence": "", "contested": 0, "supported": 0,
             "unverifiable": 0, "questions": 0, "sources_cited": 0,
             "out_dir": "", "error": "ValueError: empty deck"}]
    body = render_summary(rows, "inbound")
    assert "1 deck(s) analyzed, 1 failed" in body
    assert "| 1 | Acme | a.pdf | LEAN NO |" in body
    assert "**bad.pdf** — ValueError: empty deck" in body
    assert "a triage order, not a judgment" in body
    table = write_table(rows, tmp_path)
    assert table.exists() and table.suffix in (".xlsx", ".csv"), (
        "xlsx when openpyxl is installed, CSV otherwise — both are the "
        "same columns")


def test_batch_refuses_an_empty_folder(tmp_path):
    from deckscope.commands.batch import command

    args = types.SimpleNamespace(folder=str(tmp_path), provider=None,
                                 config=None, out=str(tmp_path / "out"),
                                 lens=None, format=None)
    assert command(args) == 2


# ----------------------------------------------------------- audit-report

_SOURCES = [{"sid": "S1", "title": "IDC sizing", "url": "https://e.gov/a",
             "snippet": "the category is $18-24B"},
            {"sid": "S2", "title": "Vendor blog", "url": "https://e.gov/b",
             "snippet": "x", "status": "quarantined",
             "note": "vendor-sponsored"},
            {"sid": "S4", "title": "Census CBP", "url": "https://e.gov/c",
             "snippet": "y"}]


def test_audit_text_finds_dangling_quarantined_and_unsourced_figures():
    from deckscope.commands.audit_report import audit_text, build_registry

    reg = build_registry(list(_SOURCES))
    text = ("The market is $18-24B [S1]. Growth is 23% [S9]. "
            "Vendor data says 40% [S2]. Margins are 78% at scale. "
            "Founded in 2019 and headquartered in Austin.")
    a = audit_text(text, reg)
    assert [d[0] for d in a["dangling"]] == ["S9"]
    assert [q[0] for q in a["quarantined"]] == ["S2"]
    assert any("78%" in s for s in a["unsourced_figures"])
    assert not any("2019" in s for s in a["unsourced_figures"]), (
        "a bare year is not a figure that needs a source")
    assert [s.sid for s in a["unused_sources"]] == ["S4"]


def test_registry_keeps_caller_sids_and_refuses_ambiguity():
    from deckscope.commands.audit_report import build_registry

    reg = build_registry(list(_SOURCES))
    assert [s.sid for s in reg.sources] == ["S1", "S2", "S4"], (
        "the caller's S7 stays S7 — renumbering would falsify the audit")
    try:
        build_registry([{"sid": "S1", "title": "a"}, {"title": "no sid"}])
        raise AssertionError("mixed sid/no-sid must be refused")
    except ValueError as e:
        assert "ambiguous" in str(e)


def test_audit_report_command_end_to_end(tmp_path):
    from deckscope.commands.audit_report import command

    (tmp_path / "sources.json").write_text(json.dumps(_SOURCES),
                                           encoding="utf-8")
    report = tmp_path / "memo.md"
    report.write_text("The market is $18-24B [S1]. But also $99B [S9].",
                      encoding="utf-8")
    args = types.SimpleNamespace(report=str(report),
                                 sources=str(tmp_path / "sources.json"),
                                 out=str(tmp_path))
    assert command(args) == 1, "a dangling citation is a failing exit"
    body = (tmp_path / "memo_audit.md").read_text(encoding="utf-8")
    assert "Dangling citations" in body and "[S9]" in body
    assert "cannot prove a cited source actually supports" in body

    clean = tmp_path / "clean.md"
    clean.write_text("The market is $18-24B [S1].", encoding="utf-8")
    args.report = str(clean)
    assert command(args) == 0


def test_audit_report_runs_the_structured_pass_on_json(tmp_path):
    from deckscope.commands.audit_report import command

    (tmp_path / "sources.json").write_text(json.dumps(_SOURCES),
                                           encoding="utf-8")
    report = tmp_path / "result.json"
    report.write_text(json.dumps(
        {"summary": "sized at $18-24B [S1]",
         "claim_audit": [{"claim": "x", "source_ids": ["S8"]}]}),
        encoding="utf-8")
    args = types.SimpleNamespace(report=str(report),
                                 sources=str(tmp_path / "sources.json"),
                                 out=str(tmp_path))
    assert command(args) == 1, (
        "a bracketless source_ids reference to a nonexistent source is "
        "caught by the recursive pass, not just the text scan")
    body = (tmp_path / "result_audit.md").read_text(encoding="utf-8")
    assert "S8" in body and "Structured pass" in body


# -------------------------------------------------------- the package rule

def test_commands_package_states_the_migration_rule():
    import deckscope.commands as pkg

    doc = pkg.__doc__ or ""
    assert "beachhead" in doc
    assert "NEW commands are born in this package" in doc


def test_new_verbs_are_wired_into_the_cli():
    from deckscope.cli import build_parser

    p = build_parser()
    helptext = p.format_help()
    for verb in ("diff", "batch", "audit-report"):
        assert verb in helptext
