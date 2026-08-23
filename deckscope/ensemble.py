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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import Lens, ProviderConfig, RunConfig
from .orchestrator import AnalysisResult, Pipeline
from .prompts.lenses import lens_block
from .prompts.templates import (CONSENSUS_SYSTEM, CONSENSUS_USER, REVIEW_SYSTEM,
                                REVIEW_USER, REVISE_SYSTEM, REVISE_USER)
from .providers.registry import get_provider
from .schemas import (COMPARISON_SCHEMA, CONSENSUS_SCHEMA, REVIEW_SCHEMA, coerce,
                      schema_block, scorecard_total)
from .security.sanitizer import fence
from .security.text_scanner import scan_text
from .sources import SourceRegistry

#: Anonymous labels. A panelist judging "Panelist B" cannot favour a brand.
LABELS = [f"Panelist {c}" for c in "ABCDEFGH"]


@dataclass
class Panelist:
    """One AI connection sitting on the panel."""

    label: str                       # "Panelist A" — what the others see
    name: str                        # "anthropic/claude-sonnet-5" — what you see
    provider: ProviderConfig
    result: Optional[AnalysisResult] = None
    review: Dict[str, Any] = field(default_factory=dict)
    revised: Dict[str, Any] = field(default_factory=dict)   # lens -> comparison
    error: Optional[str] = None
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return self.result is not None and self.error is None

    def final(self, lens: str) -> Dict[str, Any]:
        """The revised comparison if there is one, else the original."""
        if self.revised.get(lens):
            return self.revised[lens]
        return (self.result.comparisons.get(lens, {}) if self.result else {})

    def to_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "name": self.name, "ok": self.ok,
                "error": self.error, "elapsed_seconds": round(self.elapsed, 1),
                "review": self.review,
                "final": {lens: self.final(lens) for lens in (self.revised or
                          (self.result.comparisons if self.result else {}))}}


@dataclass
class PanelResult:
    panelists: List[Panelist] = field(default_factory=list)
    consensus: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # lens -> report
    metrics: Dict[str, Any] = field(default_factory=dict)               # lens -> metrics
    registry: Optional[SourceRegistry] = None
    security: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)
    written_files: List[str] = field(default_factory=list)

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
                "security": self.security, "stats": self.stats,
                "references": self.registry.to_dict() if self.registry else {}}


# ====================================================================== run

