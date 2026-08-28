"""Command line interface.

    deckscope setup                     guided configuration
    deckscope app                       drag-and-drop window in your browser
    deckscope run deck.pdf              analyze a deck
    deckscope panel deck.pdf            analyze with several AIs that review each other
    deckscope demo                      full sample run, no AI or key needed
    deckscope models                    see which AIs work, and pick your panel
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
        description=(
            "Market reports with every figure traceable to its source, and "
            "pitch decks read against that evidence.\n\n"
            "START HERE\n"
            "  setup      connect an AI and a search backend (seven questions)\n"
            "  demo       a full sample analysis, no key and no network\n"
            "  app        the drag-and-drop window\n\n"
            "MARKET REPORTS\n"
            "  ask        ask about a market in plain words\n"
            "  report     produce one named report type about one subject\n"
            "  reports    what report types exist, and how each is scoped\n"
            "  market     the full twelve-question industry report\n"
            "  panels     re-open reports you have already produced\n\n"
            "PITCH DECKS\n"
            "  run        analyze a deck against researched evidence\n"
            "  panel      the same, across several AIs that review each other\n"
            "  research   the question-driven research loop on its own\n\n"
            "CHECKING AND SETTINGS\n"
            "  doctor     check that everything is working\n"
            "  models     which AI connections actually respond\n"
            "  config     the current settings\n"
            "  providers  available AI backends\n"
            "  formats    available output formats\n"
            "  eval       score DeckScope against decks with known answers"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  deckscope setup                        set everything up, step by step
  deckscope app                          open the drag-and-drop window
  deckscope demo                         see a full sample report, free
  deckscope models                       which AIs work, and choose your panel
  deckscope models --check               actually test each connection
  deckscope run deck.pdf                 analyze with your saved settings
  deckscope run deck.pdf --lens founder --format html pdf
  deckscope run deck.pdf --lens all --research tavily --security strict
  deckscope run https://example.com/deck.pdf --company "Acme Flow"

  deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-5.2
  deckscope panel deck.pdf --panel anthropic openai gemini --rounds 2 --format html pdf
""")
    p.add_argument("--version", action="version",
                   version=f"DeckScope {__version__} (unreleased — "
                           f"see the README for what is and is not proven)")
    # The metavar is spelled out so retired aliases do not appear in the
    # choice list. Thirteen commands is still a lot; it is one fewer than it
    # was, and the one removed was a strict subset of another.
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    md = sub.add_parser(
        "models",
        help="See which AI connections actually work, and choose your panel",
        description=(
            "Lists every model DeckScope knows, with what is genuinely usable "
            "right now — key present, binary on PATH, daemon running, model not "
            "withdrawn. Structural checks are instant and free; --check does a "
            "real round-trip and remembers the answer."))
    md.add_argument("--check", action="store_true",
                    help="Actually call each usable connection to confirm it works. "
                         "Costs a token or two per provider; the result is cached.")
    md.add_argument("--select", nargs="+", default=None, metavar="PROVIDER:MODEL",
                    help="Save these as your panel, e.g. "
                         "--select anthropic:claude-sonnet-5 openai:gpt-5.2")
    md.add_argument("--clear", action="store_true",
                    help="Forget the saved panel selection")
    md.add_argument("--all", action="store_true",
                    help="Include connections that are not set up")
    md.add_argument("--json", action="store_true", help="Machine-readable output")

    sub.add_parser("setup", help="Guided setup — start here")
    sub.add_parser("doctor", help="Check that everything is working")
    sub.add_parser("providers", help="List available AI backends")
    sub.add_parser("formats", help="List available output formats")
    sub.add_parser("config", help="Show the current settings")

    ev = sub.add_parser(
        "eval",
        help="Score DeckScope against decks with planted, known-correct answers",
        description=(
            "Runs a suite of constructed decks whose evidence is frozen and whose "
            "correct answers are known, because both were authored together. Scores "
            "claim accuracy, blind-spot recall, citation integrity, fabrication, "
            "calibration and injection detection — each computed in Python, never "
            "asked of a model."))
    ev.add_argument("--mode", nargs="+", default=["pipeline"],
                    choices=["pipeline", "baseline", "panel", "research"],
                    help="Which mode(s) to score. Give more than one to compare "
                         "them — the report says whether the comparison was "
                         "actually able to tell them apart.")
    ev.add_argument("--panel-size", type=int, default=3,
                    help="Panelists convened by --mode panel (default 3)")
    ev.add_argument("--trials", "-t", type=int, default=1,
                    help="Runs per case, to measure stability (default 1)")
    ev.add_argument("--provider", default="mock",
                    help="AI backend. Defaults to mock so the harness runs free.")
    ev.add_argument("--model", default=None)
    ev.add_argument("--lens", default="investor")
    ev.add_argument("--only", nargs="+", default=None, metavar="ID_OR_TAG",
                    help="Run only these case ids or tags")
    ev.add_argument("--suite", default=None, help="A different case directory")
    ev.add_argument("--out", "-o", default="./eval_output")
    ev.add_argument("--save", default=None, metavar="FILE",
                    help="Write the full result as JSON")

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
    demo.add_argument("--opportunity", action="store_true",
                      help="Demo the opportunity-cost comparison")
    demo.add_argument("--cold-discovery", action="store_true",
                      help="Demo the claim-blind market discovery pass")

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
    run.add_argument("--cold-discovery", action="store_true",
                     help="Also research the category from scratch, without the deck, "
                          "and report what that pass found which the claim-directed "
                          "research never looked for")
    run.add_argument("--save-corpus", default=None, metavar="FILE",
                     help="Write the frozen evidence to a file, so a later run can "
                          "replay the identical sources")
    run.add_argument("--corpus", default=None, metavar="FILE",
                     help="Replay a saved corpus instead of researching. Makes a "
                          "prompt change measurable against fixed evidence.")
    run.add_argument("--opportunity", action="store_true",
                     help="Also price the alternative: which named competitors are "
                          "publicly traded, and what this company would have to reach "
                          "to match holding them instead")
    run.add_argument("--dilution", type=float, default=None,
                     help="Assumed future dilution before exit (default 0.5)")
    run.add_argument("--exit-multiple", type=float, default=None,
                     help="Assumed exit revenue multiple (default 6.0)")
    run.add_argument("--horizon", type=int, default=None,
                     help="Years for the comparison (default 5)")
    run.add_argument("--mode", default="pipeline",
                     choices=["pipeline", "baseline", "both"],
                     help="pipeline = three isolated agents, and the only mode "
                          "that produces the standalone market analysis "
                          "(saturation, absorption risk, open-source landscape); "
                          "baseline = one prompt, ~1/6 the input tokens, and "
                          "scores the same on every measured dimension; "
                          "both = run each and compare")
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
                            "openai:gpt-5.2 gemini")
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

    research = sub.add_parser(
        "research",
        help="Question-driven research: a loop that reads, then asks the next question",
        description=(
            "The difference from `run` is what happens in the middle. `run` writes "
            "its search queries before reading anything, retrieves once, and reports. "
            "This posts a queue of open questions, works the highest-priority one, "
            "and lets what it reads add questions to any beat — so a regulation page "
            "can put a question on the economics queue. Questions close only when a "
            "stated rule fires: two independent sources agreeing, a flat "
            "contradiction, or the attempts running out. Nothing closes because a "
            "model felt finished.\n\n"
            "Output is an evidence table, not a narrative: every finding carries a "
            "source, a date and a method, and the ones that could not be sourced are "
            "deleted rather than softened."))
    research.add_argument("deck", help="Path or URL to the deck")
    research.add_argument("--provider", default=None, help="Override the AI backend")
    research.add_argument("--model", default=None, help="Override the model")
    research.add_argument("--research-backend", default=None, dest="research_backend",
                          help="auto tavily serper brave exa provider_native mcp none")
    research.add_argument("--security", default=None,
                          choices=["strict", "balanced", "permissive", "off"])
    research.add_argument("--max-iterations", type=int, default=None,
                          help="Questions the loop may work (default 24)")
    research.add_argument("--max-retrievals", type=int, default=None,
                          help="Retrievals across the whole run (default 40)")
    research.add_argument("--max-seconds", type=float, default=None,
                          help="Wall-clock cap (default 600)")
    research.add_argument("--nda", action="store_true",
                          help="Refuse to send any deck-derived text to a provider "
                               "that is not running on this machine. Structurally "
                               "enforced: the call raises rather than being logged.")
    research.add_argument("--save", default=None, metavar="FILE",
                          help="Write the full evidence table as JSON")
    research.add_argument("--company", default=None,
                          help="Company name, if the deck omits it")
    research.add_argument("--quiet", "-q", action="store_true")
    research.add_argument("--demo", action="store_true",
                          help="Run the loop against fixed sample evidence with "
                               "no AI connection and no search key. Every figure "
                               "is illustrative; the point is to show the "
                               "mechanics.")
    research.add_argument("--config", default=None)

    reports_cmd = sub.add_parser(
        "reports",
        help="List the report types this can produce",
        description=(
            "Each type is a set of sections, each one researched and returned "
            "as a panel you can check.\n\n"
            "Every type states what it is honestly bad at as well as what it "
            "answers, because a menu that only lists strengths teaches "
            "nothing about which item to pick."))
    reports_cmd.add_argument("--type", default="",
                             help="Show one type's sections in detail")

    report_cmd = sub.add_parser(
        "report",
        help="Produce one report about one subject",
        description=(
            "  deckscope report market-share \"cell phones\"\n"
            "  deckscope report market-size \"landscaping\" --in Phoenix\n"
            "  deckscope report demographics \"PS5 streaming users\"\n\n"
            "'deckscope reports' lists the types."))
    report_cmd.add_argument("type", help="Report type — see 'deckscope reports'")
    report_cmd.add_argument("subject", help="What the report is about")
    report_cmd.add_argument("--in", dest="place", default="", metavar="PLACE")
    report_cmd.add_argument("--save", default=None, metavar="FILE")
    report_cmd.add_argument("--plan", action="store_true",
                            help="Show what would be researched and stop")
    report_cmd.add_argument("--demo", action="store_true",
                            help="Replay real pages recorded 2026-08-27 with "
                                 "the offline model — no keys, no network")
    report_cmd.add_argument("--json", action="store_true")

    panels_cmd = sub.add_parser(
        "panels",
        help="List, show and re-open panels you have already produced",
        description=(
            "Every panel is written to disk when it is made, so a question "
            "answered once does not have to be paid for twice.\n\n"
            "  deckscope panels                       list what you have\n"
            "  deckscope panels --show <id>           print one\n"
            "  deckscope panels --show <id> --save p.html\n"
            "  deckscope panels --market \"cell phones\"\n\n"
            "Re-asking a question stores a NEW panel rather than replacing the "
            "old one: two runs of the same question are different panels "
            "because the market moved, and keeping both is what makes the "
            "change readable."))
    panels_cmd.add_argument("--show", default=None, metavar="ID",
                            help="Print one panel by id")
    panels_cmd.add_argument("--market", default="",
                            help="Only panels matching this market")
    panels_cmd.add_argument("--save", default=None, metavar="FILE",
                            help="With --show: write it to a file")
    panels_cmd.add_argument("--delete", default=None, metavar="ID",
                            help="Remove one panel from the library")
    panels_cmd.add_argument("--limit", type=int, default=40)

    ask = sub.add_parser(
        "ask",
        help="Ask about a market in plain words and get panels back",
        description=(
            "Say what you want to know and it works out which specialists to "
            "run, researches each one, and hands back a panel per question — "
            "the finding, the chart it chose, the numbers with their sources, "
            "and what it could not establish.\n\n"
            "  deckscope ask \"market share of cell phone companies in Ireland\"\n"
            "  deckscope ask \"who leads the smartphone market in Japan\" "
            "--save report.html\n\n"
            "This is the door for questions no statistical code covers. "
            "'deckscope market' is the door for a full twelve-section report "
            "on a US industry; the two share their machinery and increasingly "
            "their answers."))
    ask.add_argument("question", help="What you want to know, in plain words")
    ask.add_argument("--report", default="market-share", metavar="TYPE",
                     help="Which report to produce: market-share, "
                          "market-size, growth, regulation, "
                          "competitive-landscape, demographics. "
                          "'deckscope reports' lists them with the values "
                          "each accepts.")
    ask.add_argument("--measures", default=None, metavar="LIST",
                     help="Comma-separated values to report, one report each. "
                          "What is valid depends on --report: bases "
                          "(revenue, units, usage...) for market-share, price "
                          "levels (wholesale, retail, manufacturer_revenue) "
                          "for market-size, a jurisdiction for regulation. "
                          "Two values of one dimension are different answers "
                          "that often disagree, so each gets its own report "
                          "rather than sharing a chart. Omit this and you get "
                          "one undifferentiated report, the degraded path.")
    ask.add_argument("--save", default=None, metavar="FILE",
                     help="Write the panels to a file — .html .md .txt .json")
    ask.add_argument("--json", action="store_true",
                     help="Print the panels as JSON instead")
    ask.add_argument("--demo", action="store_true",
                     help="Replay real pages recorded on 2026-08-27 with the "
                          "offline mock model — no keys, no network. The "
                          "sources are genuine published research; the replay "
                          "is fixed to that day.")
    ask.add_argument("--plan", action="store_true",
                     help="Show what would be researched and stop, spending "
                          "nothing")
    ask.add_argument("--config", default=None)

    market = sub.add_parser(
        "market",
        help="The full market report: twelve questions, answered or explained",
        description=(
            "Produces the document an investment bank produces once, at "
            "enormous cost, when a company goes public — the industry section "
            "of an S-1 — for a market you name.\n\n"
            "It answers twelve standing questions drawn from the intersection "
            "of two professional formats: filed S-1 industry sections and the "
            "IBISWorld report structure. A reader who finishes it with "
            "questions has been failed by it, so the report states its own "
            "completeness at the top and lists every question it could not "
            "answer, with the reason, at the bottom.\n\n"
            "Ask for a market the way you would say it out loud:\n"
            "  deckscope market \"landscaping in Phoenix\"\n"
            "  deckscope market \"gyms\" --in Seattle\n"
            "  deckscope market 561730 --state 04 --county 013\n\n"
            "When a phrase matches several industries it lists them and stops, "
            "rather than picking one. A report about the wrong market is "
            "internally consistent and undetectably wrong, so that guess is "
            "the one guess never worth making."))
    market.add_argument(
        "market",
        help="The market, in plain words — \"landscaping in Phoenix\" — or a "
             "NAICS code if you know it")
    market.add_argument("--in", dest="place", default="", metavar="PLACE",
                        help="The geography, if you would rather give it "
                             "separately: a city, a state, or "
                             "\"Maricopa County, Arizona\"")
    market.add_argument("--label", default="", help="A name for this market")
    market.add_argument("--state", default="", metavar="FIPS",
                        help="2-digit state FIPS, if you would rather be exact")
    market.add_argument("--county", default="", metavar="FIPS",
                        help="3-digit county FIPS, with --state")
    market.add_argument("--customer", default="",
                        help="Who buys — narrows the boundary")
    market.add_argument("--save", default=None, metavar="FILE",
                        help="Write the report to a file. The format follows "
                             "the extension: .html .md .txt .json")
    market.add_argument("--format", default=None, metavar="FMT",
                        choices=("html", "md", "txt", "json"),
                        help="Override the format --save would infer. HTML is "
                             "the document one: it prints to PDF from any "
                             "browser.")
    market.add_argument("--json", action="store_true",
                        help="Print the machine-readable summary instead")
    market.add_argument("--sizing-only", action="store_true",
                        help="Print just the sizing arithmetic — the rings and "
                             "their operands — and none of the other sections")
    market.add_argument("--demo", action="store_true",
                        help="Run against recorded sample data — no Census key, "
                             "no network. Every figure is illustrative and is "
                             "labelled as such in the report itself.")

    # RETIRED. `size` was a strict subset of `market` and its own entry in a
    # fourteen-command help screen, which is how one product came to look like
    # five. It is hidden rather than deleted so existing scripts keep working,
    # and it says on every run where it went.
    size = sub.add_parser(
        "size",
        description=(
            "RETIRED — use 'deckscope market <naics> --sizing-only'. This name "
            "still works and forwards to it.\n\n"
            "Counts establishments and industry revenue from the US Census, and "
            "reports the market nationally, by state and by county — each ring "
            "sized separately, with the calculation written out.\n\n"
            "The arithmetic is the deliverable. '$34 billion' is an assertion; "
            "'N establishments in these size bands x $R average revenue, from "
            "these two sources, as of this date' is a claim you can check and "
            "disagree with. Every S-1 industry section that does this well "
            "states its operands, and this one does too.\n\n"
            "It measures the INDUSTRY's revenue, not one company's addressable "
            "opportunity. Those are different numbers — every filing surveyed "
            "uses its own realized revenue for the second, which no outside "
            "party can source."))
    size.add_argument("naics", help="4-6 digit NAICS industry code, e.g. 561730")
    size.add_argument("--state", default="", metavar="FIPS",
                      help="2-digit state FIPS, e.g. 04 for Arizona")
    size.add_argument("--county", default="", metavar="FIPS",
                      help="3-digit county FIPS, e.g. 013 for Maricopa")
    size.add_argument("--label", default="", help="A name for this market")
    size.add_argument("--save", default=None, metavar="FILE",
                      help="Write the sizing as JSON")
    return p


