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

import hashlib
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

    def discrimination(self) -> Dict[str, Any]:
        """Did the modes actually produce different analyses?

        This exists because of a real and embarrassing result. Running
        `--mode pipeline baseline` under the mock returned a delta of +0.000 on
        every dimension, and that was reported as though it were a measurement:
        "the three-agent pipeline performs identically to a single prompt."

        It was not a measurement. The two modes had emitted *byte-identical
        analyses*, because the provider driving them returns the same fixture
        either way. A comparison between two things that were never
        distinguished cannot tell you they perform the same — it can only tell
        you the comparison did not happen. Reporting +0.000 as a finding is the
        same class of error as an evaluator reporting "every check passed" over
        zero cases: a gate that cannot fail, quoted as though it had passed.

        So: fingerprint what each mode produced, and say plainly whether the
        comparison was capable of showing a difference at all.
        """
        if len(self.modes) < 2:
            return {"comparable": False,
                    "reason": "only one mode was run, so nothing was compared"}

        by_case: Dict[str, Dict[str, str]] = {}
        for score in self.scores:
            if score.error or not score.output_fingerprint:
                continue
            by_case.setdefault(score.case_id, {})[score.mode] = \
                score.output_fingerprint

        compared = identical = 0
        identical_cases: List[str] = []
        for case_id, prints in by_case.items():
            present = [prints[m] for m in self.modes if m in prints]
            if len(present) < 2:
                continue
            compared += 1
            if len(set(present)) == 1:
                identical += 1
                identical_cases.append(case_id)

        if not compared:
            return {"comparable": False,
                    "reason": "no case ran in more than one mode"}

        rate = identical / compared
        informative = rate < 1.0
        return {
            "comparable": informative,
            "cases_compared": compared,
            "cases_with_identical_output": identical,
            "identical_rate": round(rate, 3),
            "identical_cases": sorted(identical_cases),
            "reason": ("" if informative else
                       f"all {compared} case(s) produced byte-identical analyses in "
                       f"every mode, so this provider does not distinguish them. Any "
                       f"score difference between modes would be zero by "
                       f"construction; this comparison measures nothing about the "
                       f"architectures. Re-run against a real model to make it "
                       f"informative."),
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
            "discrimination": self.discrimination(),
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
              only: Optional[List[str]] = None, panel_size: int = 3,
              on_event: Optional[Callable[[str], None]] = None) -> SuiteResult:
    """Run every case, in every mode, `trials` times.

    `panel_size` is how many panelists the `panel` mode convenes. It is a real
    cost multiplier — a panel of three costs roughly three times a pipeline run
    plus the review rounds — which is precisely why the mode needed to be
    measurable rather than assumed to help.
    """
    from ..baseline import BaselineAnalyst
    from ..orchestrator import Pipeline

    def log(message: str) -> None:
        if on_event:
            on_event(message)

    # Every way this run could check nothing is an error, not a pass. The
    # evaluator reports success when no check fails, so "no checks" used to read
    # as "all good" — including from an installed wheel with no fixtures, from
    # `--trials 0`, and from a misspelled `--only`.
    if trials < 1:
        raise ValueError(
            f"trials must be at least 1, got {trials}. A zero-trial run executes "
            f"no cases and would report success without checking anything.")

    root = Path(suite_dir) if suite_dir else default_suite_dir()
    suite_root = root.parent
    cases = load_suite(str(root))
    if only:
        wanted = set(only)
        selected = [c for c in cases
                    if c.id in wanted or wanted & set(c.tags)]
        if not selected:
            known_ids = ", ".join(sorted(c.id for c in cases))
            known_tags = ", ".join(sorted({t for c in cases for t in c.tags}))
            raise ValueError(
                f"--only {sorted(wanted)} matched no cases. "
                f"Known ids: {known_ids or '(none)'}. "
                f"Known tags: {known_tags or '(none)'}.")
        cases = selected
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
                    elif mode == "panel":
                        analysis = _run_panel(cfg, corpus, provider, model, panel_size)
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
                # Fingerprint what this mode actually produced. Two modes that
                # emit the same analysis have not "performed equally" — they have
                # not been distinguished at all, and the difference matters.
                score.output_fingerprint = _fingerprint_analysis(analysis, lens)
                result.scores.append(score)
                fails = len(score.failures)
                log(f"    {'all checks passed' if not fails else f'{fails} check(s) failed'}")

    result.elapsed = time.time() - started
    return result


