"""The guided setup. Plain language, no jargon, tests everything as it goes.

Run by the installer automatically, and any time afterwards with:
    deckscope setup
"""
from __future__ import annotations

import os
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import settings
from .config import ALL_LENSES

# ---------------------------------------------------------------- terminal

def _supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.name == "nt" and not os.getenv("WT_SESSION") and not os.getenv("TERM"):
        try:
            import colorama  # type: ignore
            colorama.just_fix_windows_console()
            return True
        except Exception:  # noqa: BLE001
            return False
    return sys.stdout.isatty()


COLOR = _supports_color()


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def bold(t: str) -> str: return c(t, "1")
def dim(t: str) -> str: return c(t, "2")
def green(t: str) -> str: return c(t, "32")
def yellow(t: str) -> str: return c(t, "33")
def blue(t: str) -> str: return c(t, "36")
def red(t: str) -> str: return c(t, "31")


WIDTH = min(shutil.get_terminal_size((80, 24)).columns, 84)


def rule(char: str = "─") -> None:
    print(dim(char * WIDTH))


def banner(title: str, subtitle: str = "") -> None:
    print()
    rule("━")
    print(bold(f"  {title}"))
    if subtitle:
        print(dim(f"  {subtitle}"))
    rule("━")
    print()


def say(text: str, indent: str = "  ") -> None:
    for para in text.split("\n"):
        if not para.strip():
            print()
            continue
        print(textwrap.fill(para, WIDTH - 2, initial_indent=indent,
                            subsequent_indent=indent))