def _orientation() -> int:
    """What this is and the one command to try next.

    Seventeen commands is not a front door. This shows the two things the tool
    actually does, one runnable line each that needs no setup and no key, and
    where to find the rest — on the principle that a first screen should let
    someone see output before it asks them for anything.
    """
    configured = settings.is_configured()

    _out("")
    _out("  DeckScope")
    _out("  Market reports with every figure traceable to its source, and")
    _out("  pitch decks read against that evidence.")
    _out("")
    _out("  Try it now — no key, no network, real recorded sources:")
    _out("")
    _out("      deckscope demo                      analyze a sample deck")
    _out("      deckscope ask \"market share of cell phones\" --demo")
    _out("")
    if configured:
        _out("  Then, on a real subject:")
        _out("")
        _out("      deckscope ask \"who leads the hearing aid market\"")
        _out("      deckscope run yourdeck.pdf")
    else:
        _out("  To use it on a real subject you need an AI connection and a")
        _out("  web search backend. Seven questions, changeable later:")
        _out("")
        _out("      deckscope setup")
    _out("")
    _out("  deckscope --help     every command, grouped")
    _out("  deckscope reports    what kinds of report it can produce")
    _out("  deckscope doctor     check what is working")
    _out("")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    # Make the console safe before anything is written to it.
    console.enable()
    args = build_parser().parse_args(argv)
    cmd = args.command

    if cmd == "setup":
        from .wizard import run_wizard
        run_wizard(reconfigure=True)
        return 0

    if cmd is None:
        # Bare `deckscope` used to launch the seven-question setup wizard on an
        # unconfigured machine. Two things wrong with that: typing a command's
        # name to see what it does is not consent to be interrogated, and the
        # wizard blocks on stdin, so any non-interactive invocation — a script,
        # a CI step, a container — hung with no output and no way to know why.
        # It now orients, and offers setup as the next step rather than
        # starting it.
        return _orientation()

    if cmd == "doctor":
        from .wizard import doctor
        return doctor()

    if cmd == "providers":
        return _list_providers()

    if cmd == "formats":
        return _list_formats()

    if cmd == "config":
        return _show_config()

    if cmd == "models":
        return _models(args)
    if cmd == "eval":
        return _eval(args)

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

    if cmd == "research":
        return _research(args)

    if cmd == "size":
        _out("Note: 'deckscope size' has been retired — it was a subset of "
             "'deckscope market'.\n"
             "      The same output is now 'deckscope market "
             f"{getattr(args, 'naics', None) or '<market>'} --sizing-only'.""\n"
             "      This name still works and will keep working.\n")
        return _size(args)

    if cmd == "reports":
        return _report_types(args)

    if cmd == "report":
        return _run_report(args)

    if cmd == "panels":
        return _panels(args)

    if cmd == "ask":
        return _ask_market(args)

    if cmd == "market":
        return _market(args)

    build_parser().print_help()
    return 1


# ------------------------------------------------------------------ actions