def _run_panel(cfg, corpus, provider: str, model: Optional[str], size: int):
    """Run the panel and return its winning report shaped like a single analysis.

    The panel exists to be compared against the cheaper modes, so it has to be
    scoreable by the same scorer. The consensus report is the panel's actual
    output — the thing a user reads — so that is what gets scored, carrying the
    merged registry so citation checks resolve against the unified bibliography.
    """
    from ..ensemble import Panel
    from ..config import ProviderConfig

    # Distinct model names so the mock panelists diverge; a panel that agrees by
    # construction would measure nothing about the panel.
    members = [ProviderConfig(name=provider, model=model or f"panel-{i}")
               for i in range(size)]
    panel = Panel(cfg, members, rounds=1)
    result = panel.run(corpus=corpus)

    primary = result.primary_result()
    if primary is None:
        raise RuntimeError("every panelist failed")

    # Score the panel's *winning comparison*, not the chair's consensus.
    #
    # The consensus follows CONSENSUS_SCHEMA — headline, agreement level,
    # contested topics — and has no `claim_audit` or `verdict.call` at all.
    # Scoring it gave the panel 0.000 on claim accuracy and verdict, which looked
    # like a devastating result for the panel and was actually a category error:
    # the scorer was reading a document that does not contain the fields it
    # checks. The comparable artifact is the report the panel voted highest,
    # which is what a user is told to read as the panel's answer.
    ranked = sorted(result.working,
                    key=lambda p: (p.rank if p.rank is not None else 99))
    winner = ranked[0] if ranked else None
    if winner is not None:
        primary.comparisons = {lens: winner.final(lens)
                               for lens in winner.lenses()}
    primary.registry = result.registry or primary.registry

    # Report what the panel actually cost, not what one panelist cost.
    #
    # `primary` is a single panelist's result, so its token counts describe one
    # member. Left alone, a three-member panel reported the same cost as a single
    # pipeline run — which would make a cost/benefit comparison between modes
    # worse than useless, since the expensive option would look free.
    total = {"input": 0, "output": 0}
    for member in result.working:
        usage = ((member.result.stats or {}).get("token_usage") or {}
                 if member.result else {})
        total["input"] += int(usage.get("input") or 0)
        total["output"] += int(usage.get("output") or 0)
    stats = dict(primary.stats or {})
    stats["token_usage"] = total
    stats["panelists"] = len(result.working)
    stats["elapsed_seconds"] = (result.stats or {}).get(
        "elapsed_seconds", stats.get("elapsed_seconds"))
    primary.stats = stats
    return primary


def _fingerprint_analysis(analysis, lens: str) -> str:
    """A stable hash of the comparison this mode produced.

    Deliberately over the *content* a reader would see — claims, assessments,
    citations, verdict — and not over metadata like timings or model names,
    which differ between modes for uninteresting reasons.
    """
    comp = (getattr(analysis, "comparisons", {}) or {}).get(lens, {})
    payload = {
        "claims": [{"claim": r.get("claim"), "assessment": r.get("assessment"),
                    "source_ids": sorted(str(s) for s in (r.get("source_ids") or []))}
                   for r in (comp.get("claim_audit") or []) if isinstance(r, dict)],
        "blind_spots": sorted(str(b) for b in
                              ((comp.get("alignment") or {}).get("blind_spots") or [])),
        "verdict": (comp.get("verdict") or {}).get("call"),
        "confidence": (comp.get("verdict") or {}).get("confidence"),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def save(result: SuiteResult, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
    return str(p)
