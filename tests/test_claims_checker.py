"""The claims checker must hold on the real tree AND fire on seeded drift.

A checker that only ever passes is a green light wired to nothing. Each test
here doctors a temp copy of the relevant files with the exact drift class an
external audit once found — announced gates, un-admitted benchmark staleness,
a stale cost multiple, a surface documented but unbuilt — and asserts the
check refuses it.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_claims  # noqa: E402


def _tree(tmp_path, *rel: str) -> Path:
    """A temp root holding real copies of just the named files."""
    for r in rel:
        dst = tmp_path / r
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / r, dst)
    return tmp_path


def test_every_claim_holds_on_the_real_tree():
    """The gate itself: the shipped documents and the shipped code agree."""
    assert check_claims.run(ROOT) == []


def test_announced_gates_are_refused(tmp_path):
    root = _tree(tmp_path, "docs/SYSTEM_AUDIT.md")
    doc = root / "docs" / "SYSTEM_AUDIT.md"
    doc.write_text(doc.read_text(encoding="utf-8")
                   + "\nAll gates pass on this branch.\n", encoding="utf-8")
    problems = check_claims.audit_gate_language(root)
    assert problems and "gates pass" in problems[0]


def test_the_standing_rule_quote_itself_is_not_flagged():
    """The blockquote states the forbidden phrase in order to forbid it."""
    assert check_claims.audit_gate_language(ROOT) == []


def test_unadmitted_benchmark_staleness_is_refused(tmp_path):
    root = _tree(tmp_path, ".github/workflows/ci.yml",
                 "benchmarks/README.md")
    readme = root / "benchmarks" / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8")
                      .replace("STALE", "old"), encoding="utf-8")
    problems = check_claims.benchmark_staleness_admitted(root)
    assert problems and "--stale-ok" in problems[0]


def test_a_fresh_replay_needs_no_admission(tmp_path):
    root = _tree(tmp_path, ".github/workflows/ci.yml")
    ci = root / ".github" / "workflows" / "ci.yml"
    ci.write_text(ci.read_text(encoding="utf-8")
                  .replace(" --stale-ok", ""), encoding="utf-8")
    assert check_claims.benchmark_staleness_admitted(root) == []


def test_a_stale_cost_multiple_is_refused(tmp_path):
    """The exact defect the audit found: prose arithmetic ('3-4x') beside a
    table measuring 12.7x."""
    root = _tree(tmp_path, "docs/PANEL.md", "docs/FAQ.md")
    faq = root / "docs" / "FAQ.md"
    faq.write_text(faq.read_text(encoding="utf-8").replace(
        "12× the single-run input tokens",
        "3× the single-run input tokens"), encoding="utf-8")
    problems = check_claims.panel_cost_multiple(root)
    assert problems and "3×" in problems[0] and "12.7×" in problems[0]


def test_a_missing_measured_table_is_refused(tmp_path):
    """Prose pointing at a table that is gone is a citation to nothing."""
    root = _tree(tmp_path, "docs/PANEL.md", "docs/FAQ.md")
    panel = root / "docs" / "PANEL.md"
    text = panel.read_text(encoding="utf-8")
    panel.write_text("\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("| panel")), encoding="utf-8")
    problems = check_claims.panel_cost_multiple(root)
    assert problems and "points at nothing" in problems[0]


def test_a_documented_but_unbuilt_mcp_surface_is_refused(tmp_path):
    root = _tree(tmp_path, "deckscope/mcp_server.py")
    src = root / "deckscope" / "mcp_server.py"
    src.write_text(src.read_text(encoding="utf-8")
                   .replace("market_reports", "mkt_rpts"), encoding="utf-8")
    problems = check_claims.mcp_surface_alignment(root)
    assert problems and "never mentions it" in problems[0]


def test_a_promised_but_unsupported_format_is_refused(tmp_path):
    root = _tree(tmp_path, "docs/FIRST_RUN.md")
    doc = root / "docs" / "FIRST_RUN.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace(
        "decks all work", "and Keynote decks all work"), encoding="utf-8")
    problems = check_claims.deck_formats_as_documented(root)
    assert problems and "keynote" in problems[0]


def test_a_drifted_lead_is_refused(tmp_path):
    root = _tree(tmp_path, "pyproject.toml", "README.md")
    py = root / "pyproject.toml"
    py.write_text(py.read_text(encoding="utf-8").replace(
        "traceable", "linkable"), encoding="utf-8")
    problems = check_claims.lead_claims_match(root)
    assert problems and "traceable" in problems[0]


def test_a_crashing_check_is_a_failure_not_a_pass(tmp_path):
    """The checker must not launder its own bugs — the same rule the report
    pipeline lives by."""
    original = check_claims.CHECKS
    check_claims.CHECKS = [lambda root: (_ for _ in ()).throw(TypeError("x"))]
    try:
        problems = check_claims.run(tmp_path)
    finally:
        check_claims.CHECKS = original
    assert problems and "TypeError" in problems[0]
