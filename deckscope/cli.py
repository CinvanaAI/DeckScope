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

from . import __version__, settings
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
    p.add_argument("--version", action="version", version=f"DeckScope {__version__}")
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
    panel.add_argument("--rounds", "-r", type=int, default=1,
                       help="Cross-review rounds (default 1, 0 skips review)")
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
    from .config import Lens
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
            print("DeckScope isn't set up yet. Run:  deckscope setup\n")
            print("Or try it with no setup at all:   deckscope demo")
            return 1
        cfg = settings.settings_to_runconfig(overrides)

    pipe = Pipeline(cfg)
    try:
        result = pipe.run()
        files = pipe.render(result)
    except SecurityAbort as exc:
        print(f"\n{exc}\n")
        return 3
    except FileNotFoundError as exc:
        print(f"\nCouldn't find that file: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"\nAnalysis failed: {exc}\n")
        print("Run `deckscope doctor` to check your setup.")
        return 1
    finally:
        pipe.close()

    _print_summary(result, files)
    return 0


def _panel(args: Any) -> int:
    from .ensemble import Panel, parse_panelist
    from .security.report import SecurityAbort

    settings.load_env()
    saved_panel = (settings.load_settings().get("panel") or {})
    members = args.panel or saved_panel.get("members")
    if not members or len(members) < 2:
        print("\nA panel needs at least two AI connections.\n")
        print("  deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-4o\n")
        print("Or save a default panel by running:  deckscope setup\n")
        return 2
    rounds = args.rounds if args.rounds is not None else saved_panel.get("rounds", 1)

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
        panel = Panel(cfg, panelists, rounds=rounds, chair=chair,
                      parallel=not args.sequential)
        result = panel.run()
        files = panel.render(result)
    except SecurityAbort as exc:
        print(f"\n{exc}\n")
        return 3
    except ValueError as exc:
        print(f"\n{exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"\nPanel failed: {exc}\n")
        print("Run `deckscope doctor` to check your connections.")
        return 1

    _print_panel_summary(result, files)
    return 0


def _print_panel_summary(result: Any, files: List[str]) -> None:
    print()
    print("═" * 68)
    print(f"  {result.company} — panel of {len(result.working)}")
    print("═" * 68)
    for lens in result.lenses:
        cons = result.consensus.get(lens, {})
        m = result.metrics.get(lens, {})
        v = cons.get("consensus_verdict") or {}
        print(f"\n  [{lens}]  {v.get('call', '—')}  "
              f"({v.get('agreement', '—')}, {v.get('confidence', '—')} confidence)")
        if cons.get("headline"):
            print(f"           {cons['headline'][:96]}")
        for mv in m.get("movement") or []:
            moved = ("→ " + str(mv.get("verdict_after"))
                     if mv.get("verdict_before") != mv.get("verdict_after")
                     else "held")
            print(f"    {mv.get('panelist'):11s} {str(mv.get('name'))[:26]:28s} "
                  f"{str(mv.get('verdict_after'))[:20]:22s} "
                  f"{mv.get('score_after')}/100  {moved}")
        score = m.get("score") or {}
        print(f"    spread {score.get('spread', '—')} pts ({score.get('convergence', '—')})"
              f" · {m.get('total_position_changes', 0)} position(s) changed after review")
        contested = m.get("contested_claims") or []
        if contested:
            print(f"    contested claims: {', '.join(contested)}")
    failed = result.stats.get("panelists_failed") or []
    if failed:
        print("\n  Failed to run:")
        for f in failed:
            print(f"    {f.get('name')}: {str(f.get('error'))[:80]}")
    print("\n" + "═" * 68)
    if files:
        print("  Reports written:")
        for f in files:
            print(f"    {f}")
    print()


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
        print("Running a demo PANEL. Three simulated analysts, no AI, no key, no cost.\n")
        panel = Panel(cfg, [ProviderConfig(name="mock", model=m)
                            for m in ("mock-a", "mock-b", "mock-c")], rounds=1)
        res = panel.run()
        files = panel.render(res)
        _print_panel_summary(res, files)
        print("That was sample output. To run a real panel:  deckscope setup\n")
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
    print("Running a demo analysis. No AI, no API key, no cost — the model's answers "
          "are built in.\n")
    pipe = Pipeline(cfg)
    result = pipe.run()
    files = pipe.render(result)
    _print_summary(result, files)
    print("That was sample output. To analyze a real deck, run:  deckscope setup\n")
    return 0


def _print_summary(result: Any, files: List[str]) -> None:
    print()
    print("─" * 66)
    print(f"  {result.company}")
    print("─" * 66)
    for lens, comp in result.comparisons.items():
        v = comp.get("verdict") or {}
        score = ((comp.get("_meta") or {}).get("weighted_score") or {}).get("score", "—")
        print(f"  {lens:9s} {v.get('call', '—')}  ({v.get('confidence', '—')} "
              f"confidence, {score}/100)")
        if comp.get("headline"):
            print(f"            {comp['headline'][:100]}")
    sec = result.security or {}
    if sec:
        print(f"  security  input screen: {sec.get('overall_risk', 'clean').upper()}")
    reg = getattr(result, "registry", None)
    if reg:
        st = reg.stats()
        print(f"  sources   {st['cited']} cited of {st['total']} retrieved"
              + (f", {st['quarantined']} dropped" if st["quarantined"] else ""))
    print("─" * 66)
    if files:
        print("  Reports written:")
        for f in files:
            print(f"    {f}")
    print()


def _list_providers() -> int:
    from .providers.registry import catalog, list_providers

    print("\nAI backends:\n")
    for name in list_providers():
        models = catalog(name)
        print(f"  {name}")
        for m, desc in models[:4]:
            print(f"      {m:44s} {desc}")
    print("\nSet one with:  deckscope run deck.pdf --provider NAME --model MODEL\n")
    return 0


def _list_formats() -> int:
    from .render.registry import DESCRIPTIONS, list_formats

    print("\nOutput formats:\n")
    for f in list_formats():
        print(f"  {f:6s} {DESCRIPTIONS.get(f, '')}")
    print("\nUse several at once:  deckscope run deck.pdf --format html pdf docx\n")
    return 0


def _show_config() -> int:
    import json

    if not settings.is_configured():
        print("Not set up yet. Run:  deckscope setup")
        return 1
    print(f"\nSettings file: {settings.config_path()}\n")
    print(json.dumps(settings.load_settings(), indent=2))
    keys = settings.load_env(into_environ=False)
    if keys:
        print(f"\nSaved keys ({settings.env_path()}):")
        for k, v in keys.items():
            print(f"  {k:28s} {settings.masked(v)}")
    print()
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
