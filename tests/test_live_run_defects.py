"""Every defect the first live runs exposed, pinned.

These were all found by driving the pipeline with a real model rather than by
reading the code, and every one of them was invisible to the test suite that
existed at the time. That is the point of the file: each test below is a
failure that shipped, ran, and produced a plausible-looking wrong answer.

They share a shape worth naming, because it is the shape this repository keeps
producing. In every case the system had two different situations it could not
tell apart, and rendered the worse one as the better:

    a search that failed          → a citable source
    two companies' shares         → two sources disagreeing
    two firms sizing one market   → two different subjects, not compared
    a fact nobody publishes       → a sourced figure reading "n/a"
    one disagreement              → three disagreements
    a NameError                   → a clean lint report

None of these is a crash. All of them are the system being confidently wrong
in a way a reader cannot see, which is the only failure mode that actually
matters for a research tool.
"""
import ast
import os
import subprocess
import sys
from pathlib import Path

try:                                    # pragma: no cover
    import pytest
except ImportError:                      # pragma: no cover
    pytest = None                        # the suite runs without it below

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.corpus import gather
from deckscope.research.base import Researcher, SearchResult
from deckscope.research.findings import FindingRegistry
from deckscope.research.metrics import classify, comparable
from deckscope.security.policy import SecurityPolicy
from marketreport.dimensions import PRICE_LEVEL, get as get_dimension
from marketreport.panel import ABSENT, SOURCED
from marketreport.shaper import build_panel


# --------------------------------------------------------------- retrieval

class _Flaky(Researcher):
    """Fails on any query containing 'boom'."""

    name = "flaky"

    def search(self, query, max_results=8):
        if "boom" in query:
            raise RuntimeError("No answer appeared within 45s.")
        return [SearchResult("Real page", "https://example.org/x", "a fact",
                             None, query)]


def test_a_failed_search_never_becomes_a_citable_source():
    """The live run handed the reader a Python timeout as source [S1].

    `search_many` caught the exception and put its text in `snippet`, which
    made the row an ordinary result: registered, given a citation ID, and
    shown to the reader as research material about the market.
    """
    corpus = gather(_Flaky(), ["boom please", "fine query"], SecurityPolicy())
    assert not any("search failed" in s.title for s in corpus.registry.sources)
    assert corpus.retrieved == 1
    assert len(corpus.failures) == 1
    assert "45s" in corpus.failures[0]["error"]


def test_a_total_outage_yields_no_sources_and_records_why():
    corpus = gather(_Flaky(), ["boom one", "boom two"], SecurityPolicy())
    assert len(corpus.registry.sources) == 0
    # Not silence. A corpus reporting zero sources after a backend failure is
    # describing the network, and whatever consumes it has to be able to tell
    # that apart from a market nobody covers.
    assert len(corpus.failures) == 2


# ------------------------------------------------------------ disagreement

def _shares() -> FindingRegistry:
    registry = FindingRegistry()
    common = dict(question_id="Q1", unit="%", beat="competitors",
                  source_ids=["S2"])
    registry.add("WS Audiology holds approximately 27% of the global hearing "
                 "aid market.", value_text="27%", **common)
    registry.add("GN Group holds approximately 17% of the global hearing aid "
                 "market.", value_text="17%", **common)
    registry.add("Sonova holds approximately 25% of the global hearing aid "
                 "market.", value_text="25%", **common)
    registry.add("Sonova Holding AG holds approximately 8% of the global "
                 "hearing aid market.", value_text="8%", question_id="Q1",
                 unit="%", beat="competitors", source_ids=["S9"])
    return registry


def _contested(registry: FindingRegistry) -> set:
    registry.detect_contradictions()
    return {tuple(sorted((a.value_text, b.value_text)))
            for a, b in registry.contested()}


def test_two_companies_are_not_a_disagreement():
    """The run printed: contested: F2 (~27%) and F4 (~17%) disagree.

    F2 was WS Audiology and F4 was GN Group. One question about who holds what
    share returns one finding per company, and grouping on question_id alone
    made every company's share contradict every other one.
    """
    assert ("17%", "27%") not in _contested(_shares())


def test_the_same_company_across_two_sources_still_is_one():
    """The fix must not buy quiet by suppressing real conflicts."""
    assert ("25%", "8%") in _contested(_shares())


def test_a_publisher_is_not_the_subject_of_its_own_finding():
    """The first entity fix read "Grand View Research estimates..." as being
    ABOUT Grand View Research, so five firms sizing one market became five
    different subjects. The 2:1 spread — the most important fact in the
    section — was silently dropped, and the only pair flagged survived by the
    accident of both firms having "Research" in their names.
    """
    low = classify("IMARC Group puts the global hearing aid market at USD 7.5 "
                   "billion in 2025.", unit="USD")
    high = classify("Fortune Business Insights puts the global hearing aids "
                    "market at USD 15.11 billion in 2025.", unit="USD")
    assert low.entity == frozenset()
    assert high.entity == frozenset()
    assert comparable(low, high)[0]

    # And a genuine subject is still read as one.
    holder = classify("WS Audiology holds approximately 27% of the global "
                      "hearing aid market.", unit="%")
    assert "audiology" in holder.entity