def ask(prompt: str, default: Optional[str] = None) -> str:
    suffix = f" {dim('[' + default + ']')}" if default else ""
    try:
        val = input(f"  {blue('›')} {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("\nSetup cancelled. Run `deckscope setup` any time to resume.")
    return val or (default or "")


def ask_yes(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    while True:
        val = ask(f"{prompt} ({d})").lower()
        if not val:
            return default
        if val in ("y", "yes"):
            return True
        if val in ("n", "no"):
            return False
        print(dim("    Please answer y or n."))


def choose(prompt: str, options: List[Tuple[str, str, str]],
           default: int = 1) -> str:
    """options: (value, label, description). Returns the chosen value."""
    print()
    print(f"  {bold(prompt)}")
    print()
    for i, (_, label, desc) in enumerate(options, 1):
        mark = green("→") if i == default else " "
        print(f"   {mark} {bold(str(i) + '.')} {label}")
        if desc:
            for line in textwrap.wrap(desc, WIDTH - 10):
                print(f"        {dim(line)}")
    print()
    while True:
        raw = ask(f"Pick 1-{len(options)}", str(default))
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        except ValueError:
            pass
        print(dim(f"    Enter a number between 1 and {len(options)}."))


def ask_secret(prompt: str) -> str:
    import getpass
    try:
        return getpass.getpass(f"  › {prompt}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nSetup cancelled.")
    except Exception:  # noqa: BLE001 - no tty
        return ask(prompt)


def spinner_done(ok: bool, message: str) -> None:
    print(f"    {green('✓') if ok else red('✗')} {message}")


# ============================================================== the wizard

PROVIDER_MENU: List[Tuple[str, str, str]] = [
    ("anthropic", "Claude (Anthropic)",
     "Best-in-class analysis and the deepest reasoning. Needs an API key from "
     "console.anthropic.com — pay per use, roughly a few cents per deck."),
    ("openai", "ChatGPT (OpenAI)",
     "Strong general analysis. Needs an API key from platform.openai.com."),
    ("gemini", "Gemini (Google)",
     "Fast, very large context window, cheap. Needs a key from "
     "aistudio.google.com."),
    ("cli", "An AI app already on this computer",
     "Free if you already have Claude Code, Ollama, or a similar CLI signed in. "
     "No API key needed."),
    ("openai_compatible", "A local or self-hosted model",
     "Ollama, LM Studio, vLLM, or any OpenAI-compatible server. Free and private, "
     "but needs a capable machine."),
    ("openrouter", "OpenRouter (many models, one key)",
     "One key, access to Claude, GPT, Gemini and open models."),
    ("manual", "No AI account — I'll copy and paste",
     "DeckScope writes each prompt to a file; you paste it into whatever chat AI "
     "you already use and paste the answer back. Slow, but free."),
    ("mock", "Just show me a demo first",
     "Runs the whole pipeline with built-in sample output. No AI, no key, no cost."),
]

RESEARCH_MENU: List[Tuple[str, str, str]] = [
    ("tavily", "Tavily (recommended)",
     "Search built for AI research. Free tier covers roughly a thousand decks. "
     "Get a key at tavily.com."),
    ("serper", "Serper (Google results)",
     "Google's index via API. 2,500 free searches at serper.dev."),
    ("brave", "Brave Search",
     "Independent index with a free tier at brave.com/search/api."),
    ("exa", "Exa (semantic search)",
     "Finds high-quality analyst pages rather than blog spam. exa.ai."),
    ("provider_native", "Let the AI search for itself",
     "Uses the AI provider's own web search. No second key — only some providers "
     "support it."),
    ("none", "Skip web research",
     "Fastest and free, but the market analysis comes only from the model's "
     "training data and cannot see anything recent. Not recommended."),
]

KEY_ENVS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY",
            "groq": "GROQ_API_KEY", "openai_compatible": "OPENAI_COMPATIBLE_API_KEY"}

KEY_URLS = {"anthropic": "https://console.anthropic.com/settings/keys",
            "openai": "https://platform.openai.com/api-keys",
            "gemini": "https://aistudio.google.com/apikey",
            "openrouter": "https://openrouter.ai/keys",
            "tavily": "https://app.tavily.com/home",
            "serper": "https://serper.dev/api-key",
            "brave": "https://brave.com/search/api/",
            "exa": "https://dashboard.exa.ai/api-keys"}

RESEARCH_KEY_ENVS = {"tavily": "TAVILY_API_KEY", "serper": "SERPER_API_KEY",
                     "brave": "BRAVE_API_KEY", "exa": "EXA_API_KEY"}


def run_wizard(reconfigure: bool = False) -> Dict[str, Any]:
    settings.load_env()
    existing = settings.load_settings()

    banner("DeckScope setup",
           "Six questions. You can change any answer later with: deckscope setup")

    if existing and not reconfigure:
        say(f"You already have settings saved at {settings.config_path()}.")
        if not ask_yes("Start over and reconfigure?", default=False):
            say("Keeping your existing settings.")
            return existing
        print()

    say("DeckScope reads a pitch deck, researches the market it competes in, and "
        "tells you where the two agree and where they don't.\n\n"
        "To do that it needs two things: an AI to do the thinking, and a way to "
        "search the web. Let's set both up.")

    # ---------------------------------------------------------- 1. provider
    banner("1 of 6 · Which AI should do the analysis?")
    say("If you're not sure, pick Claude — it produces the strongest analysis. "
        "If you'd rather not create an account yet, pick the demo at the bottom "
        "and everything will still run.")
    provider = choose("Choose your AI", PROVIDER_MENU, default=1)

    cfg: Dict[str, Any] = {"provider": {"name": provider}}
    prov_extra: Dict[str, Any] = {}

    if provider in KEY_ENVS:
        env = KEY_ENVS[provider]
        cfg["provider"]["api_key_env"] = env
        if settings.has_key(env):
            current = os.getenv(env) or settings.load_env(False).get(env, "")
            say(f"\nFound an existing key: {settings.masked(current)}")
            if ask_yes("Use it?", default=True):
                pass
            else:
                _collect_key(provider, env)
        else:
            _collect_key(provider, env)

    if provider == "openai_compatible":
        print()
        say("Point DeckScope at your local server. The default is Ollama's address.")
        base = ask("Server address", "http://localhost:11434/v1")
        cfg["provider"]["base_url"] = base
        cfg["provider"]["model"] = ask("Model name", "llama3.1:8b")

    if provider == "cli":
        print()
        found = [(name, cmd) for name, cmd in
                 (("claude", "claude"), ("ollama", "ollama"),
                  ("codex", "codex"), ("gemini", "gemini"))
                 if shutil.which(cmd)]
        if found:
            say("Found these on your computer:")
            for name, _ in found:
                print(f"      {green('•')} {name}")
            preset = choose("Which should DeckScope use?",
                            [(n, n, "") for n, _ in found], default=1)
        else:
            say(yellow("No supported AI command was found on this computer."))
            say("Install Claude Code (claude.com/code) or Ollama (ollama.com), then "
                "run `deckscope setup` again. For now, choosing `claude` anyway.")
            preset = "claude"
        prov_extra["preset"] = preset
        cfg["provider"]["model"] = preset
        if preset == "ollama":
            prov_extra["ollama_model"] = ask("Which Ollama model?", "llama3.1:8b")

    if provider == "manual":
        print()
        say("In this mode DeckScope pauses at each step, puts the prompt on your "
            "clipboard, and waits while you paste it into whatever chat AI you use. "
            "You save the reply into a file and press Enter to continue.")
        prov_extra["exchange_dir"] = str(settings.app_dir() / "exchange")

    if prov_extra:
        cfg["provider"]["extra"] = prov_extra

    # ------------------------------------------------------------- 2. model
    if provider in ("anthropic", "openai", "gemini", "openrouter"):
        from .providers.registry import catalog

        options = catalog(provider)
        if options:
            banner("2 of 6 · Which model?")
            say("Bigger models cost more and think harder. The middle option is "
                "the right default for almost everyone.")
            model = choose("Choose a model",
                           [(m, m, d) for m, d in options],
                           default=min(2, len(options)))
            cfg["provider"]["model"] = model
    else:
        banner("2 of 6 · Model")
        say("Nothing to choose for this option — moving on.")

    # ---------------------------------------------------------- 3. research
    banner("3 of 6 · How should DeckScope research the market?")
    say("This is what makes the analysis worth reading. Without it, the market "
        "half of the report is just the AI's memory, which has a cutoff date and "
        "cannot see recent funding rounds, pricing, or new entrants.\n\n"
        "Tavily's free tier is generous and takes about a minute to set up.")
    research = choose("Choose a research source", RESEARCH_MENU, default=1)
    cfg["research"] = {"name": research}

    if research in RESEARCH_KEY_ENVS:
        env = RESEARCH_KEY_ENVS[research]
        cfg["research"]["api_key_env"] = env
        if settings.has_key(env):
            say(f"\nFound an existing key: "
                f"{settings.masked(os.getenv(env) or settings.load_env(False).get(env, ''))}")
            if not ask_yes("Use it?", default=True):
                _collect_key(research, env)
        else:
            _collect_key(research, env)

    # ------------------------------------------------------------- 4. lens
    banner("4 of 6 · Whose point of view should the report take?")
    say("Same evidence, different question. You can produce more than one, and "
        "you can change this per run.")
    lens_menu = [
        ("investor", "Investor — is this worth funding?",
         "Diligence tone. Market timing, defensibility, traction for the stage, "
         "and a clear verdict."),
        ("founder", "Founder — how does my deck hold up?",
         "Coaching tone. What an investor will attack, and exactly how to fix it "
         "before the next pitch."),
        ("neutral", "Neutral analyst — just line up the facts",
         "No recommendation. Claims beside evidence, gaps characterized precisely."),
        ("all", "All three",
         "Produces a separate report from each point of view. Costs about twice as "
         "much to run."),
    ]
    lens = choose("Choose a default point of view", lens_menu, default=1)
    cfg["lenses"] = ALL_LENSES if lens == "all" else [lens]

    # ---------------------------------------------------------- 5. outputs
    banner("5 of 6 · What files should DeckScope produce?")
    from .render.registry import DESCRIPTIONS

    say("Pick as many as you like — type the numbers separated by commas.")
    print()
    fmt_options = ["html", "pdf", "docx", "md", "pptx", "xlsx", "json", "txt"]
    for i, f in enumerate(fmt_options, 1):
        print(f"     {bold(str(i) + '.')} {f.upper():5s} {dim(DESCRIPTIONS.get(f, ''))}")
    print()
    while True:
        raw = ask("Which formats?", "1,2")
        picked = []
        for part in raw.replace(" ", "").split(","):
            if part.isdigit() and 1 <= int(part) <= len(fmt_options):
                picked.append(fmt_options[int(part) - 1])
            elif part.lower() in fmt_options:
                picked.append(part.lower())
        if picked:
            break
        print(dim("    Enter at least one number, e.g. 1,2"))
    print()
    out_dir = ask("Where should reports be saved?", str(settings.default_output_dir()))
    cfg["output"] = {"formats": list(dict.fromkeys(picked)), "out_dir": out_dir,
                     "theme": "slate"}
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------- 6. security
    banner("6 of 6 · Security")
    say("Pitch decks and web pages are written by other people, and both can carry "
        "text meant to steer an AI rather than inform you — white text on a white "
        "slide, hidden speaker notes, a web page seeded with fake instructions.\n\n"
        "DeckScope screens both before analyzing them. The recommended setting "
        "neutralizes anything it finds and reports it, rather than stopping.")
    sec = choose("Choose a security posture", [
        ("balanced", "Balanced (recommended)",
         "Removes hostile content, keeps going, and reports everything it found."),
        ("strict", "Strict",
         "Refuses to analyze a deck or source that contains hidden instructions. "
         "Best if you are reviewing decks from strangers."),
        ("permissive", "Report only",
         "Changes nothing, just tells you what it found. For investigating a deck "
         "you already suspect."),
    ], default=1)
    cfg["security"] = {"mode": sec}

    # ----------------------------------------------------- optional panel
    banner("Optional · A panel of AIs")
    say("DeckScope can run the same deck through several AI services at once. They "
        "analyze it separately, then read each other's reports, argue, and revise. "
        "Where they disagree is usually the most useful thing in the report.\n\n"
        "This costs roughly one run per AI, plus a review pass. You can skip it now "
        "and turn it on for any single run later with `deckscope panel`.")
    if ask_yes("Set up a panel now?", default=False):
        print()
        say("Enter the connections you want on the panel, separated by commas.")
        say(dim("   Examples: anthropic:claude-sonnet-5, openai:gpt-4o, gemini"))
        say(dim("   Each one needs its own key — run `deckscope setup` again to add more."))
        raw = ask("Panel", f"{provider}, openai:gpt-4o")
        members = [m.strip() for m in raw.split(",") if m.strip()]
        if len(members) >= 2:
            cfg["panel"] = {"members": members,
                            "rounds": int(ask("How many cross-review rounds?", "1") or 1)}
            say(green(f"   Panel of {len(members)} saved. Run it with: "
                      f"deckscope panel deck.pdf"))
        else:
            say(yellow("   Need at least two — skipping the panel for now."))

    # ------------------------------------------------------------ test run
    banner("Testing your setup")
    ok = _test_everything(cfg)

    cfg["_wizard"] = {"version": 1, "completed": True}
    path = settings.save_settings(cfg)

    banner("Setup complete" if ok else "Setup saved — with warnings")
    say(f"Settings saved to {path}")
    if settings.env_path().exists():
        say(f"Keys saved to {settings.env_path()} (readable only by you)")
    print()
    say(bold("What to do next:"))
    print()
    print(f"    {green('deckscope app')}              open the drag-and-drop window")
    print(f"    {green('deckscope demo')}             run a full sample analysis, free")
    print(f"    {green('deckscope run deck.pdf')}     analyze a real deck")
    print(f"    {green('deckscope panel deck.pdf --panel A B')}")
    print(f"    {dim('                              ')} several AIs that review each other")
    print(f"    {green('deckscope doctor')}           re-check everything is working")
    print()
    return cfg


def _collect_key(service: str, env: str) -> None:
    url = KEY_URLS.get(service, "")
    print()
    say(f"{bold(service.title())} needs an API key.")
    if url:
        say(f"Get one here: {blue(url)}")
        say(dim("Sign in, create a key, and copy it. It usually starts with a few "
                "letters and a dash."))
    print()
    while True:
        key = ask_secret(f"Paste your {service} key (or press Enter to skip)")
        if not key:
            say(yellow(f"Skipped. DeckScope will look for {env} in your environment "
                       f"when it runs."))
            return
        if len(key) < 16:
            say(red("That looks too short to be a key. Try copying it again."))
            continue
        settings.save_key(env, key)
        spinner_done(True, f"Key saved as {env}")
        return


def _test_everything(cfg: Dict[str, Any]) -> bool:
    """Prove the configuration works before the user meets a real deck."""
    from .config import ProviderConfig, ResearchConfig
    from .providers.registry import get_provider
    from .research.registry import get_researcher

    all_ok = True

    print("  Checking the AI connection...")
    try:
        pcfg = ProviderConfig(**cfg["provider"])
        provider = get_provider(pcfg)
        health = provider.health_check()
        if health.get("ok"):
            spinner_done(True, f"{health['provider']} responded "
                               f"({health.get('model') or 'default model'})")
        else:
            all_ok = False
            spinner_done(False, f"{health.get('provider')}: {health.get('error')}")
            say(dim("    Your analysis will fail until this is fixed. Run "
                    "`deckscope doctor` for details."))
        try:
            provider.close()
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        all_ok = False
        spinner_done(False, str(exc)[:200])

    print("  Checking web research...")
    try:
        rcfg = ResearchConfig(**cfg["research"])
        researcher = get_researcher(rcfg)
        health = researcher.health_check()
        if health.get("ok"):
            spinner_done(True, f"{health['backend']} returned "
                               f"{health.get('results', 0)} result(s)")
        else:
            all_ok = False
            spinner_done(False, f"{health.get('backend')}: {health.get('error')}")
    except Exception as exc:  # noqa: BLE001
        all_ok = False
        spinner_done(False, str(exc)[:200])

    print("  Checking output formats...")
    from .render.registry import resolve
    missing = []
    for fmt in cfg["output"]["formats"]:
        f = resolve(fmt)
        needs = {"docx": "docx", "pptx": "pptx", "xlsx": "openpyxl",
                 "pdf": "reportlab"}.get(f)
        if needs:
            try:
                __import__(needs)
            except ImportError:
                missing.append((f, needs))
    if missing:
        for f, mod in missing:
            spinner_done(False, f"{f.upper()} needs the `{mod}` package "
                                f"(pip install {mod})")
        all_ok = False
    else:
        spinner_done(True, f"{', '.join(f.upper() for f in cfg['output']['formats'])} ready")

    print("  Checking the reports folder...")
    try:
        out = Path(cfg["output"]["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        probe = out / ".deckscope_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        spinner_done(True, f"can write to {out}")
    except Exception as exc:  # noqa: BLE001
        all_ok = False
        spinner_done(False, f"cannot write there: {exc}")

    return all_ok


# ------------------------------------------------------------------ doctor

def doctor() -> int:
    """Diagnose an existing install. Exit code 0 means healthy."""
    settings.load_env()
    banner("DeckScope health check")

    print(f"  Python           {sys.version.split()[0]}")
    print(f"  DeckScope        {_version()}")
    print(f"  Settings file    {settings.config_path()}")
    print(f"  Key file         {settings.env_path()}"
          f"{'' if settings.env_path().exists() else dim('  (none yet)')}")
    print()

    if not settings.is_configured():
        say(yellow("DeckScope has not been set up yet."))
        say("Run: deckscope setup")
        return 1

    cfg = settings.load_settings()
    print(f"  AI provider      {cfg.get('provider', {}).get('name')} "
          f"({cfg.get('provider', {}).get('model') or 'default model'})")
    print(f"  Research         {cfg.get('research', {}).get('name')}")
    print(f"  Lenses           {', '.join(cfg.get('lenses', []))}")
    print(f"  Formats          {', '.join(cfg.get('output', {}).get('formats', []))}")
    print(f"  Reports folder   {cfg.get('output', {}).get('out_dir')}")
    print(f"  Security mode    {cfg.get('security', {}).get('mode', 'balanced')}")
    panel = cfg.get("panel") or {}
    if panel.get("members"):
        print(f"  Panel            {', '.join(panel['members'])} "
              f"({panel.get('rounds', 1)} review round(s))")
    print()
    rule()
    print()
    ok = _test_everything(cfg)
    print()
    if ok:
        say(green("Everything is working."))
        return 0
    say(yellow("Some checks failed — see above."))
    say("Fix the key or package it names, then run `deckscope doctor` again.")
    return 1


def _version() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return "unknown"
