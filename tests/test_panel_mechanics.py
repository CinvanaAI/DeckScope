"""Stopping strategies, ranked voting, and the single-prompt baseline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.config import (Lens, OutputConfig, ProviderConfig, ResearchConfig,
                              RunConfig)
from deckscope.panel.strategies import (RoundState, get_strategy, list_strategies)
from deckscope.panel.voting import Ballot, ballot_from_json, tally

DECK = Path(__file__).resolve().parent.parent / "examples" / "sample_deck.md"


def _state(**kw):
    defaults = dict(round_number=0, max_rounds=3,
                    scores={"A": 60.0, "B": 65.0}, verdicts={"A": "PASS", "B": "PASS"},
                    confidences={"A": "high", "B": "high"}, changes={},
                    previous_spread=None, contested_claims=0)
    defaults.update(kw)
    return RoundState(**defaults)


# ==================================================================== strategies

def test_every_strategy_is_registered():
    assert set(list_strategies()) == {"adaptive", "confidence_floor", "convergence",
                                      "fixed"}


def test_zero_rounds_is_absolute_for_every_strategy():
    """An explicit rounds=0 must never be overridden by a strategy's own default."""
    for name in list_strategies():
        decision = get_strategy(name, max_rounds=0).should_continue(
            _state(confidences={"A": "low", "B": "low"}, contested_claims=9))
        assert not decision.proceed, name


def test_fixed_runs_exactly_the_configured_rounds():
    strategy = get_strategy("fixed", max_rounds=2)
    assert strategy.should_continue(_state(round_number=0)).proceed
    assert strategy.should_continue(_state(round_number=1)).proceed
    assert not strategy.should_continue(_state(round_number=2)).proceed


def test_convergence_skips_review_when_the_panel_already_agrees():
    """Three models that independently agreed do not need introducing."""
    decision = get_strategy("convergence", max_rounds=3).should_continue(
        _state(scores={"A": 70.0, "B": 71.0}, verdicts={"A": "PASS", "B": "PASS"}))
    assert not decision.proceed
    assert decision.detail.get("converged") is True
    assert "agreed independently" in decision.reason


def test_convergence_keeps_going_while_positions_are_still_changing():
    strategy = get_strategy("convergence", max_rounds=3)
    assert strategy.should_continue(
        _state(scores={"A": 40.0, "B": 80.0},
               verdicts={"A": "PASS", "B": "STRONG YES"})).proceed
    still_moving = strategy.should_continue(
        _state(round_number=1, scores={"A": 45.0, "B": 78.0},
               verdicts={"A": "PASS", "B": "STRONG YES"},
               changes={"A": 2, "B": 1}, previous_spread=40.0))
    assert still_moving.proceed


def test_convergence_stops_once_nobody_moves():
    decision = get_strategy("convergence", max_rounds=3).should_continue(
        _state(round_number=1, scores={"A": 64.0, "B": 66.0},
               changes={"A": 0, "B": 0}, previous_spread=3.0))
    assert not decision.proceed
    assert decision.detail.get("converged") is True


def test_confidence_floor_keeps_going_on_a_weak_answer():
    strategy = get_strategy("confidence_floor", max_rounds=3, floor="medium")
    assert strategy.should_continue(
        _state(round_number=1, confidences={"A": "low", "B": "high"},
               changes={"A": 0, "B": 0})).proceed


def test_confidence_floor_admits_when_it_failed_to_reach_the_floor():
    """Running out of rounds must not be presented as a settled result."""
    decision = get_strategy("confidence_floor", max_rounds=2).should_continue(
        _state(round_number=2, confidences={"A": "low", "B": "low"},
               contested_claims=4))
    assert not decision.proceed
    assert decision.detail.get("floor_met") is False
    assert "WITHOUT reaching the confidence floor" in decision.reason


def test_adaptive_picks_confidence_floor_when_confidence_is_low():
    strategy = get_strategy("adaptive", max_rounds=3)
    decision = strategy.should_continue(
        _state(confidences={"A": "low", "B": "medium"}, contested_claims=4))
    assert decision.detail["strategy_chosen"] == "confidence_floor"
    assert decision.detail["why_this_strategy"]