def test_the_market_size_spread_is_raised_not_suppressed():
    registry = FindingRegistry()
    sizing = dict(question_id="Q9", unit="USD", beat="sizing")
    registry.add("IMARC Group puts the global hearing aid market at USD 7.5 "
                 "billion in 2025.", value_text="$7.5B", source_ids=["S10"],
                 **sizing)
    registry.add("Fortune Business Insights puts the global hearing aids "
                 "market at USD 15.11 billion in 2025.", value_text="$15.11B",
                 source_ids=["S8"], **sizing)
    assert ("$15.11B", "$7.5B") in _contested(registry)


# ---------------------------------------------------------------- shaping

class _Absent:
    """An established absence, as the reader records one."""

    id = "F1"
    statement = "No tracker publishes whether these shares are units or revenue."
    value = None
    value_text = "n/a"
    unit = "n/a"
    as_of = "2026-08"
    method = "absent"
    # It cites the sources it CHECKED. That is what made keying provenance off
    # source_ids alone render it as a sourced figure.
    source_ids = ["S1", "S6", "S7"]
    note = "Asked twice against different sources and unresolved both times."
    confidence = "high"


def test_an_established_absence_is_not_a_sourced_figure():
    """Three of ten headline figures in the live run were absences drawn as
    measured facts — including the one saying the basis is unpublished. The
    provenance guarantee exactly inverted: the reader was told the gap had
    been measured.
    """
    panel = build_panel(
        "who leads", [_Absent()],
        {"headline": "x", "form": "stat", "series": [],
         "figures": [{"label": "Basis of the share figures",
                      "finding_id": "F1"}]},
        agent="market-share")
    figure = panel.figures[0]
    assert figure.state == ABSENT
    assert figure.state != SOURCED
    assert not figure.value_text
    assert "unresolved" in figure.because


# -------------------------------------------------------------- dimensions

def test_a_specialist_resolves_values_in_its_own_dimension():
    """`--measures wholesale` on market-size was resolved against the basis
    vocabulary while market share was the only specialist, which rejects every
    price level there is.
    """
    resolved, unknown = PRICE_LEVEL.resolve(["wholesale", "revenue"])
    assert [o.key for o in resolved] == ["wholesale"]
    assert unknown == ["revenue"]      # a basis, not a price level


def test_an_open_dimension_accepts_what_cannot_be_enumerated():
    jurisdiction = get_dimension("jurisdiction")
    assert jurisdiction.open
    resolved, unknown = jurisdiction.resolve(["Ireland", "European Union"])
    assert unknown == []
    assert [o.key for o in resolved] == ["ireland", "european_union"]


def test_the_measures_shim_and_the_dimension_are_one_definition():
    """Two copies of "share of units sold" diverging quietly is the drift the
    dimension module exists to stop, so the old door must read through it.
    """
    from marketreport.dimensions import BASIS
    from marketreport.measures import UNITS, registered

    assert UNITS is BASIS.get("units")
    assert [m.key for m in registered()] == [o.key for o in BASIS.options]


def test_every_specialist_declares_a_dimension():
    """A specialist without one cannot be scoped, so a brief naming values for
    it fails at dispatch rather than at review.
    """
    from marketreport.specialists import registered as specialists

    for spec in specialists():
        assert spec.dimension, f"{spec.name} declares no dimension"
        assert get_dimension(spec.dimension) is not None, (
            f"{spec.name} names dimension {spec.dimension!r}, which is not "
            f"registered")


def test_the_report_catalogue_matches_the_specialists():
    """Growth had a specialist and no report type, so `deckscope reports` did
    not list it while `--report growth` ran it.

    `industry-report` is the deliberate exception: it is a twelve-section brief
    with no specialist of its own, and `deckscope reports` says so on its line
    rather than leaving a blank where the scoping would be.
    """
    from marketreport.reports import registered as report_types
    from marketreport.specialists import registered as specialists

    types = {r.key for r in report_types()}
    agents = {s.name for s in specialists()}
    assert agents - types == set(), "a specialist nobody can find in the catalogue"
    assert types - agents == {"industry-report"}


def test_the_registry_answers_the_same_in_any_import_order():
    """It did not. A fresh process asking `reports.registered()` first saw five
    types; going through the CLI saw seven, because `growth` is registered by
    `catalog` and `industry-report` by `s1` and neither had a reason to load.
    Same function, same process, two different answers about what this software
    can produce — and every caller looked correct.
    """
    import subprocess as _sp

    root = Path(__file__).resolve().parent.parent
    script = ("import sys; sys.path.insert(0, %r)\n"
              "from marketreport.reports import registered\n"
              "print(len(registered()))\n" % str(root))
    first = _sp.run([sys.executable, "-c", script], capture_output=True,
                    text=True, cwd=str(root))
    assert first.returncode == 0, first.stderr
    assert int(first.stdout.strip()) == 7, (
        "reports.registered() must load every registrar itself, not rely on "
        "the caller having imported the right modules first")


