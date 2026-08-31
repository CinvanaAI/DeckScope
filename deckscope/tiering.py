"""Which model does which job, and what may never leave the machine.

Two constraints force this, and they point the same way.

**Cost.** Most of the work in a research loop is small and mechanical: read this
page, pull the figure, classify this question, decide whether two entities are
the same company. Sending all of that to a frontier model is how a per-deck cost
becomes absurd. Only the final judgment genuinely needs the best model available.

**Confidentiality.** A deck under NDA cannot be sent to a third-party API at all.
That is not a preference to be configured away — it is disqualifying, and it
means the analysis has to be able to run against a local model.

The second constraint is enforced structurally rather than documented politely.
`NDAGuard` refuses outbound calls carrying deck-derived text to any provider not
marked local, and it does so with two independent checks: an explicit taint flag
on the call, and a content fingerprint as a backstop for when somebody forgets to
set the flag. Belt and braces, because a privacy control that depends on every
future caller remembering something is not a control.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from .config import ProviderConfig

#: What a call is for. Routing is by task, not by agent, because the same agent
#: does cheap and expensive work at different moments.
EXTRACT = "extract"        # page → structured rows
ROUTE = "route"            # classify a question
RESOLVE = "resolve"        # entity resolution, deduplication
CONTRADICT = "contradict"  # does this disagree with that
FRAME = "frame"            # what market is this — high leverage
JUDGE = "judge"            # the single call that concludes
TASKS = (EXTRACT, ROUTE, RESOLVE, CONTRADICT, FRAME, JUDGE)

#: Rough capability floor per task. `small` is a 7-14B local model; `best` is
#: whatever the user has configured as their strongest connection.
DEFAULT_TIERS: Dict[str, str] = {
    EXTRACT: "small",
    ROUTE: "small",
    RESOLVE: "small",
    CONTRADICT: "mid",
    FRAME: "mid",
    JUDGE: "best",
}

#: Provider names that CAN run on the user's own hardware. Membership here
#: is necessary, not sufficient — `is_local` decides per configuration:
#: an openai_compatible endpoint must be loopback, and a `cli` preset must
#: be a genuinely on-device runtime (ollama), because Claude Code, Codex
#: and Gemini CLIs are hosted subscriptions whatever directory they run in
#: (fifth external audit).
LOCAL_PROVIDERS = {"mock", "manual", "openai_compatible", "cli"}

#: CLI presets that execute the model on-device. Everything else in the cli
#: backend proxies a hosted service.
LOCAL_CLI_PRESETS = {"ollama"}


class NDAViolation(RuntimeError):
    """Deck-derived content was about to leave the machine. The call is refused."""


@dataclass
class ModelPlan:
    """Which configured connection serves each tier."""

    small: Optional[ProviderConfig] = None
    mid: Optional[ProviderConfig] = None
    best: Optional[ProviderConfig] = None
    tiers: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TIERS))

    def for_task(self, task: str) -> Optional[ProviderConfig]:
        """The connection for a task, degrading upward when a tier is unset.

        Upward rather than downward on purpose: if no small model is configured,
        doing the work on a bigger one is expensive but correct. Doing judgment
        on a model too weak for it is cheap and wrong.
        """
        tier = self.tiers.get(task, "best")
        for candidate in _tier_chain(tier):
            cfg = getattr(self, candidate, None)
            if cfg is not None:
                return cfg
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tiers": dict(self.tiers),
            "assigned": {
                task: (lambda c: f"{c.name}:{c.model}" if c else None)(
                    self.for_task(task))
                for task in TASKS},
        }

    @classmethod
    def single(cls, provider: ProviderConfig) -> "ModelPlan":
        """Everything on one connection — the behaviour before tiering existed."""
        return cls(small=provider, mid=provider, best=provider)


def _tier_chain(tier: str) -> List[str]:
    return {"small": ["small", "mid", "best"],
            "mid": ["mid", "best", "small"],
            "best": ["best", "mid", "small"]}.get(tier, ["best", "mid", "small"])


def is_local(provider: ProviderConfig) -> bool:
    """Whether this connection keeps data ON THE USER'S MACHINE.

    Rewritten after the fifth external audit demonstrated three ways the old
    answer was wrong:

    - Every `cli` provider counted as local, but Claude Code, Codex and
      Gemini CLIs proxy hosted subscriptions — sandboxing removes tools, it
      does not move the model on-device. Only an on-device runtime (ollama)
      qualifies now.
    - The endpoint check was a substring regex, so `localhost.evil.com`,
      `127.0.0.1.evil.com`, `10.example.com` and `192.168.evil.com` all
      passed as local. The hostname is now PARSED (urlparse + ipaddress),
      never pattern-matched.
    - LAN addresses counted as "the user's machine". Traffic to 192.168.x.x
      has left the machine; under a promise that reads "nothing leaves your
      machine", only loopback qualifies.

    `manual` stays local because the tool itself transmits nothing — a
    human carries each prompt, and the human is the boundary.
    """
    name = (provider.name or "").strip().lower()
    if name in ("mock", "manual"):
        return True
    if name == "cli":
        extra = provider.extra or {}
        preset = str(extra.get("preset", "")).strip().lower()
        # A custom command may proxy anything, whatever preset it claims
        # (eighth external audit): the preset earns local trust only when
        # the preset's own command is what actually runs.
        if str(extra.get("command", "") or "").strip():
            return False
        return preset in LOCAL_CLI_PRESETS
    if name == "openai_compatible":
        return _is_loopback_url(provider.base_url or "")
    return False


def _is_loopback_url(url: str) -> bool:
    """True only for a parsed loopback host — never for a lookalike."""
    import ipaddress
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").strip("[]").lower()
    except ValueError:
        return False
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a DNS name is not provably this machine


class NDAGuard:
    """Refuses to let deck-derived text reach a non-local provider.

    Enabled per run. When off, it does nothing at all — no fingerprinting, no
    scanning — so the normal path pays nothing for a feature it is not using.
    """

    #: Length of the overlapping word windows used as content fingerprints.
    SHINGLE = 8
    #: How many distinct shingles must match before a payload is treated as
    #: carrying deck content. One can occur by chance in boilerplate; several in
    #: the same document cannot.
    THRESHOLD = 2

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._shingles: Set[str] = set()
        #: Every refusal, so a run can report what it declined to send.
        self.refusals: List[Dict[str, str]] = []

    def protect(self, text: str) -> None:
        """Register deck text as confidential. Safe to call repeatedly."""
        if not self.enabled or not text:
            return
        for shingle in _shingles(text, self.SHINGLE):
            self._shingles.add(shingle)

    def check(self, provider: ProviderConfig, payload: str, *,
              tainted: bool = False, where: str = "") -> None:
        """Raise if this call would send protected content off the machine.

        `tainted` is the caller declaring it knows the payload contains deck
        content. The fingerprint scan is the backstop for when it does not.
        """
        if not self.enabled or is_local(provider):
            return

        reason = ""
        if tainted:
            reason = "the caller marked this payload as containing deck content"
        else:
            hits = 0
            for shingle in _shingles(payload or "", self.SHINGLE):
                if shingle in self._shingles:
                    hits += 1
                    if hits >= self.THRESHOLD:
                        reason = (f"{hits} passages of deck text were found in the "
                                  f"payload")
                        break
        if not reason:
            return

        self.refusals.append({"provider": provider.name, "where": where,
                              "reason": reason})
        raise NDAViolation(
            f"NDA mode: refusing to send deck content to {provider.name!r} — "
            f"{reason}. Configure a local model for this task, or turn NDA mode "
            f"off if this deck is not confidential.\n"
            f"Local backends: {', '.join(sorted(LOCAL_PROVIDERS))}.")

    def report(self) -> Dict[str, Any]:
        return {"enabled": self.enabled,
                "protected_passages": len(self._shingles),
                "refusals": list(self.refusals)}


def _shingles(text: str, size: int) -> Iterable[str]:
    words = re.findall(r"\w+", (text or "").lower())
    if len(words) < size:
        return []
    return (hashlib.sha1(" ".join(words[i:i + size]).encode()).hexdigest()[:16]
            for i in range(len(words) - size + 1))


def plan_from_config(cfg: Any) -> ModelPlan:
    """Build a plan from a RunConfig, honouring `extract_provider` if set."""
    primary = getattr(cfg, "provider", None)
    small = getattr(cfg, "extract_provider", None) or primary
    return ModelPlan(small=small, mid=primary, best=primary)
