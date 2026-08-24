"""The panel: several AI connections analyze the same deck, then review each other.

One model analyzing a deck gives you one model's blind spots. A panel gives you
something better — but only if the panelists actually engage with each other rather
than being averaged together. So the flow is:

    1. INDEPENDENT   each panelist runs the full three-agent pipeline alone, with no
                     knowledge of the others. Runs in parallel.
    2. CROSS-REVIEW  each panelist reads every other panelist's deck extraction, market
                     analysis and comparison — anonymized, so it judges the work and not
                     the brand — and records what it concedes, what it holds, and what
                     errors it found.
    3. REVISE        each panelist rewrites its own analysis to reflect what it conceded.
                     A panelist that was right and challenged badly should barely change.
    4. CONSENSUS     a chair reports where the panel agreed, where it split, and how much
                     the agreement is actually worth — including shared blind spots.

Agreement metrics are computed in code, not asked of a model, so the consensus report
is anchored to something measurable.
"""
from __future__ import annotations

import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .console import out as _out
from .claim_align import align_claims
from .config import Lens, ProviderConfig, RunConfig
from .orchestrator import AnalysisResult, Pipeline
from .prompts.lenses import lens_block
from .panel.strategies import RoundState, RoundStrategy, get_strategy
from .panel.voting import Ballot, VoteResult, ballot_from_json, tally
from .prompts.templates import (CONSENSUS_SYSTEM, CONSENSUS_USER, REVIEW_SYSTEM,
                                REVIEW_USER, REVISE_SYSTEM, REVISE_USER,
                                VOTE_SYSTEM, VOTE_USER)
from .providers.registry import get_provider
from .schemas import (COMPARISON_SCHEMA, CONSENSUS_SCHEMA, REVIEW_SCHEMA, coerce,
                      schema_block, scorecard_total)
from .validate import ValidationReport, _check_ids, validate_comparison
from .security.sanitizer import fence
from .sources import (SourceRegistry, audit_fragment, merge_registries,
                      rewrite_citations)

#: A panel needs at least two analysts, because one cannot cross-review itself.
#: Selecting a single model is a perfectly reasonable thing to want; it is just
#: not a panel, and callers should route it to a normal single-model run rather
#: than refuse it. See `deckscope.cli._panel`.
MIN_PANELISTS = 2

#: Panel sizes past this get a warning, not a refusal. It is the user's money and
#: the user's decision — the job here is to make the cost legible beforehand, not
#: to pick a ceiling on their behalf.
LARGE_PANEL_ADVISORY = 8


def panel_labels(count: int) -> List[str]:
    """Anonymous labels: A-Z, then AA, AB, … for as many as are asked for.

    A panelist judging "Panelist B" cannot favour a brand, which is the whole
    point of labelling. This used to be a hardcoded string of eight letters, so
    the panel silently capped at 8 — a limit that came from running out of
    letters rather than from anything real about panels.
    """
    out: List[str] = []
    i = 0
    while len(out) < count:
        name, n = "", i
        while True:
            name = chr(ord("A") + n % 26) + name
            n = n // 26 - 1
            if n < 0:
                break
        out.append(f"Panelist {name}")
        i += 1
    return out


#: Retained for anything importing the old name; A-Z as before.
LABELS = panel_labels(26)


def panel_cost_note(size: int) -> str:
    """What a panel of this size costs, in units a user can act on.

    Two different things scale differently and conflating them is misleading:

      * **API calls scale linearly** — roughly six per panelist (deck, market,
        comparison, review, revision, ballot). A 46-model panel is about 280
        calls, not thousands.
      * **Tokens scale quadratically in the review rounds**, because each
        panelist's single review call carries every *other* panelist's full
        analysis inside it. N panelists means N x (N-1) analyses of text moved,
        spread across only N calls.

    So a big panel is not call-throttled, it is token-expensive, and the surprise
    is in the bill rather than the wall clock.
    """
    calls = size * 6
    readings = size * (size - 1)
    note = (f"{size} panelists: about {calls} API calls (~6 each), and {readings} "
            f"peer readings carried inside the {size} review calls. Call count "
            f"grows with the panel; token cost grows with its square.")
    if size > LARGE_PANEL_ADVISORY:
        note += (" At this size the review rounds dominate the bill — worth "
                 "running once with `--rounds 0` first to see the independent "
                 "analyses before paying for cross-review.")
    return note


@dataclass
class Panelist:
    """One AI connection sitting on the panel."""

    label: str                       # "Panelist A" — what the others see
    name: str                        # "anthropic/claude-sonnet-5" — what you see
    provider: ProviderConfig
    result: Optional[AnalysisResult] = None
    review: Dict[str, Any] = field(default_factory=dict)
    revised: Dict[str, Any] = field(default_factory=dict)   # lens -> comparison
    #: lens -> every revision this panelist has made, oldest first. The panel's
    #: whole claim is that positions move under review, so the record of how they
    #: moved is a result, not debug output: a panelist that revised in round one
    #: and held firm in round two has said something different from one that never
    #: revised at all, and only the history distinguishes them.
    revision_history: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    error: Optional[str] = None
    elapsed: float = 0.0
    #: Where the other panelists ranked this report, and how they scored it.
    rank: Optional[int] = None
    vote_score: Optional[float] = None

    @property
    def ok(self) -> bool:
        return self.result is not None and self.error is None

    def lenses(self) -> List[str]:
        """Every lens this panelist has a position on, revised or original."""
        keys = list(self.result.comparisons if self.result else {})
        for lens in self.revised:
            if lens not in keys:
                keys.append(lens)
        return keys

    def final(self, lens: str) -> Dict[str, Any]:
        """The revised comparison if there is one, else the original."""
        if self.revised.get(lens):
            return self.revised[lens]
        return (self.result.comparisons.get(lens, {}) if self.result else {})

    def record_revision(self, lens: str, comparison: Dict[str, Any]) -> None:
        """Adopt a revision and keep the one it replaced."""
        self.revised[lens] = comparison
        self.revision_history.setdefault(lens, []).append(comparison)

    def to_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "name": self.name, "ok": self.ok,
                "error": self.error, "elapsed_seconds": round(self.elapsed, 1),
                "rank": self.rank, "vote_score": self.vote_score,
                "review": self.review,
                "revisions_per_lens": {lens: len(v)
                                       for lens, v in self.revision_history.items()},
                # Every lens, not just the revised ones. Keying off `revised`
                # dropped any lens the panelist never changed its mind about,
                # which silently removed unrevised positions from the output.
                "final": {lens: self.final(lens) for lens in self.lenses()}}