# ------------------------------------------------------------------- lint

def test_the_linter_catches_a_name_that_does_not_exist():
    """It reported files clean that raised NameError the moment they ran —
    three times in one day, the third being a `red()` call in the branch that
    fires when every evaluation case has crashed.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import lint

    tree = ast.parse(
        "def build(x):\n"
        "    return Figure(label=x, state=ABSENT)\n"
        "def by_measure(names):\n"
        "    return getattr(args, 'report', None)\n")
    found = {message for _, message in lint._undefined(tree)}
    assert "undefined name: ABSENT" in found
    assert "undefined name: args" in found


def test_the_linter_does_not_cry_wolf_on_ordinary_code():
    """Getting the check quiet mattered as much as getting it right: the first
    version reported 3255 problems on a clean repository, 2457 of them an
    undefined `self`. A checker nobody trusts gets worked around.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import lint

    tree = ast.parse(
        "import os\n"
        "TOP = 1\n"
        "class Thing:\n"
        "    attr = TOP\n"
        "    def method(self, query, *rest, **kw):\n"
        "        inner = [q for q in query if q]\n"
        "        def nested(extra=TOP):\n"
        "            return self.attr + extra + inner[0] + len(rest) + len(kw)\n"
        "        return nested()\n"
        "def uses_os():\n"
        "    with open('x') as handle:\n"
        "        for line in handle:\n"
        "            try:\n"
        "                return os.path.join(line)\n"
        "            except OSError as exc:\n"
        "                return str(exc)\n")
    assert list(lint._undefined(tree)) == []


def test_the_repository_itself_is_clean():
    """The gate, run as a test, so a broken name fails the suite and not only
    the lint job.
    """
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "lint.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(root))
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":  # pragma: no cover
    # Delegates to the real runner, which collects AFTER the module is fully
    # imported. The block this replaces ran the tests itself from its own
    # lexical position mid-file — so the thirty-one tests appended below it
    # over a working day never executed, while it printed "0 failed". A gate
    # that runs part of itself and reports on all of itself is the exact
    # defect shape this file exists to pin.
    import runpy

    sys.argv = [sys.argv[0], "--only", "live_run_defects"]
    runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts"
                       / "run_tests.py"), run_name="__main__")


# ------------------------------------------------- the market-size live run

class _Fact:
    """A finding, as the reader records one."""

    metric = None

    def __init__(self, statement, value, value_text, unit="USD"):
        self.statement, self.value = statement, value
        self.value_text, self.unit = value_text, unit


def _size_spread(findings) -> bool:
    from marketreport.catalog import _size_check
    from marketreport.panel import Panel

    result = _size_check(findings=findings, panel=Panel(question="q"),
                         market="hearing aids")
    return any("disagree by more than half" in c for c in result["caveats"])


def test_a_unit_price_is_not_a_market_total():
    """The market-size run reported "published totals for this market
    disagree, from $774 to $400-3500" — comparing the average wholesale
    invoice for ONE hearing aid against the price range for ONE hearing aid,
    and calling both market sizes. Same currency unit, nine orders of
    magnitude apart.
    """
    assert not _size_spread([
        _Fact("The average wholesale invoice for a hearing aid was $774 in "
              "2019.", 774, "$774"),
        _Fact("Single-unit wholesale prices range from $400 to $3,500 per "
              "hearing aid.", 1950, "$400-3500"),
    ])


def test_two_real_totals_still_disagree():
    assert _size_spread([
        _Fact("IMARC Group puts the global hearing aid market at USD 7.5 "
              "billion in 2025.", 7.5, "$7.5B"),
        _Fact("The global hearing aids market was USD 15.11 billion in 2025.",
              15.11, "$15.11B"),
    ])


def test_a_caption_promising_a_share_over_a_non_share_is_flagged():
    """The run drew a row reading "Retail share of channel — 3-4x". Every part
    of it was sourced and traceable; the row still told the reader something
    false, and the citation led to a statement that did not say it.
    """
    from marketreport.shaper import _mislabelled

    markup = _Fact("Dispensers mark hearing aids up three to four times.",
                   3.5, "3-4x", unit="n/a")
    assert _mislabelled("Retail share of channel", markup)
    # A caption that promises a share over an actual share is fine, and so is
    # one that promises nothing.
    real = _Fact("Retail stores were 70.6% of the channel.", 70.6, "70.6%",
                 unit="%")
    assert not _mislabelled("Retail share of channel", real)
    assert not _mislabelled("Dispensing markup", markup)


# ------------------------------------------- sizing as three separate terms

def _sized(findings):
    from marketreport.catalog import _size_check
    from marketreport.panel import Panel
    return _size_check(findings=findings, panel=Panel(question="q"),
                       market="scrubs", place="United States")