def _ask(question: str, options: Any = ()) -> int:
    """Put the question back to the user and stop.

    Exit code 7: "understood the command, could not understand the request".
    Distinct from 6 ("ran correctly, report incomplete") and from a crash,
    because a script driving this needs to tell "ask the user" apart from
    "the data was not there".
    """
    _out("")
    _out(f"  {question}")
    for option in options or ():
        _out(f"    - {option}")
    _out("")
    _out("  Re-run with one of these, or give the NAICS code directly.")
    return 7


def _report_types(args: Any) -> int:
    """The menu."""
    import marketreport.s1  # noqa: F401 - registers the industry report
    from marketreport.reports import get, registered

    if args.type:
        report = get(args.type)
        if report is None:
            _out(f"  No report type called '{args.type}'.")
            _out("  " + ", ".join(r.key for r in registered()))
            return 1
        _out("")
        _out(f"  {report.title}  ({report.key})")
        _out(f"  {report.answers}")
        _out("")
        if report.basis:
            _out(f"  Based on: {report.basis}")
        if report.limits:
            _out(f"  Bad at:   {report.limits}")
        _out("")
        for spec in report.order():
            need = (f"  (after {', '.join(spec.needs)})" if spec.needs else "")
            mark = "" if spec.required else "  [optional]"
            _out(f"    {spec.key}{mark}{need}")
            _out(f"      {spec.brief[:150]}")
            if spec.sources:
                _out(f"      sources: {spec.sources[:100]}")
            if spec.paid:
                _out(f"      paid:    {spec.paid_source}")
            _out("")
        return 0

    _out("")
    _out("  Report types:")
    _out("")
    # The scoping parameter is listed with each type, because it is the thing
    # a caller has to decide before running one and there is nowhere else they
    # would find it. A reader who does not know that market-size wants a price
    # level will get the degraded single-report path and never learn why the
    # published totals they are shown disagree.
    from marketreport.dimensions import get as get_dimension
    from marketreport.specialists import get as get_specialist

    for report in registered():
        _out(f"  {report.key}")
        _out(f"    {report.answers}")
        _out(f"    {len(report.sections)} sections · "
             + " → ".join(s.key for s in report.order()))
        spec = get_specialist(report.key)
        axis = get_dimension(spec.dimension) if spec and spec.dimension else None
        if axis is not None:
            values = ", ".join(o.key for o in axis.options) or axis.expects
            _out(f"    scoped by {axis.key} ({axis.label}) — one report each: "
                 f"{values}")
        elif spec is None:
            _out("    no specialist yet — runs as section briefs, unscoped")
        _out("")
    _out("  'deckscope reports --type market-share' shows one in detail.")
    _out("  'deckscope report market-share \"cell phones\"' runs one.")
    _out("  'deckscope ask \"...\" --report market-size --measures "
         "wholesale,retail' runs one per value.")
    return 0


def _run_report(args: Any) -> int:
    """Produce one report."""
    import json as _json

    import marketreport.s1  # noqa: F401 - registers the industry report
    from marketreport.reports import build_report, get, registered

    report = get(args.type)
    if report is None:
        _out(f"\n  No report type called '{args.type}'.")
        _out("  Available: " + ", ".join(r.key for r in registered()))
        return 7

    if args.plan:
        _out("")
        _out(f"  {report.title} — {args.subject}"
             + (f" in {args.place}" if args.place else ""))
        _out(f"  {report.answers}")
        _out("")
        for spec in report.order():
            _out(f"    {spec.key}: {spec.brief[:120]}")
        _out("")
        _out(f"  Bad at: {report.limits}")
        _out("")
        _out("  Nothing was researched. Drop --plan to run it.")
        return 0

    from marketreport.library import Library
    from marketreport.panel_render import panel_text
    from marketreport.section_agent import make_section_agent
    from .security.policy import SecurityPolicy

    settings.load_env()
    provider, researcher, problem = _research_tools(args)
    if problem:
        return problem

    result = build_report(
        report, args.subject, place=args.place,
        run_section=make_section_agent(provider=provider,
                                       researcher=researcher,
                                       policy=SecurityPolicy()),
        on_event=_out)
    panels = result["panels"]

    # Stored as they are produced. A report that cost a research budget and
    # evaporated because the caller forgot to save it is the expensive kind of
    # forgetting, and it is what puts the report in the UI.
    stored = []
    try:
        stored = Library().save_all(panels, market=args.subject,
                                    place=args.place, request=args.subject)
    except OSError as exc:
        _out(f"  could not store the report: {exc}")

    if args.json:
        _out(_json.dumps({"type": report.key, "subject": args.subject,
                          "coverage": result["coverage"],
                          "panels": [p.to_dict() for p in panels]},
                         indent=2, default=str))
    else:
        for panel in panels:
            _out("")
            _out(panel_text(panel))
        _out("")
        stats = result["coverage"]
        _out(f"  {stats['answered']} of {stats['sections']} sections "
             f"established · {stats['checkable']} of {stats['figures']} "
             f"figures traceable to a source")
        for offer in result["upgrades"]:
            _out(f"  {offer['title']} came back thin ({offer['established']}) "
                 f"— {offer['sources']} publish this")
    for ref in stored:
        _out(f"  stored as {ref.id}")

    if args.save:
        from marketreport.document import infer_format, panel_document
        from marketreport.panel_render import panel_markdown

        fmt = infer_format(args.save, default="html")
        title = f"{report.title} — {args.subject}" + (
            f" in {args.place}" if args.place else "")
        body = (panel_document(panels, title=title) if fmt == "html"
                else "\n\n".join(panel_markdown(p) for p in panels)
                if fmt == "md"
                else _json.dumps([p.to_dict() for p in panels], indent=2,
                                 default=str) if fmt == "json"
                else "\n\n".join(panel_text(p) for p in panels))
        try:
            _write_text(body, args.save)
        except OSError as exc:
            _out(f"\n  Could not write {args.save}: {exc}")
            return 5
        _out(f"\n  Written to {args.save} ({fmt})")

    return 0 if any(p.answered for p in panels) else 6


def _research_tools(args: Any):
    """The model and the search backend, or a message saying which is missing.

    Shared by `ask` and `report` so one missing key produces the same
    explanation whichever door the user came in through.
    """
    from .config import load_config
    from .providers import get_provider
    from .research.registry import get_researcher

    if getattr(args, "demo", False):
        from marketreport.demo_sources import NOTE, RecordedResearcher, covered
        from .providers.mock_provider import MockProvider

        subject = getattr(args, "subject", "") or getattr(args, "market", "")
        if not covered(subject):
            _out("")
            _out(f"  The offline demo only has recorded pages for the mobile "
                 f"phone market, and this is about '{subject}'.")
            _out("  Running it would produce an empty report that reads like "
                 "a real failure rather than a demo with the wrong subject.")
            return None, None, 2
        _out(f"  {NOTE}")
        return MockProvider(), RecordedResearcher(), 0

    config = load_config(getattr(args, "config", None) or None)
    missing = []
    provider = researcher = None
    try:
        provider = get_provider(config.provider)
    except Exception as exc:  # noqa: BLE001
        missing.append(f"no AI model is connected — {exc}")
    try:
        researcher = get_researcher(config.research, provider)
    except Exception as exc:  # noqa: BLE001
        missing.append(f"no search backend is connected — {exc}")

    if missing:
        _out("")
        _out("  Not ready to research yet:" if len(missing) == 1
             else "  Not ready to research yet — two things are missing:")
        for problem in missing:
            _out(f"    - {problem}")
        _out("")
        _out("  Run 'deckscope setup' to connect them.")
        _out("  '--plan' works with neither and shows what would be "
             "researched.")
        return None, None, 4
    return provider, researcher, 0


def _panels(args: Any) -> int:
    """The library: what has already been produced."""
    from marketreport.document import infer_format, panel_document
    from marketreport.library import Library
    from marketreport.panel_render import (panel_markdown, panel_text)

    shelf = Library()

    if args.delete:
        if shelf.delete(args.delete):
            _out(f"  Removed {args.delete}")
            return 0
        _out(f"  No panel with id {args.delete}")
        return 1

    if args.show:
        panel = shelf.load(args.show)
        if panel is None:
            _out(f"  No panel with id {args.show}")
            _out("  Run 'deckscope panels' to see what is stored.")
            return 1
        if args.save:
            fmt = infer_format(args.save, default="html")
            body = (panel_document([panel], title=panel.headline or "Panel")
                    if fmt == "html" else
                    panel_markdown(panel) if fmt == "md" else
                    panel_text(panel))
            try:
                _write_text(body, args.save)
            except OSError as exc:
                _out(f"  Could not write {args.save}: {exc}")
                return 5
            _out(f"  Written to {args.save} ({fmt})")
            return 0
        _out("")
        _out(panel_text(panel))
        related = shelf.related(args.show)
        if related:
            _out(f"  {len(related)} earlier answer(s) to this same question:")
            for ref in related[:5]:
                _out(f"    {ref.id}  {ref.generated[:10]}  "
                     f"{ref.headline[:52]}")
            _out("  Compare them to see what moved.")
        return 0

    refs = shelf.list(limit=args.limit, market=args.market)
    if not refs:
        _out("")
        _out("  No panels stored yet.")
        _out("  'deckscope ask \"market share of cell phones in Ireland\"' "
             "makes one.")
        return 0

    _out("")
    _out(f"  {len(refs)} panel(s), newest first:")
    _out("")
    for ref in refs:
        state = "" if ref.answered else "  (not established)"
        _out(f"  {ref.generated[:10]}  {ref.id}")
        _out(f"    {(ref.headline or ref.question)[:66]}{state}")
        _out(f"    {ref.form} · {ref.checkable}/{ref.figures} figures "
             f"checkable · {', '.join(ref.sources[:2]) or 'no sources named'}")
        _out("")
    _out("  'deckscope panels --show <id>' prints one.")
    return 0


