"""Single-prompt analysis, as a control for the three-agent pipeline.

DeckScope's central claim is that separating extraction, research and comparison
produces a better analysis than asking one model to do all three at once. That is
a reasonable hypothesis and it is the reason the project is shaped the way it is —
but it had never been tested, because there was nothing to test it against.

This is the something. One prompt, one call, the same schema, the same lens, the
same research material. Run both on the same deck and the difference is visible
rather than assumed.

It is a real mode, not benchmark scaffolding, for two reasons. Scaffolding rots
when nobody runs it. And it is genuinely the right choice sometimes: it is roughly
a third of the cost, and on a deck you already understand it may be all you need.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .config import RunConfig
from .ingest.loader import DeckDocument, load_deck
from .orchestrator import AnalysisResult
from .prompts.lenses import lens_block
from .prompts.templates import BASELINE_SYSTEM, BASELINE_USER
from .providers.base import LLMProvider
from .providers.registry import get_provider
from .research.registry import get_researcher
from .schemas import COMPARISON_SCHEMA, coerce, schema_block, scorecard_total
from .security.policy import SecurityPolicy
from .security.report import ScanReport
from .security.sanitizer import fence
from .security.screening import screen_deck
from .sources import resolve_citations
from .validate import validate_comparison

MAX_DECK_CHARS = 120_000


class BaselineAnalyst:
    """One prompt, one call. Everything else about the run stays identical."""

    name = "baseline"

    def __init__(self, config: RunConfig,
                 on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 provider: Optional[LLMProvider] = None) -> None:
        self.config = config
        self.on_event = on_event or (lambda *_: None)
        self.provider = provider or get_provider(config.provider)
        self._owns_provider = provider is None
        self.researcher = get_researcher(config.research, self.provider)

    def _log(self, message: str, **data: Any) -> None:
        self.on_event(message, data)
        if self.config.verbose:
            from .console import out
            out(f"[baseline] {message}")

    def run(self, deck_path: Optional[str] = None,
            corpus: Any = None) -> AnalysisResult:
        cfg = self.config
        started = time.time()
        source = deck_path or cfg.deck_path
        self._log(f"Single-prompt analysis ({self.provider.name}/{self.provider.model})")

        doc: DeckDocument = (load_deck(cfg.deck_text, is_text=True) if cfg.deck_text
                             else load_deck(source))

        # Identical screening to the pipeline. The comparison is only meaningful
        # if the only difference between the two modes is the prompting.
        policy: SecurityPolicy = cfg.security or SecurityPolicy()
        deck_scan = ScanReport(target="pitch deck")
        if policy.enabled:
            doc, deck_scan = screen_deck(doc, policy,
                                         deck_path=None if cfg.deck_text else source)
            self._log(deck_scan.summary_line())

        from .corpus import gather

        if corpus is None:
            queries = self._queries(doc) if self.researcher.name != "none" else []
            if queries:
                self._log(f"researching with {self.researcher.name}: "
                          f"{len(queries)} queries")
            corpus = gather(self.researcher, queries, policy,
                            max_results=cfg.research.max_results,
                            on_event=lambda m, _d=None: self._log(m))
        else:
            self._log(f"using frozen corpus {corpus.fingerprint()} "
                      f"({corpus.kept} source(s)) — identical evidence to the "
                      f"pipeline run")

        registry = corpus.registry
        source_scan = corpus.security or ScanReport(target="web sources")
        research_block = ""
        if not corpus.empty:
            research_block = fence(corpus.prompt_block(char_budget=60_000),
                                   "RESEARCH MATERIAL")

        text = doc.text
        if len(text) > MAX_DECK_CHARS:
            text = text[:MAX_DECK_CHARS] + "\n\n[... deck truncated for length ...]"

        comparisons: Dict[str, Dict[str, Any]] = {}
        usage = {"input": 0, "output": 0}

        def track(completion: Any) -> None:
            if getattr(completion, "usage", None):
                usage["input"] += completion.usage.get("input", 0)
                usage["output"] += completion.usage.get("output", 0)

        for lens in cfg.lenses:
            self._log(f"analyzing ({lens.value})")
            user = BASELINE_USER.format(
                schema=schema_block(COMPARISON_SCHEMA, "Comparison"),
                research_note=("Cite every figure by its source ID." if registry.sources
                               else "No external research was available for this run. "
                                    "Set confidence accordingly and say so."),
                deck_text=text,
                research_material=research_block)
            result = self.provider.complete_json(
                BASELINE_SYSTEM.format(lens_block=lens_block(lens)),
                user, temperature=0.3, on_usage=track)
            result = coerce(result, COMPARISON_SCHEMA)
            validation = validate_comparison(
                result, valid_source_ids=registry.citable_ids)
            if not validation.ok:
                self._log(f"validation: {validation.summary()}")
            result["_meta"] = {
                "lens": lens.value, "mode": "baseline",
                "weighted_score": scorecard_total(result.get("scorecard") or []),
                "validation": validation.to_dict(),
            }
            comparisons[lens.value] = result
            verdict = (result.get("verdict") or {}).get("call", "—")
            self._log(f"verdict: {verdict} "
                      f"({result['_meta']['weighted_score']['score']}/100)")

        combined = ScanReport(target="all inputs")
        combined.extend(deck_scan)
        combined.extend(source_scan)

        out = AnalysisResult(
            deck={"company": {"name": self._company(comparisons)},
                  "_meta": {"mode": "baseline",
                            "note": "Single-prompt mode does not produce a separate "
                                    "deck extraction — the model was not asked for "
                                    "one. This is one of the differences being "
                                    "measured."}},
            market={"_meta": {"mode": "baseline", "backend": self.researcher.name,
                              "n_results": len(registry.sources),
                              "registry": registry.to_dict()}},
            comparisons=comparisons,
            corpus=corpus,
            config=cfg.to_dict(),
            security={"overall_risk": combined.risk, "mode": policy.mode.value,
                      "deck": deck_scan.to_dict(),
                      "web_sources": source_scan.to_dict(),
                      "summary": [deck_scan.summary_line(),
                                  source_scan.summary_line()]},
            stats={
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "elapsed_seconds": round(time.time() - started, 1),
                "mode": "baseline",
                "provider": self.provider.name, "model": self.provider.model,
                "research_backend": corpus.backend,
                "sources_found": corpus.kept,
                "corpus_fingerprint": corpus.fingerprint(),
                "security_risk": combined.risk,
                "token_usage": usage,
                "model_calls": len(cfg.lenses),
            },
        )
        out.registry = resolve_citations(out)
        out.stats["references"] = out.registry.stats()
        self._log(f"done in {out.stats['elapsed_seconds']}s, "
                  f"{out.stats['model_calls']} model call(s)")
        return out

    def _queries(self, doc: DeckDocument) -> List[str]:
        """Cheap keyword queries.

        Deliberately not the pipeline's model-generated research agenda: that
        agenda is one of the things the three-agent design is supposed to be
        buying, so handing it to the baseline would test the wrong thing.
        """
        import re

        words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{3,}", doc.text[:4000])
        stop = {"slide", "with", "that", "this", "from", "have", "your", "their",
                "which", "about", "will", "into", "more", "than", "when", "them"}
        seen, terms = set(), []
        for w in words:
            lw = w.lower()
            if lw in stop or lw in seen:
                continue
            seen.add(lw)
            terms.append(w)
            if len(terms) >= 6:
                break
        head = " ".join(terms[:4])
        return [f"{head} market size",
                f"{head} competitors",
                f"{head} funding rounds 2026"][: max(1, self.config.research.max_queries)]

    @staticmethod
    def _company(comparisons: Dict[str, Dict[str, Any]]) -> str:
        for c in comparisons.values():
            headline = c.get("headline") or ""
            if headline:
                return headline.split(" ")[0].strip(",.:") or "Unknown company"
        return "Unknown company"

    def close(self) -> None:
        if self._owns_provider:
            try:
                self.provider.close()
            except Exception:  # noqa: BLE001
                pass


def compare_modes(pipeline_result: AnalysisResult,
                  baseline_result: AnalysisResult) -> Dict[str, Any]:
    """What the two modes made of the same evidence.

    **Metric design matters here more than anywhere else in the project**, because
    a badly chosen metric will make the architecture look good regardless of
    whether it is. Counting claims, citations, risks and blind spots — the first
    version of this function — rewards verbosity: a mode that says more scores
    higher whether or not it is more correct.

    So the counts are replaced by rates and by matched differences:

      * **citation density** — what fraction of claims carry a source, rather than
        how many citations appear in total
      * **uncited assertion rate** — the inverse, stated directly, because an
        assertion resting on nothing is the failure the bibliography exists to
        catch
      * **evidence-quality mix** — how the mode graded its own support
      * **unique findings** — claims one mode raised and the other did not,
        matched on content with the same aligner the panel uses, so a rephrasing
        is not counted as a discovery
      * **contradictions** — the same claim assessed differently, which is the
        most interesting output of all

    Even so this measures difference, not correctness. Deciding which analysis is
    *better* needs labelled decks or a blinded human rubric, and the caveat at the
    bottom says so rather than letting a reader infer a verdict from a table.
    """
    from .claim_align import align_claims

    out: Dict[str, Any] = {"lenses": {}}

    pipe_corpus = getattr(pipeline_result, "corpus", None)
    base_corpus = getattr(baseline_result, "corpus", None)
    pipe_fp = pipe_corpus.fingerprint() if pipe_corpus else None
    base_fp = base_corpus.fingerprint() if base_corpus else None
    shared = bool(pipe_fp) and pipe_fp == base_fp

    out["evidence"] = {
        "pipeline_corpus": pipe_fp,
        "baseline_corpus": base_fp,
        "identical": shared,
        "sources": pipe_corpus.kept if pipe_corpus else 0,
        "note": ("Both modes read the same frozen sources, so any difference below "
                 "is attributable to how the evidence was processed."
                 if shared else
                 "The two modes did NOT read the same sources, so differences below "
                 "are confounded by the evidence and cannot be attributed to the "
                 "architecture. Run with --mode both to share a corpus."),
    }

    for lens, pipe_cmp in (pipeline_result.comparisons or {}).items():
        base_cmp = (baseline_result.comparisons or {}).get(lens)
        if not base_cmp:
            continue

        pipe_claims = [c for c in (pipe_cmp.get("claim_audit") or [])
                       if isinstance(c, dict)]
        base_claims = [c for c in (base_cmp.get("claim_audit") or [])
                       if isinstance(c, dict)]

        clusters = align_claims({"pipeline": pipe_claims, "baseline": base_claims})
        both, only_pipe, only_base, contradictions = [], [], [], []
        for cluster in clusters:
            row = cluster.to_dict(2)
            who = set(row["assessments"])
            if who == {"pipeline", "baseline"}:
                both.append(row)
                if row["distinct_positions"] > 1:
                    contradictions.append({
                        "claim": row["claim"],
                        "pipeline": row["assessments"].get("pipeline"),
                        "baseline": row["assessments"].get("baseline")})
            elif who == {"pipeline"}:
                only_pipe.append(row["claim"])
            elif who == {"baseline"}:
                only_base.append(row["claim"])

        out["lenses"][lens] = {
            "verdict": {
                "pipeline": (pipe_cmp.get("verdict") or {}).get("call"),
                "baseline": (base_cmp.get("verdict") or {}).get("call"),
                "agree": ((pipe_cmp.get("verdict") or {}).get("call")
                          == (base_cmp.get("verdict") or {}).get("call"))},
            "confidence": {
                "pipeline": (pipe_cmp.get("verdict") or {}).get("confidence"),
                "baseline": (base_cmp.get("verdict") or {}).get("confidence")},
            "score": {
                "pipeline": _score(pipe_cmp), "baseline": _score(base_cmp),
                "difference": round(abs(_score(pipe_cmp) - _score(base_cmp)), 1)},
            # Rates, not counts.
            "citation_density": {
                "pipeline": _density(pipe_claims), "baseline": _density(base_claims),
                "means": "fraction of claims carrying at least one source ID"},
            "uncited_assertion_rate": {
                "pipeline": round(1 - _density(pipe_claims), 2),
                "baseline": round(1 - _density(base_claims), 2),
                "means": "claims resting on no source at all — lower is better"},
            "evidence_quality": {
                "pipeline": _quality_mix(pipe_claims),
                "baseline": _quality_mix(base_claims)},
            # Matched differences, not raw volume.
            "claims": {
                "raised_by_both": len(both),
                "only_pipeline": only_pipe,
                "only_baseline": only_base,
                "note": ("Matched on content, so a rephrasing counts as the same "
                         "claim rather than as a new finding.")},
            "contradictions": contradictions,
        }

    out["cost"] = {
        "pipeline_tokens": (pipeline_result.stats or {}).get("token_usage"),
        "baseline_tokens": (baseline_result.stats or {}).get("token_usage"),
        "pipeline_calls": (pipeline_result.stats or {}).get("model_calls"),
        "baseline_calls": (baseline_result.stats or {}).get("model_calls"),
        "pipeline_seconds": (pipeline_result.stats or {}).get("elapsed_seconds"),
        "baseline_seconds": (baseline_result.stats or {}).get("elapsed_seconds"),
    }
    out["caveat"] = (
        "This measures DIFFERENCE, not correctness. Nothing here establishes which "
        "analysis is better — that needs decks with known answers or a blinded human "
        "rubric, neither of which DeckScope ships. Two runs of the SAME mode will "
        "also differ, so treat a single comparison as one observation rather than a "
        "result. The contradictions are the part worth reading: they mark where the "
        "same evidence supported two different readings.")
    return out


def _score(comparison: Dict[str, Any]) -> float:
    meta = comparison.get("_meta") or {}
    return float((meta.get("weighted_score") or {}).get("score") or 0.0)


def _density(claims: List[Dict[str, Any]]) -> float:
    """Fraction of claims carrying at least one citation."""
    if not claims:
        return 0.0
    cited = sum(1 for c in claims if c.get("source_ids"))
    return round(cited / len(claims), 2)


def _quality_mix(claims: List[Dict[str, Any]]) -> Dict[str, int]:
    mix: Dict[str, int] = {}
    for c in claims:
        key = str(c.get("evidence_quality") or "unstated")
        mix[key] = mix.get(key, 0) + 1
    return mix
