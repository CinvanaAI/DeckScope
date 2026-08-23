"""What can this install actually talk to, right now?

`deckscope providers` lists the catalogue — everything DeckScope knows how to
drive. That is a different question from what will work when you press go, and
the gap between them is most of the support burden: a key that was never set, a
CLI that is installed but not signed in, an Ollama binary with no daemon running,
a Bedrock account without model access granted, a model name the vendor retired.

Presenting the catalogue as if it were a list of working options is how a picker
sends someone confidently into a failure.

Why this is not one check
-------------------------

"Available" means something different for every connection type:

===================  =========================================================
API-key providers    An environment variable exists. Cheap to check, and the
                     common failure.
CLI providers        A binary is on PATH **and the user is signed in**. The
                     first is free to check; the second is not knowable without
                     running it.
Ollama               Binary present, daemon running, *and the specific model
                     pulled*. Three independent conditions, two of them local
                     and free to check.
Bedrock              Credentials resolve **and model access is granted in the
                     AWS console, per account, per model**. Key presence proves
                     nothing here; only a live call does.
MCP                  A server command that launches and completes a handshake.
                     Cheap to check that the command exists; the handshake needs
                     a subprocess.
manual / mock        Always available. No dependencies at all.
===================  =========================================================

So the model here is a **ladder**, not a boolean:

1. **Structural checks** — free, local, instant, run every time. Env var set?
   Binary on PATH? Daemon answering on localhost? Model in the retired list?
2. **Live probe** — a real round-trip. Costs money and time, so it is run on
   demand and the answer is *cached with a fingerprint of the configuration*, so
   changing a key invalidates it rather than serving a stale pass.
3. **Unverified** — structurally fine, never probed. Reported honestly as its
   own state rather than being rounded up to "ready", because the whole point is
   not to promise something we have not seen work.

The states are deliberately not collapsible to a checkbox. A picker that shows
"unverified" differently from "ready" is telling the truth; one that shows both
as green is guessing on the user's behalf.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

#: How long a successful live probe is trusted before it is worth re-checking.
#: A day: long enough that a picker is not re-probing constantly, short enough
#: that a revoked key surfaces without the user having to think about caching.
PROBE_TTL_SECONDS = 24 * 60 * 60

READY = "ready"                 # verified working by a live probe
UNVERIFIED = "unverified"       # structurally fine, never actually tried
NEEDS_SETUP = "needs_setup"     # a prerequisite is missing
FAILED = "failed"               # probed and it did not work
RETIRED = "retired"             # the vendor withdrew this model

#: Ordered worst-first, so a picker can sort by "what needs my attention".
STATE_ORDER = {FAILED: 0, RETIRED: 1, NEEDS_SETUP: 2, UNVERIFIED: 3, READY: 4}


@dataclass
class Requirement:
    """One thing that must be true before a provider can be used."""

    #: "api_key" | "binary" | "daemon" | "python_package" | "credentials" | "none"
    kind: str
    #: The env var, binary name, URL or package this refers to.
    name: str
    #: What to tell a user who does not have it.
    fix: str = ""
    #: When True, its absence downgrades rather than blocks.
    optional: bool = False

    def check(self) -> Optional[str]:
        """None when satisfied, else a human explanation of what is missing."""
        if self.kind == "none":
            return None
        if self.kind == "api_key":
            return None if os.getenv(self.name) else f"{self.name} is not set"
        if self.kind == "binary":
            return (None if shutil.which(self.name)
                    else f"`{self.name}` is not on PATH")
        if self.kind == "python_package":
            try:
                __import__(self.name)
                return None
            except Exception:  # noqa: BLE001
                return f"the `{self.name}` package is not installed"
        if self.kind == "daemon":
            return None if _daemon_answers(self.name) else f"nothing answering at {self.name}"
        if self.kind == "credentials":
            return None if _aws_credentials_present() else "no AWS credentials resolved"
        return None


def _daemon_answers(url: str, timeout: float = 0.4) -> bool:
    """Is something listening? Local, fast, and free — worth doing every time.

    Deliberately short-timeouted: this runs while a user waits for a list to
    render, and a slow answer is worse than an honest "not sure".
    """
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except urllib.error.HTTPError:
        return True          # answering, even if it dislikes the request
    except Exception:  # noqa: BLE001
        return False


def _aws_credentials_present() -> bool:
    if os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_PROFILE"):
        return True
    return (os.path.expanduser("~/.aws/credentials") and
            os.path.exists(os.path.expanduser("~/.aws/credentials")))


#: What each provider needs, declared here rather than discovered by running it.
#:
#: Providers resolve their own keys inside `__init__`, so there was no way to ask
#: one what it required without constructing it — and constructing it raises when
#: the requirement is missing, which is precisely the case a picker needs to
#: describe rather than crash on.
REQUIREMENTS: Dict[str, List[Requirement]] = {
    "anthropic": [Requirement("api_key", "ANTHROPIC_API_KEY",
                              "Get a key at console.anthropic.com, then run "
                              "`deckscope setup`.")],
    "openai": [Requirement("api_key", "OPENAI_API_KEY",
                           "Get a key at platform.openai.com, then run "
                           "`deckscope setup`.")],
    "gemini": [Requirement("api_key", "GEMINI_API_KEY",
                           "Get a key at aistudio.google.com, then run "
                           "`deckscope setup`.")],
    "groq": [Requirement("api_key", "GROQ_API_KEY",
                         "Get a key at console.groq.com, then run "
                         "`deckscope setup`.")],
    "openrouter": [Requirement("api_key", "OPENROUTER_API_KEY",
                               "Get a key at openrouter.ai, then run "
                               "`deckscope setup`.")],
    "openai_compatible": [
        Requirement("api_key", "OPENAI_COMPATIBLE_API_KEY",
                    "Only needed if your endpoint requires one.", optional=True)],
    "bedrock": [
        Requirement("python_package", "boto3", "pip install boto3"),
        Requirement("credentials", "aws",
                    "Configure AWS credentials (`aws configure`), and grant the "
                    "model access in the Bedrock console — access is per-account "
                    "and per-model, so credentials alone are not enough."),
    ],
    "manual": [Requirement("none", "", "")],
    "mock": [Requirement("none", "", "")],
}

#: CLI providers need their binary *and* a signed-in session. Only the first is
#: checkable for free; the second is why they land in `unverified` rather than
#: `ready` until something has actually run.
CLI_BINARIES = {"claude": "claude", "codex": "codex",
                "gemini": "gemini", "ollama": "ollama"}


@dataclass
class Capability:
    """Whether one provider/model pair can be used, and what to do if not."""

    provider: str
    model: str = ""
    state: str = UNVERIFIED
    reasons: List[str] = field(default_factory=list)
    fix: str = ""
    description: str = ""
    #: True when a real round-trip confirmed this, rather than a local check.
    verified_live: bool = False
    checked_at: str = ""

    @property
    def usable(self) -> bool:
        """Safe to offer as a choice. Unverified counts: it may well work, and
        refusing to list it would hide every provider nobody has probed yet."""
        return self.state in (READY, UNVERIFIED)

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}" if self.model else self.provider

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["usable"] = self.usable
        d["key"] = self.key
        return d


def requirements_for(provider: str) -> List[Requirement]:
    """What this provider needs. Unknown providers require nothing checkable."""
    if provider in REQUIREMENTS:
        return REQUIREMENTS[provider]
    if provider == "cli":
        return []            # depends on which CLI; handled per-model
    return []


def _cli_requirements(model: str) -> List[Requirement]:
    binary = CLI_BINARIES.get(model, model)
    reqs = [Requirement("binary", binary,
                        f"Install the {model} CLI and sign in, then re-check.")]
    if model == "ollama":
        # Three separate conditions, and the daemon is the one people miss.
        reqs.append(Requirement("daemon", "http://localhost:11434/api/tags",
                                "Start Ollama (`ollama serve`) and pull a model "
                                "(`ollama pull llama3.3`)."))
    return reqs


def _retired_models(provider: str) -> Dict[str, str]:
    try:
        from .providers.registry import provider_class
        return dict(getattr(provider_class(provider), "retired_models", {}) or {})
    except Exception:  # noqa: BLE001
        return {}


def inspect(provider: str, model: str = "",
            probes: Optional[Dict[str, Any]] = None) -> Capability:
    """The structural verdict for one provider/model, plus any cached probe.

    Never makes a network call. Everything here is an env lookup, a PATH lookup,
    or a local socket — so a picker can render the whole list instantly.
    """
    cap = Capability(provider=provider, model=model)

    retired = _retired_models(provider)
    if model and model in retired:
        cap.state = RETIRED
        cap.reasons = [f"{model} has been withdrawn by the provider"]
        cap.fix = f"Use {retired[model]} instead."
        return cap

    reqs = _cli_requirements(model) if provider == "cli" else requirements_for(provider)
    missing = []
    for req in reqs:
        problem = req.check()
        if problem and not req.optional:
            missing.append((problem, req.fix))

    if missing:
        cap.state = NEEDS_SETUP
        cap.reasons = [p for p, _ in missing]
        cap.fix = next((f for _, f in missing if f), "")
        return cap

    # Structurally fine. Has anything actually confirmed it works?
    record = (probes or {}).get(cap.key)
    if record and _probe_is_current(record, provider):
        if record.get("ok"):
            cap.state = READY
            cap.verified_live = True
            cap.checked_at = record.get("at", "")
        else:
            cap.state = FAILED
            cap.reasons = [record.get("error", "the last live check failed")]
            cap.fix = "Re-run the check after fixing the error above."
            cap.checked_at = record.get("at", "")
        return cap

    if provider in ("mock", "manual"):
        # No dependencies at all, so there is nothing a probe could add.
        cap.state = READY
        return cap

    cap.state = UNVERIFIED
    cap.reasons = ["configured, but nothing has confirmed it works yet"]
    cap.fix = "Run `deckscope models --check` to try it for real."
    return cap


def _probe_is_current(record: Dict[str, Any], provider: str) -> bool:
    """A cached probe is only good while its inputs and its age hold.

    Fingerprinting the credential means rotating a key invalidates the cache
    instead of serving a pass that was earned by a different key.
    """
    if time.time() - float(record.get("epoch") or 0) > PROBE_TTL_SECONDS:
        return False
    return record.get("fingerprint") == credential_fingerprint(provider)


def credential_fingerprint(provider: str) -> str:
    """A hash of whatever this provider authenticates with.

    Hashed, never stored raw — this ends up in a settings file that users share
    when reporting bugs.
    """
    import hashlib

    parts = []
    for req in requirements_for(provider):
        if req.kind == "api_key":
            parts.append(f"{req.name}={os.getenv(req.name) or ''}")
    if not parts:
        parts.append(provider)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def survey(probes: Optional[Dict[str, Any]] = None,
           include_unusable: bool = True) -> List[Capability]:
    """Every provider/model DeckScope knows, with its current state.

    Instant: structural checks only. Sorted worst-first so whatever needs
    attention is at the top rather than buried under working options.
    """
    from .providers.registry import catalog, list_providers

    out: List[Capability] = []
    for provider in sorted(list_providers()):
        models = catalog(provider) or []
        if not models:
            out.append(inspect(provider, "", probes))
            continue
        for entry in models:
            name, description = (entry if isinstance(entry, (list, tuple))
                                 else (entry, ""))
            cap = inspect(provider, str(name), probes)
            cap.description = str(description or "")
            out.append(cap)
    if not include_unusable:
        out = [c for c in out if c.usable]
    return sorted(out, key=lambda c: (STATE_ORDER.get(c.state, 9), c.provider,
                                      c.model))


def probe(provider: str, model: str = "", timeout: int = 30) -> Dict[str, Any]:
    """Actually try it. Costs a call; that is the point.

    Returns a record suitable for caching, including the credential fingerprint
    so a later rotation invalidates it.
    """
    from datetime import datetime, timezone

    from .config import ProviderConfig
    from .providers.registry import get_provider

    record: Dict[str, Any] = {
        "provider": provider, "model": model,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "epoch": time.time(),
        "fingerprint": credential_fingerprint(provider),
    }
    try:
        instance = get_provider(ProviderConfig(name=provider, model=model or None))
        try:
            health = instance.health_check()
        finally:
            instance.close()
        record["ok"] = bool(health.get("ok"))
        if not health.get("ok"):
            record["error"] = str(health.get("error", "unknown error"))[:300]
    except Exception as exc:  # noqa: BLE001 - a failed probe is a result
        record["ok"] = False
        record["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return record


def diversity(selection: List[str]) -> Dict[str, Any]:
    """How independent a panel selection actually is.

    A panel exists to catch what one model gets wrong. Models from one vendor
    share training data and tend to agree for correlated reasons, so five
    Anthropic models is closer to one opinion sampled five times than to five
    opinions. That is a legitimate thing to choose — comparing within a family is
    a real use — but it should be visible rather than discovered afterwards in a
    consensus that looks unanimous for the wrong reason.
    """
    providers = [str(s).split(":", 1)[0] for s in selection]
    unique = sorted(set(providers))
    size = len(selection)
    note = ""
    if size < 2:
        note = "One model is not a panel — DeckScope will run a single analysis."
    elif len(unique) == 1:
        note = (f"All {size} panelists come from {unique[0]}. They share training "
                f"data and will tend to agree for correlated reasons, which is the "
                f"failure a panel is meant to catch. Adding one model from a "
                f"different provider buys more independence than adding three more "
                f"from this one.")
    elif len(unique) < size:
        note = (f"{len(unique)} providers across {size} panelists — reasonable. "
                f"Provider diversity does more for independence than model count.")
    else:
        note = f"{size} panelists from {size} different providers — maximally independent."
    return {"panelists": size, "providers": unique,
            "provider_count": len(unique),
            "independent": len(unique) > 1,
            "note": note}


def load_probes(settings_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from . import settings as _settings

    data = settings_data if settings_data is not None else _settings.load_settings()
    return dict((data.get("availability") or {}).get("probes") or {})


def save_probe(record: Dict[str, Any]) -> None:
    from . import settings as _settings

    data = _settings.load_settings()
    availability = dict(data.get("availability") or {})
    probes = dict(availability.get("probes") or {})
    key = (f"{record['provider']}:{record['model']}" if record.get("model")
           else record["provider"])
    probes[key] = record
    availability["probes"] = probes
    data["availability"] = availability
    _settings.save_settings(data)


def as_json(caps: List[Capability]) -> str:
    return json.dumps([c.to_dict() for c in caps], indent=2)
