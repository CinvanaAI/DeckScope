"""Run the evaluation suite and aggregate the results.

Each case is run against frozen evidence, so a change in score between two runs
reflects a change in DeckScope rather than a change in what the web said that day.
Cases can be run several times to measure stability, because a system that returns
a different verdict on each run of the same inputs is not usefully accurate even
when its average is good.

Modes are compared on identical cases and identical evidence, which is what makes
"is the three-agent pipeline better than one prompt" an answerable question rather
than a matter of opinion.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..config import Lens, OutputConfig, ProviderConfig, ResearchConfig, RunConfig
from ..corpus import EvidenceCorpus
from .cases import default_suite_dir, load_suite
from .scoring import CaseScore, failed_case, score_case

#: Dimensions reported separately. Never averaged into one number: they trade
#: against each other, and a single figure would hide that a system scored
#: perfectly on fabrication by refusing to say anything.
DIMENSIONS = ["claim_accuracy", "claim_citation", "blind_spot_recall",
              "no_fabrication", "citation_integrity", "calibration",
              "verdict", "injection_detection"]


@dataclass
class SuiteResult:
    scores: List[CaseScore] = field(default_factory=list)
    modes: List[str] = field(default_factory=list)
    trials: int = 1
    started: str = ""
    elapsed: float = 0.0
    provider: str = ""
    model: str = ""

    def for_mode(self, mode: str) -> List[CaseScore]:
        return [s for s in self.scores if s.mode == mode and not s.error]

    def dimension_rate(self, mode: str, dimension: str) -> Optional[float]:
        passed = total = 0.0
        for score in self.for_mode(mode):
            got, possible = score.by_dimension().get(dimension, (0.0, 0.0))
            passed += got
            total += possible
        return round(passed / total, 3) if total else None

    def stability(self, mode: str) -> Dict[str, Any]:
        """How much the same inputs move between trials."""
        by_case: Dict[str, List[CaseScore]] = {}
        for score in self.for_mode(mode):
            by_case.setdefault(score.case_id, []).append(score)
        verdict_stable = 0
        measured = 0
        spreads = []
        for case_id, runs in by_case.items():
            if len(runs) < 2:
                continue
            measured += 1
            if len({r.verdict for r in runs}) == 1:
                verdict_stable += 1
            values = [r.weighted_score for r in runs
                      if isinstance(r.weighted_score, (int, float))]
            if len(values) > 1:
                spreads.append(max(values) - min(values))
        return {
            "cases_measured": measured,
            "verdict_identical_across_trials": (
                round(verdict_stable / measured, 3) if measured else None),
            "mean_score_spread": (round(statistics.mean(spreads), 1)
                                  if spreads else None),
            "max_score_spread": round(max(spreads), 1) if spreads else None,
        }

    def cost(self, mode: str) -> Dict[str, Any]:
        runs = self.for_mode(mode)
        return {
            "input_tokens": sum((r.tokens or {}).get("input", 0) for r in runs),
            "output_tokens": sum((r.tokens or {}).get("output", 0) for r in runs),
            "seconds": round(sum(r.elapsed_seconds or 0 for r in runs), 1),
            "runs": len(runs),
        }

    def failures(self, mode: str) -> List[Dict[str, Any]]:
        out = []
        for score in self.for_mode(mode):
            for check in score.failures:
                out.append({"case": score.case_id, "trial": score.trial,
                            "dimension": check.dimension, "detail": check.detail,
                            "rationale": check.rationale, "got": check.got})
        return out

    def errors(self) -> List[Dict[str, str]]:
        return [{"case": s.case_id, "mode": s.mode, "error": s.error}
                for s in self.scores if s.error]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started": self.started, "elapsed_seconds": round(self.elapsed, 1),
            "provider": self.provider, "model": self.model,
            "modes": self.modes, "trials": self.trials,
            "by_mode": {
                mode: {
                    "dimensions": {d: self.dimension_rate(mode, d)
                                   for d in DIMENSIONS},
                    "stability": self.stability(mode),
                    "cost": self.cost(mode),
                    "failures": self.failures(mode),
                } for mode in self.modes},
            "errors": self.errors(),
            "scores": [s.to_dict() for s in self.scores],
            "caveat": CAVEAT,
        }


CAVEAT = (
    "These are constructed cases with planted answers, so the score measures "
    "whether an analysis correctly reads evidence placed in front of it — not "
    "real-world accuracy. A system tuned against this suite could learn the "
    "fixtures rather than the skill. Read a high score as 'does not fail in the "
    "ways we know how to check', which is a floor and not a ceiling. The control "
    "case exists because a system that calls everything contradicted would "
    "otherwise score well.")


def run_suite(*, suite_dir: Optional[str] = None, modes: Optional[List[str]] = None,
              trials: int = 1, provider: str = "mock", model: Optional[str] = None,
              lens: str = "investor", out_dir: Optional[str] = None,
              only: Optional[List[str]] = None,
              on_event: Optional[Callable[[str], None]] = None) -> SuiteResult:
    """Run every case, in every mode, `trials` times."""
    from ..baseline import BaselineAnalyst
    from ..orchestrator import Pipeline

    def log(message: str) -> None:
        if on_event:
            on_event(message)

    root = Path(suite_dir) if suite_dir else default_suite_dir()
    suite_root = root.parent
    cases = load_suite(str(root))
    if only:
        wanted = set(only)
        cases = [c for c in cases
                 if c.id in wanted or wanted & set(c.tags)]
    modes = modes or ["pipeline"]

    result = SuiteResult(
        modes=list(modes), trials=trials, provider=provider, model=model or "",
        started=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    started = time.time()

    output_root = Path(out_dir) if out_dir else Path("./eval_output")
    output_root.mkdir(parents=True, exist_ok=True)

    for case in cases:
        deck = case.deck_path(suite_root)
        corpus_path = case.corpus_path(suite_root)
        corpus = EvidenceCorpus.load(str(corpus_path)) if corpus_path else None

        for mode in modes:
            for trial in range(trials):
                label = f"{case.id} [{mode}]" + (f" trial {trial + 1}"
                                                 if trials > 1 else "")
                log(f"  {label}")
                cfg = RunConfig(
                    deck_path=str(deck), lenses=[Lens.parse(lens)],
                    provider=ProviderConfig(name=provider, model=model),
                    # The corpus supplies the evidence, so the backend is unused.
                    research=ResearchConfig(name="none"),
                    output=OutputConfig(
                        formats=["json"],
                        out_dir=str(output_root / case.id / mode / str(trial))),
                    cache_dir=None, verbose=False)
                try:
                    if mode == "baseline":
                        analyst = BaselineAnalyst(cfg)
                        try:
                            analysis = analyst.run(corpus=corpus)
                        finally:
                            analyst.close()
                    else:
                        pipe = Pipeline(cfg)
                        try:
                            analysis = pipe.run(corpus=corpus)
                        finally:
                            pipe.close()
                except Exception as exc:  # noqa: BLE001 - one case must not end the run
                    log(f"    FAILED: {exc}")
                    result.scores.append(
                        failed_case(case, mode, f"{type(exc).__name__}: {exc}", trial))
                    continue

                score = score_case(case, analysis, mode=mode, lens=lens, trial=trial)
                result.scores.append(score)
                fails = len(score.failures)
                log(f"    {'all checks passed' if not fails else f'{fails} check(s) failed'}")

    result.elapsed = time.time() - started
    return result


def save(result: SuiteResult, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
    return str(p)
