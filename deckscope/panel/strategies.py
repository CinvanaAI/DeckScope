"""When should the panel stop reviewing?

There is no single right answer, which is why this is a strategy rather than a
constant. Three decks make the point:

  * A deck where all three panelists immediately agree. A second review round
    costs money and changes nothing.
  * A deck where they split 2-1 on whether the moat is real. That is exactly the
    case where another round might resolve something — or might reveal that the
    disagreement is structural and no amount of reviewing will close it.
  * A deck being used for an actual investment decision, where "we ran out of
    rounds" is not an acceptable reason to stop with a low-confidence answer.

Each strategy answers one question — `should_continue` — and explains itself, so
the report can say *why* the panel stopped rather than just how many rounds ran.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type


@dataclass
class Decision:
    """Whether to run another round, and the reason either way."""

    proceed: bool
    reason: str
    #: Anything the strategy wants preserved in the report.
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoundState:
    """What the strategy gets to look at after each round."""

    round_number: int          # 0 = after the independent round, before any review
    max_rounds: int
    #: Weighted score per panelist label, this round.
    scores: Dict[str, float] = field(default_factory=dict)
    #: Verdict call per panelist label, this round.
    verdicts: Dict[str, str] = field(default_factory=dict)
    #: Confidence per panelist label ("high" | "medium" | "low").
    confidences: Dict[str, str] = field(default_factory=dict)
    #: How many positions each panelist changed in the round just finished.
    changes: Dict[str, int] = field(default_factory=dict)
    #: Score spread from the previous round, for stability comparison.
    previous_spread: Optional[float] = None
    #: Number of claims the panel assessed differently.
    contested_claims: int = 0

    @property
    def spread(self) -> float:
        vals = [v for v in self.scores.values() if isinstance(v, (int, float))]
        return round(max(vals) - min(vals), 1) if len(vals) > 1 else 0.0

    @property
    def verdict_agreement(self) -> str:
        calls = [v for v in self.verdicts.values() if v]
        if not calls:
            return "unknown"
        counts: Dict[str, int] = {}
        for c in calls:
            counts[c] = counts.get(c, 0) + 1
        top = max(counts.values())
        if top == len(calls) and len(calls) > 1:
            return "unanimous"
        return "majority" if top > len(calls) / 2 else "split"

    @property
    def total_changes(self) -> int:
        return sum(self.changes.values())

    @property
    def weakest_confidence(self) -> str:
        order = {"high": 3, "medium": 2, "low": 1}
        vals = [order.get(c, 1) for c in self.confidences.values()]
        if not vals:
            return "low"
        return {3: "high", 2: "medium", 1: "low"}[min(vals)]


class RoundStrategy(ABC):
    """Decides whether the panel runs another review round."""

    name: str = "base"
    blurb: str = ""

    def __init__(self, max_rounds: int = 3, **options: Any) -> None:
        self.max_rounds = max(0, max_rounds)
        self.options = options

    def should_continue(self, state: RoundState) -> Decision:
        """Called after each round, including round 0 (independent analyses)."""
        if self.max_rounds <= 0:
            return Decision(False, "cross-review is disabled (rounds = 0)",
                            {"disabled": True})
        return self._decide(state)

    @abstractmethod
    def _decide(self, state: RoundState) -> Decision:
        """Strategy-specific decision. Only called when rounds remain."""

    def describe(self) -> str:
        return f"{self.name}: {self.blurb}"


class FixedRoundsStrategy(RoundStrategy):
    """Run exactly N rounds. Predictable cost, indifferent to what happens."""

    name = "fixed"
    blurb = "always run the configured number of rounds"

    def _decide(self, state: RoundState) -> Decision:
        if state.round_number >= self.max_rounds:
            return Decision(False, f"completed all {self.max_rounds} configured round(s)")
        return Decision(True, f"round {state.round_number + 1} of {self.max_rounds}")


class ConvergenceStrategy(RoundStrategy):
    """Stop when the panel has stopped moving.

    Two signals, both required. Positions must have stopped changing — if a
    panelist conceded something this round, another round may produce more. And
    the scores must be close enough that further movement would not change the
    reading.

    This can stop after zero review rounds when the panel already agrees, which
    is the point: three models that independently reached the same verdict do not
    need to be introduced to each other.
    """

    name = "convergence"
    blurb = "stop once positions stop changing and scores are stable"

    def __init__(self, max_rounds: int = 3, *, spread_tolerance: float = 8.0,
                 stability_tolerance: float = 3.0, **options: Any) -> None:
        super().__init__(max_rounds, **options)
        self.spread_tolerance = spread_tolerance
        self.stability_tolerance = stability_tolerance

    def _decide(self, state: RoundState) -> Decision:
        if state.round_number >= self.max_rounds:
            return Decision(False, f"reached the {self.max_rounds}-round cap while the "
                                   f"panel was still {state.verdict_agreement}",
                            {"converged": False, "spread": state.spread})

        tight = state.spread <= self.spread_tolerance
        settled = state.round_number > 0 and state.total_changes == 0
        stable = (state.previous_spread is not None
                  and abs(state.spread - state.previous_spread) <= self.stability_tolerance)

        if state.round_number == 0:
            if tight and state.verdict_agreement == "unanimous":
                return Decision(
                    False,
                    f"the panel agreed independently — unanimous verdict with a "
                    f"{state.spread}-point spread — so cross-review was skipped",
                    {"converged": True, "spread": state.spread, "rounds_saved":
                     self.max_rounds})
            return Decision(True, f"panel is {state.verdict_agreement} with a "
                                  f"{state.spread}-point spread; reviewing")

        if settled and (tight or stable):
            return Decision(
                False,
                f"converged: no panelist changed position this round and the spread "
                f"is {state.spread} points ({state.verdict_agreement})",
                {"converged": True, "spread": state.spread})

        return Decision(
            True,
            f"still moving: {state.total_changes} position change(s) this round, "
            f"spread {state.spread}",
            {"converged": False})


class ConfidenceFloorStrategy(ConvergenceStrategy):
    """Converge, but refuse to finish on a weak answer.

    For decisions where "we ran out of rounds" is not an acceptable stopping
    condition. Keeps going while any panelist is still low-confidence or claims
    remain contested — and when the cap is hit anyway, says so explicitly rather
    than presenting the result as settled.
    """

    name = "confidence_floor"
    blurb = "converge, but keep going while confidence is low or claims are contested"

    def __init__(self, max_rounds: int = 4, *, floor: str = "medium",
                 max_contested: int = 0, **options: Any) -> None:
        super().__init__(max_rounds, **options)
        self.floor = floor
        self.max_contested = max_contested

    def _decide(self, state: RoundState) -> Decision:
        order = {"low": 1, "medium": 2, "high": 3}
        below_floor = order.get(state.weakest_confidence, 1) < order.get(self.floor, 2)
        too_contested = state.contested_claims > self.max_contested

        if state.round_number >= self.max_rounds:
            if below_floor or too_contested:
                return Decision(
                    False,
                    f"stopped at the {self.max_rounds}-round cap WITHOUT reaching the "
                    f"confidence floor — weakest confidence is "
                    f"'{state.weakest_confidence}' and {state.contested_claims} claim(s) "
                    f"remain contested. Treat this result as unsettled.",
                    {"floor_met": False, "weakest": state.weakest_confidence,
                     "contested": state.contested_claims})
            return Decision(False, f"reached the {self.max_rounds}-round cap with the "
                                   f"confidence floor met",
                            {"floor_met": True})

        if below_floor:
            return Decision(True, f"weakest confidence is '{state.weakest_confidence}', "
                                  f"below the '{self.floor}' floor")
        if too_contested:
            return Decision(True, f"{state.contested_claims} claim(s) still contested "
                                  f"(floor allows {self.max_contested})")

        base = super()._decide(state)
        if not base.proceed:
            base.detail["floor_met"] = True
        return base


class AdaptiveStrategy(RoundStrategy):
    """Pick a strategy from the shape of the run, then delegate to it.

    The right approach depends on what the panel looks like after its first pass,
    which is not knowable in advance:

      * unanimous with a tight spread -> nothing to resolve, stop
      * split verdicts or a wide spread -> convergence, the disagreement may close
      * anyone low-confidence, or claims contested -> confidence floor

    The choice is recorded and reported, so the run explains its own cost.
    """

    name = "adaptive"
    blurb = "choose the stopping rule from how the panel actually behaves"

    def __init__(self, max_rounds: int = 3, **options: Any) -> None:
        super().__init__(max_rounds, **options)
        self.delegate: Optional[RoundStrategy] = None
        self.rationale: str = ""

    def _choose(self, state: RoundState) -> RoundStrategy:
        # Never exceed the caller's cap. Raising it here would mean `rounds=0`
        # silently ran review rounds anyway.
        if state.weakest_confidence == "low" or state.contested_claims > 2:
            self.rationale = (
                f"a panelist is low-confidence and {state.contested_claims} claim(s) are "
                f"contested, so the panel keeps going until that improves")
            return ConfidenceFloorStrategy(self.max_rounds, **self.options)
        if state.verdict_agreement == "unanimous" and state.spread <= 8.0:
            self.rationale = ("the panel reached the same verdict independently with a "
                              "tight spread, so there is nothing for review to resolve")
            return ConvergenceStrategy(self.max_rounds, **self.options)
        self.rationale = (f"the panel is {state.verdict_agreement} with a {state.spread}-"
                          f"point spread, so review may still close the gap")
        return ConvergenceStrategy(self.max_rounds, **self.options)

    def _decide(self, state: RoundState) -> Decision:
        if self.delegate is None:
            self.delegate = self._choose(state)
        decision = self.delegate.should_continue(state)
        decision.detail.setdefault("strategy_chosen", self.delegate.name)
        decision.detail.setdefault("why_this_strategy", self.rationale)
        decision.reason = f"[{self.delegate.name}] {decision.reason}"
        return decision


STRATEGIES: Dict[str, Type[RoundStrategy]] = {
    "fixed": FixedRoundsStrategy,
    "convergence": ConvergenceStrategy,
    "confidence_floor": ConfidenceFloorStrategy,
    "adaptive": AdaptiveStrategy,
}


def list_strategies() -> List[str]:
    return sorted(STRATEGIES)


def get_strategy(name: str, max_rounds: int = 3, **options: Any) -> RoundStrategy:
    key = (name or "adaptive").strip().lower()
    if key not in STRATEGIES:
        raise ValueError(f"Unknown round strategy {name!r}. "
                         f"Available: {', '.join(list_strategies())}")
    return STRATEGIES[key](max_rounds, **options)
