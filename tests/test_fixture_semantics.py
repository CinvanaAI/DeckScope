"""Golden tests for the demo fixture's parsers.

The advertised market demo produced a figure whose label described one
measurement while its value stored another — "Worldwide smartphone
shipments reached 277.5 mil…" labeled a 6.7% decline, stamped `sourced` and
`checkable: true` — and invented a company called No.1 from a rank token
(external audit findings #3). A demo is a release artifact: it teaches the
product's honesty bar to every first-time user, so its parsers get golden
assertions on the exact sentence shape that failed.
"""
from __future__ import annotations

IDC = ("Worldwide smartphone shipments reached 277.5 million units in "
       "Q2 2026, down 6.7% year-over-year, according to IDC. No.1 was "
       "Samsung with a 19.7% share; Apple held 15.7%.")


def test_count_figures_are_figures_with_count_units():
    """"277.5 million units" carried a count the pattern did not know, so
    the percentage beside it inherited the whole sentence as a label."""
    from deckscope.providers.mock_provider import _figures_in, _unit_of

    figures = _figures_in(IDC)
    assert "277.5 million units" in figures
    assert _unit_of("277.5 million units") == "units"


def test_no_figure_is_stamped_usd_by_default():
    """Everything non-percentage used to become USD."""
    from deckscope.providers.mock_provider import _unit_of

    assert _unit_of("$47B") == "USD"
    assert _unit_of("6.7%") == "%"
    assert _unit_of("277.5 million units") == "units"
    assert _unit_of("1,200 units") == "units"


def test_each_figure_gets_a_statement_entailed_by_it():
    """Label/value semantic agreement: a statement must describe ITS figure,
    not every figure in the sentence."""
    from deckscope.providers.mock_provider import _figures_in, _statement_for

    for figure in _figures_in(IDC):
        statement = _statement_for(IDC, figure)
        assert figure in statement, (
            f"the statement for {figure!r} does not contain it: {statement!r}")
        others = [f for f in _figures_in(IDC) if f != figure]
        for other in others:
            assert other not in statement, (
                f"the statement for {figure!r} also carries {other!r} — the "
                f"two-numbers-one-label defect: {statement!r}")


def test_the_decline_keeps_its_subject_without_a_dangling_verb():
    from deckscope.providers.mock_provider import _statement_for

    statement = _statement_for(IDC, "6.7%")
    assert "smartphone shipments" in statement.lower(), (
        "the fragment clause must be re-anchored to what fell")
    assert "reached —" not in statement and not statement.rstrip().endswith(
        "reached"), f"dangling verb: {statement!r}"


def test_rank_tokens_are_not_companies():
    """"No.1 was Samsung" put a company called No.1 into a report, then
    asked the founder what position No.1 holds in this market."""
    from deckscope.providers.mock_provider import _org_names

    names = _org_names(IDC)
    assert "Samsung" in names and "Apple" in names
    assert not any(n.lower().startswith("no.") for n in names)
    assert "Worldwide" not in names, "a sentence-initial adjective is not a firm"
    for probe in ("Top10 dominates the sector.", "Q2 was strong for FY2026."):
        for name in _org_names(probe):
            assert name not in ("Top10", "Q2", "FY2026"), (
                f"rank/period token read as a company: {name}")


def test_trailing_punctuation_is_not_part_of_a_name():
    from deckscope.providers.mock_provider import _org_names

    assert "IDC" in _org_names(IDC)
    assert "IDC." not in _org_names(IDC)


if __name__ == "__main__":  # pragma: no cover
    import runpy
    import sys
    from pathlib import Path

    sys.argv = [sys.argv[0], "--only", Path(__file__).stem]
    runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts"
                       / "run_tests.py"), run_name="__main__")