def _ask_market(args: Any) -> int:
    """A plain question, answered as panels."""
    import json as _json

    from marketreport.manager import answer, plan, read_request
    from marketreport.panel_render import panel_text

    settings.load_env()

    request = read_request(args.question)
    if not request.ready:
        return _ask(request.question, request.options)

    if args.plan:
        _out("")
        _out(f"  Market:      {request.market}")
        _out(f"  Place:       {request.place or 'not specified — worldwide'}")
        if request.naics:
            _out(f"  NAICS:       {request.naics}")
        for note in request.notes:
            _out(f"  · {note}")
        _out("")
        for spec in plan(request):
            _out(f"  {spec.name} — {spec.job}")
            for row in spec.questions(request.market, request.place):
                _out(f"      [{row['beat']}] {row['text']}")
        _out("")
        _out("  Nothing was researched and nothing was spent. Drop --plan to "
             "run it.")
        return 0

    from .config import load_config
    from .providers import get_provider
    from .research.registry import get_researcher
    from .security.policy import SecurityPolicy

    if getattr(args, "demo", False):
        from marketreport.demo_sources import NOTE, RecordedResearcher, covered
        from .providers.mock_provider import MockProvider

        if not covered(request.market):
            _out("")
            _out(f"  The offline demo only has recorded pages for the mobile "
                 f"phone market, and this request is about "
                 f"'{request.market}'.")
            _out("  Running it would produce an empty panel that reads like a "
                 "real failure rather than a demo with the wrong subject.")
            _out("  Try: deckscope ask \"market share of cell phones\" --demo")
            return 2
        _out(f"  {NOTE}")
        result = answer(args.question, provider=MockProvider(),
                        researcher=RecordedResearcher(),
                        policy=SecurityPolicy(), on_event=_out)
        return _finish_ask(args, result)

    # Both take a config object. Passing None produced "'NoneType' object has
    # no attribute 'name'" — a message that named neither the missing setup
    # step nor the real mistake, which was mine.
    #
    # Resolved one at a time so the message says WHICH of the two a user still
    # owes; catching them together makes one missing key look like two.
    config = load_config(getattr(args, "config", None) or None)
    missing = []
    provider = researcher = None
    try:
        provider = get_provider(config.provider)
    except Exception as exc:  # noqa: BLE001
        missing.append(f"no AI model is connected — {exc}")
    try:
        researcher = get_researcher(config.research, provider)
    except Exception as exc:  # noqa: BLE001
        missing.append(f"no search backend is connected — {exc}")

    if missing:
        _out("")
        _out("  Not ready to research yet:" if len(missing) == 1
             else "  Not ready to research yet — two things are missing:")
        for problem in missing:
            _out(f"    - {problem}")
        _out("")
        _out("  Run 'deckscope setup' to connect them, or 'deckscope models' "
             "to see what is already reachable.")
        _out("  'deckscope ask \"...\" --plan' works with neither, and shows "
             "exactly what would be researched.")
        return 4

    named = _measures_arg(args)
    if named is not None:
        return _finish_ask(args, _by_measure(
            request, named, provider=provider, researcher=researcher,
            report=getattr(args, "report", None) or "market-share"))

    result = answer(args.question, provider=provider, researcher=researcher,
                    policy=SecurityPolicy(), on_event=_out)
    return _finish_ask(args, result)


def _measures_arg(args: Any) -> Optional[List[str]]:
    """The --measures list, or None when the caller named none."""
    raw = (getattr(args, "measures", None) or "").strip()
    if not raw:
        return None
    return [part.strip() for part in raw.split(",") if part.strip()]


def _by_measure(request: Any, names: List[str], *, provider: Any,
                researcher: Any, report: str = "market-share") -> Dict[str, Any]:
    """One report per named measure, through the handoff.

    This is the shape the report agent is meant to be driven in: a market and
    a list of yardsticks arrive together, and one report comes back for each —
    including the yardsticks nobody publishes, which are reports too. Typing
    `--measures` by hand stands in for the upstream stage that will eventually
    read a deck and decide both.
    """
    from marketreport.handoff import Brief, coverage, run_brief
    from marketreport.measures import registered
    from .security.policy import SecurityPolicy

    try:
        brief = Brief(market=request.market, place=request.place,
                      measures=names, framing=request.framing(),
                      specialist=report or "market-share")
    except ValueError as exc:
        _out("")
        _out(f"  {exc}")
        return {"panels": [], "error": str(exc)}

    result = run_brief(brief, provider=provider, researcher=researcher,
                       policy=SecurityPolicy(), on_event=_out)
    stats = coverage(result)

    # `_finish_ask` prints, saves and stores whatever it is handed, and it
    # expects the request alongside the panels. Reusing it rather than growing
    # a second printer keeps the two doors rendering identically — but it does
    # mean this dict has to satisfy the same shape, which the first version
    # did not and which no test caught because nothing ran the two together.
    result["request"] = request
    try:
        from marketreport.library import Library
        result["stored"] = Library().save_all(
            result["panels"], market=request.market, place=request.place,
            request=request.text)
    except OSError as exc:
        _out(f"  could not store the reports: {exc}")
        result["stored"] = []

    _out("")
    for row in stats["measures"]:
        mark = "·" if row["answered"] else "—"
        _out(f"  {mark} {row['label'] or row['measure']}: {row['headline'][:78]}")
    for name in stats["unknown"]:
        _out(f"  ? {name}: not a registered measure. Available: "
             f"{', '.join(m.key for m in registered())}")
    for row in result.get("failed") or []:
        _out(f"  ! {row['label']}: {row['error'][:70]}")
    _out(f"  {stats['answered']} of {stats['requested']} measures returned a "
         f"chart; {stats['unsourceable']} came back empty because nobody "
         f"publishes that basis for this market.")
    return result


def _finish_ask(args: Any, result: Dict[str, Any]) -> int:
    """Print, save and report — shared by the live and demo paths.

    One implementation so the demo cannot show something the real run would
    not, which is the whole failure mode a demo exists to avoid.
    """
    import json as _json

    from marketreport.panel_render import panel_text

    panels = result["panels"]
    request = result["request"]
    for ref in result.get("stored") or []:
        _out(f"  stored as {ref.id}")

    if args.json:
        _out(_json.dumps({"request": result["request"].__dict__,
                          "panels": [p.to_dict() for p in panels]},
                         indent=2, default=str))
    else:
        for panel in panels:
            _out("")
            _out(panel_text(panel))

    if args.save:
        from marketreport.document import infer_format, panel_document
        from marketreport.panel_render import panel_markdown

        fmt = infer_format(args.save, default="html")
        title = f"{request.market.title()}" + (
            f" in {request.place}" if request.place else "")
        if fmt == "html":
            body = panel_document(panels, title=title)
        elif fmt == "md":
            body = "\n\n".join(panel_markdown(p) for p in panels)
        elif fmt == "json":
            body = _json.dumps([p.to_dict() for p in panels], indent=2,
                               default=str)
        else:
            body = "\n\n".join(panel_text(p) for p in panels)
        try:
            _write_text(body, args.save)
        except OSError as exc:
            _out(f"\nCould not write {args.save}: {exc}")
            return 5
        _out(f"\nWritten to {args.save} ({fmt})")

    # Exit 6 means "ran correctly, could not establish it" — distinct from a
    # crash and from a request we could not understand, which is 7.
    return 0 if any(p.answered for p in panels) else 6


def _market(args: Any) -> int:
    """The full report. Twelve questions, each answered or explained."""
    import json as _json

    # One implementation, two doors. The sizing view is the same arithmetic the
    # report's own sizing sections use; forking it would let the two drift and
    # the difference would show up as a number that changed depending on which
    # command you asked.
    if getattr(args, "sizing_only", False):
        return _size(args)

    import marketreport.agents  # noqa: F401 - registers the agents
    from marketreport.render import summary, text
    from marketreport.report import MarketDefinition, build
    from marketreport.request import interpret

    settings.load_env()

    if args.state or args.county:
        # Explicit FIPS wins outright. Someone who typed --state 04 has said
        # what they mean and should not have it re-derived from a phrase.
        from marketreport.naics import resolve as resolve_naics
        from marketreport.naics import too_broad

        found = resolve_naics(args.market, offline=args.demo)
        if not found.certain:
            return _ask(found.problem or
                        f"'{args.market}' matches several industries",
                        [str(c) for c in found.candidates])
        broad = too_broad(found.code or "")
        if broad:
            return _ask(broad)
        definition = MarketDefinition(
            label=args.label or found.title or f"NAICS {found.code}",
            naics=found.code or "", state_fips=args.state,
            county_fips=args.county, customer=args.customer, demo=args.demo)
    else:
        read = interpret(args.market, place=args.place, offline=args.demo)
        if not read.ready:
            return _ask(read.question, read.options)
        definition = read.definition(demo=args.demo, customer=args.customer)
        if args.label:
            definition.label = args.label
        if not args.json:
            for note in read.notes:
                _out(f"  {note}")

    answers = build(definition,
                    on_event=(lambda m: None) if args.json else _out)
    if args.json:
        _out(_json.dumps(summary(answers), indent=2, default=str))
    else:
        _out("")
        _out(text(answers))

    if args.save:
        from marketreport.document import infer_format, render_as

        # The extension decides, because that is what the user already said.
        # `--format` overrides it for the case where they want HTML in a file
        # called something else.
        fmt = args.format or infer_format(args.save, default="json")
        try:
            body = render_as(fmt, answers)
        except ValueError as exc:
            _out(f"\n{exc}")
            return 2
        try:
            _write_text(body, args.save)
        except OSError as exc:
            _out(f"\nCould not write {args.save}: {exc}")
            return 5
        _out(f"\nReport written to {args.save} ({fmt})")
        if fmt == "html":
            _out("  Open it in a browser and print to PDF for a filed copy.")

    # An incomplete report is a real output and not a success. A script driving
    # this should be able to tell the difference without parsing prose.
    return 0 if answers.closure()["complete"] else 6


