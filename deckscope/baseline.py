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
from .security.screening import screen_deck, screen_sources
from .sources import SourceRegistry, resolve_citations
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

    def run(self, deck_path: Optional[str] = None) -> AnalysisResult:
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

        registry = SourceRegistry()
        source_scan = ScanReport(target="web sources")
        research_block = ""
        if self.researcher.name != "none":
            queries = self._queries(doc)
            self._log(f"researching with {self.researcher.name}: {len(queries)} queries")
            results = self.researcher.search_many(
                queries, max_results=cfg.research.max_results)
            registry.add_results(results, backend=self.researcher.name)
            results, source_scan = screen_sources(results, policy)
            kept = {(getattr(r, "url", "") or getattr(r, "title", "")).lower()
                    for r in results}
            for src in registry.sources:
                if (src.url or src.title).lower() not in kept:
                    src.status = "quarantined"
                    src.note = "Dropped by the security screen."
            research_block = fence(registry.prompt_block(char_budget=60_000),
                                   "RESEARCH MATERIAL")
            self._log(f"{len(registry.sources)} source(s)")

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
                result, valid_source_ids=[s.sid for s in registry.sources])
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
                "research_backend": self.researcher.name,
                "sources_found": len(registry.sources),
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
    """What the two modes actually produced, side by side.

    Reports the differences; deliberately does not declare a winner. Which
    analysis is better is a judgement about reasoning quality that these numbers
    cannot make — they tell you where to look.
    """
    out: Dict[str, Any] = {"lenses": {}}
    for lens, pipe_cmp in (pipeline_result.comparisons or {}).items():
        base_cmp = (baseline_result.comparisons or {}).get(lens)
        if not base_cmp:
            continue
        pipe_score = ((pipe_cmp.get("_meta") or {}).get("weighted_score") or {}).get("score")
        base_score = ((base_cmp.get("_meta") or {}).get("weighted_score") or {}).get("score")
        pipe_claims = pipe_cmp.get("claim_audit") or []
        base_claims = base_cmp.get("claim_audit") or []

        def cited(rows):
            return sum(1 for r in rows if r.get("source_ids"))

        out["lenses"][lens] = {
            "verdict": {"pipeline": (pipe_cmp.get("verdict") or {}).get("call"),
                        "baseline": (base_cmp.get("verdict") or {}).get("call"),
                        "agree": (pipe_cmp.get("verdict") or {}).get("call")
                                 == (base_cmp.get("verdict") or {}).get("call")},
            "confidence": {"pipeline": (pipe_cmp.get("verdict") or {}).get("confidence"),
                           "baseline": (base_cmp.get("verdict") or {}).get("confidence")},
            "score": {"pipeline": pipe_score, "baseline": base_score,
                      "difference": (round(abs((pipe_score or 0) - (base_score or 0)), 1))},
            "claims_examined": {"pipeline": len(pipe_claims), "baseline": len(base_claims)},
            "claims_with_a_citation": {"pipeline": cited(pipe_claims),
                                       "baseline": cited(base_claims)},
            "blind_spots_named": {
                "pipeline": len((pipe_cmp.get("alignment") or {}).get("blind_spots") or []),
                "baseline": len((base_cmp.get("alignment") or {}).get("blind_spots") or [])},
            "risks_identified": {"pipeline": len(pipe_cmp.get("risks") or []),
                                 "baseline": len(base_cmp.get("risks") or [])},
        }
    out["cost"] = {
        "pipeline_tokens": (pipeline_result.stats or {}).get("token_usage"),
        "baseline_tokens": (baseline_result.stats or {}).get("token_usage"),
        "pipeline_seconds": (pipeline_result.stats or {}).get("elapsed_seconds"),
        "baseline_seconds": (baseline_result.stats or {}).get("elapsed_seconds"),
        "pipeline_sources": (pipeline_result.stats or {}).get("sources_found"),
        "baseline_sources": (baseline_result.stats or {}).get("sources_found"),
    }
    out["caveat"] = (
        "These are differences, not a verdict on which analysis is better. Whether "
        "the extra passes bought anything is a judgement about reasoning quality — "
        "read both and decide. Two runs of the same mode will also differ.")
    return out