class Panel:
    """Orchestrates the four rounds."""

    def __init__(self, config: RunConfig, panel: List[ProviderConfig],
                 *, rounds: int = 1, chair: Optional[ProviderConfig] = None,
                 parallel: bool = True,
                 on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> None:
        if len(panel) < 2:
            raise ValueError(
                "A panel needs at least two AI connections. Give it two providers, or "
                "the same provider with two different models.")
        if len(panel) > len(LABELS):
            raise ValueError(f"At most {len(LABELS)} panelists.")
        self.config = config
        self.rounds = max(0, rounds)
        self.parallel = parallel
        self.on_event = on_event or (lambda *_: None)
        self.panelists = [
            Panelist(label=LABELS[i], name=_pname(pc), provider=pc)
            for i, pc in enumerate(panel)]
        #: The chair writes the consensus. Defaults to the first panelist's backend.
        self.chair_config = chair or panel[0]

    # ------------------------------------------------------------- logging
    def _log(self, message: str, **data: Any) -> None:
        self.on_event(message, data)
        if self.config.verbose:
            print(f"[panel] {message}", flush=True)

    # ---------------------------------------------------------- round one
    def run(self) -> PanelResult:
        started = time.time()
        self._log(f"Convening a panel of {len(self.panelists)}: "
                  f"{', '.join(p.name for p in self.panelists)}")

        self._round_independent()
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
        result.registry = primary.registry if primary else None
        result.security = primary.security if primary else {}

        lenses = list(primary.comparisons) if primary else []

        if len(working) >= 2 and self.rounds > 0:
            for round_no in range(1, self.rounds + 1):
                self._log(f"Cross-review round {round_no} of {self.rounds}")
                self._round_review(working, lenses)
                self._round_revise(working, lenses)

        for lens in lenses:
            result.metrics[lens] = measure_agreement(working, lens)
            self._log(f"[{lens}] verdict agreement: "
                      f"{result.metrics[lens]['verdict']['agreement']}; "
                      f"score spread {result.metrics[lens]['score']['spread']}")

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
            "rounds": self.rounds,
            "chair": _pname(self.chair_config),
            "research_backend": (primary.stats or {}).get("research_backend") if primary else None,
            "sources_found": (primary.stats or {}).get("sources_found", 0) if primary else 0,
            "security_risk": (primary.security or {}).get("overall_risk") if primary else None,
            "deckscope_version": _version(),
        }
        self._log(f"Panel complete in {result.stats['elapsed_seconds']}s")
        return result

    # ------------------------------------------------------------- rounds
    def _round_independent(self) -> None:
        self._log("Round 1: each panelist analyzes the deck independently")

        def one(p: Panelist) -> Panelist:
            t0 = time.time()
            cfg = _clone_config(self.config, p.provider)
            cfg.verbose = False
            pipe = Pipeline(cfg, on_event=lambda m, d, _p=p: self.on_event(
                f"[{_p.name}] {m}", d))
            try:
                p.result = pipe.run()
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

    def _round_review(self, working: List[Panelist], lenses: List[str]) -> None:
        self._log("Round 2: each panelist reviews the others")
        sources = _sources_block(working)

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
                system = REVIEW_SYSTEM.format(
                    lens_block=lens_block(Lens.parse(lenses[0]) if lenses
                                          else Lens.INVESTOR))
                me.review = coerce(provider.complete_json(system, user, temperature=0.3),
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

    def _round_revise(self, working: List[Panelist], lenses: List[str]) -> None:
        self._log("Round 3: each panelist revises its own analysis")
        sources = _sources_block(working)

        def one(me: Panelist) -> None:
            if me.review.get("error"):
                return
            changes = me.review.get("position_changes") or []
            if not changes and str(me.review.get("will_revise")).lower() in ("false", "no"):
                me.revised = {}
                return
            provider = get_provider(me.provider)
            try:
                for lens in lenses:
                    own = json.dumps(_strip(me.result.comparisons.get(lens, {})),  # type: ignore[union-attr]
                                     indent=2)[:60_000]
                    user = REVISE_USER.format(
                        schema=schema_block(COMPARISON_SCHEMA, "RevisedComparison"),
                        own=fence(own, "YOUR ORIGINAL ANALYSIS"),
                        review=fence(json.dumps(me.review, indent=2)[:40_000],
                                     "YOUR REVIEW NOTES"),
                        sources=fence(sources, "SHARED BIBLIOGRAPHY"))
                    system = REVISE_SYSTEM.format(lens_block=lens_block(Lens.parse(lens)))
                    revised = coerce(provider.complete_json(system, user, temperature=0.3),
                                     COMPARISON_SCHEMA)
                    revised["_meta"] = {
                        "lens": lens, "revised": True,
                        "weighted_score": scorecard_total(revised.get("scorecard") or []),
                        "revision_log": revised.get("revision_log") or [],
                    }
                    me.revised[lens] = revised
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
        sources = _sources_block(working)
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
                report = coerce(provider.complete_json(system, user, temperature=0.3),
                                CONSENSUS_SCHEMA)
                report["_meta"] = {"lens": lens, "chair": _pname(self.chair_config),
                                   "metrics": result.metrics.get(lens, {})}
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

    # per-claim assessment agreement
    claims: Dict[str, Dict[str, str]] = {}
    claim_text: Dict[str, str] = {}
    for lbl, _, c in finals:
        for row in c.get("claim_audit") or []:
            cid = str(row.get("id") or "")
            if not cid:
                continue
            claims.setdefault(cid, {})[lbl] = str(row.get("assessment") or "—")
            claim_text.setdefault(cid, str(row.get("claim") or ""))
    claim_stats = []
    for cid, per in claims.items():
        vals = list(per.values())
        uniq = set(vals)
        claim_stats.append({
            "id": cid, "claim": claim_text.get(cid, ""),
            "assessments": per,
            "unanimous": len(uniq) == 1 and len(vals) == len(finals),
            "distinct_positions": len(uniq),
            "contested": len(uniq) > 1})

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


def _sources_block(working: List[Panelist]) -> str:
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
                                    ["anthropic:claude-sonnet-5", "openai:gpt-4o"],
                                    formats=["html", "pdf"])
        print(result.consensus["investor"]["headline"])

    Each panel entry is "provider" or "provider:model".
    """
    from .config import OutputConfig, ResearchConfig

    lenses = lens if isinstance(lens, list) else [lens]
    cfg = RunConfig(
        deck_path=deck, company_hint=company,
        lenses=[Lens.parse(l) for l in lenses],
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
