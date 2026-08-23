"""Comparing architectures: the panel as an evaluable mode, and honest deltas.

The panel is the most expensive thing DeckScope can do — roughly N times a single
pipeline run, plus review rounds — and until now it had no evaluation path at
all. `--mode` accepted only `pipeline` and `baseline`, so the feature that costs
the most was the one feature nobody could measure.

The subtler problem these tests pin down: a comparison between modes can report a
delta of zero for two completely different reasons. Either the modes really do
perform alike, or the provider never produced different analyses for them, in
which case the delta is zero by construction and measures nothing. Presenting the
second as though it were the first turns a non-measurement into a finding — the
same family of error as an evaluator reporting "every check passed" over zero
cases.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.evaluation.runner import SuiteResult, _fingerprint_analysis
from deckscope.evaluation.scoring import CaseScore


class FakeAnalysis:
    def __init__(self, comparisons):
        self.comparisons = comparisons


def _score(case_id, mode, fingerprint):
    s = CaseScore(case_id=case_id, mode=mode)
    s.output_fingerprint = fingerprint
    return s


# =============================================== the delta must be interpretable

def test_identical_outputs_are_reported_as_an_uninformative_comparison():
    result = SuiteResult(modes=["pipeline", "baseline"])
    for case in ("a", "b", "c"):
        result.scores.append(_score(case, "pipeline", "same"))
        result.scores.append(_score(case, "baseline", "same"))

    disc = result.discrimination()
    assert disc["comparable"] is False
    assert disc["cases_with_identical_output"] == 3
    assert disc["identical_rate"] == 1.0
    assert "measures nothing about the architectures" in disc["reason"]


def test_differing_outputs_make_the_comparison_meaningful():
    result = SuiteResult(modes=["pipeline", "baseline"])
    for i, case in enumerate(("a", "b", "c")):
        result.scores.append(_score(case, "pipeline", f"p{i}"))
        result.scores.append(_score(case, "baseline", f"b{i}"))

    disc = result.discrimination()
    assert disc["comparable"] is True
    assert disc["cases_with_identical_output"] == 0
    assert disc["reason"] == ""


def test_a_partially_identical_comparison_still_counts_as_informative():
    """One case where the modes agree does not invalidate the others."""
    result = SuiteResult(modes=["pipeline", "baseline"])
    result.scores.append(_score("a", "pipeline", "same"))
    result.scores.append(_score("a", "baseline", "same"))
    result.scores.append(_score("b", "pipeline", "x"))
    result.scores.append(_score("b", "baseline", "y"))

    disc = result.discrimination()
    assert disc["comparable"] is True
    assert disc["identical_cases"] == ["a"]


def test_a_single_mode_run_makes_no_comparison_claim():
    result = SuiteResult(modes=["pipeline"])
    result.scores.append(_score("a", "pipeline", "x"))
    disc = result.discrimination()
    assert disc["comparable"] is False
    assert "only one mode" in disc["reason"]


def test_errored_runs_do_not_count_as_agreement():
    """A mode that crashed produced no output; that is not the modes agreeing."""
    result = SuiteResult(modes=["pipeline", "baseline"])
    ok = _score("a", "pipeline", "x")
    broken = _score("a", "baseline", None)
    broken.error = "boom"
    result.scores.extend([ok, broken])
    disc = result.discrimination()
    assert disc["comparable"] is False
    assert "no case ran in more than one mode" in disc["reason"]


# ================================================== the fingerprint's contents

def test_the_fingerprint_tracks_content_not_metadata():
    """Two runs differing only in timing or model name are the same analysis."""
    comp = {"claim_audit": [{"claim": "TAM is $47B", "assessment": "contradicted",
                             "source_ids": ["S1"]}],
            "alignment": {"blind_spots": ["An incumbent"]},
            "verdict": {"call": "LEAN NO", "confidence": "low"}}
    a = FakeAnalysis({"investor": dict(comp, _meta={"elapsed": 1.2})})
    b = FakeAnalysis({"investor": dict(comp, _meta={"elapsed": 9.9})})
    assert _fingerprint_analysis(a, "investor") == _fingerprint_analysis(b, "investor")


def test_the_fingerprint_changes_when_an_assessment_changes():
    base = {"claim_audit": [{"claim": "TAM is $47B", "assessment": "contradicted",
                             "source_ids": ["S1"]}],
            "alignment": {"blind_spots": []}, "verdict": {"call": "LEAN NO"}}
    flipped = {"claim_audit": [{"claim": "TAM is $47B", "assessment": "supported",
                                "source_ids": ["S1"]}],
               "alignment": {"blind_spots": []}, "verdict": {"call": "LEAN NO"}}
    assert (_fingerprint_analysis(FakeAnalysis({"investor": base}), "investor")
            != _fingerprint_analysis(FakeAnalysis({"investor": flipped}), "investor"))


def test_the_fingerprint_changes_when_a_citation_changes():
    base = {"claim_audit": [{"claim": "x", "assessment": "supported",
                             "source_ids": ["S1"]}],
            "alignment": {"blind_spots": []}, "verdict": {}}
    other = {"claim_audit": [{"claim": "x", "assessment": "supported",
                              "source_ids": ["S2"]}],
             "alignment": {"blind_spots": []}, "verdict": {}}
    assert (_fingerprint_analysis(FakeAnalysis({"investor": base}), "investor")
            != _fingerprint_analysis(FakeAnalysis({"investor": other}), "investor"))


# ========================================================= the panel is runnable

def test_panel_is_an_accepted_eval_mode():
    """It was not, which is why the most expensive feature went unmeasured."""
    from deckscope.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["eval", "--mode", "panel"])
    assert args.mode == ["panel"]
    assert getattr(args, "panel_size", None) == 3


def test_the_panel_mode_scores_and_reports_its_true_cost():
    """Scoring must read the panel's winning comparison, and cost must count
    every panelist — a three-member panel that reports one member's tokens makes
    the expensive option look free."""
    from deckscope.evaluation import run_suite

    result = run_suite(modes=["pipeline", "panel"], provider="mock",
                       only=["inflated_tam"], panel_size=3)

    panel_scores = result.for_mode("panel")
    assert panel_scores, "the panel mode produced no scores"

    # It must be scored on the same dimensions as the other modes, not left
    # blank because the chair's consensus lacks a claim audit.
    rate = result.dimension_rate("panel", "claim_accuracy")
    assert rate is not None, "panel was not scored on claim accuracy at all"

    pipeline_cost = result.cost("pipeline")["input_tokens"]
    panel_cost = result.cost("panel")["input_tokens"]
    assert panel_cost > pipeline_cost * 2, (
        f"a 3-panelist panel reported {panel_cost} input tokens against "
        f"{pipeline_cost} for one pipeline — the cost of every panelist must be "
        f"counted or the comparison flatters the expensive mode")


def test_the_mock_revision_keeps_the_deck_it_was_analysing():
    """The revise path called `_compare()` with no prompt, so a panelist revising
    its analysis of one deck returned claims about a different company. It scored
    the panel at zero and looked like a result rather than a fixture defect."""
    from deckscope.providers.mock_provider import MockProvider

    provider = MockProvider()
    prompt = ("YOUR ORIGINAL ANALYSIS\nRESEARCH MATERIAL\n"
              "[S1] Reconciliation sizing\n      url: https://e.org/1\n"
              "      content: The category is $6-8B, not $80B.\n"
              "CLAIMS\n- The financial reconciliation software market is $88B\n")
    out = provider.complete_json(
        "You are producing the final version of your analysis.",
        prompt)
    claims = " ".join(str(r.get("claim", "")) for r in (out.get("claim_audit") or []))
    assert "reconciliation" in claims.lower() or "88" in claims, (
        f"revision returned claims about another deck: {claims[:120]}")
