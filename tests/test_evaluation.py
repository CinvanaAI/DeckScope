"""The evaluation harness itself.

Two things need testing here, and the second matters more:

  1. that the scorer correctly rewards a good analysis, and
  2. that it correctly PUNISHES a bad one.

A rubric that cannot fail is not a rubric. Most of these tests construct a
deliberately wrong analysis and assert that the relevant dimension drops.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.evaluation import (DIMENSIONS, default_suite_dir, load_suite,
                                  run_suite, score_case)
from deckscope.evaluation.cases import (BlindSpotExpectation, ClaimExpectation,
                                        EvalCase, Expectations)
from deckscope.orchestrator import AnalysisResult
from deckscope.sources import Source, SourceRegistry


def _result(claim_audit=None, *, verdict="LEAN NO", confidence="medium",
            sources=("S1",), security_risk="clean", extra_text=""):
    registry = SourceRegistry()
    for sid in sources:
        src = Source(sid=sid, title=sid, url=f"https://ex.org/{sid}")
        registry.sources.append(src)
        registry._by_url[src.url] = src
    result = AnalysisResult(
        comparisons={"investor": {
            "verdict": {"call": verdict, "confidence": confidence},
            "claim_audit": claim_audit or [],
            "summary": extra_text,
            "_meta": {"weighted_score": {"score": 50.0}}}},
        stats={"elapsed_seconds": 1.0, "token_usage": {"input": 10, "output": 5}},
        security={"overall_risk": security_risk})
    result.registry = registry
    return result


def _case(**kw):
    expect = kw.pop("expect", Expectations())
    defaults = {"id": "t", "name": "t", "deck": "d.md"}
    defaults.update(kw)
    return EvalCase(expect=expect, **defaults)


# ================================================== the shipped suite loads

def test_the_shipped_suite_is_valid():
    cases = load_suite(str(default_suite_dir()))
    assert len(cases) >= 5
    root = default_suite_dir().parent
    for case in cases:
        assert case.deck_path(root).exists(), f"{case.id}: deck missing"
        if case.corpus:
            assert case.corpus_path(root).exists(), f"{case.id}: corpus missing"
        assert case.description, f"{case.id}: needs a description"


def test_the_suite_contains_a_false_positive_control():
    """Without it, a system that calls everything contradicted scores well."""
    cases = {c.id: c for c in load_suite(str(default_suite_dir()))}
    control = cases.get("honest_control")
    assert control is not None
    assert any("supported" in c.assessment for c in control.expect.claims), \
        "the control must expect at least one claim to be SUPPORTED"


def test_every_expectation_carries_a_rationale():
    """A failure has to be legible without opening the fixture."""
    for case in load_suite(str(default_suite_dir())):
        for claim in case.expect.claims:
            assert claim.rationale, f"{case.id}: claim expectation needs a rationale"
        for spot in case.expect.blind_spots:
            assert spot.rationale, f"{case.id}: blind spot needs a rationale"


# ================================================ the scorer rewards correctness

def test_a_correct_assessment_passes():
    case = _case(expect=Expectations(claims=[ClaimExpectation(
        matches="47B", assessment=["contradicted"], must_cite=True,
        rationale="evidence says $3-5B")]))
    result = _result([{"id": "C1", "claim": "$47B TAM", "assessment": "contradicted",
                       "source_ids": ["S1"]}])
    score = score_case(case, result, mode="pipeline")
    assert score.rate("claim_accuracy") == 1.0
    assert score.rate("claim_citation") == 1.0


def test_a_wrong_assessment_fails():
    case = _case(expect=Expectations(claims=[ClaimExpectation(
        matches="47B", assessment=["contradicted"], rationale="r")]))
    result = _result([{"id": "C1", "claim": "$47B TAM", "assessment": "supported",
                       "source_ids": ["S1"]}])
    score = score_case(case, result, mode="pipeline")
    assert score.rate("claim_accuracy") == 0.0
    assert "supported" in score.failures[0].detail


def test_a_claim_never_raised_at_all_fails():
    case = _case(expect=Expectations(claims=[ClaimExpectation(
        matches="47B", assessment=["contradicted"], rationale="r")]))
    score = score_case(case, _result([]), mode="pipeline")
    assert score.rate("claim_accuracy") == 0.0
    assert "not raised" in score.failures[0].got


# ============================================= the scorer punishes bad analysis

def test_a_missed_blind_spot_fails():
    case = _case(expect=Expectations(blind_spots=[BlindSpotExpectation(
        must_mention=["Microsoft", "Power Automate"], rationale="dominant incumbent")]))
    assert score_case(case, _result([]), mode="pipeline").rate("blind_spot_recall") == 0.0
    found = _result([], extra_text="Microsoft bundles this into E5.")
    assert score_case(case, found, mode="pipeline").rate("blind_spot_recall") == 1.0


def test_a_fabricated_figure_fails():
    case = _case(expect=Expectations(must_not_fabricate=["$120B", "SoftBank"]))
    clean = score_case(case, _result([]), mode="pipeline")
    assert clean.rate("no_fabrication") == 1.0
    dirty = score_case(case, _result([], extra_text="The market may reach $120B."),
                       mode="pipeline")
    assert dirty.rate("no_fabrication") == 0.5
    assert "$120B" in dirty.failures[0].detail


def test_a_citation_to_a_nonexistent_source_fails():
    case = _case()
    result = _result([{"id": "C1", "claim": "x", "assessment": "supported",
                       "source_ids": ["S1", "S99"]}], sources=("S1",))
    score = score_case(case, result, mode="pipeline")
    assert score.rate("citation_integrity") == 0.0
    assert "S99" in score.failures[0].detail


def test_overclaiming_confidence_fails_calibration():
    case = _case(expect=Expectations(confidence_at_most="medium"))
    ok = score_case(case, _result([], confidence="low"), mode="pipeline")
    assert ok.rate("calibration") == 1.0
    over = score_case(case, _result([], confidence="high"), mode="pipeline")
    assert over.rate("calibration") == 0.0


def test_a_missed_injection_fails_hard():
    """The most serious failure in the suite, and weighted as such."""
    case = _case(expect=Expectations(injection_planted=True))
    missed = score_case(case, _result([], security_risk="clean"), mode="pipeline")
    assert missed.rate("injection_detection") == 0.0
    check = next(c for c in missed.checks if c.dimension == "injection_detection")
    assert check.weight >= 2.0, "missing an injection must outweigh a normal check"
    caught = score_case(case, _result([], security_risk="critical"), mode="pipeline")
    assert caught.rate("injection_detection") == 1.0


def test_a_false_positive_on_a_clean_deck_fails():
    case = _case(expect=Expectations(security_risk="clean"))
    noisy = score_case(case, _result([], security_risk="critical"), mode="pipeline")
    assert noisy.rate("injection_detection") == 0.0


# ============================================ dimensions are not averaged away

def test_dimensions_are_reported_separately():
    """Averaging would hide that a system scored well by refusing to say anything."""
    case = _case(expect=Expectations(
        claims=[ClaimExpectation(matches="47B", assessment=["contradicted"],
                                 rationale="r")],
        must_not_fabricate=["$120B"]))
    silent = score_case(case, _result([]), mode="pipeline")
    rates = {d: silent.rate(d) for d in DIMENSIONS if silent.rate(d) is not None}
    assert rates["no_fabrication"] == 1.0, "saying nothing cannot be fabrication"
    assert rates["claim_accuracy"] == 0.0, "but it is a total failure of accuracy"
    assert len(rates) > 1, "the two must not be collapsed into one number"


# ==================================================== the runner end to end

def test_the_runner_scores_the_shipped_suite(tmp_path):
    result = run_suite(modes=["pipeline"], trials=1, provider="mock",
                       out_dir=str(tmp_path))
    assert not result.errors(), f"cases failed to run: {result.errors()}"
    assert len(result.scores) == len(load_suite(str(default_suite_dir())))
    # Structural dimensions must hold even for a crude fixture provider.
    for dimension in ("citation_integrity", "no_fabrication", "injection_detection"):
        assert result.dimension_rate("pipeline", dimension) == 1.0, dimension


def test_the_runner_measures_stability_across_trials(tmp_path):
    result = run_suite(modes=["pipeline"], trials=2, provider="mock",
                       out_dir=str(tmp_path), only=["inflated_tam"])
    stability = result.stability("pipeline")
    assert stability["cases_measured"] == 1
    # The mock is deterministic, so repeated runs must agree exactly.
    assert stability["verdict_identical_across_trials"] == 1.0
    assert stability["mean_score_spread"] == 0.0


def test_the_runner_compares_modes_on_the_same_cases(tmp_path):
    result = run_suite(modes=["pipeline", "baseline"], trials=1, provider="mock",
                       out_dir=str(tmp_path))
    assert set(result.modes) == {"pipeline", "baseline"}
    assert result.for_mode("pipeline") and result.for_mode("baseline")
    assert result.cost("baseline")["input_tokens"] < \
        result.cost("pipeline")["input_tokens"], \
        "one prompt should cost less than three agents"


def test_filtering_by_tag_works(tmp_path):
    result = run_suite(modes=["pipeline"], provider="mock", out_dir=str(tmp_path),
                       only=["security"])
    assert {s.case_id for s in result.scores} == {"hidden_injection"}


def test_the_result_carries_its_own_caveat(tmp_path):
    result = run_suite(modes=["pipeline"], provider="mock", out_dir=str(tmp_path),
                       only=["honest_control"])
    payload = result.to_dict()
    assert "constructed cases" in payload["caveat"]
    assert "not real-world accuracy" in payload["caveat"]
    assert "floor and not a ceiling" in payload["caveat"]


def test_the_suite_runs_against_frozen_evidence(tmp_path):
    """A score change must mean DeckScope changed, not that the web did."""
    first = run_suite(modes=["pipeline"], provider="mock", out_dir=str(tmp_path / "a"),
                      only=["inflated_tam"])
    second = run_suite(modes=["pipeline"], provider="mock", out_dir=str(tmp_path / "b"),
                       only=["inflated_tam"])
    assert (first.dimension_rate("pipeline", "claim_accuracy")
            == second.dimension_rate("pipeline", "claim_accuracy"))
