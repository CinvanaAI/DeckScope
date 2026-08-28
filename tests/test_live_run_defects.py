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
        capture_output=True, text=True, cwd=str(root))
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":  # pragma: no cover
    # Runnable without pytest installed, because the environment that most
    # needs to run these — a clean box checking a release — may not have it.
    failed = 0
    for _name, _fn in sorted(dict(globals()).items()):
        if not _name.startswith("test_") or not callable(_fn):
            continue
        try:
            _fn()
            print(f"  PASS {_name}")
        except Exception as _exc:        # noqa: BLE001 - reporting, not handling
            failed += 1
            print(f"  FAIL {_name}: {type(_exc).__name__}: {_exc}")
    print(f"\n  {failed} failed")
    raise SystemExit(1 if failed else 0)


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
        capture_output=True, text=True, cwd=str(root), stdin=subprocess.DEVNULL,
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
