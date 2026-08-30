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

from .console import out as _out
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
    _out(dim(char * WIDTH))


def banner(title: str, subtitle: str = "") -> None:
    _out()
    rule("━")
    _out(bold(f"  {title}"))
    if subtitle:
        _out(dim(f"  {subtitle}"))
    rule("━")
    _out()


def say(text: str, indent: str = "  ") -> None:
    for para in text.split("\n"):
        if not para.strip():
            _out()
            continue
        _out(textwrap.fill(para, WIDTH - 2, initial_indent=indent,
                            subsequent_indent=indent))


def ask(prompt: str, default: Optional[str] = None) -> str:
    suffix = f" {dim('[' + default + ']')}" if default else ""
    try:
        val = input(f"  {blue('›')} {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        _out()
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
        _out(dim("    Please answer y or n."))


def choose(prompt: str, options: List[Tuple[str, str, str]],
           default: int = 1) -> str:
    """options: (value, label, description). Returns the chosen value."""
    _out()
    _out(f"  {bold(prompt)}")
    _out()
    for i, (_, label, desc) in enumerate(options, 1):
        mark = green("→") if i == default else " "
        _out(f"   {mark} {bold(str(i) + '.')} {label}")
        if desc:
            for line in textwrap.wrap(desc, WIDTH - 10):
                _out(f"        {dim(line)}")
    _out()
    while True:
        raw = ask(f"Pick 1-{len(options)}", str(default))
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        except ValueError:
            pass
        _out(dim(f"    Enter a number between 1 and {len(options)}."))


def ask_secret(prompt: str) -> str:
    import getpass
    try:
        return getpass.getpass(f"  › {prompt}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nSetup cancelled.")
    except Exception:  # noqa: BLE001 - no tty
        return ask(prompt)


def spinner_done(ok: bool, message: str) -> None:
    _out(f"    {green('✓') if ok else red('✗')} {message}")


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
    ("mcp", "An MCP server you already run",
     "Route DeckScope's prompts through a Model Context Protocol server over "
     "stdio — yours, or any server exposing a completion tool. No new key."),
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

#: Government statistical data — a different thing from web search, and worth
#: its own step. Web search finds what somebody wrote about a market; these
#: publish what the market measurably is. One free key unlocks all of them.
CENSUS_ENV = "CENSUS_API_KEY"
CENSUS_SIGNUP = "https://api.census.gov/data/key_signup.html"


def run_wizard(reconfigure: bool = False) -> Dict[str, Any]:
    settings.load_env()
    existing = settings.load_settings()

    banner("DeckScope setup",
           "Seven questions. You can change any answer later with: deckscope setup")

    if existing and not reconfigure:
        say(f"You already have settings saved at {settings.config_path()}.")
        if not ask_yes("Start over and reconfigure?", default=False):
            say("Keeping your existing settings.")
            return existing
        _out()

    say("DeckScope does two things. It writes market reports — who holds what "
        "share, how large a market is, what rules govern it — with every "
        "figure traceable to the source it came from. And it reads a pitch "
        "deck against that evidence, to show where the two disagree.\n\n"
        "Either way it needs an AI to do the thinking and a way to search the "
        "web. Let's set both up.")

    # ---------------------------------------------------------- 1. provider
    banner("1 of 7 · Which AI should do the analysis?")
    # This used to read "pick Claude — it produces the strongest analysis",
    # which was an efficacy claim nothing here has ever tested. No comparison
    # of providers on analysis quality has been run, and a setup wizard is a
    # bad place to assert one: it is the moment a new user has least ability
    # to tell whether they are being told a fact or sold something.
    say("Any of these work. If you have no account yet, pick the demo at the "
        "bottom — it runs the whole pipeline on recorded pages with no key "
        "and no network, so you can see the output before choosing.\n\n"
        "DeckScope has not compared these providers on analysis quality, so "
        "it has no recommendation to make. Pick the one you already pay for.")
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
        _out()
        say("Point DeckScope at your local server. The default is Ollama's address.")
        base = ask("Server address", "http://localhost:11434/v1")
        cfg["provider"]["base_url"] = base
        cfg["provider"]["model"] = ask("Model name", "llama3.1:8b")

    if provider == "cli":
        _out()
        found = [(name, cmd) for name, cmd in
                 (("claude", "claude"), ("ollama", "ollama"),
                  ("codex", "codex"), ("gemini", "gemini"))
                 if shutil.which(cmd)]
        if found:
            say("Found these on your computer:")
            for name, _ in found:
                _out(f"      {green('•')} {name}")
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

    if provider == "mcp":
        _out()
        say("DeckScope will launch your MCP server as a subprocess and speak "
            "MCP over stdio. Give the command exactly as you would run it in "
            "a terminal (e.g. `npx -y my-mcp-server` or `python -m myserver`).")
        import shlex
        raw_cmd = ask("Server command", "npx -y my-mcp-server")
        prov_extra["command"] = shlex.split(raw_cmd)
        say("Two ways a server can answer: `sampling` (the MCP sampling API — "
            "the default, works with servers that proxy a model) or a named "
            "tool that takes a prompt and returns text.")
        mode = ask("Mode (sampling, or a tool name)", "sampling").strip()
        if mode and mode != "sampling":
            prov_extra["mode"] = "tool"
            prov_extra["tool_name"] = mode
        say(dim("   The same block works in config.yaml: provider: {name: mcp, "
                "extra: {command: [...]}} — see docs/PROVIDERS.md."))

    if provider == "manual":
        _out()
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
            banner("2 of 7 · Which model?")
            say("Bigger models cost more and think harder. The middle option is "
                "the right default for almost everyone.")
            model = choose("Choose a model",
                           [(m, m, d) for m, d in options],
                           default=min(2, len(options)))
            cfg["provider"]["model"] = model
    else:
        banner("2 of 7 · Model")
        say("Nothing to choose for this option — moving on.")

    # ---------------------------------------------------------- 3. research
    banner("3 of 7 · How should DeckScope research the market?")
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

    # ------------------------------------------------- 4. government data
    _census_step(cfg)

    # ------------------------------------------------------------- 5. lens
    banner("5 of 7 · Whose point of view should the report take?")
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
    banner("6 of 7 · What files should DeckScope produce?")
    from .render.registry import DESCRIPTIONS

    say("Pick as many as you like — type the numbers separated by commas.")
    _out()
    fmt_options = ["html", "pdf", "docx", "md", "pptx", "xlsx", "json", "txt"]
    for i, f in enumerate(fmt_options, 1):
        _out(f"     {bold(str(i) + '.')} {f.upper():5s} {dim(DESCRIPTIONS.get(f, ''))}")
    _out()
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
        _out(dim("    Enter at least one number, e.g. 1,2"))
    _out()
    out_dir = ask("Where should reports be saved?", str(settings.default_output_dir()))
    cfg["output"] = {"formats": list(dict.fromkeys(picked)), "out_dir": out_dir,
                     "theme": "slate"}
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------- 6. security
    banner("7 of 7 · Security")
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
        _out()
        say("Enter the connections you want on the panel, separated by commas.")
        say(dim("   Examples: anthropic:claude-sonnet-5, openai:gpt-5.2, gemini"))
        say(dim("   Each one needs its own key — run `deckscope setup` again to add more."))
        raw = ask("Panel", f"{provider}, openai:gpt-5.2")
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
    _out()
    say(bold("What to do next:"))
    _out()
    _out(f"    {green('deckscope app')}              open the drag-and-drop window")
    _out(f"    {green('deckscope demo')}             run a full sample analysis, free")
    _out(f"    {green('deckscope run deck.pdf')}     analyze a real deck")
    _out(f"    {green('deckscope panel deck.pdf --panel A B')}")
    _out(f"    {dim('                              ')} several AIs that review each other")
    _out(f"    {green('deckscope doctor')}           re-check everything is working")
    _out()
    return cfg


def _census_step(cfg: Dict[str, Any]) -> None:
    """Offer the Census key, with the walkthrough it actually needs.

    Its own step rather than a line in the research menu, because it is a
    different kind of source. Web search finds what somebody *wrote* about a
    market. The Census publishes what the market measurably *is* — how many
    businesses operate in an industry, in a county, and what they take in. Those
    are the two terms every market size is built from.

    The generic key flow is not reused here for one specific reason: the Census
    emails a confirmation link that must be clicked before the key works. A user
    who pastes the key straight from the email gets a key that silently fails on
    first run, and nothing in a generic "paste your key" prompt would tell them
    why.
    """
    banner("4 of 7 · Government data (optional, free)")
    say("Market sizes are built from two numbers: how many businesses are in an "
        "industry, and what each one takes in. The US Census publishes both, "
        "free, by industry and down to the county.\n\n"
        "This is the same data an investment bank pays a research firm for. "
        "Skipping it does not break anything — market sizes will just report "
        "as unestablished, with a note saying why.")
    _out()

    if settings.has_key(CENSUS_ENV):
        current = os.getenv(CENSUS_ENV) or \
            settings.load_env(into_environ=False).get(CENSUS_ENV, "")
        say(f"Found an existing key: {settings.masked(current)}")
        if ask_yes("Use it?", default=True):
            cfg.setdefault("data", {})["census"] = True
            return

    if not ask_yes("Set up Census data access now?", default=True):
        say(yellow("Skipped. Market sizing will report figures as unestablished "
                   "until a key is added. Run `deckscope setup` again any time."))
        return

    _out()
    say(bold("How to get one — about two minutes:"))
    say(f"1. Open {blue(CENSUS_SIGNUP)}")
    say("2. Enter any organization name and your email address. There is no "
        "approval step and no cost.")
    say("3. " + bold("Check your email and click the confirmation link.") +
        " The key does not work until you do — this is the step everyone "
        "misses.")
    say("4. Copy the key from that email. It is 40 characters, letters and "
        "numbers, no dashes.")
    _out()

    while True:
        key = ask_secret("Paste your Census key (or press Enter to skip)")
        if not key:
            say(yellow("Skipped. Market sizing will report figures as "
                       "unestablished until a key is added."))
            return
        problem = _census_key_problem(key)
        if problem:
            say(red(problem))
            continue
        settings.save_key(CENSUS_ENV, key)
        spinner_done(True, f"Key saved to {settings.env_path()}")
        cfg.setdefault("data", {})["census"] = True
        say(dim("  Owner-only permissions. Never written into the settings file "
                "or into any report."))
        return


def _census_key_problem(key: str) -> str:
    """Why this cannot be a Census key, or empty if it looks fine.

    Checked before saving because the alternative is a key that fails silently
    on the first real run, long after the user has forgotten this screen.
    """
    key = key.strip()
    if len(key) != 40:
        return (f"A Census key is exactly 40 characters; that one is "
                f"{len(key)}. Copy the whole string from the email.")
    if not all(ch.isalnum() for ch in key):
        return ("A Census key is letters and numbers only. That one has other "
                "characters in it — check for a stray space or a line break.")
    return ""


def _collect_key(service: str, env: str) -> None:
    url = KEY_URLS.get(service, "")
    _out()
    say(f"{bold(service.title())} needs an API key.")
    if url:
        say(f"Get one here: {blue(url)}")
        say(dim("Sign in, create a key, and copy it. It usually starts with a few "
                "letters and a dash."))
    _out()
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

    _out("  Checking the AI connection...")
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

    _out("  Checking web research...")
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

    _out("  Checking output formats...")
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

    _out("  Checking the reports folder...")
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

    _out(f"  Python           {sys.version.split()[0]}")
    _out(f"  DeckScope        {_version()}")
    _out(f"  Settings file    {settings.config_path()}")
    key_file = settings.env_path()
    if key_file.exists():
        locked = settings.restrict_to_owner(key_file)
        state = green("owner-only") if locked else yellow(
            "could NOT be restricted to your account — check its permissions")
        _out(f"  Key file         {key_file}  [{state}]")
    else:
        _out(f"  Key file         {key_file}{dim('  (none yet)')}")
    _out()

    if not settings.is_configured():
        say(yellow("DeckScope has not been set up yet."))
        say("Run: deckscope setup")
        return 1

    cfg = settings.load_settings()
    _out(f"  AI provider      {cfg.get('provider', {}).get('name')} "
          f"({cfg.get('provider', {}).get('model') or 'default model'})")
    _out(f"  Research         {cfg.get('research', {}).get('name')}")
    _out(f"  Lenses           {', '.join(cfg.get('lenses', []))}")
    _out(f"  Formats          {', '.join(cfg.get('output', {}).get('formats', []))}")
    _out(f"  Reports folder   {cfg.get('output', {}).get('out_dir')}")
    _out(f"  Security mode    {cfg.get('security', {}).get('mode', 'balanced')}")
    # Reported at a glance because its absence is silent otherwise: market
    # sizes simply come back unestablished, which looks like a broken product
    # rather than a missing free credential.
    if settings.has_key(CENSUS_ENV):
        current = os.getenv(CENSUS_ENV) or \
            settings.load_env(into_environ=False).get(CENSUS_ENV, "")
        problem = _census_key_problem(current)
        state = green(settings.masked(current)) if not problem else red(problem)
        _out(f"  Census data      {state}")
    else:
        _out(f"  Census data      {yellow('no key')}"
             f"{dim('  — market sizes will report as unestablished')}")
    panel = cfg.get("panel") or {}
    if panel.get("members"):
        _out(f"  Panel            {', '.join(panel['members'])} "
              f"({panel.get('rounds', 1)} review round(s))")
    _out()
    rule()
    _out()
    ok = _test_everything(cfg)
    _out()
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
