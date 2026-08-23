"""The panel: independent runs, cross-review, revision, consensus, metrics."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.config import Lens, OutputConfig, ProviderConfig, ResearchConfig, RunConfig
from deckscope.ensemble import Panel, measure_agreement, parse_panelist
from deckscope.research.base import Researcher, SearchResult
from deckscope.research.registry import register_researcher

DECK = Path(__file__).resolve().parent.parent / "deckscope" / "examples" / "sample_deck.md"


class PanelStubSearch(Researcher):
    name = "panel_stub"

    def search(self, query, max_results=8):
        # Deliberately *mixed* on one claim, so the panel has something real to
        # disagree about. An earlier version supplied a single unambiguous
        # sentence, and the panel only appeared to disagree because the fixture
        # overwrote a claim's assessment to manufacture divergence. Three
        # analysts reading one clear sentence and agreeing is correct behaviour;
        # the way to test disagreement is to give them evidence that genuinely
        # admits two readings.
        return [
            SearchResult("Analyst note", "https://research.example.org/1",
                         "Serviceable slice $3-5B; category $18-24B.", "2026-03",
                         query),
            SearchResult("Contract value benchmarks",
                         "https://research.example.org/2",
                         "An ACV of $28,000 is achievable at the top of the "
                         "range. Gross margins of 78% are not the norm once "
                         "inference is loaded into COGS.", "2026-04", query),
        ]


register_researcher(PanelStubSearch)


def _panel(tmp_path, models=("mock-a", "mock-b", "mock-c"), rounds=1, lenses=("investor",)):
    cfg = RunConfig(
        deck_path=str(DECK), lenses=[Lens.parse(x) for x in lenses],
        provider=ProviderConfig(name="mock"),
        research=ResearchConfig(name="panel_stub", max_queries=2),
        output=OutputConfig(formats=["md", "html"], out_dir=str(tmp_path)),
        cache_dir=None, verbose=False)
    return Panel(cfg, [ProviderConfig(name="mock", model=m) for m in models],
                 rounds=rounds)


def test_panel_needs_two_members(tmp_path):
    cfg = RunConfig(deck_path=str(DECK), provider=ProviderConfig(name="mock"),
                    output=OutputConfig(out_dir=str(tmp_path)), verbose=False)
    try:
        Panel(cfg, [ProviderConfig(name="mock")])
    except ValueError as exc:
        assert "at least two" in str(exc)
    else:
        raise AssertionError("a one-member panel should be rejected")


def test_panel_runs_and_disagrees(tmp_path):
    result = _panel(tmp_path).run()
    assert len(result.working) == 3
    m = result.metrics["investor"]
    assert m["panelists"] == 3
    assert m["verdict"]["agreement"] in ("unanimous", "majority", "split")
    assert m["score"]["spread"] > 0, "the stub panel should not be unanimous"
    # Deliberately NOT asserting contested claims here.
    #
    # This used to require that the panel disagreed about at least one claim,
    # and the fixture satisfied it by overwriting a claim's assessment with
    # "contradicted" regardless of the evidence. That is the one thing a fixture
    # must never do: it fabricates a finding rather than reflecting a reading.
    #
    # Three analysts given the same unambiguous sentence and reaching the same
    # conclusion have agreed, correctly. Disagreement is tested where it belongs
    # — against genuinely ambiguous evidence — in
    # test_analysts_differ_only_where_the_evidence_is_genuinely_ambiguous.
    assert isinstance(m["contested_claims"], list)


def test_cross_review_produces_revisions(tmp_path):
    result = _panel(tmp_path).run()
    for p in result.working:
        assert p.review, "each panelist should produce a review"
        assert p.review.get("peer_reviews")
        assert p.revised, "each panelist should revise after conceding"
        log = (p.revised["investor"].get("_meta") or {}).get("revision_log")
        assert log, "a revision should be logged"
    assert result.metrics["investor"]["total_position_changes"] == 3


def test_revision_actually_moves_the_score(tmp_path):
    result = _panel(tmp_path).run()
    moved = [m for m in result.metrics["investor"]["movement"]
             if m["score_before"] != m["score_after"]]
    assert moved, "conceding a position should change the score"


def test_consensus_report_produced(tmp_path):
    result = _panel(tmp_path).run()
    cons = result.consensus["investor"]
    assert cons.get("consensus_verdict", {}).get("call")
    assert cons.get("where_all_agree")
    assert cons.get("contested")
    assert cons.get("reliability", {}).get("shared_blind_spots") is not None


def test_rounds_zero_skips_review(tmp_path):
    result = _panel(tmp_path, rounds=0).run()
    assert all(not p.review for p in result.working)
    assert result.metrics["investor"]["total_position_changes"] == 0


def test_failing_panelist_degrades_gracefully(tmp_path):
    cfg = RunConfig(
        deck_path=str(DECK), provider=ProviderConfig(name="mock"),
        research=ResearchConfig(name="panel_stub", max_queries=1),
        output=OutputConfig(formats=["md"], out_dir=str(tmp_path)),
        cache_dir=None, verbose=False)
    panel = Panel(cfg, [ProviderConfig(name="mock", model="mock-a"),
                        ProviderConfig(name="does_not_exist")], rounds=1)
    result = panel.run()
    assert len(result.working) == 1
    assert result.stats["panelists_failed"], "the broken panelist should be reported"
    # A one-panelist panel must say so rather than pretending to be corroborated.
    assert "single panelist" in \
        result.consensus["investor"]["consensus_verdict"]["agreement"]


def test_panel_renders_all_reports(tmp_path):
    panel = _panel(tmp_path)
    result = panel.run()
    files = panel.render(result)
    names = [Path(f).name for f in files]
    assert any("_panel_investor.md" in n for n in names)
    assert any("_panel_investor.html" in n for n in names)
    assert any("_panel_full.json" in n for n in names)
    # every panelist's own final report too
    assert sum(1 for n in names if "mock_mock_" in n) >= 3
    for f in files:
        assert Path(f).stat().st_size > 400, f

    md = Path(next(f for f in files if f.endswith("_panel_investor.md"))).read_text("utf-8")
    for section in ("Where the panel landed", "Where the panel split",
                    "What changed when the panelists read each other",
                    "How much this agreement is worth", "References",
                    "Input integrity screen"):
        assert section in md, f"missing section: {section}"


def test_multiple_lenses(tmp_path):
    panel = _panel(tmp_path, lenses=("investor", "founder"))
    result = panel.run()
    assert set(result.consensus) == {"investor", "founder"}
    assert set(result.metrics) == {"investor", "founder"}


def test_parse_panelist_spec():
    assert parse_panelist("anthropic").name == "anthropic"
    pc = parse_panelist("anthropic:claude-sonnet-5")
    assert (pc.name, pc.model) == ("anthropic", "claude-sonnet-5")


def test_measure_agreement_math():
    class FakeResult:
        comparisons = {"investor": {"verdict": {"call": "PASS"},
                                    "scorecard": [{"dimension": "Market", "score": 4,
                                                   "weight": 5}]}}

    class FakePanelist:
        def __init__(self, label, call, score):
            self.label, self.name = label, label
            self.review = {}
            self._c = {"verdict": {"call": call},
                       "scorecard": [{"dimension": "Market", "score": score, "weight": 5}],
                       "claim_audit": [{"id": "C1", "claim": "x",
                                        "assessment": "supported" if score > 5
                                        else "contradicted"}]}
            self.result = FakeResult()

        def final(self, lens):
            return self._c

    panel = [FakePanelist("A", "PASS", 3), FakePanelist("B", "PASS", 9)]
    m = measure_agreement(panel, "investor")
    assert m["verdict"]["agreement"] == "unanimous"
    assert m["score"]["spread"] == 60.0
    assert m["score"]["convergence"] == "wide"
    assert m["dimensions"]["Market"]["contested"] is True
    # Claims are keyed by the panel-level cluster (K1), not by each panelist's
    # own C-numbering, which is independent and not comparable across panelists.
    assert m["contested_claims"] == ["K1"]
    assert m["claims"][0]["local_ids"] == {"A": "C1", "B": "C1"}


def test_claims_align_across_independent_numbering():
    """A's C1 and B's C1 are different claims; matching must be by content."""
    from deckscope.claim_align import align_claims

    clusters = align_claims({
        "A": [{"id": "C1", "claim": "$47B TAM growing 23% CAGR",
               "type": "market-size", "assessment": "partially-supported"},
              {"id": "C2", "claim": "18% MoM growth for four months",
               "type": "traction", "assessment": "supported"}],
        "B": [{"id": "C1", "claim": "18% month-over-month growth sustained four months",
               "type": "traction", "assessment": "supported"},
              {"id": "C2", "claim": "Total addressable market of $47B at 23% CAGR",
               "type": "market-size", "assessment": "contradicted"}],
    })
    by_type = {c.claim_type: c for c in clusters}
    traction = by_type["traction"].to_dict(2)
    assert traction["raised_by"] == 2
    assert traction["local_ids"] == {"A": "C2", "B": "C1"}, \
        "the cross-numbered traction claim must still be matched"
    assert traction["unanimous"] is True

    sizing = by_type["market-size"].to_dict(2)
    assert sizing["raised_by"] == 2
    assert sizing["contested"] is True, "a real disagreement must survive matching"


def test_claims_with_a_shared_number_but_different_types_do_not_merge():
    from deckscope.claim_align import align_claims

    clusters = align_claims({
        "A": [{"id": "C1", "claim": "$47B total addressable market",
               "type": "market-size", "assessment": "contradicted"}],
        "B": [{"id": "C1", "claim": "$47B of signed pipeline this quarter",
               "type": "traction", "assessment": "unverifiable"}],
    })
    assert len(clusters) == 2


def test_single_panelist_claim_is_reported_not_dropped():
    from deckscope.claim_align import align_claims

    clusters = align_claims({
        "A": [{"id": "C1", "claim": "78% gross margin", "type": "financial",
               "assessment": "unverifiable"}],
        "B": [{"id": "C1", "claim": "18% MoM growth", "type": "traction",
               "assessment": "supported"}],
    })
    solo = [c.to_dict(2) for c in clusters]
    assert all(c["single_panelist"] for c in solo)
    assert not any(c["contested"] for c in solo), \
        "one panelist not addressing a claim is silence, not disagreement"