def test_adaptive_picks_convergence_when_the_panel_agrees():
    strategy = get_strategy("adaptive", max_rounds=3)
    decision = strategy.should_continue(
        _state(scores={"A": 70.0, "B": 72.0}, verdicts={"A": "PASS", "B": "PASS"}))
    assert decision.detail["strategy_chosen"] == "convergence"
    assert not decision.proceed


def test_unknown_strategy_is_rejected_by_name():
    try:
        get_strategy("vibes")
    except ValueError as exc:
        assert "Unknown round strategy" in str(exc)
    else:
        raise AssertionError("an unknown strategy should be refused")


# ======================================================================= voting

def test_two_panelist_vote_does_not_score_zero():
    """Textbook Borda gives first place n-1 points, which is 0 when n is 2."""
    result = tally([Ballot("A", ["B"]), Ballot("B", ["A"])], ["A", "B"])
    assert all(v > 0 for v in result.scores.values())


def test_borda_prefers_the_broadly_respected_report():
    """A report everyone ranks second can beat one with more first places."""
    result = tally([Ballot("C", ["B", "A"]), Ballot("A", ["B", "C"]),
                    Ballot("B", ["A", "C"])], ["A", "B", "C"])
    assert result.winner == "B"
    assert result.order == ["B", "A", "C"]


def test_self_votes_are_ignored():
    result = tally([Ballot("A", ["A", "A", "B"]), Ballot("B", ["B", "A"])], ["A", "B"])
    for ballot in result.ballots:
        assert ballot.voter not in [c for c in ballot.ranking]


def test_a_preference_cycle_is_named_rather_than_broken():
    """A > B > C > A has no honest winner, and saying so is the finding."""
    result = tally([Ballot("A", ["C", "B"]), Ballot("B", ["A", "C"]),
                    Ballot("C", ["B", "A"])], ["A", "B", "C"])
    assert result.cycle is True
    assert result.winner is None
    assert not result.decisive
    assert "cycle" in result.note.lower()


def test_a_clear_winner_is_not_reported_as_a_cycle():
    result = tally([Ballot("A", ["B", "C"]), Ballot("C", ["B", "A"]),
                    Ballot("B", ["A", "C"])], ["A", "B", "C"])
    assert result.cycle is False
    assert result.decisive


def test_a_panelist_ranked_by_fewer_voters_is_not_penalised():
    """Happens whenever another panelist fails mid-run."""
    result = tally([Ballot("A", ["B", "C"]), Ballot("B", ["A"])], ["A", "B", "C"])
    assert result.scores["B"] > 0 and result.scores["C"] > 0


def test_single_surviving_panelist_is_not_declared_a_winner_of_anything():
    result = tally([], ["A"])
    assert result.winner == "A"
    assert "nothing to rank against it" in result.note


def test_ballot_parsing_tolerates_the_shapes_models_produce():
    valid = ["Panelist B", "Panelist C"]
    ballot = ballot_from_json("Panelist A", {"ranking": [
        {"panelist": "Panelist C (openai/gpt-4o)", "reason": "better citations"},
        {"panelist": "Panelist A", "reason": "mine"},
        "Panelist B",
    ]}, valid)
    assert ballot.ranking == ["Panelist C", "Panelist B"]
    assert "Panelist A" not in ballot.reasons, "a self-reason is not a ranking"
    assert ballot.reasons["Panelist C"] == "better citations"


# ====================================================================== baseline

def _cfg(tmp_path, lenses=("investor",)):
    return RunConfig(
        deck_path=str(DECK), lenses=[Lens.parse(x) for x in lenses],
        provider=ProviderConfig(name="mock"),
        research=ResearchConfig(name="none"),
        output=OutputConfig(formats=["md"], out_dir=str(tmp_path)),
        cache_dir=None, verbose=False)