@dataclass
class PanelResult:
    panelists: List[Panelist] = field(default_factory=list)
    consensus: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # lens -> report
    metrics: Dict[str, Any] = field(default_factory=dict)               # lens -> metrics
    registry: Optional[SourceRegistry] = None
    security: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)
    written_files: List[str] = field(default_factory=list)
    #: lens -> how the panel ranked each other's reports
    votes: Dict[str, VoteResult] = field(default_factory=dict)
    #: Every stopping decision, so the report can explain its own cost.
    round_log: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def working(self) -> List[Panelist]:
        return [p for p in self.panelists if p.ok]

    @property
    def company(self) -> str:
        for p in self.working:
            return p.result.company  # type: ignore[union-attr]
        return "Unknown company"

    @property
    def lenses(self) -> List[str]:
        for p in self.working:
            return list(p.result.comparisons)  # type: ignore[union-attr]
        return []

    def primary_result(self) -> Optional[AnalysisResult]:
        """The first working panelist's result — used for the deck/market annexes."""
        return self.working[0].result if self.working else None

    def to_dict(self) -> Dict[str, Any]:
        return {"company": self.company,
                "panelists": [p.to_dict() for p in self.panelists],
                "consensus": self.consensus, "metrics": self.metrics,
                "votes": {k: v.to_dict() for k, v in self.votes.items()},
                "round_log": self.round_log,
                "security": self.security, "stats": self.stats,
                "references": self.registry.to_dict() if self.registry else {}}


# ====================================================================== run

