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
    """
    from marketreport.reports import registered as report_types
    from marketreport.specialists import registered as specialists

    types = {r.key for r in report_types()}
    agents = {s.name for s in specialists()}
    assert types == agents


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
