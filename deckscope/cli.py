"""Command line interface.

    deckscope setup                     guided configuration
    deckscope app                       drag-and-drop window in your browser
    deckscope run deck.pdf              analyze a deck
    deckscope panel deck.pdf            analyze with several AIs that review each other
    deckscope demo                      full sample run, no AI or key needed
    deckscope doctor                    check the install
    deckscope providers | formats       list what's available
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .console import out as _out
from . import __version__, console, settings
from .config import ALL_LENSES


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="deckscope",
        description="Analyze a pitch deck, research its market, and compare the two.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  deckscope setup                        set everything up, step by step
  deckscope app                          open the drag-and-drop window
  deckscope demo                         see a full sample report, free
  deckscope run deck.pdf                 analyze with your saved settings
  deckscope run deck.pdf --lens founder --format html pdf
  deckscope run deck.pdf --lens all --research tavily --security strict
  deckscope run https://example.com/deck.pdf --company "Acme Flow"

  deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-4o
  deckscope panel deck.pdf --panel anthropic openai gemini --rounds 2 --format html pdf
""")
    p.add_argument("--version", action="version",
                   version=f"DeckScope {__version__} (unreleased — "
                           f"see the README for what is and is not proven)")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("setup", help="Guided setup — start here")
    sub.add_parser("doctor", help="Check that everything is working")
    sub.add_parser("providers", help="List available AI backends")
    sub.add_parser("formats", help="List available output formats")
    sub.add_parser("config", help="Show the current settings")

    app = sub.add_parser("app", help="Open the drag-and-drop window in your browser")
    app.add_argument("--port", type=int, default=8765)
    app.add_argument("--no-browser", action="store_true",
                     help="Don't open a browser automatically")

    demo = sub.add_parser("demo", help="Run a full sample analysis with no AI or key")
    demo.add_argument("--format", "-f", nargs="+", default=["html", "md"])
    demo.add_argument("--lens", "-l", nargs="+", default=["investor"])
    demo.add_argument("--out", "-o", default=None)
    demo.add_argument("--injected", action="store_true",
                      help="Use the sample deck that contains a hidden injection")
    demo.add_argument("--panel", action="store_true",
                      help="Demo the multi-model panel instead of a single analysis")

    run = sub.add_parser("run", help="Analyze a pitch deck")
    run.add_argument("deck", help="Path or URL to a .pdf .pptx .docx .md .txt deck")
    run.add_argument("--lens", "-l", nargs="+", default=None,
                     help=f"One or more of: {', '.join(ALL_LENSES)}, or `all`")
    run.add_argument("--format", "-f", nargs="+", default=None,
                     help="md html pdf docx pptx xlsx json txt")
    run.add_argument("--out", "-o", default=None, help="Output folder")
    run.add_argument("--company", default=None, help="Company name, if the deck omits it")
    run.add_argument("--provider", default=None, help="Override the AI backend")
    run.add_argument("--model", default=None, help="Override the model")
    run.add_argument("--research", default=None,
                     help="auto tavily serper brave exa provider_native mcp none")
    run.add_argument("--security", default=None,
                     choices=["strict", "balanced", "permissive", "off"])
    run.add_argument("--theme", default=None, choices=["slate", "midnight", "paper"])
    run.add_argument("--max-queries", type=int, default=None)
    run.add_argument("--no-cache", action="store_true")
    run.add_argument("--quiet", "-q", action="store_true")
    run.add_argument("--mode", default="pipeline",
                     choices=["pipeline", "baseline", "both"],
                     help="pipeline = three isolated agents (default); "
                          "baseline = one prompt; both = run each and compare")
    run.add_argument("--config", default=None, help="Use a specific config file")

    panel = sub.add_parser(
        "panel",
        help="Analyze with several AIs, then have them review each other and revise",
        description=(
            "Runs the full pipeline once per AI connection, independently and in "
            "parallel. Each model then reads the others' deck extraction, market "
            "analysis and comparison — anonymized — decides what to concede and what "
            "to hold, and rewrites its own analysis. A chair then reports where the "
            "panel agreed, where it split, and how much the agreement is worth."))
    panel.add_argument("deck", help="Path or URL to the deck")
    panel.add_argument("--panel", "-p", nargs="+", default=None,
                       metavar="PROVIDER[:MODEL]",
                       help="Two or more AI connections, e.g. anthropic:claude-sonnet-5 "
                            "openai:gpt-4o gemini")
    panel.add_argument("--rounds", "-r", type=int, default=None,
                       help="Maximum cross-review rounds (0 skips review entirely)")
    panel.add_argument("--strategy", "-s", default="adaptive",
                       choices=["adaptive", "convergence", "confidence_floor", "fixed"],
                       help="When to stop reviewing. adaptive (default) picks a rule "
                            "from how the panel actually behaves")
    panel.add_argument("--no-vote", action="store_true",
                       help="Skip the round where panelists rank each other's reports")
    panel.add_argument("--chair", default=None,
                       help="Which connection writes the consensus (default: the first)")
    panel.add_argument("--lens", "-l", nargs="+", default=None)
    panel.add_argument("--format", "-f", nargs="+", default=None)
    panel.add_argument("--out", "-o", default=None)
    panel.add_argument("--company", default=None)
    panel.add_argument("--research", default=None)
    panel.add_argument("--security", default=None,
                       choices=["strict", "balanced", "permissive", "off"])
    panel.add_argument("--theme", default=None, choices=["slate", "midnight", "paper"])
    panel.add_argument("--sequential", action="store_true",
                       help="Run panelists one at a time instead of in parallel")
    panel.add_argument("--no-cache", action="store_true")
    panel.add_argument("--quiet", "-q", action="store_true")
    panel.add_argument("--config", default=None)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    # Make the console safe before anything is written to it.
    console.enable()
    args = build_parser().parse_args(argv)
    cmd = args.command

    if cmd is None or cmd == "setup":
        from .wizard import run_wizard
        if cmd is None and settings.is_configured():
            build_parser().print_help()
            return 0
        run_wizard(reconfigure=(cmd == "setup"))
        return 0

    if cmd == "doctor":
        from .wizard import doctor
        return doctor()

    if cmd == "providers":
        return _list_providers()

    if cmd == "formats":
        return _list_formats()

    if cmd == "config":
        return _show_config()

    if cmd == "app":
        from .webapp import serve
        serve(port=args.port, open_browser=not args.no_browser)
        return 0

    if cmd == "demo":
        return _demo(args)

    if cmd == "run":
        return _run(args)

    if cmd == "panel":
        return _panel(args)

    build_parser().print_help()
    return 1


