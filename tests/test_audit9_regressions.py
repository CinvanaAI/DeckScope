"""Seventh external audit: the wrong-basis chimera, the panel's silent
revision degradation, shared spreadsheet safety, router subject masking,
the NDA gate on the main workflow, and the help-text claim.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marketreport.dimensions import get as get_dimension
from marketreport.panel import Panel, Series, Slice
from marketreport.specialists import _off_basis, _stamp

_AXIS = get_dimension("basis")
_REVENUE = _AXIS.get("revenue")


def _units_series():
    return Series(label="Units", measure="units share", unit="%",
                  slices=[Slice(label="Samsung shipments", value=22.6),
                          Slice(label="Apple shipments", value=20.1)])


def _revenue_series():
    return Series(label="Revenue", measure="revenue share", unit="%",
                  slices=[Slice(label="Apple revenue", value=49.0),
                          Slice(label="Samsung revenue", value=16.0)])


# ------------------------------------------------- the basis invariant

def test_a_revenue_report_refuses_a_units_only_chart():
    """The audit's chimera: a revenue-scoped panel kept a units series,
    drew the units chart, and stamped '(revenue share)' on the units
    leader. Enforcement now removes the series, the panel becomes
    honestly unanswered, and the stamp has nothing to crown."""
    p = Panel(question="q", headline="Samsung leads this market",
              form="share", series=[_units_series()])
    _off_basis(p, _REVENUE, _AXIS)
    _stamp(p, _REVENUE)
    assert not p.answered
    assert p.series == []
    assert "Samsung leads" not in (p.headline or "")
    assert "read as" in " ".join(p.caveats)
    assert "publish the other basis" in p.problem
    assert "(share of revenue)" not in (p.headline or "").lower()


def test_on_basis_series_survive_and_off_basis_ones_are_excluded():
    p = Panel(question="q", headline="Samsung leads this market",
              form="share_pair",
              series=[_units_series(), _revenue_series()])
    _off_basis(p, _REVENUE, _AXIS)
    _stamp(p, _REVENUE)
    assert [s.label for s in p.series] == ["Revenue"]
    assert p.answered
    assert "Apple" in p.headline, (
        "the headline is rebuilt from the surviving on-basis series — the "
        "units leader does not keep the crown")
    assert "share of revenue" in p.headline.lower(), "stamp lands after"
    assert any("Excluded" in c for c in p.caveats)


def test_a_clean_on_basis_panel_is_untouched():
    p = Panel(question="q", headline="Apple leads this market",
              form="share", series=[_revenue_series()])
    _off_basis(p, _REVENUE, _AXIS)
    _stamp(p, _REVENUE)
    assert p.answered and len(p.series) == 1
    assert not any("Excluded" in c for c in p.caveats)


def test_mock_shaper_refuses_to_substitute_the_other_basis():
    """The mock's `or groups` fallback WAS the substitution: revenue
    requested, only units found, units returned. A competent shaper says
    'the sources publish the other basis' instead."""
    from deckscope.providers.mock_provider import MockProvider

    prompt = (
        "What this section must establish:\n"
        "who takes the most money, measured strictly as revenue share — "
        "dollars, not boxes\n\n"
        "[F1] Samsung ranked No.1 in the global smartphone market with 22% "
        "shipment share\n"
        "  value: 22%  unit: %  as of: 2026-06  sources: S1 (idc.com)\n")
    mock = MockProvider()
    out = mock._shape_for(prompt) if hasattr(mock, "_shape_for") else None
    if out is None:  # drive through the public seam instead
        import json as _json

        from deckscope.providers.base import Message

        completion = mock.complete(
            "You decide what shape an answer has",
            [Message("user", prompt)])
        out = _json.loads(completion.text)
    assert out["series"] == [], "no substitution: zero series, not units"
    assert any("other" in c.lower() or "not revenue" in c.lower()
               or "units" in c.lower() for c in out["caveats"]), (
        "the refusal names what the sources actually publish")


# ------------------------------------- panel: silent degradation is over

def _panelist(claimed_changes, revised, error=""):
    import types

    p = types.SimpleNamespace()
    p.label, p.name = "Panelist A", "mock/mock-a"
    p.review = {"position_changes": [{"what": "x"}] * claimed_changes,
                "positions_held": []}
    if error:
        p.review["revision_error"] = error
    p.revised = revised
    p.result = types.SimpleNamespace(comparisons={"investor": {}})
    p.final = lambda lens: {}
    p.revision_history = {}
    return p


def test_claimed_changes_count_zero_when_revision_never_applied():
    from deckscope.ensemble import measure_agreement

    ok = _panelist(2, {"investor": {"verdict": {"call": "GO"}}})
    failed = _panelist(3, {}, error="KeyError: 'brief'")
    m = measure_agreement([ok, failed], "investor")
    assert m["total_position_changes"] == 2, (
        "the failed panelist's 3 claimed changes moved nothing and count "
        "for nothing")
    assert m["revision_failures"] == [
        {"panelist": "Panelist A", "name": "mock/mock-a",
         "error": "KeyError: 'brief'"}]


def test_panel_exit_is_incomplete_when_revisions_failed():
    import types

    from deckscope.cli import _revision_failures

    result = types.SimpleNamespace(metrics={
        "investor": {"revision_failures": [{"panelist": "A", "name": "n",
                                            "error": "boom"}]}})
    assert len(_revision_failures(result)) == 1
    clean = types.SimpleNamespace(metrics={"investor":
                                           {"revision_failures": []}})
    assert _revision_failures(clean) == []


# ----------------------------------------- shared spreadsheet cell safety

def test_safe_cell_is_shared_and_the_main_xlsx_renderer_uses_it():
    from deckscope.commands.batch import neutralize_cell
    from deckscope.render.common import safe_cell

    assert neutralize_cell is safe_cell, (
        "one implementation — the sixth audit fixed batch, the seventh "
        "found the main workbook renderer still raw")
    src = (Path(__file__).resolve().parent.parent
           / "deckscope" / "render" / "xlsx_renderer.py"
           ).read_text(encoding="utf-8")
    assert "safe_cell" in src
    assert 'ws.append([safe_cell(txt(v, "")) for v in r])' in src


# ------------------------------------------------ router subject masking

def test_subject_words_do_not_route_to_edgar():
    from deckscope.research.router import classify

    subj = "revenue cycle management"
    reg = classify(f"What regulations affect {subj}?", subject=subj)
    cost = classify(f"What are typical operating costs in {subj}?",
                    subject=subj)
    assert reg.kind != "filing" and cost.kind != "filing", (
        "'revenue' inside the market's NAME is the subject, not the intent")
    real = classify("What is Apple's revenue?", subject="smartphones")
    assert real.kind == "filing", (
        "a genuine financial-metric question still reaches filings")


# --------------------------------------------------- NDA on the main verb

def test_run_has_an_nda_flag_that_fails_closed():
    from deckscope.cli import build_parser

    args = build_parser().parse_args(["run", "deck.pdf", "--nda"])
    assert args.nda is True


# ------------------------------------------ statements match the behavior

def test_privacy_statement_discloses_search_queries():
    root = Path(__file__).resolve().parent.parent
    app = (root / "deckscope" / "webapp.py").read_text(encoding="utf-8")
    assert "search service" in app, (
        "the app's privacy sentence must disclose deck-derived queries "
        "going to the search backend")
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "search service" in readme.split("## ")[0] or \
           "search queries" in readme, "README carries the same disclosure"


def test_help_text_quality_claim_is_evidence_scoped():
    from deckscope.cli import build_parser  # noqa: F401 — import guard
    src = (Path(__file__).resolve().parent.parent
           / "deckscope" / "cli.py").read_text(encoding="utf-8")
    assert "scores the same on every measured dimension" not in src, (
        "the seventh audit: help text asserted parity the README calls a "
        "mock tie with a stale real benchmark")


def test_new_commands_default_to_the_ignored_output_dir():
    root = Path(__file__).resolve().parent.parent
    for f in ("audit_report", "batch", "diff", "improve"):
        src = (root / "deckscope" / "commands" / f"{f}.py"
               ).read_text(encoding="utf-8")
        assert '"deckscope_output"' in src and '"deckscope_out")' not in src, (
            f"{f}.py must default to the same gitignored directory as the "
            "main pipeline")
