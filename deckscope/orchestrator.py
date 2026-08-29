"""The pipeline that wires the three agents together."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .console import out as _out
from .agents import ComparisonSynthesist, DeckAnalyst, MarketAnalyst
from .agents.discovery_agent import DiscoveryAnalyst
from .agents.opportunity_agent import OpportunityAnalyst
from .config import Lens, RunConfig
from .ingest.loader import DeckDocument, load_deck
from .providers.base import LLMProvider
from .providers.registry import get_provider
from .research.registry import get_researcher
from .security.policy import SecurityPolicy
from .security.report import ScanReport
from .security.screening import screen_deck
from .sources import (SourceRegistry, audit_citations, merge_into,
                      resolve_citations, rewrite_citations)


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
    #: What buying the listed alternative would require instead. Empty when the
    #: opportunity-cost pass was not enabled.
    opportunity: Dict[str, Any] = field(default_factory=dict)
    #: The evidence this analysis read. Shared verbatim when two modes are compared.
    corpus: Any = None
    #: The market as it looks to an analyst who never saw the deck, and the diff
    #: against the claim-directed view. Empty unless cold discovery was enabled.
    cold_market: Dict[str, Any] = field(default_factory=dict)
    #: The specialist market reports that ran inside this pipeline (stored
    #: panel ids, scoper notes, and the per-claim reconciliation entries).
    #: None when the pass was off; present-but-empty when it ran and refused.
    market_reports: Optional[Dict[str, Any]] = None
    discovery_delta: Dict[str, Any] = field(default_factory=dict)

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
                "opportunity": self.opportunity,
                "cold_market": self.cold_market,
                "discovery_delta": self.discovery_delta,
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
    def run(self, deck_path: Optional[str] = None,
            corpus: Any = None) -> AnalysisResult:
        """Run the analysis.

        `corpus` replaces the research phase with frozen evidence, which is how
        two modes are compared on identical sources instead of on whatever each
        happened to retrieve.
        """
        cfg = self.config
        started = time.time()
        source = deck_path or cfg.deck_path
        if not source and not cfg.deck_text:
            raise ValueError("Nothing to analyze: give a deck file path or deck_text.")

        self._log("Starting analysis",
                  provider=self.provider.name, model=self.provider.model,
                  research=self.researcher.name,
                  lenses=[lens.value for lens in cfg.lenses])

        doc: DeckDocument = (load_deck(cfg.deck_text, is_text=True) if cfg.deck_text
                             else load_deck(source))

        # ---- Security screen #1: the deck, before any of it reaches a model.
        policy: SecurityPolicy = cfg.security or SecurityPolicy()
        deck_scan = ScanReport(target="pitch deck")
        if policy.enabled:
            self._log(f"Screening deck for hidden instructions (mode: {policy.mode.value})")
            # `doc.local_path` is the on-disk original for a deck fetched from a
            # URL. Forensics can only read hidden slides, speaker notes and
            # invisible text out of the real binary — passing the URL, as this
            # did before, meant the scanner had nothing to open and every
            # file-level check silently skipped remote decks entirely.
            forensic_target = doc.local_path or (None if cfg.deck_text else source)
            try:
                doc, deck_scan = screen_deck(doc, policy, deck_path=forensic_target)
            finally:
                # The temporary download has served its purpose either way.
                doc.cleanup()
            self._log(deck_scan.summary_line())
            for f in deck_scan.findings[:8]:
                if f.severity in ("critical", "high"):
                    self._log(f"  ! [{f.severity}] {f.where}: {f.detail}")
        else:
            doc.cleanup()

        if doc.is_thin:
            self._log("Deck contains very little readable text — results will be weak. "
                      "If it is a scanned PDF, OCR it first.")

        kw = {"cache_dir": cfg.cache_dir, "on_event": self.on_event,
              "verbose": cfg.verbose}

        deck_agent = DeckAnalyst(self.extract_provider, **kw)
        deck = deck_agent.run(doc, company_hint=cfg.company_hint,
                              max_queries=cfg.research.max_queries)

        # The deck against itself, before anything external is consulted —
        # deterministic arithmetic over the extracted numbers (TAM≥SAM≥SOM,
        # growth vs the plan's implied rate, price × customers vs revenue).
        # Attached inside the extraction so it reaches the comparison model's
        # prompt and every renderer without a schema change; the deck is its
        # own source here, cited slide against slide.
        from .consistency import check_deck

        deck["_consistency"] = check_deck(deck)
        if deck["_consistency"]["conflicts"]:
            self._log(f"the deck disagrees with itself in "
                      f"{deck['_consistency']['conflicts']} place(s)")

        # ---- Optional: the structured specialist reports, run BEFORE the
        # comparison so the verdict is derived from them rather than the
        # reports arriving as a post-hoc appendage. This is the staged
        # consolidation of the product's two research paths (the split an
        # external audit named the largest product-level gap): one scoper
        # reads the deck's claims, the specialists research each one, their
        # sources merge into the run's single registry below, and their
        # findings enter the synthesist's prompt as citable evidence.
        report_outcomes: List[Any] = []
        report_notes: List[str] = []
        reports_registry = None
        if cfg.market_reports:
            from marketreport.handoff import run_brief
            from marketreport.library import Library
            from marketreport.scoping import briefs_from_deck
            from .sources import SourceRegistry

            self._log("scoping the market reports this deck's claims depend on")
            briefs, report_notes = briefs_from_deck(deck, self.provider)
            for note in report_notes:
                self._log(f"  {note.strip()}")
            reports_registry = SourceRegistry()
            shelf = Library()
            for brief in briefs:
                self._log(f"  producing {brief.specialist} "
                          f"({', '.join(brief.measures)})")
                try:
                    outcome = run_brief(brief, provider=self.provider,
                                        researcher=self.researcher,
                                        registry=reports_registry,
                                        policy=policy,
                                        on_event=lambda m: self._log(m))
                except Exception as exc:  # noqa: BLE001 - one report must not sink the run
                    report_notes.append(f"{brief.specialist} failed: {exc}")
                    self._log(f"  {brief.specialist} failed: {exc}")
                    continue
                try:
                    stored = shelf.save_all(outcome["panels"],
                                            market=brief.market,
                                            place=brief.place,
                                            request=brief.market)
                except OSError as exc:
                    report_notes.append(f"could not store: {exc}")
                    stored = []
                report_outcomes.append((brief, outcome["panels"],
                                        [r.id for r in stored]))

        market_agent = MarketAnalyst(self.provider, self.researcher,
                                     policy=policy, **kw)
        market = market_agent.run(deck, max_queries=cfg.research.max_queries,
                                  max_results=cfg.research.max_results,
                                  corpus=corpus)

        if report_outcomes:
            # One registry for the run. The stored panels keep their own
            # bibliographies (they are standalone documents); the COPIES of
            # their figures entering this run's prompt are re-cited into the
            # run namespace via the remap, per merge_into's contract.
            remap = merge_into(market_agent.registry, reports_registry,
                               note="Retrieved by a specialist market report.")
            block = []
            for brief, panels, stored_ids in report_outcomes:
                for panel, pid in zip(panels, stored_ids or
                                      [""] * len(panels)):
                    block.append({
                        "checks_deck_claim": brief.because or "(unrecorded)",
                        "specialist": brief.specialist,
                        "measure": getattr(panel, "measure_label", "")
                                   or getattr(panel, "measure", ""),
                        "finding": (panel.headline
                                    if getattr(panel, "answered", False)
                                    else "Could not be established: "
                                         + (getattr(panel, "problem", "")
                                            or "no reason recorded")),
                        "figures": [{
                            "label": f.label, "value": f.value_text,
                            "source_ids": [remap.get(s, s)
                                           for s in (f.source_ids or [])],
                        } for f in list(getattr(panel, "figures", []))[:6]],
                        "stored_as": pid,
                    })
            market["specialist_reports"] = block
            self._log(f"{len(block)} specialist report(s) merged into the "
                      f"run's evidence — the comparison sees their findings "
                      f"and can cite their sources")

        comparisons: Dict[str, Dict[str, Any]] = {}
        # Security findings from the optional passes, folded into the run report
        # at the end rather than discarded.
        opportunity_scan = None
        cold_scan = None
        synth = ComparisonSynthesist(self.provider, **kw)
        # ---- Optional: map the market cold, without the deck.
        cold_market: Dict[str, Any] = {}
        delta: Dict[str, Any] = {}
        if cfg.research.cold_discovery:
            from .discovery_delta import compare as compare_discovery

            try:
                cold_agent = DiscoveryAnalyst(self.provider, self.researcher,
                                              policy=policy, **kw)
                cold_market = cold_agent.run(
                    deck, max_queries=cfg.research.cold_max_queries,
                    max_results=cfg.research.max_results)
                if cold_agent.corpus and cold_agent.corpus.registry.sources:
                    # Fold the cold pass's sources into the one bibliography, so
                    # a finding it contributes is traceable like any other.
                    #
                    # The renumbering here MUST be paired with rewriting the
                    # citations in `cold_market`. The cold pass numbered its own
                    # sources from S1, and its model output cites those local
                    # IDs. Renumbering the source without rewriting the citation
                    # leaves the number pointing at whatever the main registry
                    # happens to hold at that index — so a claim about Microsoft
                    # Power Automate ended up citing a market-sizing document,
                    # and a claim about ServiceNow cited the Microsoft one.
                    #
                    # That is the worst failure this product can have: a visible
                    # source badge under a claim the source never supported.
                    # Build the map first, apply it to the output, and only then
                    # is the merge complete.
                    remap = merge_into(market_agent.registry,
                                       cold_agent.corpus.registry,
                                       note="Found by the claim-blind discovery pass.")
                    rewrite_citations(cold_market, remap)
                    cold_scan = getattr(cold_agent.corpus, "security", None)
                dobj = compare_discovery(market, cold_market)
                delta = dobj.to_dict()
                if dobj.anything_found:
                    self._log(f"Cold discovery: {dobj.note[:150]}")
                else:
                    self._log("Cold discovery surfaced nothing the directed pass missed")
            except Exception as exc:  # noqa: BLE001 - an optional pass, not the run
                self._log(f"Cold discovery failed, continuing without it: {exc}")
                delta = {"ran": False, "reason_skipped": str(exc)}

        # ---- Optional: price the alternative.
        opportunity: Dict[str, Any] = {}
        if getattr(cfg, "opportunity", None) and cfg.opportunity.enabled:
            from .market_data.registry import get_market_data
            from .opportunity import Assumptions

            # The whole block is guarded, construction included: an unknown
            # backend name raises here, and losing the entire analysis to an
            # optional extra would be the wrong trade.
            try:
                # The policy and the registry go in because a market-data
                # backend that reads listing facts out of web pages is doing
                # research, and research that skips the screen or the
                # bibliography is exactly the hole this pass used to have.
                feed = get_market_data(cfg.opportunity.market_data,
                                       config=cfg.opportunity,
                                       researcher=self.researcher,
                                       provider=self.provider,
                                       policy=policy,
                                       registry=market_agent.registry)
                opp_agent = OpportunityAnalyst(
                    self.provider, feed, researcher=self.researcher,
                    policy=policy,
                    assumptions=Assumptions(
                        future_dilution=cfg.opportunity.future_dilution,
                        exit_revenue_multiple=cfg.opportunity.exit_revenue_multiple,
                        horizon_years=cfg.opportunity.horizon_years,
                        preference_stack=cfg.opportunity.preference_stack),
                    **kw)
                opportunity = opp_agent.run(deck, market, market_agent.registry)
                # Fold this pass's screening into the run's security report, so
                # "every source was screened" describes the whole run rather
                # than only the market pass.
                if getattr(opp_agent, "security", None):
                    opportunity_scan = opp_agent.security
                # The listing lookups screen their own pages too. Merge their
                # findings in, or a hostile page reached through the market-data
                # backend would be screened and then never disclosed.
                for extra in getattr(feed, "security_reports", []) or []:
                    if opportunity_scan is None:
                        opportunity_scan = extra
                    else:
                        opportunity_scan.findings.extend(extra.findings)
            except Exception as exc:  # noqa: BLE001
                self._log(f"Opportunity-cost pass failed, continuing without it: {exc}")
                opportunity = {"error": str(exc)}

        # Only sources that actually reached the model. A quarantined source is in
        # the registry for reporting, but was never shown, so citing it is a
        # fabrication like any other.
        # Build the block first: rendering it marks those sources as admitted,
        # and `citable_ids` is defined as what actually reached a prompt.
        sources_block = market_agent.registry.prompt_block()
        valid_ids = market_agent.registry.citable_ids
        for lens in cfg.lenses:
            comparisons[lens.value] = synth.run(deck, market, lens=lens,
                                                valid_source_ids=valid_ids,
                                                sources_block=sources_block)

        usage = {"input": 0, "output": 0}
        for agent in (deck_agent, market_agent, synth):
            usage["input"] += agent.usage["input"]
            usage["output"] += agent.usage["output"]

        source_scan = market_agent.security_report or ScanReport(target="web sources")
        combined = ScanReport(target="all inputs")
        combined.extend(deck_scan)
        combined.extend(source_scan)
        # Every optional pass that fetched anything is screened too, and its
        # findings belong in the run's report. Leaving them out meant "all
        # sources were screened" described the market pass and quietly excluded
        # cold discovery and the opportunity research.
        for extra in (opportunity_scan, cold_scan):
            if extra:
                combined.extend(extra)
                source_scan.extend(extra)

        result = AnalysisResult(
            deck=deck, market=market, comparisons=comparisons,
            opportunity=opportunity,
            cold_market=cold_market,
            discovery_delta=delta,
            corpus=market_agent.corpus,
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
                "corpus_fingerprint": (market.get("_meta") or {}).get(
                    "corpus_fingerprint"),
                "security_risk": combined.risk,
                "token_usage": usage,
                "deckscope_version": _version(),
            },
        )
        # ---- Check every citation in the finished artifact, once. Then, and
        # only then, work out what the bibliography is allowed to claim.
        #
        # The order is load-bearing. Attributing first and auditing second let
        # the References section say "cited" about a source whose only reference
        # the audit had already removed from the report — a status the reader
        # cannot verify, wrong in the direction that flatters us.
        #
        # This is the last line of defence for the product's core promise. A
        # source badge the reader can open is worthless — actively harmful — if
        # it can resolve to a document that never supported the claim.
        registry = market_agent.registry
        audit = audit_citations(result, registry, strip=True)

        # The live registry, not a snapshot rebuilt from the market agent's
        # metadata: the optional passes added sources after that snapshot was
        # taken, and rebuilding from it silently dropped them.
        result.registry = resolve_citations(result, registry)
        result.stats["citation_audit"] = audit.to_dict()
        if not audit.ok:
            self._log(f"Citation audit: {audit.summary()} — removed from the report")
            for where, sid in (audit.dangling + audit.quarantined
                               + audit.unadmitted)[:5]:
                self._log(f"  ! {sid} at {where}")

        result.stats["references"] = result.registry.stats()
        self._log(f"References: {result.registry.stats()['cited']} cited of "
                  f"{result.registry.stats()['total']} consulted")
        # The reconciliation entries — each report read back against the deck
        # claim that dispatched it — computed here where the panels are still
        # in memory, so the CLI and app render them without re-running a
        # single search.
        if report_outcomes:
            from marketreport.reconcile import entry_for

            entries = []
            for brief, panels, stored_ids in report_outcomes:
                for panel, pid in zip(panels,
                                      stored_ids or [""] * len(panels)):
                    entries.append(entry_for(brief, panel,
                                             pid or "(not stored)",
                                             self.provider).to_dict())
            result.market_reports = {
                "stored": [pid for _, _, ids in report_outcomes
                           for pid in ids],
                "notes": report_notes,
                "entries": entries,
                "market": report_outcomes[0][0].market,
                "definition": report_outcomes[0][0].definition,
            }
        elif cfg.market_reports:
            result.market_reports = {"stored": [], "notes": report_notes,
                                     "entries": [], "market": "",
                                     "definition": ""}

        self._log(f"Analysis complete in {result.stats['elapsed_seconds']}s "
                  f"— {usage['input']} tokens in, {usage['output']} out")
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
        failed: List[str] = []
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
                failed.append(fmt)
        result.written_files = written
        # Recorded rather than raised: the analysis succeeded and the other
        # formats are on disk. The CLI turns this into a non-zero exit, so a
        # script that asked for a PDF is not told everything went fine.
        result.stats["formats_failed"] = failed
        return written

    def close(self) -> None:
        if self._owns_provider:
            try:
                self.provider.close()
            except Exception:  # noqa: BLE001
                pass
        if self._run_log not in (None, False):
            try:
                self._run_log.close()
            except Exception:  # noqa: BLE001
                pass
            self._run_log = None

    def _log(self, message: str, **data: Any) -> None:
        self.on_event(message, data)
        if self.config.verbose:
            _out(f"[deckscope] {message}", flush=True)
        self._persist(message)

    #: None = not opened yet; False = failed once, stay off; else a file.
    _run_log: Any = None

    def _persist(self, message: str) -> None:
        """Append every event to `run.log` beside the outputs.

        The narration is the run's flight recorder — which queries went out,
        which sources came back, what each agent did, in what order. Console
        and app both show it live and both lose it: the console scrolls away,
        the app keeps 400 lines in memory for one session. When a run
        surprises somebody an hour later, the log is the difference between
        "what happened?" and an answer.

        Logging must never sink an analysis, so the first OSError turns it
        off for the rest of the run instead of raising — a full disk should
        cost the flight recorder, not the flight.
        """
        if self._run_log is False:
            return
        try:
            if self._run_log is None:
                out_dir = Path(self.config.output.out_dir)
                out_dir.mkdir(parents=True, exist_ok=True)
                self._run_log = open(out_dir / "run.log", "a", encoding="utf-8")
                # Local time on purpose, matching the per-line stamps: the
                # reader of a flight recorder is correlating with their own
                # wall clock, not with UTC.
                self._run_log.write(
                    f"\n=== deckscope run · "
                    f"{datetime.now().astimezone().isoformat(timespec='seconds')}"
                    f" · {self.provider.name}"
                    f"{'/' + self.provider.model if self.provider.model else ''}"
                    f" ===\n")
            self._run_log.write(
                time.strftime("%H:%M:%S ") + message.rstrip() + "\n")
            self._run_log.flush()
        except OSError:
            self._run_log = False


def analyze(deck: str, *, lens: "str | Lens | List[Any]" = "investor",
            formats: Optional[List[str]] = None, out_dir: str = "./deckscope_output",
            provider: str = "anthropic", model: Optional[str] = None,
            research: str = "auto", company: Optional[str] = None,
            security: str = "balanced", verbose: bool = True,
            **kwargs: Any) -> AnalysisResult:
    """One-call convenience API.

        from deckscope import analyze
        result = analyze("deck.pdf", lens="investor", formats=["md", "html"])
        _out(result.primary["headline"])
        _out(result.security["overall_risk"], len(result.sources), "sources")
    """
    from .config import OutputConfig, ProviderConfig, ResearchConfig

    lenses = lens if isinstance(lens, list) else [lens]
    cfg = RunConfig(
        deck_path=deck, company_hint=company, lenses=[Lens.parse(x) for x in lenses],
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