class _Term(_Fact):
    """A finding with the fields the term sorter reads."""

    def __init__(self, statement, value, value_text, unit):
        super().__init__(statement, value, value_text, unit)
        self.source_ids, self.as_of, self.method = ["S1"], "2025", "search"


def test_three_sourced_terms_produce_the_arithmetic():
    """FIGS's actual sizing, reproduced: 20 million healthcare professionals,
    85% who buy their own uniforms, $120 a head. The point is not the total —
    it is that a reader can disagree with each factor.
    """
    result = _sized([
        _Term("There are 20 million healthcare professionals in the United "
              "States.", 20_000_000, "20m", "count"),
        _Term("85% of them buy their own uniforms.", 85.0, "85%", "%"),
        _Term("Average annual spend is $120 per person.", 120.0, "$120",
              "USD"),
    ])
    derived = [f for f in result["figures"] if f.state == "derived"]
    assert len(derived) == 1
    assert derived[0].value == 2_040_000_000
    assert set(derived[0].operands) == {"count", "rate", "value"}
    assert "×" in derived[0].how


def test_a_computed_total_is_not_also_reported_absent():
    """The first version added "A total for this market — ABSENT" whenever no
    publisher had one, even when the same function had just derived a total
    from three sourced terms four lines earlier.
    """
    result = _sized([
        _Term("There are 20 million healthcare professionals in the United "
              "States.", 20_000_000, "20m", "count"),
        _Term("85% of them buy their own uniforms.", 85.0, "85%", "%"),
        _Term("Average annual spend is $120 per person.", 120.0, "$120",
              "USD"),
    ])
    absent = [f for f in result["figures"] if f.state == "absent"]
    assert not absent


def test_a_missing_term_is_named_rather_than_substituted():
    """The hearing-aid case: the count is free and exact, the value does not
    exist worldwide after 2019. The useful output is which factor is missing
    and where it would come from — not a total built on a substitute.
    """
    result = _sized([
        _Term("EHIMA members sold 23.16 million hearing aids in 2025.",
              23_160_000, "23.16m", "count"),
    ])
    assert not [f for f in result["figures"] if f.state == "derived"]
    gap = " ".join(result["caveats"])
    assert "what each one is worth per year" in gap
    assert "commissioned studies exist to sell" in gap


def test_a_market_total_is_never_read_as_the_value_term():
    """A published total is an OUTPUT of the arithmetic. Feeding one in as the
    per-unit value would multiply a total by a count.
    """
    from marketreport.catalog import _per_unit

    assert not _per_unit("IMARC Group puts the global hearing aid market at "
                         "USD 7.5 billion in 2025.")
    assert _per_unit("Average annual spend is $120 per person.")
    assert _per_unit("agilon takes $10,000 of revenue per member.")


# ------------------------------------------------- measured versus reasoned

def test_a_reasoned_report_says_so_before_anything_else():
    """Barriers to entry and what substitutes for a market are arguments;
    nobody publishes a number for either. Set in the same typeface with
    citations underneath, an argument is indistinguishable from a
    measurement — so the report has to say which it is, first.
    """
    from marketreport.specialists import EVIDENCE_NOTES, get

    landscape = get("competitive-landscape")
    assert landscape.evidence == "mixed"
    assert "mixed" in EVIDENCE_NOTES

    # And a measured job does not carry the disclaimer, or it means nothing.
    assert get("market-share").evidence == "measured"
    assert EVIDENCE_NOTES.get("measured") is None


def test_every_specialist_declares_how_it_knows():
    from marketreport.specialists import registered

    for spec in registered():
        assert spec.evidence in ("measured", "reasoned", "mixed"), spec.name


# --------------------------------------------------------- the front door

