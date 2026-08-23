"""The pipeline that wires the three agents together."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .agents import ComparisonSynthesist, DeckAnalyst, MarketAnalyst
from .config import Lens, RunConfig
from .ingest.loader import DeckDocument, load_deck
from .providers.base import LLMProvider
from .providers.registry import get_provider
from .research.registry import get_researcher
from .security.policy import SecurityPolicy
from .security.report import ScanReport, SecurityAbort
from .security.screening import screen_deck
from .sources import SourceRegistry, resolve_citations


@dataclass
class AnalysisResult:
    """Everything one run produced."""

    deck: Dict[str, Any] = field(default_factory=dict)
    market: Dict[str, Any] = field(default_factory=dict)
    comparisons: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # lens -> report
    config: Dict[str, Any] = field(default_factory=dict)
    written_files: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    #: Everything the injection screen found, deck + web sources combined.
    security: Dict[str, Any] = field(default_factory=dict)
    #: Full bibliography: every source retrieved, cited or not.
    registry: Optional[SourceRegistry] = None

    @property
    def company(self) -> str:
        return ((self.deck.get("company") or {}).get("name") or "Unknown company")

    @property
    def primary(self) -> Dict[str, Any]:
        """The first lens's report — what a single-lens caller wants."""
        return next(iter(self.comparisons.values()), {})

    @property
    def sources(self) -> List[Any]:
        """Every source consulted, in citation order."""
        return self.registry.sources if self.registry else []

    def to_dict(self) -> Dict[str, Any]:
        return {"deck": self.deck, "market": self.market,
                "comparisons": self.comparisons, "config": self.config,
                "stats": self.stats, "security": self.security,
                "references": self.registry.to_dict() if self.registry else {}}

    def save_json(self, path: str) -> str:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, default=str),
                              encoding="utf-8")
        return path