def _size(args: Any) -> int:
    """Size one market from Census data, nationally then narrowing."""
    from marketreport.sizing import Ring, Sizing
    from marketreport.sources.census import (CBP_YEAR, ECN_YEAR, Unavailable,
                                             establishment_count,
                                             revenue_per_establishment,
                                             unavailable_term)

    settings.load_env()

    # Both doors reach here: the retired `size` command, which takes a NAICS
    # code, and `market --sizing-only`, which takes a phrase. Normalise once
    # rather than making the arithmetic below care which one called it.
    from marketreport.naics import resolve as resolve_naics

    given = getattr(args, "naics", "") or getattr(args, "market", "")
    found = resolve_naics(given, offline=getattr(args, "demo", False))
    if not found.certain:
        return _ask(found.problem or f"'{given}' matches several industries",
                    [str(c) for c in found.candidates])
    naics = found.code or ""

    def count(**kw):
        try:
            return establishment_count(naics, year=CBP_YEAR, **kw)
        except Unavailable as exc:
            return unavailable_term("count", str(exc))

    def value(**kw):
        try:
            return revenue_per_establishment(naics, year=ECN_YEAR, **kw)
        except Unavailable as exc:
            return unavailable_term("value", str(exc))

    sizing = Sizing(
        getattr(args, "label", "") or found.title or f"NAICS {naics}",
        basis="establishment-based: counts from County Business Patterns, value "
              "from Economic Census average revenue per establishment. This "
              "measures the industry's revenue, not one firm's opportunity")

    sizing.add(Ring(label="United States", count=count(), value=value()))
    if args.state:
        state_value = value(state_fips=args.state)
        sizing.add(Ring(label=f"State {args.state}",
                        count=count(state_fips=args.state), value=state_value))
        if args.county:
            sizing.add(Ring(
                label=f"County {args.state}{args.county}",
                count=count(state_fips=args.state, county_fips=args.county),
                value=state_value))

    _out(sizing.render())
    if args.save:
        try:
            _save_json(sizing.to_dict(), args.save)
        except TypeError as exc:
            _out(f"\nCould not write {args.save}: {exc}")
            return 5
        _out(f"\nWritten to {args.save}")
    # A sizing that established nothing is a real answer, not a crash — but it
    # is not a success either, and a script driving this should be able to tell.
    return 0 if sizing.headline is not None else 6


def _research(args: Any) -> int:
    """The question-driven loop, end to end, printing its reasoning as it goes."""
    import json

    from .agents.deck_agent import DeckAnalyst
    from .ingest.loader import load_deck
    from .providers import get_provider
    from .research.engine import run_research
    from .research.loop import Budget
    from .research.registry import get_researcher
    from .security.policy import SecurityPolicy
    from .security.report import SecurityAbort
    from .security.screening import screen_deck
    from .tiering import NDAGuard, NDAViolation, plan_from_config

    settings.load_env()
    overrides: Dict[str, Any] = {"deck_path": args.deck,
                                 "company_hint": args.company,
                                 "verbose": not args.quiet}
    if args.security:
        overrides["security"] = args.security
    prov: Dict[str, Any] = {}
    if args.provider:
        prov["name"] = args.provider
    if args.model:
        prov["model"] = args.model
    if prov:
        overrides["provider"] = prov
    if args.research_backend:
        overrides["research"] = {"name": args.research_backend}

    if args.demo:
        from .config import ProviderConfig, ResearchConfig, RunConfig
        cfg = RunConfig(deck_path=args.deck, company_hint=args.company,
                        provider=ProviderConfig(name="mock"),
                        research=ResearchConfig(name=_register_demo_research()),
                        verbose=not args.quiet, cache_dir=None)
        _out("Demo mode: no AI connection, no search key, fixed sample evidence. "
             "Every figure below is illustrative — what is real is the loop.\n")
    elif args.config:
        from .config import load_config
        cfg = load_config(args.config, **overrides)
    else:
        if not settings.is_configured():
            _out("DeckScope isn't set up yet. Run:  deckscope setup\n"
                 "Or watch the loop work with no setup at all:  "
                 "deckscope research <deck> --demo")
            return 1
        cfg = settings.settings_to_runconfig(overrides)

    provider = get_provider(cfg.provider)
    researcher = get_researcher(cfg.research, provider)
    policy: SecurityPolicy = cfg.security or SecurityPolicy()

    if getattr(researcher, "name", "") == "none":
        # Otherwise the run does everything correctly and prints sixteen lines
        # of "could not be established", which is true but reads like a broken
        # product rather than a missing search key.
        _out("No web-research backend is configured, so nothing can be looked "
             "up and every question will close as unanswerable. Run "
             "`deckscope setup` to add one, or pass --research-backend.\n")

    if args.nda and not _all_local(cfg):
        # Said plainly and up front rather than discovered halfway through a run
        # that has already sent three requests.
        _out("NDA mode is on and at least one configured connection is a hosted "
             "API. Deck content will not be sent to it — those calls will be "
             "refused, not quietly downgraded. Point --provider at a local model "
             "(Ollama or LM Studio through the openai_compatible backend) for a "
             "complete run.\n")

    doc = load_deck(cfg.deck_path)
    try:
        if policy.enabled:
            doc, scan = screen_deck(doc, policy, deck_path=doc.local_path or cfg.deck_path)
            _out(scan.summary_line())
    except SecurityAbort as exc:
        _out(f"\n{exc}")
        return 3
    finally:
        doc.cleanup()

    _out("Reading the deck…")
    extraction = DeckAnalyst(provider, cache_dir=cfg.cache_dir,
                             verbose=not args.quiet).run(
        doc, company_hint=cfg.company_hint)

    budget = Budget()
    if args.max_iterations:
        budget.max_iterations = args.max_iterations
    if args.max_retrievals:
        budget.max_retrievals = args.max_retrievals
    if args.max_seconds:
        budget.max_seconds = args.max_seconds

    try:
        result = run_research(
            extraction=extraction, provider=provider, researcher=researcher,
            policy=policy, plan=plan_from_config(cfg),
            guard=NDAGuard(enabled=bool(args.nda)), budget=budget,
            deck_text=doc.text,
            on_event=(lambda m: None) if args.quiet else _out)
    except NDAViolation as exc:
        _out(f"\n{exc}")
        return 4

    _print_research(result)

    if args.save:
        try:
            _save_json(result, args.save)
        except TypeError as exc:
            _out(f"\nCould not write {args.save}: {exc}")
            _out("The run itself succeeded — the evidence above is complete. "
                 "Nothing was written, so no partial file was left behind.")
            return 5
        _out(f"\nFull evidence table written to {args.save}")
    return 0


def _write_text(text: str, destination: str) -> None:
    """Write via a temp file, then replace. Never truncate the target first.

    A crash or a full disk mid-write must not damage a file that was already
    good, and must not leave a new one that has a plausible name, a plausible
    opening, and stops in the middle of a line — output that looks like output.
    """
    import os
    import tempfile

    target = Path(destination).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".partial")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, target)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _save_json(payload: Any, destination: str) -> None:
    """Serialize first, then write. In that order.

    The obvious `json.dump(payload, open(dest, "w"))` opens and truncates the
    destination before it knows whether the payload can be serialized. When it
    could not, the user was left with a truncated file. Serializing to a string
    first turns that into a clean failure with the destination untouched.

    The write itself is `_write_text`, shared rather than copied: a second
    implementation of "write safely" is a second place for the guarantee to
    quietly stop holding.
    """
    import json

    _write_text(json.dumps(payload, indent=2, ensure_ascii=False), destination)


def _register_demo_research() -> str:
    """Fixed sources on two distinct publishers, so the loop has real work.

    Two domains rather than one is the whole point: with a single publisher
    every question would close as "could not be independently corroborated" and
    the demo would show the guard rail instead of the mechanism. The figures
    disagree deliberately, so the contested path is visible too.
    """
    from .research.base import Researcher, SearchResult
    from .research.registry import register_researcher

    # Snippets vary by what was asked.
    #
    # The first version returned the same two paragraphs for every query, which
    # meant a regulation question got handed a market-size figure and a startup
    # cost. Once the loop started checking that a finding answers its question,
    # that produced a demo where nothing was ever relevant and no finding
    # survived. A search backend that ignores the query is not a simplification
    # of a search backend; it is a different thing that teaches the loop to
    # behave wrongly.
    TOPICS = (
        (("size", "large", "market", "tam", "grow"),
         "Independent estimates put the addressable segment at $6-8B in 2026, "
         "growing 14-18% annually.",
         "A wider category boundary that includes adjacent tooling is measured "
         "at $41B in 2026, which is a different definition rather than a "
         "different measurement."),
        (("compet", "who else", "rival", "incumbent"),
         "BlackLine and Trintech are the established incumbents in this "
         "category and both have moved down-market since 2024.",
         "Bundled modules from the ERP suites already installed at these "
         "buyers are the most common alternative to a standalone product."),
        (("licen", "permit", "regulat", "exempt"),
         "State registration is required for operators above the small-business "
         "threshold; the filing fee is $250 annually.",
         "No source states whether an exemption applies below that threshold."),
        (("cost", "capital", "start", "operate", "equipment"),
         "Startup capital for a single-crew operation runs about $10,000 once "
         "equipment, licensing and insurance are counted.",
         "Operating costs are dominated by labour, at 55-65% of revenue."),
        (("surviv", "fail", "five year", "5 year"),
         "Roughly half of new firms in this sector are still trading after "
         "five years.",
         "Failures cluster in years two and three, most often on working "
         "capital rather than demand."),
        (("price", "pricing", "charge", "contract value"),
         "Typical pricing is $2,000 per month for a mid-market seat count.",
         "Average annual contract value across the category is $19,000."),
    )

    class _DemoResearch(Researcher):
        name = "demo_research_loop"

        def search(self, query, max_results=8):
            q = (query or "").lower()
            body = next((t for t in TOPICS if any(k in q for k in t[0])), None)
            if body is None:
                # Nothing in the fixed corpus addresses this. Returning
                # something anyway is what made the demo compare a market size
                # against a startup cost.
                return []
            stamp = abs(hash(query)) % 9999
            return [
                SearchResult(f"Independent analyst note {stamp}",
                             f"https://analyst.example.com/{stamp}",
                             body[1], "2026-02", query),
                SearchResult(f"Category research {stamp}",
                             f"https://research.example.org/{stamp}",
                             body[2], "2026-01", query),
            ]

    register_researcher(_DemoResearch)
    return _DemoResearch.name