def _cli(*argv) -> "subprocess.CompletedProcess":
    root = Path(__file__).resolve().parent.parent
    return subprocess.run(
        [sys.executable, "-m", "deckscope.cli", *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(root), stdin=subprocess.DEVNULL,
        timeout=120)


def test_bare_invocation_does_not_block_on_stdin():
    """It launched the seven-question setup wizard, which blocks reading
    stdin — so any non-interactive invocation hung with no output and no way
    to know why. Typing a command's name to see what it does is also not
    consent to be interrogated.
    """
    result = _cli()
    assert result.returncode == 0
    assert "DeckScope" in result.stdout
    assert "deckscope setup" in result.stdout      # offered, not started
    assert "1 of 7" not in result.stdout           # the wizard did not run


def test_a_misspelled_report_type_is_not_reported_as_a_missing_api_key():
    """`--report nonsense` fell through to the provider check and came back
    "no AI model is connected", sending the user to fix their credentials when
    the actual problem was one misspelled word.
    """
    result = _cli("ask", "hearing aids", "--report", "nonsense")
    assert result.returncode == 2
    assert "no report type called 'nonsense'" in result.stdout
    assert "API key" not in result.stdout
    # And it lists the real ones rather than making the user go looking.
    assert "market-size" in result.stdout


def test_a_value_from_the_wrong_dimension_says_where_it_belongs():
    """Reaching for another report's vocabulary is the commonest mistake, so
    the message names where the value actually lives.
    """
    result = _cli("ask", "hearing aids", "--report", "market-size",
                  "--measures", "units")
    assert result.returncode == 2
    assert "not one of its values" in result.stdout
    assert "wholesale" in result.stdout
    assert "is a value of 'basis'" in result.stdout
    assert "market-share" in result.stdout
    assert "API key" not in result.stdout


def test_the_commands_the_front_page_suggests_actually_run():
    """The orientation screen tells a new user to run two things. Suggesting a
    command that does not work is the same class of claim as any other.
    """
    assert _cli("demo").returncode == 0
    assert _cli("ask", "market share of cell phones", "--demo").returncode == 0


# ---------------------------------------------------- the --report flag

def test_report_is_not_silently_ignored():
    """`--report` was parsed, validated against the registry, and then dropped
    unless `--measures` was also given — and the demo path returned before
    either was read. So `--report growth`, `--report regulation` and
    `--report demographics` each produced the SAME market-share panel, down to
    the identical list of questions they failed to answer.

    A flag that is accepted and then discarded is worse than one rejected: the
    user has no way to find out it did nothing.
    """
    result = _cli("ask", "market share of cell phones",
                  "--report", "competitive-landscape", "--demo")
    assert result.returncode == 0
    assert "competitive-landscape:" in result.stdout
    assert "market-share:" not in result.stdout


def test_the_demo_refuses_a_report_its_pages_cannot_answer():
    """The recorded corpus is five smartphone market-share articles. Run a
    regulation report against them and every stage works, producing "Samsung
    leads on units; Apple leads on revenue" under a regulation heading — a
    confident answer to a question the sources never addressed.

    The demo is what somebody runs to learn what the tool does, so that was
    not a thin answer, it was a false lesson about four of seven report types.
    """
    result = _cli("ask", "market share of cell phones",
                  "--report", "regulation", "--demo")
    assert result.returncode == 2
    assert "cannot support a 'regulation' report" in result.stdout
    assert "Samsung" not in result.stdout
    # And it says which ones do work rather than leaving the user guessing.
    assert "market-share" in result.stdout


def test_the_demo_still_runs_what_it_can():
    for report in ("market-share", "competitive-landscape"):
        result = _cli("ask", "market share of cell phones",
                      "--report", report, "--demo")
        assert result.returncode == 0, f"{report}: {result.stdout[-400:]}"


def test_every_producer_returns_the_shape_the_printer_reads():
    """Twice a new producer returned a result without `request`, and
    `_finish_ask` raised KeyError AFTER the research had been paid for — the
    most expensive moment to discover a missing dictionary key.
    """
    from deckscope import cli

    try:
        cli._finish_ask(object(), {"panels": []})
    except RuntimeError as exc:
        assert "_completed()" in str(exc)
    else:                                          # pragma: no cover
        raise AssertionError("a malformed result was accepted")


# --------------------------------------------------- the evaluation harness

def _case():
    from marketreport.cases import Case, Expect, Trap

    return Case(
        id="toy", name="toy", market="widgets", report="market-share",
        pages=[{"title": "t", "url": "https://e.org", "published": "2026-01-01",
                "snippet": "The market was 10 million units in 2025."}],
        expect=[Expect(r"10 million", "the only real fact", weight=1.0)],
        traps=[Trap(r"20 million", "no source says twenty")],
        absences=[Expect(r"not established", "must say what it lacks")])


def test_the_scorer_can_actually_fail():
    """A harness that cannot fail is decoration. Checked first, because every
    later assertion is worthless if this one is not true.
    """
    from marketreport.cases import score

    perfect = score(_case(), "The market was 10 million units. Growth was "
                             "not established.")
    assert perfect.recall == 1.0 and perfect.clean and perfect.passed

    empty = score(_case(), "")
    assert empty.recall == 0.0 and not empty.passed


def test_a_fabrication_is_not_offset_by_recall():
    """The asymmetry the harness exists for. A report that finds everything
    and invents one thing must not outrank one that finds less and invents
    nothing — the reader cannot tell which sentence was invented.
    """
    from marketreport.cases import score

    invents = score(_case(), "The market was 10 million units, or 20 million "
                             "by another count. Growth was not established.")
    assert invents.recall == 1.0        # found every fact
    assert not invents.clean            # and is still a failure
    assert not invents.passed
    assert "no source says twenty" in invents.fabricated[0][1]


def test_an_omitted_absence_fails_even_with_full_recall():
    """Saying nothing about what could not be established is its own failure:
    the reader is left to assume the gap is zero.
    """
    from marketreport.cases import score

    quiet = score(_case(), "The market was 10 million units.")
    assert quiet.recall == 1.0
    assert quiet.clean
    assert not quiet.passed
    assert quiet.absences_omitted


def test_a_case_with_no_corpus_is_refused():
    """It would grade a report against nothing and pass whatever it saw."""
    from marketreport.cases import Case, Expect

    try:
        Case(id="x", name="x", market="m", report="market-share",
             expect=[Expect("a", "b")])
    except ValueError as exc:
        assert "no recorded pages" in str(exc)
    else:                                          # pragma: no cover
        raise AssertionError("a case with no corpus was accepted")


def test_a_case_that_only_sets_traps_is_refused():
    """Traps alone reward silence — a report saying nothing would score
    perfectly.
    """
    from marketreport.cases import Case, Trap

    try:
        Case(id="x", name="x", market="m", report="market-share",
             pages=[{"title": "t", "url": "u", "snippet": "s"}],
             traps=[Trap("a", "b")])
    except ValueError as exc:
        assert "rewards silence" in str(exc)
    else:                                          # pragma: no cover
        raise AssertionError("a trap-only case was accepted")


def test_every_case_names_real_pages_with_urls():
    """The corpus is the ground truth. A case built on invented material
    grades the fixture, which is the failure CRITIQUE.md #1 already records
    once for the Census demo.
    """
    from marketreport.cases import registered

    for case in registered():
        assert case.pages, case.id
        for page in case.pages:
            assert page.get("url", "").startswith("http"), case.id
            assert len(page.get("snippet", "")) > 80, case.id
        assert case.traps, f"{case.id} sets no traps"


def test_the_harness_says_when_a_score_measures_the_fixture():
    """Run against the offline mock every case fails, which reads as "the
    specialists are broken" and means "the stub cannot answer". Publishing
    that number without saying so would be the same class of thing the
    harness exists to catch.
    """
    from deckscope.providers.mock_provider import MockProvider
    from marketreport.cases.runner import caveat

    said = caveat(MockProvider())
    assert "measure the fixture" in said
    assert caveat(object()) == ""


def test_check_runs_from_the_command_line():
    # Both directions of the gate, because each alone can be faked: an
    # exit-1-always harness looks rigorous, an exit-0-always one looks
    # healthy. The growth case passes under the mock (honest partial recall,
    # nothing invented — it used to fail only because the trap convicted the
    # question preamble); the regulation case genuinely fails on recall.
    result = _cli("check", "--demo", "--only", "growth")
    assert "growth-hearing-aids-worldwide" in result.stdout
    assert "recall" in result.stdout
    assert result.returncode == 0, "a passing case must be exit 0"

    failing = _cli("check", "--demo", "--only", "regulation")
    assert failing.returncode == 1, (
        "a failing case must be non-zero, so a gate built on this cannot be "
        "satisfied by a report that invents things confidently")


# -------------------------------------------- the harness judged itself

def test_a_stated_absence_does_not_trip_the_trap_it_denies():
    """The growth case REQUIRES the report to say "no forecast is published"
    (its absences check) and its trap pattern contains the word "forecast" —
    so the honest sentence satisfied the absence and tripped the trap in the
    same breath. A perfect report could not pass: recall 100%, absence
    stated, FABRICATED anyway. The judge convicted the innocent for
    complying with the court.
    """
    from marketreport.cases import get, score

    case = get("growth-hearing-aids-worldwide")
    honest = ("EHIMA member unit sales rose from 14.12 million in 2020 to "
              "23.16 million in 2025, up 2.1% in the most recent year. The "
              "figures are net wholesale units sold to dispensers. No "
              "forecast is published, and EHIMA does not publish a "
              "per-manufacturer split.")
    result = score(case, honest)
    assert result.clean, result.fabricated
    assert result.passed, result.summary()


def test_an_actual_forecast_is_still_convicted():
    """The fix must not buy the acquittal by blinding the trap."""
    from marketreport.cases import get, score

    case = get("growth-hearing-aids-worldwide")
    result = score(case, "No forecast is published; units were 14.12 million "
                         "in 2020 and 23.16 million in 2025 per EHIMA, "
                         "wholesale, up 2.1%. The market is projected to "
                         "reach 30 million units by 2030.")
    assert not result.clean


def test_negation_after_the_claim_does_not_excuse_it():
    """"Will reach 30 million, not 25 million" is still a forecast. Only a
    denial BEFORE or INSIDE the matched span reads as denying the claim.
    """
    from marketreport.cases.schema import _asserted

    assert not _asserted(r"forecast", "No forecast is published.")
    assert _asserted(r"will reach", "Units will reach 30 million, not 25.")
    assert not _asserted(r"worldwide",
                         "The $774 figure is US-only, not worldwide.")


def test_the_question_line_is_not_an_assertion():
    """The growth specialist's job description says "on whose forecast", and
    the rendered panel prints it as "Asked: How fast a market is growing …
    on whose forecast". The forecast trap convicted that line — the report
    was FABRICATED before the model under test said anything at all. Same
    class as the denial bug two tests up, in interrogative form: a question
    is not a claim. The fix strips only the Asked:/Answered by: preamble
    from the trap's jurisdiction; headline and findings stay inside it.
    """
    from marketreport.cases import suite
    from marketreport.cases.runner import run_case
    from deckscope.providers import get_provider

    provider = get_provider(type("C", (), {"name": "mock", "model": None,
                                           "temperature": 0.0})())
    result = run_case(suite.GROWTH_WORLDWIDE, provider=provider)
    assert result.clean, (
        f"the question preamble convicted the report: {result.fabricated}")


def test_the_two_human_read_types_now_have_graded_cases():
    """The README table admitted the coverage was backwards: the two types
    with the most human attention (market-share, market-size) had no graded
    case, while the three with cases had no human read. Every specialist-run
    type now has both a case and a validated pair of directions — an honest
    report passes, the characteristic fabrication is convicted.
    """
    from marketreport.cases import get, score

    size = get("market-size-hearing-aids-wholesale")
    share = get("market-share-smartphones-q2-2026")
    assert size is not None and share is not None

    honest_size = (
        "EHIMA members sold 23.16 million hearing aids in 2025 at wholesale. "
        "The only per-unit price found is $774, from 2019 and the United "
        "States only — no worldwide value is published. Published totals of "
        "$7.5 billion and $9.1 billion state no price level.")
    assert score(size, honest_size).passed

    # The forbidden multiplication: a worldwide 2025 count times a US 2019
    # price. Any $10-19B total proves it happened, because no source says one.
    artefact = honest_size + " The wholesale market is worth $17.9 billion."
    assert not score(size, artefact).clean

    honest_share = (
        "Samsung leads on units with 22% (SAG) or 22.6% (IDC), while holding "
        "16% of revenue. Apple holds 20.1% of units and 49% of revenue "
        "(Counterpoint), on a $946 average selling price.")
    assert score(share, honest_share).passed

    # The blend: 22.3% is the average of two trackers and exists in no source.
    assert not score(share, honest_share
                     + " Averaged across trackers, Samsung holds 22.3%.").clean
    # The crown: promoting the unit lead to a revenue lead.
    assert not score(share, honest_share
                     + " Samsung leads on revenue as well.").clean


def test_every_specialist_run_type_has_a_graded_case():
    """The registry-drift lesson, applied to coverage: asserted, so a new
    specialist without a case fails the suite instead of shipping unchecked
    the way the first four did.
    """
    from marketreport.cases import registered as cases
    from marketreport.specialists import registered as specialists

    covered = {c.report for c in cases()}
    for spec in specialists():
        assert spec.name in covered, (
            f"{spec.name} has no graded case. Every report type before the "
            f"harness shipped unchecked and averaged two defects each when "
            f"finally run; a case is the price of registration now.")


def test_an_uncited_load_bearing_figure_fails_the_case():
    """The first full docket run PASSED a case with "1 uncited": a figure its
    own Expect marked must_cite, present but unattributed, flagged in the
    summary and waved through the verdict. The product's one-line promise is
    that every figure is traceable to its source; a grader that treats
    untraceable as a footnote is grading a different product.
    """
    from marketreport.cases import Case, Expect, score

    case = Case(id="c", name="c", market="m", report="market-share",
                pages=[{"title": "t", "url": "https://e.org",
                        "published": "2026-01-01",
                        "snippet": "The market was 10 million units in 2025, "
                                   "per a named tracker's quarterly count."}],
                expect=[Expect(r"10 million", "the fact", must_cite=True)])
    # Present in the report but absent from the cited portion:
    result = score(case, "The market was 10 million units.", cited="S1 blank")
    assert result.uncited
    assert not result.passed
    # And cited, it passes.
    assert score(case, "The market was 10 million units.",
                 cited="10 million units S1").passed


# --------------------------------------------------- the guest's first run

def test_an_env_configured_provider_counts_as_configured():
    """DECKSCOPE_PROVIDER is a documented configuration layer and every
    ask/report path honours it — but is_configured() only looked for the
    wizard's file, so `deckscope run` with the env set said "isn't set up
    yet" and pointed at a seven-question wizard to answer a question the
    environment had already answered. Found walking the exact path a
    first-time guest walks.
    """
    import tempfile

    root = Path(__file__).resolve().parent.parent
    # tempfile paths, not /tmp: the machine this trial actually happens on is
    # Windows, and the suite's own audit test rejects hard-coded POSIX
    # temporary directories — a rule that caught this very test the first
    # time the whole suite could run.
    env = dict(os.environ, DECKSCOPE_PROVIDER="mock", DECKSCOPE_RESEARCH="none",
               HOME=tempfile.mkdtemp(prefix="ds_guest_home_"))
    result = subprocess.run(
        [sys.executable, "-m", "deckscope.cli", "run",
         "deckscope/evaluation/suite/decks/inflated_tam.md",
         "--format", "md", "--out", tempfile.mkdtemp(prefix="ds_guest_out_")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(root), env=env,
        stdin=subprocess.DEVNULL, timeout=400)
    assert "isn't set up yet" not in result.stdout
    assert result.returncode == 0, result.stdout[-500:]


def test_a_mock_provider_on_a_real_deck_banners_loudly():
    """The mock's replies are canned analysis of a fictional company,
    whatever deck it is given. Reached through saved settings or the env, it
    produced specific-sounding advice about products the deck never mentions,
    disclosed only in a footer. --demo banners this; run did not. And the
    first fix patched exactly one of the three commands that resolve config
    the same way — the research command, not the run command being tested —
    so the banner lives in one helper called at all three sites now.
    """
    import tempfile

    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, DECKSCOPE_PROVIDER="mock", DECKSCOPE_RESEARCH="none",
               HOME=tempfile.mkdtemp(prefix="ds_guest_home_"))
    result = subprocess.run(
        [sys.executable, "-m", "deckscope.cli", "run",
         "deckscope/evaluation/suite/decks/inflated_tam.md",
         "--format", "md", "--out", tempfile.mkdtemp(prefix="ds_guest_out_")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(root), env=env,
        stdin=subprocess.DEVNULL, timeout=400)
    assert "offline mock" in result.stdout
    assert "illustrative" in result.stdout


# ------------------------------------------------ the deck-to-briefs scoper

_SCOPER_DECK = {
    "company": {"name": "Northwind Ledger",
                "one_liner": "AI agents that run back-office workflows"},
    "market": {"category": "Workflow automation / agentic RPA",
               "tam_claimed": "$88B"},
    "claims": [{"type": "market-size", "load_bearing": "high",
                "claim": "The financial reconciliation software market is "
                         "$88B, growing at 31% CAGR"}],
}


def test_the_scoper_validates_everything_and_guesses_nothing():
    """The upstream the client specified from the start: read the deck, decide the
    market and its measures, hand off Briefs. Report types are validated
    against the specialist registry and values against each type's own
    dimension — anything unknown becomes a note, never a guess, because a
    guessed scope is the error the whole handoff exists to prevent.
    """
    from marketreport.scoping import briefs_from_deck

    class Good:
        def complete_json(self, s, u, **k):
            return {"market": "financial close and reconciliation software",
                    "place": "",
                    "definition": "narrower than the deck's own frame",
                    "reports": [
                        {"type": "market-size",
                         "values": ["wholesale", "bogus"]},
                        {"type": "nonsense-type", "values": ["x"]}]}

    briefs, notes = briefs_from_deck(_SCOPER_DECK, Good())
    assert [b.specialist for b in briefs] == ["market-size"]
    assert briefs[0].measures == ["wholesale"]
    # The boundary decision travels on the brief, so every panel it produces
    # carries the re-framing that shaped it.
    assert "narrower" in briefs[0].definition
    assert any("'bogus'" in n for n in notes)
    assert any("nonsense-type" in n for n in notes)


def test_a_scoper_that_cannot_scope_says_so_and_dispatches_nothing():
    """The mock answers every unknown prompt with {'note': 'mock', ...}. A
    scoper handed that must produce zero briefs and the reason — not invent a
    market to research, which would spend a full research budget on a guess.
    """
    from marketreport.scoping import briefs_from_deck

    class MockLike:
        def complete_json(self, s, u, **k):
            return {"note": "mock", "echo": u[:40]}

    class Broken:
        def complete_json(self, s, u, **k):
            raise RuntimeError("provider fell over")

    for provider in (MockLike(), Broken()):
        briefs, notes = briefs_from_deck(_SCOPER_DECK, provider)
        assert briefs == []
        assert notes and "no market reports were dispatched" in notes[0]


def test_the_deck_run_offers_and_honours_the_market_reports_flag():
    """Without the flag, one hint line. With it, the scoper section appears —
    and with the mock, it must be the honest refusal rather than a crash,
    because the first wiring referenced a variable _run never had and died
    AFTER the deck analysis was paid for.
    """
    import tempfile

    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, DECKSCOPE_PROVIDER="mock", DECKSCOPE_RESEARCH="none",
               HOME=tempfile.mkdtemp(prefix="ds_scope_home_"))

    def run(*extra):
        return subprocess.run(
            [sys.executable, "-m", "deckscope.cli", "run",
             "deckscope/evaluation/suite/decks/inflated_tam.md",
             "--format", "md", "--out",
             tempfile.mkdtemp(prefix="ds_scope_out_"), *extra],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(root), env=env,
            stdin=subprocess.DEVNULL, timeout=400)

    plain = run()
    assert plain.returncode == 0
    assert "--with-market-reports" in plain.stdout      # the offer

    flagged = run("--with-market-reports")
    assert flagged.returncode == 0, flagged.stdout[-500:]
    assert "Market reports" in flagged.stdout
    assert "no market reports were dispatched" in flagged.stdout