class Pipeline:
    """Deck -> Market -> Comparison, with every layer swappable.

        pipe = Pipeline(config)
        result = pipe.run()
    """

    def __init__(self, config: RunConfig,
                 on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 provider: Optional[LLMProvider] = None,
                 researcher: Optional[Any] = None) -> None:
        self.config = config
        self.on_event = on_event or (lambda *_: None)
        self.provider = provider or get_provider(config.provider)
        self.extract_provider = (
            get_provider(config.extract_provider) if config.extract_provider
            else self.provider
        )
        self.researcher = researcher or get_researcher(config.research, self.provider)
        self._owns_provider = provider is None

    # ------------------------------------------------------------------
    def run(self, deck_path: Optional[str] = None) -> AnalysisResult:
        cfg = self.config
        started = time.time()
        source = deck_path or cfg.deck_path
        if not source and not cfg.deck_text:
            raise ValueError("Nothing to analyze: give a deck file path or deck_text.")

        self._log("Starting analysis",
                  provider=self.provider.name, model=self.provider.model,
                  research=self.researcher.name,
                  lenses=[l.value for l in cfg.lenses])

        doc: DeckDocument = (load_deck(cfg.deck_text, is_text=True) if cfg.deck_text
                             else load_deck(source))

        # ---- Security screen #1: the deck, before any of it reaches a model.
        policy: SecurityPolicy = cfg.security or SecurityPolicy()
        deck_scan = ScanReport(target="pitch deck")
        if policy.enabled:
            self._log(f"Screening deck for hidden instructions (mode: {policy.mode.value})")
            doc, deck_scan = screen_deck(
                doc, policy, deck_path=None if cfg.deck_text else source)
            self._log(deck_scan.summary_line())
            for f in deck_scan.findings[:8]:
                if f.severity in ("critical", "high"):
                    self._log(f"  ! [{f.severity}] {f.where}: {f.detail}")

        if doc.is_thin:
            self._log("Deck contains very little readable text — results will be weak. "
                      "If it is a scanned PDF, OCR it first.")

        kw = {"cache_dir": cfg.cache_dir, "on_event": self.on_event,
              "verbose": cfg.verbose}

        deck_agent = DeckAnalyst(self.extract_provider, **kw)
        deck = deck_agent.run(doc, company_hint=cfg.company_hint,
                              max_queries=cfg.research.max_queries)

        market_agent = MarketAnalyst(self.provider, self.researcher,
                                     policy=policy, **kw)
        market = market_agent.run(deck, max_queries=cfg.research.max_queries,
                                  max_results=cfg.research.max_results)

        comparisons: Dict[str, Dict[str, Any]] = {}
        synth = ComparisonSynthesist(self.provider, **kw)
        for lens in cfg.lenses:
            comparisons[lens.value] = synth.run(deck, market, lens=lens)

        usage = {"input": 0, "output": 0}
        for agent in (deck_agent, market_agent, synth):
            usage["input"] += agent.usage["input"]
            usage["output"] += agent.usage["output"]

        source_scan = market_agent.security_report or ScanReport(target="web sources")
        combined = ScanReport(target="all inputs")
        combined.extend(deck_scan)
        combined.extend(source_scan)

        result = AnalysisResult(
            deck=deck, market=market, comparisons=comparisons,
            config=cfg.to_dict(),
            security={"overall_risk": combined.risk,
                      "mode": policy.mode.value,
                      "deck": deck_scan.to_dict(),
                      "web_sources": source_scan.to_dict(),
                      "summary": [deck_scan.summary_line(),
                                  source_scan.summary_line()]},
            stats={
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "elapsed_seconds": round(time.time() - started, 1),
                "provider": self.provider.name, "model": self.provider.model,
                "research_backend": self.researcher.name,
                "sources_found": (market.get("_meta") or {}).get("n_results", 0),
                "security_risk": combined.risk,
                "token_usage": usage,
                "deckscope_version": _version(),
            },
        )
        # ---- Resolve every citation back to the bibliography.
        result.registry = resolve_citations(result)
        result.stats["references"] = result.registry.stats()
        self._log(f"References: {result.registry.stats()['cited']} cited of "
                  f"{result.registry.stats()['total']} consulted")
        self._log(f"Analysis complete in {result.stats['elapsed_seconds']}s")
        return result

    # ------------------------------------------------------------------
    def render(self, result: AnalysisResult) -> List[str]:
        """Write every requested output format. Returns the file paths."""
        from .render.registry import render

        cfg = self.config
        out_dir = Path(cfg.output.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        base = cfg.output.basename or _slug(result.company)
        written: List[str] = []

        formats = list(dict.fromkeys(cfg.output.formats))
        if cfg.output.include_raw_json and "json" not in formats:
            formats.append("json")

        for fmt in formats:
            try:
                paths = render(fmt, result, out_dir, base, theme=cfg.output.theme)
                written.extend(paths)
                for p in paths:
                    self._log(f"Wrote {p}")
            except Exception as exc:  # noqa: BLE001 - one bad format must not lose the rest
                self._log(f"Could not write {fmt}: {exc}")
        result.written_files = written
        return written

    def close(self) -> None:
        if self._owns_provider:
            try:
                self.provider.close()
            except Exception:  # noqa: BLE001
                pass

    def _log(self, message: str, **data: Any) -> None:
        self.on_event(message, data)
        if self.config.verbose:
            print(f"[deckscope] {message}", flush=True)


def analyze(deck: str, *, lens: "str | Lens | List[Any]" = "investor",
            formats: Optional[List[str]] = None, out_dir: str = "./deckscope_output",
            provider: str = "anthropic", model: Optional[str] = None,
            research: str = "auto", company: Optional[str] = None,
            security: str = "balanced", verbose: bool = True,
            **kwargs: Any) -> AnalysisResult:
    """One-call convenience API.

        from deckscope import analyze
        result = analyze("deck.pdf", lens="investor", formats=["md", "html"])
        print(result.primary["headline"])
        print(result.security["overall_risk"], len(result.sources), "sources")
    """
    from .config import OutputConfig, ProviderConfig, ResearchConfig

    lenses = lens if isinstance(lens, list) else [lens]
    cfg = RunConfig(
        deck_path=deck, company_hint=company, lenses=[Lens.parse(l) for l in lenses],
        provider=ProviderConfig(name=provider, model=model,
                                **kwargs.pop("provider_kwargs", {})),
        research=ResearchConfig(name=research, **kwargs.pop("research_kwargs", {})),
        output=OutputConfig(formats=formats or ["md"], out_dir=out_dir),
        security=security, verbose=verbose, **kwargs,
    )
    pipe = Pipeline(cfg)
    try:
        result = pipe.run()
        pipe.render(result)
        return result
    finally:
        pipe.close()


def _slug(name: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return s or "analysis"


def _version() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return "unknown"