def _print_research(result: Dict[str, Any]) -> None:
    """The findings, then what could not be established. Both matter."""
    research = result.get("research") or {}
    comparison = result.get("comparison") or {}
    findings = (research.get("findings") or {}).get("findings") or []

    judgment = result.get("judgment") or {}
    verdict = judgment.get("verdict") or {}
    if judgment:
        _out("\n" + "=" * 68)
        _out(judgment.get("headline") or "(no headline)")
        _out("=" * 68)
        call = verdict.get("call") or "(no call)"
        _out(f"  {call}   confidence: {verdict.get('confidence', 'low')}")
        # Said out loud because it is unusual and load-bearing: the number is
        # counted from the evidence, so it cannot drift with the prose.
        _out(f"  {verdict.get('confidence_rationale', '')}")
        if verdict.get("capped_because"):
            _out(f"  (the model answered {verdict['call_before_cap']}; "
                 f"{verdict['capped_because']})")
        if judgment.get("reasoning"):
            _out("\n" + judgment["reasoning"])
        for row in judgment.get("conditions") or []:
            _out(f"  · condition: {row}")

    _out("\n" + "=" * 68)
    _out("WHAT THE RESEARCH ESTABLISHED")
    _out("=" * 68)
    established = [f for f in findings if f.get("method") != "absent"]
    if not established:
        _out("  Nothing. Every question below explains why, and an empty section "
             "here is a real result rather than a failure to render one.")
    for f in established:
        cites = " ".join(f"[{s}]" for s in f.get("source_ids") or [])
        value = f" — {f['value_text']}" if f.get("value_text") else ""
        stamp = f" (as of {f['as_of']})" if f.get("as_of") else ""
        _out(f"  • {f.get('statement', '')}{value}{stamp} {cites}")

    contested = comparison.get("contested") or []
    if contested:
        _out("\nWHERE THE SOURCES DISAGREE")
        _out("-" * 68)
        for row in contested:
            _out(f"  ? {row.get('question', '')}")
            for pos in row.get("positions") or []:
                cites = " ".join(f"[{s}]" for s in pos.get("source_ids") or [])
                _out(f"      {pos.get('value') or ''} — {pos.get('statement','')} {cites}")

    signals = comparison.get("pitcher_signals") or []
    if signals:
        _out("\nABOUT WHOEVER WROTE THIS")
        _out("-" * 68)
        for s in signals:
            _out(f"  ! {s.get('statement', '')}")
            _out(f"    {s.get('why_it_matters', '')}")

    claims = [c for c in comparison.get("claims") or []
              if c.get("assessment") == "contradicted"]
    if claims:
        _out("\nCLAIMS THE EVIDENCE CONTRADICTS")
        _out("-" * 68)
        for c in claims:
            _out(f"  ✗ {c.get('claim', '')}")
            _out(f"    {c.get('gap_text') or c.get('because', '')}")

    unanswered = comparison.get("unanswered") or []
    if unanswered:
        _out("\nWHAT COULD NOT BE ESTABLISHED, AND WHY")
        _out("-" * 68)
        for row in unanswered:
            _out(f"  – {row.get('question', '')}")
            _out(f"    {row.get('because', '')}")

    budget = research.get("budget") or {}
    _out(f"\n{budget.get('iterations', 0)} questions worked, "
         f"{budget.get('retrievals', 0)} retrievals, "
         f"{budget.get('seconds', 0)}s"
         + (f" — stopped because {budget['stopped_because']}"
            if budget.get("stopped_because") else ""))
    nda = result.get("nda") or {}
    if nda.get("enabled"):
        _out(f"NDA mode: {len(nda.get('refusals') or [])} call(s) refused; "
             f"{nda.get('protected_passages', 0)} passages fingerprinted.")


def _all_local(cfg: Any) -> bool:
    from .tiering import is_local
    return all(is_local(c) for c in
               filter(None, [cfg.provider, getattr(cfg, "extract_provider", None)]))


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
    if getattr(args, "opportunity", False) or args.dilution or args.exit_multiple \
            or args.horizon:
        opp: Dict[str, Any] = {"enabled": True}
        if args.dilution is not None:
            opp["future_dilution"] = args.dilution
        if args.exit_multiple is not None:
            opp["exit_revenue_multiple"] = args.exit_multiple
        if args.horizon is not None:
            opp["horizon_years"] = args.horizon
        overrides["opportunity"] = opp
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
    replay = None
    if getattr(args, "corpus", None):
        from .corpus import EvidenceCorpus
        try:
            replay = EvidenceCorpus.load(args.corpus)
            _out(f"Replaying corpus {replay.fingerprint()} from {args.corpus} "
                 f"({replay.kept} source(s)) — no new research will run.\n")
        except Exception as exc:  # noqa: BLE001
            _out(f"Could not read that corpus: {exc}\n")
            return 2
    try:
        if mode == "baseline":
            result, files = _run_baseline(cfg, corpus=replay)
        elif mode == "both":
            return _run_both(cfg)
        else:
            pipe = Pipeline(cfg)
            try:
                result = pipe.run(corpus=replay)
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

    if getattr(args, "save_corpus", None) and getattr(result, "corpus", None):
        saved = result.corpus.save(args.save_corpus)
        _out(f"  Evidence saved to {saved} (fingerprint "
             f"{result.corpus.fingerprint()}) — replay it with --corpus\n")

    _print_summary(result, files)
    return _format_exit_code(result)


def _format_exit_code(result: Any) -> int:
    """Non-zero when a format that was explicitly requested could not be written.

    An automation that asked for a PDF must not be told the run succeeded when no
    PDF exists. The analysis itself still completed, and the other formats are on
    disk — this only reports the shortfall.
    """
    missing = (getattr(result, "stats", None) or {}).get("formats_failed") or []
    if not missing:
        return 0
    _out(f"  Requested format(s) could not be produced: {', '.join(missing)}")
    _out("  Install the matching package, or drop them from --format.\n")
    return 4