def test_baseline_runs_one_call_per_lens(tmp_path):
    from deckscope.baseline import BaselineAnalyst

    analyst = BaselineAnalyst(_cfg(tmp_path, ("investor", "founder")))
    try:
        result = analyst.run()
    finally:
        analyst.close()
    assert result.stats["mode"] == "baseline"
    assert result.stats["model_calls"] == 2
    assert set(result.comparisons) == {"investor", "founder"}
    assert result.stats["token_usage"]["input"] > 0


def test_baseline_is_screened_identically_to_the_pipeline(tmp_path):
    """The comparison only means something if prompting is the only difference."""
    from deckscope.baseline import BaselineAnalyst

    cfg = _cfg(tmp_path)
    cfg.deck_path = str(DECK.parent / "sample_deck_with_injection.md")
    analyst = BaselineAnalyst(cfg)
    try:
        result = analyst.run()
    finally:
        analyst.close()
    assert result.security["overall_risk"] == "critical"


def test_mode_comparison_reports_differences_without_declaring_a_winner(tmp_path):
    from deckscope.baseline import BaselineAnalyst, compare_modes
    from deckscope.orchestrator import Pipeline

    cfg = _cfg(tmp_path)
    pipe = Pipeline(cfg)
    try:
        pipeline_result = pipe.run()
    finally:
        pipe.close()
    analyst = BaselineAnalyst(cfg)
    try:
        baseline_result = analyst.run()
    finally:
        analyst.close()

    comparison = compare_modes(pipeline_result, baseline_result)
    investor = comparison["lenses"]["investor"]

    # Rates rather than counts: a mode that simply says more must not score higher.
    assert 0.0 <= investor["citation_density"]["pipeline"] <= 1.0
    assert set(investor["claims"]) >= {"raised_by_both", "only_pipeline",
                                       "only_baseline"}
    assert "contradictions" in investor
    assert "cost" in comparison
    assert "evidence" in comparison
    assert "measures DIFFERENCE, not correctness" in comparison["caveat"]
    assert "winner" not in comparison


# ============================================================ end-to-end panel

def test_panel_records_why_it_stopped(tmp_path):
    from deckscope.ensemble import Panel

    cfg = _cfg(tmp_path)
    panel = Panel(cfg, [ProviderConfig(name="mock", model=m)
                        for m in ("mock-a", "mock-b", "mock-c")],
                  rounds=3, strategy="fixed")
    result = panel.run()
    assert result.round_log, "the stopping decisions must be recorded"
    assert result.stats["rounds_run"] == 3
    assert result.stats["stopped_because"]
    assert all("reason" in entry for entry in result.round_log)


def test_panel_that_agrees_skips_review_entirely(tmp_path):
    from deckscope.ensemble import Panel

    cfg = _cfg(tmp_path)
    # Same mock seed for all three => identical analyses => nothing to resolve.
    panel = Panel(cfg, [ProviderConfig(name="mock", model=m)
                        for m in ("mock-a", "mock-d", "mock-g")],
                  rounds=3, strategy="convergence")
    result = panel.run()
    assert result.stats["rounds_run"] == 0
    assert "agreed independently" in result.stats["stopped_because"]


def test_panel_vote_reaches_the_report(tmp_path):
    from deckscope.ensemble import Panel

    cfg = _cfg(tmp_path)
    panel = Panel(cfg, [ProviderConfig(name="mock", model=m)
                        for m in ("mock-a", "mock-b", "mock-c")],
                  rounds=1, strategy="fixed", vote=True)
    result = panel.run()
    files = panel.render(result)

    vote = result.votes["investor"]
    assert vote.ballots, "every panelist should have cast a ballot"
    assert len(vote.order) == 3
    for panelist in result.working:
        assert panelist.rank in (1, 2, 3)

    report = next(f for f in files if f.endswith("_panel_investor.md"))
    text = Path(report).read_text(encoding="utf-8")
    assert "The individual reports, ranked" in text
    assert "How the panel decided to stop" in text


def test_vote_can_be_disabled(tmp_path):
    from deckscope.ensemble import Panel

    cfg = _cfg(tmp_path)
    panel = Panel(cfg, [ProviderConfig(name="mock", model=m)
                        for m in ("mock-a", "mock-b")],
                  rounds=0, vote=False)
    result = panel.run()
    assert not result.votes