# ------------------------------------------------------------------ actions

def _run(args: Any) -> int:
    from .orchestrator import Pipeline
    from .security.report import SecurityAbort

    settings.load_env()
    lenses = args.lens
    if lenses and len(lenses) == 1 and lenses[0].lower() == "all":
        lenses = ALL_LENSES

    overrides: Dict[str, Any] = {"deck_path": args.deck, "company_hint": args.company,
                                 "verbose": not args.quiet}
    if lenses:
        overrides["lenses"] = lenses
    if args.security:
        overrides["security"] = args.security
    if args.no_cache:
        overrides["cache_dir"] = None
    prov: Dict[str, Any] = {}
    if args.provider:
        prov["name"] = args.provider
    if args.model:
        prov["model"] = args.model
    if prov:
        overrides["provider"] = prov
    res: Dict[str, Any] = {}
    if args.research:
        res["name"] = args.research
    if args.max_queries:
        res["max_queries"] = args.max_queries
    if res:
        overrides["research"] = res
    out: Dict[str, Any] = {}
    if args.format:
        out["formats"] = args.format
    if args.out:
        out["out_dir"] = args.out
    if args.theme:
        out["theme"] = args.theme
    if out:
        overrides["output"] = out

    if args.config:
        from .config import load_config
        cfg = load_config(args.config, **overrides)
    else:
        if not settings.is_configured():
            _out("DeckScope isn't set up yet. Run:  deckscope setup\n")
            _out("Or try it with no setup at all:   deckscope demo")
            return 1
        cfg = settings.settings_to_runconfig(overrides)

    mode = getattr(args, "mode", "pipeline")
    try:
        if mode == "baseline":
            result, files = _run_baseline(cfg)
        elif mode == "both":
            return _run_both(cfg)
        else:
            pipe = Pipeline(cfg)
            try:
                result = pipe.run()
                files = pipe.render(result)
            finally:
                pipe.close()
    except SecurityAbort as exc:
        _out(f"\n{exc}\n")
        return 3
    except FileNotFoundError as exc:
        _out(f"\nCouldn't find that file: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        _out(f"\nAnalysis failed: {exc}\n")
        _out("Run `deckscope doctor` to check your setup.")
        return 1

    _print_summary(result, files)
    return 0


def _run_baseline(cfg: Any):
    """One prompt instead of three agents."""
    from .baseline import BaselineAnalyst
    from .render.registry import render as render_fmt

    analyst = BaselineAnalyst(cfg)
    try:
        result = analyst.run()
    finally:
        analyst.close()

    out_dir = Path(cfg.output.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = (cfg.output.basename or _slug(result.company)) + "_baseline"
    files: List[str] = []
    formats = list(dict.fromkeys(cfg.output.formats))
    if cfg.output.include_raw_json and "json" not in formats:
        formats.append("json")
    for fmt in formats:
        try:
            files.extend(render_fmt(fmt, result, out_dir, base, theme=cfg.output.theme))
        except Exception as exc:  # noqa: BLE001
            _out(f"[baseline] could not write {fmt}: {exc}")
    result.written_files = files
    return result, files


def _run_both(cfg: Any) -> int:
    """Run the pipeline and the single-prompt baseline, then compare them."""
    import json as _json

    from .baseline import compare_modes
    from .orchestrator import Pipeline

    _out("Running BOTH modes on this deck so they can be compared.\n")

    pipe = Pipeline(cfg)
    try:
        pipeline_result = pipe.run()
        pipeline_files = pipe.render(pipeline_result)
    finally:
        pipe.close()

    _out("")
    baseline_result, baseline_files = _run_baseline(cfg)

    comparison = compare_modes(pipeline_result, baseline_result)
    out_path = Path(cfg.output.out_dir) / "mode_comparison.json"
    out_path.write_text(_json.dumps(comparison, indent=2, default=str), encoding="utf-8")

    _out("")
    _out("=" * 68)
    _out("  Three agents vs. one prompt")
    _out("=" * 68)
    for lens, d in comparison["lenses"].items():
        _out(f"\n  [{lens}]")
        _out(f"    verdict     pipeline {d['verdict']['pipeline']}  |  "
             f"baseline {d['verdict']['baseline']}"
             + ("   (agree)" if d["verdict"]["agree"] else "   (DIFFER)"))
        _out(f"    score       {d['score']['pipeline']} vs {d['score']['baseline']} "
             f"({d['score']['difference']} apart)")
        _out(f"    claims      {d['claims_examined']['pipeline']} vs "
             f"{d['claims_examined']['baseline']} examined, "
             f"{d['claims_with_a_citation']['pipeline']} vs "
             f"{d['claims_with_a_citation']['baseline']} cited")
        _out(f"    blind spots {d['blind_spots_named']['pipeline']} vs "
             f"{d['blind_spots_named']['baseline']}")
        _out(f"    risks       {d['risks_identified']['pipeline']} vs "
             f"{d['risks_identified']['baseline']}")
    cost = comparison["cost"]
    _out(f"\n  cost        {cost['pipeline_tokens']} vs {cost['baseline_tokens']} tokens")
    _out(f"              {cost['pipeline_seconds']}s vs {cost['baseline_seconds']}s")
    _out("=" * 68)
    _out(f"\n  {comparison['caveat']}\n")
    _out("  Reports written:")
    for f in pipeline_files + baseline_files + [str(out_path)]:
        _out(f"    {f}")
    _out("")
    return 0


def _slug(name: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(name)).strip("_").lower()
    return s or "analysis"


def _panel(args: Any) -> int:
    from .ensemble import Panel, parse_panelist
    from .security.report import SecurityAbort

    settings.load_env()
    saved_panel = (settings.load_settings().get("panel") or {})
    members = args.panel or saved_panel.get("members")
    if not members or len(members) < 2:
        _out("\nA panel needs at least two AI connections.\n")
        _out("  deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-4o\n")
        _out("Or save a default panel by running:  deckscope setup\n")
        return 2
    rounds = args.rounds if args.rounds is not None else saved_panel.get("rounds", 3)

    lenses = args.lens
    if lenses and len(lenses) == 1 and lenses[0].lower() == "all":
        lenses = ALL_LENSES

    overrides: Dict[str, Any] = {"deck_path": args.deck, "company_hint": args.company,
                                 "verbose": not args.quiet}
    if lenses:
        overrides["lenses"] = lenses
    if args.security:
        overrides["security"] = args.security
    if args.no_cache:
        overrides["cache_dir"] = None
    if args.research:
        overrides["research"] = {"name": args.research}
    out: Dict[str, Any] = {}
    if args.format:
        out["formats"] = args.format
    if args.out:
        out["out_dir"] = args.out
    if args.theme:
        out["theme"] = args.theme
    if out:
        overrides["output"] = out

    if args.config:
        from .config import load_config
        cfg = load_config(args.config, **overrides)
    elif settings.is_configured():
        cfg = settings.settings_to_runconfig(overrides)
    else:
        from .config import load_config
        cfg = load_config(None, **overrides)

    try:
        panelists = [parse_panelist(spec) for spec in members]
        chair = parse_panelist(args.chair) if args.chair else None
        panel = Panel(cfg, panelists, rounds=rounds if rounds is not None else 3,
                      chair=chair, parallel=not args.sequential,
                      strategy=args.strategy, vote=not args.no_vote)
        result = panel.run()
        files = panel.render(result)
    except SecurityAbort as exc:
        _out(f"\n{exc}\n")
        return 3
    except ValueError as exc:
        _out(f"\n{exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        _out(f"\nPanel failed: {exc}\n")
        _out("Run `deckscope doctor` to check your connections.")
        return 1

    _print_panel_summary(result, files)
    return 0


def _print_panel_summary(result: Any, files: List[str]) -> None:
    _out()
    _out("═" * 68)
    _out(f"  {result.company} — panel of {len(result.working)}")
    _out("═" * 68)
    for lens in result.lenses:
        cons = result.consensus.get(lens, {})
        m = result.metrics.get(lens, {})
        v = cons.get("consensus_verdict") or {}
        _out(f"\n  [{lens}]  {v.get('call', '—')}  "
              f"({v.get('agreement', '—')}, {v.get('confidence', '—')} confidence)")
        if cons.get("headline"):
            _out(f"           {cons['headline'][:96]}")
        for mv in m.get("movement") or []:
            moved = ("→ " + str(mv.get("verdict_after"))
                     if mv.get("verdict_before") != mv.get("verdict_after")
                     else "held")
            _out(f"    {mv.get('panelist'):11s} {str(mv.get('name'))[:26]:28s} "
                  f"{str(mv.get('verdict_after'))[:20]:22s} "
                  f"{mv.get('score_after')}/100  {moved}")
        score = m.get("score") or {}
        _out(f"    spread {score.get('spread', '—')} pts ({score.get('convergence', '—')})"
              f" · {m.get('total_position_changes', 0)} position(s) changed after review")
        contested = m.get("contested_claims") or []
        if contested:
            _out(f"    contested claims: {', '.join(contested)}")
    failed = result.stats.get("panelists_failed") or []
    if failed:
        _out("\n  Failed to run:")
        for f in failed:
            _out(f"    {f.get('name')}: {str(f.get('error'))[:80]}")
    _out("\n" + "═" * 68)
    if files:
        _out("  Reports written:")
        for f in files:
            _out(f"    {f}")
    _out()


def _demo(args: Any) -> int:
    from .config import OutputConfig, ProviderConfig, ResearchConfig, RunConfig
    from .orchestrator import Pipeline

    here = Path(__file__).resolve().parent.parent
    name = "sample_deck_with_injection.md" if args.injected else "sample_deck.md"
    deck = here / "examples" / name
    if not deck.exists():
        deck_text = _EMBEDDED_DEMO_DECK
        deck = None
    else:
        deck_text = None

    lenses = ALL_LENSES if args.lens == ["all"] else args.lens
    out_dir = args.out or str(Path.cwd() / "deckscope_demo_output")

    if getattr(args, "panel", False):
        from .ensemble import Panel
        cfg = RunConfig(
            deck_path=str(deck) if deck else None, deck_text=deck_text, lenses=lenses,
            provider=ProviderConfig(name="mock"), research=ResearchConfig(name="none"),
            output=OutputConfig(formats=args.format, out_dir=out_dir), cache_dir=None)
        _out("Running a demo PANEL. Three simulated analysts, no AI, no key, no cost.\n")
        panel = Panel(cfg, [ProviderConfig(name="mock", model=m)
                            for m in ("mock-a", "mock-b", "mock-c")], rounds=1)
        res = panel.run()
        files = panel.render(res)
        _print_panel_summary(res, files)
        _out("That was sample output. To run a real panel:  deckscope setup\n")
        return 0

    cfg = RunConfig(
        deck_path=str(deck) if deck else None,
        deck_text=deck_text,
        lenses=lenses,
        provider=ProviderConfig(name="mock"),
        research=ResearchConfig(name="none"),
        output=OutputConfig(formats=args.format, out_dir=out_dir),
        cache_dir=None,
    )
    _out("Running a demo analysis. No AI, no API key, no cost — the model's answers "
          "are built in.\n")
    pipe = Pipeline(cfg)
    result = pipe.run()
    files = pipe.render(result)
    _print_summary(result, files)
    _out("That was sample output. To analyze a real deck, run:  deckscope setup\n")
    return 0


def _print_summary(result: Any, files: List[str]) -> None:
    _out()
    _out("─" * 66)
    _out(f"  {result.company}")
    _out("─" * 66)
    for lens, comp in result.comparisons.items():
        v = comp.get("verdict") or {}
        score = ((comp.get("_meta") or {}).get("weighted_score") or {}).get("score", "—")
        _out(f"  {lens:9s} {v.get('call', '—')}  ({v.get('confidence', '—')} "
              f"confidence, {score}/100)")
        if comp.get("headline"):
            _out(f"            {comp['headline'][:100]}")
    sec = result.security or {}
    if sec:
        _out(f"  security  input screen: {sec.get('overall_risk', 'clean').upper()}")
    reg = getattr(result, "registry", None)
    if reg:
        st = reg.stats()
        _out(f"  sources   {st['cited']} cited of {st['total']} retrieved"
              + (f", {st['quarantined']} dropped" if st["quarantined"] else ""))
    _out("─" * 66)
    if files:
        _out("  Reports written:")
        for f in files:
            _out(f"    {f}")
    _out()


def _list_providers() -> int:
    from .providers.registry import catalog, list_providers

    _out("\nAI backends:\n")
    for name in list_providers():
        models = catalog(name)
        _out(f"  {name}")
        for m, desc in models[:4]:
            _out(f"      {m:44s} {desc}")
    _out("\nSet one with:  deckscope run deck.pdf --provider NAME --model MODEL\n")
    return 0


def _list_formats() -> int:
    from .render.registry import DESCRIPTIONS, list_formats

    _out("\nOutput formats:\n")
    for f in list_formats():
        _out(f"  {f:6s} {DESCRIPTIONS.get(f, '')}")
    _out("\nUse several at once:  deckscope run deck.pdf --format html pdf docx\n")
    return 0


def _show_config() -> int:
    import json

    if not settings.is_configured():
        _out("Not set up yet. Run:  deckscope setup")
        return 1
    _out(f"\nSettings file: {settings.config_path()}\n")
    _out(json.dumps(settings.load_settings(), indent=2))
    keys = settings.load_env(into_environ=False)
    if keys:
        _out(f"\nSaved keys ({settings.env_path()}):")
        for k, v in keys.items():
            _out(f"  {k:28s} {settings.masked(v)}")
    _out()
    return 0


_EMBEDDED_DEMO_DECK = """--- Slide 1 ---
Acme Flow — AI agents that run your back-office workflows. Seed round.
--- Slide 2 ---
Market: workflow automation is $47B growing 23% CAGR. SAM $6B, SOM $400M.
--- Slide 3 ---
Traction: $340k ARR, 18% MoM for four months, 11 paying customers.
--- Slide 4 ---
Competition: Zapier and Make. We're more reliable than no-code.
--- Slide 5 ---
Ask: $4M at $24M post. 78% gross margin. $2M ARR in 18 months.
"""


if __name__ == "__main__":
    sys.exit(main())