def _run_baseline(cfg: Any, corpus: Any = None):
    """One prompt instead of three agents."""
    from .baseline import BaselineAnalyst
    from .render.registry import render as render_fmt

    analyst = BaselineAnalyst(cfg)
    try:
        result = analyst.run(corpus=corpus)
    finally:
        analyst.close()

    out_dir = Path(cfg.output.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = (cfg.output.basename or _slug(result.company)) + "_baseline"
    files: List[str] = []
    formats = list(dict.fromkeys(cfg.output.formats))
    if cfg.output.include_raw_json and "json" not in formats:
        formats.append("json")
    failed: List[str] = []
    for fmt in formats:
        try:
            files.extend(render_fmt(fmt, result, out_dir, base, theme=cfg.output.theme))
        except Exception as exc:  # noqa: BLE001
            _out(f"[baseline] could not write {fmt}: {exc}")
            failed.append(fmt)
    result.written_files = files
    # Recorded, not merely printed. `_format_exit_code` reads this, and without
    # it an automation that asked for a PDF was told the run succeeded when no
    # PDF existed — the pipeline path reported the shortfall and baseline,
    # `both` and panel silently did not.
    stats = getattr(result, "stats", None)
    if isinstance(stats, dict) and failed:
        stats["formats_failed"] = failed
    return result, files


def _run_both(cfg: Any) -> int:
    """Run the pipeline and the single-prompt baseline, then compare them."""
    import json as _json

    from .baseline import compare_modes
    from .orchestrator import Pipeline

    _out("Running BOTH modes on this deck, against the SAME frozen evidence, so the")
    _out("difference between them is attributable to the prompting rather than to")
    _out("each having read different sources.\n")

    pipe = Pipeline(cfg)
    try:
        pipeline_result = pipe.run()
        pipeline_files = pipe.render(pipeline_result)
    finally:
        pipe.close()

    # The baseline replays the pipeline's corpus rather than researching again.
    # Without this the comparison is confounded: "the pipeline found more risks"
    # might only mean "the pipeline happened to retrieve a page about risks".
    shared = getattr(pipeline_result, "corpus", None)
    if shared is not None:
        _out(f"\n  Reusing corpus {shared.fingerprint()} "
             f"({shared.kept} source(s)) for the baseline.")
    _out("")
    baseline_result, baseline_files = _run_baseline(cfg, corpus=shared)

    comparison = compare_modes(pipeline_result, baseline_result)
    out_path = Path(cfg.output.out_dir) / "mode_comparison.json"
    out_path.write_text(_json.dumps(comparison, indent=2, default=str), encoding="utf-8")

    _out("")
    _out("=" * 70)
    _out("  Three agents vs. one prompt, on identical evidence")
    _out("=" * 70)
    ev = comparison["evidence"]
    _out(f"\n  evidence    corpus {ev['pipeline_corpus']} · {ev['sources']} source(s)")
    _out(f"              {'IDENTICAL for both modes' if ev['identical'] else 'NOT SHARED — comparison is confounded'}")
    for lens, d in comparison["lenses"].items():
        _out(f"\n  [{lens}]")
        _out(f"    verdict     pipeline {d['verdict']['pipeline']}  |  "
             f"baseline {d['verdict']['baseline']}"
             + ("   (agree)" if d["verdict"]["agree"] else "   (DIFFER)"))
        _out(f"    score       {d['score']['pipeline']} vs {d['score']['baseline']} "
             f"({d['score']['difference']} apart)")
        _out(f"    cited       {d['citation_density']['pipeline']:.0%} vs "
             f"{d['citation_density']['baseline']:.0%} of claims carry a source")
        c = d["claims"]
        _out(f"    claims      {c['raised_by_both']} raised by both, "
             f"{len(c['only_pipeline'])} only by pipeline, "
             f"{len(c['only_baseline'])} only by baseline")
        if d["contradictions"]:
            _out(f"    CONTRADICTIONS ({len(d['contradictions'])}) — same evidence, "
                 f"different reading:")
            for row in d["contradictions"][:3]:
                _out(f"      · {row['claim'][:58]}")
                _out(f"        pipeline: {row['pipeline']}  |  baseline: {row['baseline']}")
        for claim in c["only_pipeline"][:2]:
            _out(f"    only pipeline raised: {claim[:60]}")
        for claim in c["only_baseline"][:2]:
            _out(f"    only baseline raised: {claim[:60]}")
    cost = comparison["cost"]
    _out(f"\n  cost        {cost['pipeline_tokens']} vs {cost['baseline_tokens']} tokens")
    _out(f"              {cost['pipeline_seconds']}s vs {cost['baseline_seconds']}s")
    _out("=" * 70)
    _out(f"\n  {comparison['caveat']}\n")
    _out("  Reports written:")
    for f in pipeline_files + baseline_files + [str(out_path)]:
        _out(f"    {f}")
    _out("")
    # Either mode failing to produce a requested format is a shortfall for the
    # whole command; returning 0 here told an automation both reports existed.
    for res in (pipeline_result, baseline_result):
        code = _format_exit_code(res)
        if code:
            return code
    return 0


def _slug(name: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(name)).strip("_").lower()
    return s or "analysis"


#: How each state reads at a glance. Words, not colours — this has to survive a
#: pipe, a log file and a Windows console that cannot render a green dot.
_STATE_MARK = {
    "ready": ("[ok]     ", "verified working"),
    "unverified": ("[  ?  ]  ", "set up, never tried"),
    "needs_setup": ("[setup]  ", "something is missing"),
    "failed": ("[FAILED] ", "tried and did not work"),
    "retired": ("[gone]   ", "withdrawn by the provider"),
}


def _models(args: Any) -> int:
    """Show what actually works, and remember what the user picks."""
    from . import availability as av

    settings.load_env()

    if args.clear:
        settings.save_panel([])
        _out("\nPanel selection cleared. `deckscope panel` will ask again.\n")
        return 0

    if args.select:
        caps = {c.key: c for c in av.survey()}
        unusable = [s for s in args.select
                    if s in caps and not caps[s].usable]
        unknown = [s for s in args.select if s not in caps]
        for spec in unknown:
            _out(f"  note: {spec} is not in the catalogue — saving it anyway, "
                 f"since a custom endpoint or a new model may be valid.")
        for spec in unusable:
            cap = caps[spec]
            _out(f"  warning: {spec} is {cap.state} — {'; '.join(cap.reasons)}")
            if cap.fix:
                _out(f"           {cap.fix}")
        settings.save_panel(list(args.select))
        _out(f"\nSaved {len(args.select)} model(s) as your panel.")
        div = av.diversity(list(args.select))
        _out(f"  {div['note']}")
        if len(args.select) >= 2:
            from .ensemble import panel_cost_note
            _out(f"  {panel_cost_note(len(args.select))}")
        _out("\nChange it any time with `deckscope models --select …`, or clear it "
             "with `--clear`.\n")
        return 0

    probes = av.load_probes()

    if args.check:
        _out("\nChecking each connection for real. This makes one tiny call per "
             "provider.\n")
        for cap in av.survey(probes):
            if cap.state not in ("unverified", "failed") or cap.provider == "mock":
                continue
            _out(f"  probing {cap.key} …")
            record = av.probe(cap.provider, cap.model)
            av.save_probe(record)
            _out(f"    {'ok' if record.get('ok') else 'FAILED: ' + record.get('error', '')}")
        probes = av.load_probes()
        _out("")

    caps = av.survey(probes, include_unusable=args.all)

    if args.json:
        _out(av.as_json(caps))
        return 0

    saved = set(settings.load_panel().get("members") or [])
    _out("")
    _out("  AI connections")
    _out("  " + "─" * 72)
    current = None
    for cap in sorted(caps, key=lambda c: (c.provider, c.model)):
        if cap.provider != current:
            current = cap.provider
            _out(f"\n  {cap.provider}")
        mark, _ = _STATE_MARK.get(cap.state, ("[ ? ]    ", ""))
        chosen = " ←chosen" if cap.key in saved else ""
        _out(f"    {mark}{cap.model or '(default)':<34}{chosen}")
        if cap.state != "ready" and cap.reasons:
            _out(f"             {cap.reasons[0]}")
            if cap.fix:
                _out(f"             → {cap.fix}")

    _out("")
    _out("  " + "─" * 72)
    for state, (mark, meaning) in _STATE_MARK.items():
        if any(c.state == state for c in caps):
            _out(f"    {mark}{meaning}")
    if not args.all:
        hidden = len(av.survey(probes, include_unusable=True)) - len(caps)
        if hidden:
            _out(f"\n  {hidden} connection(s) not set up — see them with `--all`.")

    if saved:
        _out(f"\n  Your panel: {', '.join(sorted(saved))}")
        _out(f"  {av.diversity(sorted(saved))['note']}")
    else:
        _out("\n  No panel saved. Choose one with:")
        _out("    deckscope models --select anthropic:claude-sonnet-5 openai:gpt-5.2")
    _out("")
    return 0


def _as_run_args(args: Any, member: str) -> Any:
    """Re-shape `panel` arguments into what `run` expects.

    The two subcommands do not take the same flags — `run` has a dozen that
    `panel` has no reason to (`--opportunity`, `--corpus`, `--dilution` and so
    on). Delegating without filling those in raises AttributeError on the first
    one it touches, so start from `run`'s own defaults and layer the shared
    values on top. Reading the defaults from the parser rather than hardcoding
    them means a new `run` flag cannot silently break this path.
    """
    import argparse

    defaults = vars(build_parser().parse_args(["run", str(args.deck)]))
    merged = argparse.Namespace(**defaults)
    for key, value in vars(args).items():
        if key in defaults and value is not None:
            setattr(merged, key, value)

    provider, _, model = member.partition(":")
    merged.provider = provider or None
    merged.model = model or None
    merged.command = "run"
    return merged


def _panel(args: Any) -> int:
    from .ensemble import Panel, parse_panelist
    from .security.report import SecurityAbort

    settings.load_env()
    saved_panel = (settings.load_settings().get("panel") or {})
    members = args.panel or saved_panel.get("members")
    if not members:
        _out("\nNo panel selected, and none saved.\n")
        _out("  deckscope panel deck.pdf --panel anthropic:claude-sonnet-5 openai:gpt-5.2\n")
        _out("Or save a default panel by running:  deckscope setup\n")
        return 2

    # One model is a perfectly reasonable choice — it is simply not a panel, and
    # refusing it would be pedantry dressed as validation. Run the analysis the
    # user actually asked for and say what happened, rather than making them
    # retype the command with a different verb.
    if len(members) == 1:
        _out(f"\nOne model selected ({members[0]}), so there is nobody to "
             f"cross-review. Running a single analysis instead — same pipeline, "
             f"no review rounds.\n")
        return _run(_as_run_args(args, str(members[0])))
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
    research_over: Dict[str, Any] = {}
    if args.research:
        research_over["name"] = args.research
    if getattr(args, "cold_discovery", False):
        research_over["cold_discovery"] = True
    if research_over:
        overrides["research"] = research_over
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


def _panel_exit_code(result: Any) -> int:
    """Non-zero when the panel could not write a format that was asked for.

    The panel path returned 0 unconditionally, so `--format pdf` that produced no
    PDF still reported success.
    """
    missing = (getattr(result, "stats", None) or {}).get("formats_failed") or []
    if not missing:
        return 0
    _out(f"  Requested format(s) could not be produced: {', '.join(missing)}")
    _out("  Install the matching package, or drop them from --format.\n")
    return 4


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


def _demo_corpus(package_dir: Path) -> Any:
    """The frozen evidence the demo analyses against.

    Without it the demo ran with `research=none`, so every finding came back
    uncited and the report — correctly, and to its credit — said so on every
    line. That is honest and it is also a terrible advertisement: the one thing a
    new user sees was an analysis with no evidence in it, which argues against
    the product rather than for it.

    The corpus is fictional and says so in its own `_readme`. It is authored
    alongside the sample deck so the demo has known-correct answers, the same
    trick the evaluation suite uses. Missing or corrupt, the demo still runs —
    it simply falls back to the uncited behaviour rather than failing.
    """
    from .corpus import EvidenceCorpus

    path = package_dir / "examples" / "sample_corpus.json"
    if not path.exists():
        return None
    try:
        return EvidenceCorpus.load(str(path))
    except Exception:  # noqa: BLE001 - a broken fixture must not break the demo
        return None


def _demo(args: Any) -> int:
    from .config import OutputConfig, ProviderConfig, ResearchConfig, RunConfig
    from .orchestrator import Pipeline

    # Inside the package, not beside it. These decks are runtime data — `demo` is
    # the first thing the README tells a new user to run — and a file that sits
    # next to the package is not installed with it. When they lived in a
    # top-level `examples/`, an installed DeckScope fell through to the embedded
    # deck, which contains no injection: `demo --injected` then printed a clean
    # report and said nothing, so the one command whose entire purpose is to
    # demonstrate the security screen quietly demonstrated the opposite.
    here = Path(__file__).resolve().parent
    name = "sample_deck_with_injection.md" if args.injected else "sample_deck.md"
    deck = here / "examples" / name
    if deck.exists():
        deck_text = None
    elif args.injected:
        # Never silently substitute a clean deck for the injected one. If the
        # fixture is missing the install is broken, and saying so is the only
        # honest option.
        _out("")
        _out(f"  The sample deck containing the planted injection is missing from "
             f"this install (expected at {deck}).")
        _out("  Refusing to run the injection demo against a clean deck — it would "
             "show a passing security screen that proves nothing.")
        _out("  Reinstall DeckScope, or run `deckscope demo` without --injected.")
        return 2
    else:
        deck_text = _EMBEDDED_DEMO_DECK
        deck = None

    lenses = ALL_LENSES if args.lens == ["all"] else args.lens
    out_dir = args.out or str(Path.cwd() / "deckscope_demo_output")
    demo_corpus = _demo_corpus(here)

    if getattr(args, "cold_discovery", False) and not getattr(args, "panel", False):
        cfg = RunConfig(
            deck_path=str(deck) if deck else None, deck_text=deck_text, lenses=lenses,
            provider=ProviderConfig(name="mock"),
            research=ResearchConfig(name="none", cold_discovery=True),
            output=OutputConfig(formats=args.format, out_dir=out_dir), cache_dir=None)
        _out("Running a demo WITH the claim-blind discovery pass. The cold pass sees\n"
             "only the category name — never a claim — so what it finds and the\n"
             "claim-directed pass missed is a blind spot no prompt could produce.\n")
        pipe = Pipeline(cfg)
        res = pipe.run(corpus=demo_corpus)
        files = pipe.render(res)
        pipe.close()
        _print_summary(res, files)
        delta = res.discovery_delta or {}
        if delta.get("competitors_only_cold"):
            _out("  Found ONLY by the cold pass:")
            for c in delta["competitors_only_cold"]:
                _out(f"    · {c['name']} ({c.get('threat_level')} threat)")
            _out("")
        _out("That was sample output. To run it for real:  "
             "deckscope run deck.pdf --cold-discovery\n")
        return _format_exit_code(res)

    if getattr(args, "opportunity", False) and not getattr(args, "panel", False):
        from .config import OpportunityConfig
        from .research.base import Researcher, SearchResult
        from .research.registry import register_researcher

        class _DemoResearch(Researcher):
            name = "demo_research"

            def search(self, query, max_results=8):
                return [SearchResult(f"Demo source: {query[:44]}",
                                     f"https://example.org/{abs(hash(query)) % 9999}",
                                     "Mid-market slice $3-5B in 2026.", "2026-03",
                                     query)]

        register_researcher(_DemoResearch)
        cfg = RunConfig(
            deck_path=str(deck) if deck else None, deck_text=deck_text, lenses=lenses,
            provider=ProviderConfig(name="mock"),
            research=ResearchConfig(name="demo_research", max_queries=2),
            opportunity=OpportunityConfig(enabled=True),
            output=OutputConfig(formats=args.format, out_dir=out_dir), cache_dir=None)
        _out("Running a demo WITH the opportunity-cost comparison. All figures are "
             "illustrative.\n")
        pipe = Pipeline(cfg)
        res = pipe.run()
        files = pipe.render(res)
        pipe.close()
        _print_summary(res, files)
        _out("That was sample output. To run it for real:  "
             "deckscope run deck.pdf --opportunity\n")
        return _format_exit_code(res)

    if getattr(args, "panel", False):
        from .ensemble import Panel
        cfg = RunConfig(
            deck_path=str(deck) if deck else None, deck_text=deck_text, lenses=lenses,
            provider=ProviderConfig(name="mock"), research=ResearchConfig(name="none"),
            output=OutputConfig(formats=args.format, out_dir=out_dir), cache_dir=None)
        _out("Running a demo PANEL. Three simulated analysts, no AI, no key, no cost.\n")
        panel = Panel(cfg, [ProviderConfig(name="mock", model=m)
                            for m in ("mock-a", "mock-b", "mock-c")], rounds=1)
        res = panel.run(corpus=demo_corpus)
        files = panel.render(res)
        _print_panel_summary(res, files)
        _out("That was sample output. To run a real panel:  deckscope setup\n")
        return _panel_exit_code(res)

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
    result = pipe.run(corpus=demo_corpus)
    files = pipe.render(result)
    _print_summary(result, files)
    _out("That was sample output. To analyze a real deck, run:  deckscope setup\n")
    return _format_exit_code(result)


def _wrap_indented(text: str, width: int = 62, indent: str = "  ") -> List[str]:
    """Wrap for the summary block. Named apart from the plain `_wrap`
    defined further down, which takes no indent and was being shadowed."""
    import textwrap

    return textwrap.wrap(str(text), width=width,
                         initial_indent=indent,
                         subsequent_indent=indent) or [indent]


def _print_summary(result: Any, files: List[str]) -> None:
    """What the terminal says when a run finishes.

    Leads with the findings, for the same reason the report does. This used to
    print the verdict and a weighted score on the first line — the one number in
    the whole system that cannot be traced to a source — which meant the summary
    a user actually reads contradicted the report it was summarising.
    """
    from .findings import collect

    reg = getattr(result, "registry", None)
    _out()
    _out("─" * 68)
    _out(f"  {result.company}")
    _out("─" * 68)

    for lens, comp in result.comparisons.items():
        found = collect(comp, reg)
        _out()
        _out(f"  {_lens_label(lens)}")
        _out()
        for line in _wrap_indented(found.headline, indent="  "):
            _out(line)
        _out()

        counts = found.counts
        grounded = counts.get("contested_with_evidence", 0)
        _out(f"    contested   {counts.get('contested', 0):<3}"
             + (f"({grounded} with a source you can open)" if counts.get("contested")
                else ""))
        _out(f"    omissions   {counts.get('omissions', 0)}")
        _out(f"    unresolved  {counts.get('unverified', 0)}")

        if found.next_steps:
            _out()
            _out("    Next:")
            for i, step in enumerate(found.next_steps[:3], 1):
                lines = _wrap_indented(step, width=54, indent="")
                _out(f"    {i}. {lines[0].strip()}")
                for line in lines[1:]:
                    _out(f"       {line.strip()}")
            if len(found.next_steps) > 3:
                _out(f"    …  {len(found.next_steps) - 3} more in the report")

    _out()
    sec = result.security or {}
    if sec:
        _out(f"  input screen  {sec.get('overall_risk', 'clean').upper()}")
    if reg:
        st = reg.stats()
        _out(f"  sources       {st['cited']} cited of {st['total']} retrieved"
             + (f", {st['quarantined']} dropped" if st["quarantined"] else ""))
    _out("─" * 68)
    if files:
        _out("  Reports written:")
        for f in files:
            _out(f"    {f}")
    _out()


def _lens_label(lens: str) -> str:
    return {"investor": "INVESTOR / DILIGENCE",
            "founder": "FOUNDER / SELF-CRITIQUE",
            "neutral": "NEUTRAL ANALYST"}.get(lens, lens.upper())


def _eval(args: Any) -> int:
    from .evaluation import DIMENSIONS, EmptySuiteError, run_suite, save

    settings.load_env()
    _out("Scoring DeckScope against decks with planted, known-correct answers.")
    _out("Evidence is frozen, so a change in score reflects a change in DeckScope.\n")

    # A misconfigured suite is a failed evaluation, not a crash report. Exit 2
    # (configuration) so CI can tell it apart from exit 1 (checks failed).
    try:
        result = run_suite(
            suite_dir=args.suite, modes=args.mode, trials=args.trials,
            provider=args.provider, model=args.model, lens=args.lens,
            out_dir=args.out, only=args.only,
            panel_size=getattr(args, "panel_size", 3), on_event=_out)
    except (EmptySuiteError, ValueError) as exc:
        _out("")
        _out(f"  Evaluation could not run: {exc}")
        _out("  Refusing to report success for a run that checked nothing.")
        return 2

    _out("")
    _out("=" * 74)
    _out(f"  Evaluation · {args.provider}"
         + (f"/{args.model}" if args.model else "")
         + f" · {result.trials} trial(s) per case")
    _out("=" * 74)

    width = max(len(d) for d in DIMENSIONS) + 2
    header = "  " + "dimension".ljust(width) + "".join(
        m.rjust(12) for m in result.modes)
    _out("\n" + header)
    _out("  " + "-" * (width + 12 * len(result.modes)))
    for dimension in DIMENSIONS:
        cells = []
        for mode in result.modes:
            rate = result.dimension_rate(mode, dimension)
            cells.append("—".rjust(12) if rate is None
                         else f"{rate:.0%}".rjust(12))
        if any(c.strip() != "—" for c in cells):
            _out("  " + dimension.ljust(width) + "".join(cells))

    # Say whether a multi-mode comparison was capable of showing a difference.
    # Identical scores mean one of two very different things — the modes really
    # perform alike, or the provider never distinguished them — and presenting
    # the first when it is the second turns a non-measurement into a finding.
    if len(result.modes) > 1:
        disc = result.discrimination()
        _out("")
        if not disc.get("comparable"):
            _out("  ⚠ This comparison is not informative.")
            for line in _wrap_indented(disc.get("reason", ""), width=64,
                                       indent="    "):
                _out(line)
        else:
            _out(f"  Modes produced different analyses on "
                 f"{disc['cases_compared'] - disc['cases_with_identical_output']}"
                 f"/{disc['cases_compared']} case(s), so a score difference here "
                 f"is a real difference.")
            base = result.cost(result.modes[0]).get("input_tokens") or 0
            if base:
                ratios = " · ".join(
                    f"{m} {(result.cost(m).get('input_tokens') or 0) / base:.1f}x"
                    for m in result.modes)
                _out(f"  Relative input cost — {ratios}")

    for mode in result.modes:
        stability = result.stability(mode)
        cost = result.cost(mode)
        _out(f"\n  [{mode}]")
        if stability["cases_measured"]:
            _out(f"    stability   verdict identical across trials: "
                 f"{stability['verdict_identical_across_trials']:.0%}"
                 f" · mean score spread {stability['mean_score_spread']}")
        _out(f"    cost        {cost['input_tokens']} in / "
             f"{cost['output_tokens']} out tokens over {cost['runs']} run(s), "
             f"{cost['seconds']}s")
        failures = result.failures(mode)
        if failures:
            _out(f"    {len(failures)} failed check(s):")
            for f in failures[:8]:
                _out(f"      · [{f['case']}] {f['dimension']}: {f['detail'][:90]}")
                if f["rationale"]:
                    _out(f"        why it matters: {f['rationale'][:88]}")
            if len(failures) > 8:
                _out(f"      … and {len(failures) - 8} more")
        elif cost["runs"] == 0:
            # No failures because nothing ran. Saying "every check passed" here
            # is the exact failure this harness was built to prevent: a gate
            # that could not fail, quoted as though it had passed. An audit
            # found this mode reporting a clean sweep over zero runs while
            # every one of its nine cases had crashed — the errors were listed
            # forty lines further down, under a different heading.
            # `red()` was never defined or imported here, so this branch raised
            # NameError instead of printing its warning — and it is the branch
            # that fires when EVERY case in a mode crashed. The comment above
            # describes an audit finding about a gate that could not fail being
            # quoted as a pass; the code written to prevent it could not run.
            # Found by scripts/lint.py's undefined-name check, which was added
            # after this same class of bug shipped twice in one day.
            broken = len([e for e in result.errors() if e["mode"] == mode])
            _out(f"    NOTHING RAN — all {broken} case(s) failed to execute. "
                 f"The dimension table above shows no score for this mode "
                 f"because there is none, not because it was perfect. See "
                 f"'Cases that could not run' below.")
        else:
            _out("    every check passed")

    if result.errors():
        _out("\n  Cases that could not run:")
        for e in result.errors():
            _out(f"    · {e['case']} [{e['mode']}]: {e['error'][:80]}")

    _out("\n" + "=" * 74)
    _out("")
    for line in _wrap(result.to_dict()["caveat"], 72):
        _out("  " + line)
    _out("")

    if args.save:
        _out(f"  Full result: {save(result, args.save)}\n")

    # Non-zero when anything failed, so this can gate a release.
    return 1 if (result.errors()
                 or any(result.failures(m) for m in result.modes)) else 0


def _wrap(text: str, width: int) -> List[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


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
