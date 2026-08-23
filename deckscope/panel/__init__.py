"""Panel mechanics: when to stop iterating, and how to choose an output."""
from .strategies import (STRATEGIES, AdaptiveStrategy, ConfidenceFloorStrategy,
                         ConvergenceStrategy, Decision, FixedRoundsStrategy,
                         RoundStrategy, get_strategy, list_strategies)
from .voting import Ballot, VoteResult, tally

__all__ = [
    "RoundStrategy", "Decision", "FixedRoundsStrategy", "ConvergenceStrategy",
    "ConfidenceFloorStrategy", "AdaptiveStrategy", "STRATEGIES",
    "get_strategy", "list_strategies",
    "Ballot", "VoteResult", "tally",
]