class Panel:
    """Orchestrates the four rounds."""

    def __init__(self, config: RunConfig, panel: List[ProviderConfig],
                 *, rounds: int = 1, chair: Optional[ProviderConfig] = None,
                 parallel: bool = True, strategy: Any = "adaptive",
                 vote: bool = True,
                 on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> None:
        if len(panel) < MIN_PANELISTS:
            raise ValueError(
                "A panel needs at least two AI connections — one analyst cannot "
                "cross-review itself. Use `deckscope run` for a single model; it "
                "is the same analysis without the review rounds.")
        # No upper limit. A large panel is expensive, not invalid, and how much
        # someone wants to spend on their own analysis is their call. The cost is
        # made legible before the run instead — see `panel_cost_note`.
        labels = panel_labels(len(panel))
        self.config = config
        self.rounds = max(0, rounds)
        self.parallel = parallel
        #: When to stop reviewing. See deckscope/panel/strategies.py — there is no
        #: single right answer, so this is a choice rather than a constant.
        self.strategy: RoundStrategy = (
            strategy if isinstance(strategy, RoundStrategy)
            else get_strategy(strategy, max_rounds=self.rounds))
        #: Whether panelists rank each other's finished reports.
        self.vote = vote
        self.on_event = on_event or (lambda *_: None)
        self.panelists = [
            Panelist(label=labels[i], name=_pname(pc), provider=pc)
            for i, pc in enumerate(panel)]
        #: The chair writes the consensus. Defaults to the first panelist's backend.
        self.chair_config = chair or panel[0]
        #: Tokens spent on the rounds that make this a panel rather than three
        #: separate analyses: review, revision, voting and the chair's synthesis.
        #: These calls go straight to a provider, so nothing fed them into the
        #: member pipelines' accounting and the reported panel cost was simply
        #: "N independent runs" — it excluded precisely the interaction being
        #: paid for, and the CI gate that checked cost > 2x a pipeline passed
        #: while printing that the panel was honestly costed.
        self.interaction_usage: Dict[str, int] = {"input": 0, "output": 0, "calls": 0}
        self._usage_lock = threading.Lock()

    # ------------------------------------------------------------- logging
    def _log(self, message: str, **data: Any) -> None:
        self.on_event(message, data)
        if self.config.verbose:
            _out(f"[panel] {message}", flush=True)

    def _total_usage(self, working: List[Panelist]) -> Dict[str, Any]:
        """What the panel actually cost, with the interaction shown separately.

        The reported figure used to be the sum of each panelist's independent
        pipeline — that is, "N separate analyses" — and excluded review,
        revision, voting and the chair entirely. Those calls are the panel. A
        cost line that omits them makes the expensive mode look cheap, which is
        worse than reporting no cost at all.
        """
        members = {"input": 0, "output": 0}
        for p in working:
            usage = ((p.result.stats or {}).get("token_usage") or {}) if p.result else {}
            members["input"] += int(usage.get("input", 0) or 0)
            members["output"] += int(usage.get("output", 0) or 0)
        rounds = dict(self.interaction_usage)
        return {
            "input": members["input"] + rounds["input"],
            "output": members["output"] + rounds["output"],
            "independent_analyses": members,
            "panel_rounds": rounds,
            "note": ("`independent_analyses` is what N separate runs would have "
                     "cost; `panel_rounds` is the review, revision, voting and "
                     "chair calls that make it a panel."),
        }

    def _track(self, completion: Any) -> None:
        """Record a round's token cost. Safe to pass as `complete_json(on_usage=)`.

        Rounds fan out across threads, so the accumulation is locked.
        """
        usage = getattr(completion, "usage", None) or {}
        with self._usage_lock:
            self.interaction_usage["input"] += int(usage.get("input", 0) or 0)
            self.interaction_usage["output"] += int(usage.get("output", 0) or 0)
            self.interaction_usage["calls"] += 1

    # ---------------------------------------------------------- round one
    def run(self, corpus: Optional[Any] = None) -> PanelResult:
        """Convene the panel.

        `corpus` freezes the evidence every panelist reads. Without it each
        panelist researches independently, and any disagreement between them
        confounds two different things: reading the same evidence differently,
        and having been handed different evidence. Passing one corpus isolates
        the first, which is the only one the panel is trying to measure.
        """
        started = time.time()
        self._log(f"Convening a panel of {len(self.panelists)}: "
                  f"{', '.join(p.name for p in self.panelists)}")

        self._round_independent(corpus=corpus)
        working = [p for p in self.panelists if p.ok]
        if not working:
            raise RuntimeError(
                "Every panelist failed. Run `deckscope doctor` to check your "
                "connections, or run a single-model analysis to see the error.")
        if len(working) == 1:
            self._log(f"Only {working[0].name} succeeded — falling back to a "
                      f"single-model report. See the panel section for what failed.")

        result = PanelResult(panelists=self.panelists)
        primary = working[0].result
        # Every panelist's screen, not the first one's. Panelists research
        # independently, so a hostile page that only panelist C retrieved was
        # screened, quarantined — and then never disclosed, because the panel's
        # security report was a copy of panelist A's.
        result.security = _merge_security([p.result for p in working])
        lenses = list(primary.comparisons) if primary else []

        # ---- Unify the bibliography before anything is cross-read.
        #
        # Each panelist numbered its own sources from S1, so the same ID means a
        # different document to each of them. Merging first means every later
        # round — review, revision, consensus, rendering — speaks one namespace,
        # and a citation can never resolve to another panelist's source.
        result.registry, remap = merge_registries(
            {p.label: (p.result.registry if p.result else None) for p in working})
        for p in working:
            local = remap.get(p.label, {})
            if not local or not p.result:
                continue
            rewrite_citations(p.result.deck, local)
            rewrite_citations(p.result.market, local)
            for lens in p.result.comparisons:
                rewrite_citations(p.result.comparisons[lens], local)
            p.result.registry = result.registry
        self._log(f"Merged {len(working)} bibliographies into "
                  f"{len(result.registry.sources)} unique source(s)")

        # ---- Rounds 2-3, repeated until the strategy says stop.
        if len(working) >= 2:
            self._run_rounds(result, working, lenses)

        for lens in lenses:
            result.metrics[lens] = measure_agreement(working, lens)
            self._log(f"[{lens}] verdict agreement: "
                      f"{result.metrics[lens]['verdict']['agreement']}; "
                      f"score spread {result.metrics[lens]['score']['spread']}")

        # ---- Panelists rank each other's finished reports.
        if self.vote and len(working) >= 2:
            self._round_vote(result, working, lenses)

        if len(working) >= 2:
            self._round_consensus(result, working, lenses)
        elif lenses:
            result.consensus = {lens: _single_panelist_consensus(working[0], lens)
                                for lens in lenses}

        result.stats = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "elapsed_seconds": round(time.time() - started, 1),
            "panelists": [p.name for p in self.panelists],
            "panelists_ok": [p.name for p in working],
            "panelists_failed": [{"name": p.name, "error": p.error}
                                 for p in self.panelists if not p.ok],
            "rounds_configured": self.rounds,
            "rounds_run": len({e["after_round"] for e in result.round_log
                               if e.get("ran")}),
            "strategy": self.strategy.name,
            "stopped_because": ("; ".join(
                f"[{e['lens']}] {e['reason']}" for e in result.round_log
                if e["after_round"] == max(x["after_round"] for x in result.round_log))
                if result.round_log else "no review rounds"),
            "chair": _pname(self.chair_config),
            "research_backend": (primary.stats or {}).get("research_backend") if primary else None,
            # The merged bibliography, not one panelist's. `sources_found` used
            # to report the primary's count, so a panel that consulted forty
            # distinct documents could claim it found twelve.
            "sources_found": len(result.registry.sources) if result.registry else 0,
            "security_risk": (result.security or {}).get("overall_risk"),
            "token_usage": self._total_usage(working),
            "deckscope_version": _version(),
        }
        self._log(f"Panel complete in {result.stats['elapsed_seconds']}s")
        return result

    # ------------------------------------------------------------- rounds
    def _round_independent(self, corpus: Optional[Any] = None) -> None:
        self._log("Round 1: each panelist analyzes the deck independently")

        def one(p: Panelist) -> Panelist:
            t0 = time.time()
            cfg = _clone_config(self.config, p.provider)
            cfg.verbose = False
            pipe = Pipeline(cfg, on_event=lambda m, d, _p=p: self.on_event(
                f"[{_p.name}] {m}", d))
            try:
                p.result = pipe.run(corpus=corpus)
            except Exception as exc:  # noqa: BLE001 - one panelist failing is survivable
                p.error = f"{type(exc).__name__}: {exc}"
            finally:
                pipe.close()
                p.elapsed = time.time() - t0
            return p

        if self.parallel and len(self.panelists) > 1:
            with ThreadPoolExecutor(max_workers=len(self.panelists)) as pool:
                futures = {pool.submit(one, p): p for p in self.panelists}
                for fut in as_completed(futures):
                    p = futures[fut]
                    try:
                        fut.result()
                    except Exception as exc:  # noqa: BLE001
                        p.error = str(exc)
                    self._log(f"  {p.name}: "
                              + (f"done in {p.elapsed:.0f}s — "
                                 f"{_verdict_line(p)}" if p.ok
                                 else f"FAILED — {p.error}"))
        else:
            for p in self.panelists:
                one(p)
                self._log(f"  {p.name}: "
                          + (f"done in {p.elapsed:.0f}s — {_verdict_line(p)}"
                             if p.ok else f"FAILED — {p.error}"))

    def _snapshot_lens(self, working: List[Panelist], lens: str,
                       round_number: int,
                       previous_spread: Optional[float]) -> RoundState:
        """What the strategy sees for ONE lens."""
        metrics = measure_agreement(working, lens)
        return RoundState(
            round_number=round_number,
            max_rounds=self.strategy.max_rounds,
            scores={p.label: _score_of(p.final(lens)) for p in working},
            verdicts={p.label: (p.final(lens).get("verdict") or {}).get("call", "")
                      for p in working},
            confidences={p.label: (p.final(lens).get("verdict") or {}).get(
                "confidence", "low") for p in working},
            changes={p.label: len((p.review or {}).get("position_changes") or [])
                     for p in working},
            previous_spread=previous_spread,
            contested_claims=len(metrics.get("contested_claims") or []),
        )

    def _snapshot(self, working: List[Panelist], lenses: List[str],
                  round_number: int,
                  previous: Optional[Dict[str, float]] = None) -> Dict[str, RoundState]:
        """One state per lens.

        An earlier version used the first lens as a proxy for the whole panel,
        which meant an investor view that had converged could stop the run while
        the founder view was still split. The lenses ask different questions and
        converge at different rates, so each gets its own reading.
        """
        previous = previous or {}
        return {lens: self._snapshot_lens(working, lens, round_number,
                                          previous.get(lens))
                for lens in (lenses or ["investor"])}

    def _run_rounds(self, result: PanelResult, working: List[Panelist],
                    lenses: List[str]) -> None:
        """Review and revise until every lens's strategy says to stop."""
        self._log(f"Stopping rule: {self.strategy.describe()}")
        lenses = lenses or ["investor"]
        # One strategy instance per lens: `adaptive` chooses a delegate from what
        # it sees, and the right choice can differ between lenses.
        strategies = {
            lens: (self.strategy if len(lenses) == 1
                   else get_strategy(self.strategy.name,
                                     max_rounds=self.strategy.max_rounds))
            for lens in lenses}
        previous: Dict[str, float] = {}
        round_number = 0

        while True:
            states = self._snapshot(working, lenses, round_number, previous)
            decisions = {lens: strategies[lens].should_continue(state)
                         for lens, state in states.items()}

            for lens, state in states.items():
                d = decisions[lens]
                result.round_log.append({
                    "after_round": round_number,
                    "lens": lens,
                    "spread": state.spread,
                    "verdict_agreement": state.verdict_agreement,
                    "position_changes": state.total_changes,
                    "contested_claims": state.contested_claims,
                    "weakest_confidence": state.weakest_confidence,
                    "proceed": d.proceed,
                    "reason": d.reason,
                    "ran": False,
                    **d.detail,
                })

            # Continue while ANY lens still wants another round. Stopping when the
            # first lens settles would leave the others mid-argument — and an
            # earlier version did exactly that, using lens one as a proxy for the
            # whole panel.
            wants_more = [name for name, d in decisions.items() if d.proceed]
            if not wants_more:
                summary = "; ".join(f"[{name}] {d.reason}" for name, d in decisions.items())
                self._log(f"Stopping after {round_number} review round(s): {summary}")
                return

            for entry in result.round_log:
                if entry["after_round"] == round_number:
                    entry["ran"] = True
            round_number += 1
            settled = [name for name in lenses if name not in wants_more]
            self._log(f"Cross-review round {round_number} — still open: "
                      f"{', '.join(wants_more)}"
                      + (f" (settled: {', '.join(settled)})" if settled else ""))
            previous = {lens: st.spread for lens, st in states.items()}

            # Only the lenses that asked for another round.
            #
            # Every lens got its own stopping decision and then every lens was
            # reviewed and revised anyway, so the decision was computed and
            # discarded. Three things followed: a lens that had converged kept
            # changing, its settled conclusions were exposed to fresh regressions,
            # and the panel paid for review rounds nobody had asked for. The
            # reported stopping metric also described something that never
            # happened, which is the kind of number that is worse than absent.
            self._round_review(working, wants_more, result.registry)
            self._round_revise(working, wants_more, result.registry, round_number)

    def _round_vote(self, result: PanelResult, working: List[Panelist],
                    lenses: List[str]) -> None:
        """Each panelist ranks the others' finished reports.

        The chair still writes the headline synthesis. This runs alongside it so a
        reader can also see each panelist's own coherent report, ordered by which
        one the rest of the panel found most defensible — a synthesis can smooth
        away disagreement, and the ranking is evidence the synthesis cannot carry.
        """
        self._log("Round 4: panelists rank each other's reports")
        labels = [p.label for p in working]
        sources = _sources_block(working, result.registry)

        for lens in lenses:
            ballots: List[Ballot] = []

            def one(me: Panelist, _lens: str = lens) -> None:
                others = [o for o in working if o is not me]
                if not others:
                    return
                provider = get_provider(me.provider)
                try:
                    reports = "\n\n".join(
                        f"### {o.label}\n"
                        + json.dumps(_strip(o.final(_lens)), indent=2)[:40_000]
                        for o in others)
                    payload = provider.complete_json(
                        VOTE_SYSTEM.format(lens_block=lens_block(Lens.parse(_lens))),
                        VOTE_USER.format(
                            me=me.label,
                            reports=fence(reports, "PEER ANALYSES"),
                            sources=fence(sources, "SHARED BIBLIOGRAPHY")),
                        temperature=0.2, on_usage=self._track)
                    ballot = ballot_from_json(me.label, payload,
                                              [o.label for o in others])
                    if ballot:
                        ballots.append(ballot)
                except Exception as exc:  # noqa: BLE001 - a lost ballot is survivable
                    self._log(f"  {me.name}: ballot failed — {exc}")
                finally:
                    try:
                        provider.close()
                    except Exception:  # noqa: BLE001
                        pass

            _fanout(one, working, self.parallel)
            vote = tally(ballots, labels)
            result.votes[lens] = vote
            for i, label in enumerate(vote.order, 1):
                panelist = next((p for p in working if p.label == label), None)
                if panelist and lens == lenses[0]:
                    panelist.rank = i
                    panelist.vote_score = vote.scores.get(label)
            self._log(f"  [{lens}] {vote.note}")

    def _round_review(self, working: List[Panelist], lenses: List[str],
                      registry: Optional[SourceRegistry] = None) -> None:
        self._log("Round 2: each panelist reviews the others")
        sources = _sources_block(working, registry)

        def one(me: Panelist) -> None:
            others = [p for p in working if p is not me]
            provider = get_provider(me.provider)
            try:
                own = _packet(me, lenses, include_annexes=True)
                peers = "\n\n".join(_packet(o, lenses, include_annexes=True)
                                    for o in others)
                user = REVIEW_USER.format(
                    me=me.label,
                    schema=schema_block(REVIEW_SCHEMA, "PeerReview"),
                    own=fence(own, "YOUR OWN ANALYSIS"),
                    peers=fence(peers, "PEER ANALYSES"),
                    sources=fence(sources, "SHARED BIBLIOGRAPHY"))
                # Each lens asks a different question, so a review packet spanning
                # several lenses must say which posture applies to which — rather
                # than silently applying the first lens's stance to all of them.
                blocks = "\n\n".join(
                    f"### When reviewing the {name} analyses:\n{lens_block(Lens.parse(name))}"
                    for name in (lenses or ["investor"]))
                system = REVIEW_SYSTEM.format(lens_block=blocks)
                me.review = coerce(provider.complete_json(system, user, temperature=0.3,
                                                          on_usage=self._track),
                                   REVIEW_SCHEMA)
            except Exception as exc:  # noqa: BLE001
                me.review = {"error": f"{type(exc).__name__}: {exc}"}
            finally:
                try:
                    provider.close()
                except Exception:  # noqa: BLE001
                    pass

        _fanout(one, working, self.parallel)
        for p in working:
            n_changes = len(p.review.get("position_changes") or [])
            n_errors = sum(len(r.get("errors_found") or [])
                           for r in (p.review.get("peer_reviews") or []))
            if p.review.get("error"):
                self._log(f"  {p.name}: review failed — {p.review['error']}")
            else:
                self._log(f"  {p.name}: found {n_errors} error(s) in peers, "
                          f"changing {n_changes} of its own position(s)")

    def _round_revise(self, working: List[Panelist], lenses: List[str],
                      registry: Optional[SourceRegistry] = None,
                      round_number: int = 1) -> None:
        self._log("Round 3: each panelist revises its own analysis")
        sources = _sources_block(working, registry)
        citable = registry.citable_ids if registry else []

        def one(me: Panelist) -> None:
            if me.review.get("error"):
                return
            changes = me.review.get("position_changes") or []
            if not changes and str(me.review.get("will_revise")).lower() in ("false", "no"):
                # Declining to revise *this* round means the current position
                # stands — it does not retract earlier rounds. Clearing the dict
                # here threw away every revision made so far, so a panelist that
                # improved in round one and was satisfied in round two was scored
                # and voted on using its round-zero analysis.
                return
            provider = get_provider(me.provider)
            try:
                for lens in lenses:
                    # Revise from the panelist's CURRENT position, not its first
                    # one. Reading the original every round meant round three
                    # refined round zero and silently discarded round two.
                    current = me.final(lens)
                    own = json.dumps(_strip(current), indent=2)[:60_000]
                    user = REVISE_USER.format(
                        schema=schema_block(COMPARISON_SCHEMA, "RevisedComparison"),
                        own=fence(own, "YOUR ORIGINAL ANALYSIS"),
                        review=fence(json.dumps(me.review, indent=2)[:40_000],
                                     "YOUR REVIEW NOTES"),
                        sources=fence(sources, "SHARED BIBLIOGRAPHY"))
                    system = REVISE_SYSTEM.format(lens_block=lens_block(Lens.parse(lens)))
                    revised = coerce(provider.complete_json(system, user, temperature=0.3,
                                                            on_usage=self._track),
                                     COMPARISON_SCHEMA)
                    # A revision is model output like any other. Skipping
                    # validation here let out-of-range scores and invented
                    # citations into the convergence metrics and the vote.
                    validation = validate_comparison(
                        revised, valid_source_ids=citable)
                    # `validate_comparison` checks `scorecard` and `claim_audit`
                    # only. A revision is a whole comparison — summary, headline,
                    # blind spots, risks, actions, inline references — and every
                    # one of those could carry a fabricated citation that the
                    # single-model pipeline would have caught and stripped. The
                    # expensive mode must not offer the weaker guarantee.
                    cite_audit = (audit_fragment(revised, registry, strip=True)
                                  if registry is not None else None)
                    revised["_meta"] = {
                        "lens": lens, "revised": True, "round": round_number,
                        "weighted_score": scorecard_total(revised.get("scorecard") or []),
                        "revision_log": revised.get("revision_log") or [],
                        "validation": validation.to_dict(),
                        "citation_audit": (cite_audit.to_dict() if cite_audit else None),
                    }
                    me.record_revision(lens, revised)
            except Exception as exc:  # noqa: BLE001
                me.review.setdefault("revision_error", f"{type(exc).__name__}: {exc}")
            finally:
                try:
                    provider.close()
                except Exception:  # noqa: BLE001
                    pass

        _fanout(one, working, self.parallel)
        for p in working:
            if not p.revised:
                self._log(f"  {p.name}: held its original position")
                continue
            for lens in p.revised:
                before = _score_of(p.result.comparisons.get(lens, {}))  # type: ignore[union-attr]
                after = _score_of(p.revised[lens])
                v0 = (p.result.comparisons.get(lens, {}).get("verdict") or {}).get("call")  # type: ignore[union-attr]
                v1 = (p.revised[lens].get("verdict") or {}).get("call")
                moved = "verdict changed" if v0 != v1 else "verdict unchanged"
                self._log(f"  {p.name} [{lens}]: {before} → {after}/100, {moved}")

    def _round_consensus(self, result: PanelResult, working: List[Panelist],
                         lenses: List[str]) -> None:
        self._log(f"Round 4: {_pname(self.chair_config)} chairs the consensus")
        provider = get_provider(self.chair_config)
        sources = _sources_block(working, result.registry)
        citable_upper = [s.upper() for s in
                         (result.registry.citable_ids if result.registry else [])]
        composition = "\n".join(
            f"- {p.label} = {p.name}" + ("" if p.ok else f" (FAILED: {p.error})")
            for p in self.panelists)
        try:
            for lens in lenses:
                finals = "\n\n".join(
                    f"### {p.label} ({p.name})\n"
                    + json.dumps(_strip(p.final(lens)), indent=2)[:45_000]
                    for p in working)
                changes = "\n\n".join(
                    f"### {p.label} ({p.name})\n"
                    + json.dumps({"position_changes": p.review.get("position_changes"),
                                  "positions_held": p.review.get("positions_held"),
                                  "self_assessment": p.review.get("self_assessment")},
                                 indent=2)[:20_000]
                    for p in working)
                user = CONSENSUS_USER.format(
                    schema=schema_block(CONSENSUS_SCHEMA, "PanelConsensus"),
                    composition=composition,
                    metrics=json.dumps(result.metrics.get(lens, {}), indent=2),
                    finals=fence(finals, "PANELIST ANALYSES"),
                    changes=fence(changes, "PANELIST REVISIONS"),
                    sources=fence(sources, "SHARED BIBLIOGRAPHY"))
                system = CONSENSUS_SYSTEM.format(lens_block=lens_block(Lens.parse(lens)))
                report = coerce(provider.complete_json(system, user, temperature=0.3,
                                                       on_usage=self._track),
                                CONSENSUS_SCHEMA)
                # The chair is a model too. Its citations get the same treatment.
                chair_validation = ValidationReport()
                for row in report.get("contested") or []:
                    for pos in (row.get("positions") or []):
                        _check_ids(pos, "source_ids", set(citable_upper),
                                   "contested.positions", chair_validation)
                # That loop covers `contested.positions[].source_ids` and
                # nothing else, so the panel's single most-read artifact — the
                # chair's synthesis — was the least checked thing in the run.
                chair_audit = (audit_fragment(report, result.registry, strip=True)
                               if result.registry is not None else None)
                report["_meta"] = {"lens": lens, "chair": _pname(self.chair_config),
                                   "metrics": result.metrics.get(lens, {}),
                                   "validation": chair_validation.to_dict(),
                                   "citation_audit": (chair_audit.to_dict()
                                                      if chair_audit else None)}
                result.consensus[lens] = report
                self._log(f"  [{lens}] consensus: "
                          f"{(report.get('consensus_verdict') or {}).get('call', '—')} "
                          f"({(report.get('consensus_verdict') or {}).get('agreement', '—')})")
        except Exception as exc:  # noqa: BLE001
            self._log(f"  consensus failed: {exc}")
            for lens in lenses:
                result.consensus.setdefault(lens, {
                    "headline": "The chair could not produce a consensus report.",
                    "consensus_verdict": {"call": "NO CONSENSUS PRODUCED",
                                          "confidence": "low", "agreement": "unknown",
                                          "rationale": str(exc)},
                    "summary": "Each panelist's own analysis is reported below, along "
                               "with the measured agreement between them."})
        finally:
            try:
                provider.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------- output
    def render(self, result: PanelResult) -> List[str]:
        from .render.panel_renderer import render_panel

        cfg = self.config
        out_dir = Path(cfg.output.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        base = cfg.output.basename or _slug(result.company)
        written = render_panel(result, out_dir, base,
                               formats=list(dict.fromkeys(cfg.output.formats)),
                               theme=cfg.output.theme)
        for p in written:
            self._log(f"Wrote {p}")
        result.written_files = written
        return written


# =============================================================== metrics

def measure_agreement(working: List[Panelist], lens: str) -> Dict[str, Any]:
    """Agreement computed in code, so the consensus report rests on real numbers."""
    finals = [(p.label, p.name, p.final(lens)) for p in working]

    verdicts = [(lbl, (c.get("verdict") or {}).get("call") or "—")
                for lbl, _, c in finals]
    counts: Dict[str, int] = {}
    for _, v in verdicts:
        counts[v] = counts.get(v, 0) + 1
    top = max(counts.values()) if counts else 0
    agreement = ("unanimous" if top == len(verdicts) and len(verdicts) > 1
                 else "majority" if top > len(verdicts) / 2
                 else "split")

    scores = [_score_of(c) for _, _, c in finals]
    scores = [s for s in scores if isinstance(s, (int, float))]
    spread = round(max(scores) - min(scores), 1) if len(scores) > 1 else 0.0

    # per-dimension score spread
    dims: Dict[str, List[float]] = {}
    for _, _, c in finals:
        for row in c.get("scorecard") or []:
            try:
                dims.setdefault(str(row.get("dimension")), []).append(float(row.get("score")))
            except (TypeError, ValueError):
                continue
    dim_stats = {
        d: {"scores": v, "mean": round(statistics.mean(v), 1),
            "spread": round(max(v) - min(v), 1),
            "contested": (max(v) - min(v)) >= 3}
        for d, v in dims.items() if v}

    # Per-claim agreement, matched on CONTENT rather than on each panelist's own
    # numbering. Grouping by raw C-IDs compared unrelated propositions, because
    # nothing makes A's C1 and B's C1 the same claim.
    clusters = align_claims({lbl: (c.get("claim_audit") or [])
                             for lbl, _, c in finals})
    claim_stats = [cl.to_dict(len(finals)) for cl in clusters]
    for i, row in enumerate(claim_stats, 1):
        row["id"] = f"K{i}"          # panel-level key, distinct from local C-IDs

    changed = [{"panelist": p.label, "name": p.name,
                "changes": len(p.review.get("position_changes") or []),
                "held": len(p.review.get("positions_held") or []),
                "score_before": _score_of(p.result.comparisons.get(lens, {})),  # type: ignore[union-attr]
                "score_after": _score_of(p.final(lens)),
                "verdict_before": (p.result.comparisons.get(lens, {}).get("verdict")  # type: ignore[union-attr]
                                   or {}).get("call"),
                "verdict_after": (p.final(lens).get("verdict") or {}).get("call")}
               for p in working]

    return {
        "panelists": len(working),
        "verdict": {"per_panelist": dict(verdicts), "distribution": counts,
                    "agreement": agreement, "modal": max(counts, key=counts.get) if counts else None},
        "score": {"per_panelist": {lbl: _score_of(c) for lbl, _, c in finals},
                  "mean": round(statistics.mean(scores), 1) if scores else 0.0,
                  "spread": spread,
                  "stdev": round(statistics.pstdev(scores), 1) if len(scores) > 1 else 0.0,
                  "convergence": ("tight" if spread <= 5 else
                                  "moderate" if spread <= 15 else "wide")},
        "dimensions": dim_stats,
        "claims": claim_stats,
        "contested_claims": [c["id"] for c in claim_stats if c["contested"]],
        "single_panelist_claims": [c["id"] for c in claim_stats
                                   if c.get("single_panelist")],
        "claim_alignment": {
            "method": "content-based (salient numbers + significant word overlap)",
            "clusters": len(claim_stats),
            "raised_by_all": sum(1 for c in claim_stats
                                 if c["raised_by"] == len(finals)),
            "raised_by_one": sum(1 for c in claim_stats if c["raised_by"] == 1),
        },
        "movement": changed,
        "total_position_changes": sum(c["changes"] for c in changed),
    }


# ================================================================ helpers

def _fanout(fn: Callable[[Panelist], None], panelists: List[Panelist],
            parallel: bool) -> None:
    if parallel and len(panelists) > 1:
        with ThreadPoolExecutor(max_workers=len(panelists)) as pool:
            list(as_completed([pool.submit(fn, p) for p in panelists]))
    else:
        for p in panelists:
            fn(p)


def _packet(p: Panelist, lenses: List[str], include_annexes: bool = False) -> str:
    """One panelist's work, as the other panelists see it: anonymized."""
    payload: Dict[str, Any] = {"panelist": p.label}
    if include_annexes and p.result:
        payload["deck_extraction"] = _strip(p.result.deck)
        payload["market_analysis"] = _strip(p.result.market)
    payload["comparisons"] = {lens: _strip(p.final(lens)) for lens in lenses}
    return f"### {p.label}\n" + json.dumps(payload, indent=2, default=str)[:55_000]


def consensus_as_comparison(consensus: Dict[str, Any]) -> Dict[str, Any]:
    """The chair's consensus, shaped like a comparison so it can be judged.

    The panel's actual deliverable — the thing the report puts at the top and a
    user reads as "what the panel concluded" — is the consensus. It was never
    scoreable, because it follows a different schema: `consensus_verdict.call`
    rather than `verdict.call`, `claim_consensus[].consensus` rather than
    `claim_audit[].assessment`. So the evaluator scored a voted panelist
    instead, and when the vote tied or cycled it scored whichever panelist a
    sort happened to put first.

    Nothing new is invented here. The fields already exist and already mean the
    same things; this states the correspondence in one place so the panel is
    measured on its own output rather than on a proxy for it.
    """
    verdict = consensus.get("consensus_verdict") or {}
    claims = []
    for row in consensus.get("claim_consensus") or []:
        if not isinstance(row, dict):
            continue
        claims.append({
            "id": row.get("id"),
            "claim": row.get("claim"),
            "assessment": row.get("consensus"),
            "market_evidence": row.get("note") or "",
            "source_ids": list(row.get("source_ids") or []),
            "evidence_quality": row.get("confidence"),
        })
    contested_text = [
        f"{c.get('topic', '')}: {c.get('resolution', '')}"
        for c in (consensus.get("contested") or []) if isinstance(c, dict)]
    return {
        "headline": consensus.get("headline", ""),
        "verdict": {"call": verdict.get("call"),
                    "confidence": verdict.get("confidence"),
                    "confidence_rationale": verdict.get("rationale", ""),
                    "agreement": verdict.get("agreement")},
        "claim_audit": claims,
        "alignment": {
            "where_deck_matches_market": [
                p.get("point", "") for p in (consensus.get("where_all_agree") or [])
                if isinstance(p, dict)],
            "blind_spots": [
                {"what": b, "why_it_matters": "raised by the panel", "source_ids": []}
                for b in ((consensus.get("reliability") or {})
                          .get("shared_blind_spots") or [])],
        },
        "questions": [c.get("what_would_settle_it", "")
                      for c in (consensus.get("contested") or [])
                      if isinstance(c, dict)],
        "summary": "\n\n".join(
            [consensus.get("summary", "")] + contested_text).strip(),
        "_meta": dict(consensus.get("_meta") or {}, derived_from="panel consensus"),
    }


_RISK_ORDER = {"clean": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _merge_security(results: List[Optional[AnalysisResult]]) -> Dict[str, Any]:
    """One security report for the whole panel, not the first panelist's copy.

    Panelists research independently, so each one screens a different set of
    pages. Reporting only the primary's scan meant a hostile source that another
    panelist retrieved was detected, quarantined — and then invisible in the
    output, which is the half of the promise that matters. The headline risk
    becomes the worst any panelist saw, and every panelist's findings are listed
    with the panelist that hit them.
    """
    reports = [r.security for r in results if r and r.security]
    if not reports:
        return {}
    merged = dict(reports[0])
    worst = max(reports,
                key=lambda s: _RISK_ORDER.get(str(s.get("overall_risk", "")), 0))
    merged["overall_risk"] = worst.get("overall_risk")
    merged["per_panelist"] = [
        {"panelist": (r.stats or {}).get("model") or f"panelist {i + 1}",
         "overall_risk": (r.security or {}).get("overall_risk"),
         "summary": (r.security or {}).get("summary", [])}
        for i, r in enumerate(results) if r and r.security]
    merged["summary"] = [line for r in reports for line in (r.get("summary") or [])]
    return merged


def _sources_block(working: List[Panelist],
                   registry: Optional[SourceRegistry] = None) -> str:
    """The one bibliography every panelist cites from.

    Passing the merged registry is what makes cross-panelist citation coherent:
    when B says S7, A and the chair are looking at the same document.
    """
    if registry is not None and registry.sources:
        return registry.prompt_block(char_budget=45_000)
    for p in working:
        if p.result and p.result.registry:
            return p.result.registry.prompt_block(char_budget=45_000)
    return "(no shared bibliography available)"


def _strip(obj: Any) -> Any:
    """Remove internals before showing an artifact to another model."""
    if not isinstance(obj, dict):
        return obj
    return {k: v for k, v in obj.items() if not k.startswith("_")}


def _score_of(comparison: Dict[str, Any]) -> float:
    meta = comparison.get("_meta") or {}
    ws = meta.get("weighted_score") or {}
    if ws.get("score") is not None:
        return float(ws["score"])
    return float(scorecard_total(comparison.get("scorecard") or [])["score"])


def _verdict_line(p: Panelist) -> str:
    if not p.result:
        return "—"
    for lens, c in p.result.comparisons.items():
        return f"{(c.get('verdict') or {}).get('call', '—')} ({_score_of(c)}/100)"
    return "—"


def _pname(pc: ProviderConfig) -> str:
    return f"{pc.name}/{pc.model}" if pc.model else pc.name


def _clone_config(cfg: RunConfig, provider: ProviderConfig) -> RunConfig:
    import copy

    new = copy.deepcopy(cfg)
    new.provider = provider
    new.extract_provider = None
    # Each panelist gets its own cache namespace, or they would share answers.
    if cfg.cache_dir:
        new.cache_dir = str(Path(cfg.cache_dir) / _slug(_pname(provider)))
    return new


def _single_panelist_consensus(p: Panelist, lens: str) -> Dict[str, Any]:
    c = p.final(lens)
    return {
        "headline": c.get("headline", ""),
        "consensus_verdict": {
            "call": (c.get("verdict") or {}).get("call", "—"),
            "confidence": (c.get("verdict") or {}).get("confidence", "low"),
            "agreement": "single panelist — no cross-check was possible",
            "rationale": "Only one panelist completed its analysis, so nothing here has "
                         "been independently corroborated. Treat this as a single-model "
                         "report, not a panel finding."},
        "where_all_agree": [], "contested": [], "claim_consensus": [],
        "minority_report": [],
        "reliability": {"what_agreement_means_here":
                        "Nothing was corroborated: the other panelists failed to run.",
                        "shared_blind_spots": [], "caution":
                        "Re-run the panel once the failing connections are fixed."},
        "summary": c.get("summary", ""),
        "_meta": {"lens": lens, "degraded": True},
    }


def _slug(name: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(name)).strip("_").lower()
    return s or "analysis"


def _version() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return "unknown"


# ============================================================ convenience

def analyze_with_panel(deck: str, panel: List[str], *, lens: Any = "investor",
                       formats: Optional[List[str]] = None,
                       out_dir: str = "./deckscope_output",
                       research: str = "auto", rounds: int = 1,
                       company: Optional[str] = None, security: str = "balanced",
                       verbose: bool = True) -> PanelResult:
    """One-call panel API.

        from deckscope.ensemble import analyze_with_panel
        result = analyze_with_panel("deck.pdf",
                                    ["anthropic:claude-sonnet-5", "openai:gpt-5.2"],
                                    formats=["html", "pdf"])
        _out(result.consensus["investor"]["headline"])

    Each panel entry is "provider" or "provider:model".
    """
    from .config import OutputConfig, ResearchConfig

    lenses = lens if isinstance(lens, list) else [lens]
    cfg = RunConfig(
        deck_path=deck, company_hint=company,
        lenses=[Lens.parse(x) for x in lenses],
        research=ResearchConfig(name=research),
        output=OutputConfig(formats=formats or ["md"], out_dir=out_dir),
        security=security, verbose=verbose)
    p = Panel(cfg, [parse_panelist(s) for s in panel], rounds=rounds)
    result = p.run()
    p.render(result)
    return result


def parse_panelist(spec: str) -> ProviderConfig:
    """"anthropic:claude-sonnet-5" -> ProviderConfig(name=..., model=...)"""
    spec = spec.strip()
    if ":" in spec:
        name, model = spec.split(":", 1)
        return ProviderConfig(name=name.strip(), model=model.strip() or None)
    return ProviderConfig(name=spec)
