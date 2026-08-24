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

#: Provider names that run on the user's own hardware. Only these may receive
#: deck content when NDA mode is on.
LOCAL_PROVIDERS = {"mock", "manual", "openai_compatible", "cli"}


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
    """Whether this connection keeps data on the user's machine.

    `openai_compatible` counts only when pointed at a loopback or private
    address — it is the backend people use for Ollama and LM Studio, and also
    the one they use for hosted gateways, so the name alone proves nothing.
    """
    name = (provider.name or "").strip().lower()
    if name in ("mock", "manual", "cli"):
        return True
    if name == "openai_compatible":
        base = (provider.base_url or "").lower()
        return bool(re.search(r"//(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0|"
                              r"192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)", base))
    return False


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
