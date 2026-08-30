"""Shared agent plumbing: caching, logging, timing."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..console import out as _out
from ..providers.base import LLMProvider


#: Bump when a prompt or schema changes in a way that invalidates cached output.
#: Without this, an upgrade silently replays answers produced by the old prompts.
def _prompt_epoch() -> str:
    """The cache epoch, derived from the prompt templates themselves.

    It was a hand-bumped constant ("2"), and the docstring below promised
    "upgrading DeckScope does not silently replay stale analysis" — a promise
    that held exactly as long as a human remembered to bump the number. The
    first prompt change that shipped without a bump served a cached
    comparison written for the OLD prompt (found while re-driving the
    committed reference run: the replay sailed through on a warm cache and
    stalled on a cold one). Hashing the templates module makes forgetting
    impossible: edit any prompt and every cached answer is invalidated.
    """
    import inspect

    from ..prompts import templates

    try:
        source = inspect.getsource(templates)
    except (OSError, TypeError):  # frozen/bytecode-only installs
        source = "unversioned"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]


CACHE_EPOCH = _prompt_epoch()


class Agent:
    """Base class. Subclasses implement `run()` and set `name`."""

    name = "agent"
    label = "Agent"

    def __init__(self, provider: LLMProvider, *, cache_dir: Optional[str] = None,
                 on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 verbose: bool = True, cache_ttl: float = 14 * 86400) -> None:
        self.provider = provider
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            # Cache entries contain the deck's extracted contents, which may be
            # confidential. Best-effort owner-only on POSIX; on Windows the
            # directory inherits the user profile's ACL.
            try:
                import stat as _stat
                self.cache_dir.chmod(_stat.S_IRWXU)
            except Exception:  # noqa: BLE001
                pass
        self.on_event = on_event or (lambda *_: None)
        self.verbose = verbose
        #: Market evidence goes stale. Two weeks is long enough to make re-running
        #: a deck cheap and short enough that a cached market view is still current.
        self.cache_ttl = cache_ttl
        self.usage: Dict[str, int] = {"input": 0, "output": 0}
        self.calls = 0

    # ---------------------------------------------------------------- utils
    def emit(self, message: str, **data: Any) -> None:
        self.on_event(message, {"agent": self.name, **data})
        if self.verbose:
            _out(f"  [{self.label}] {message}", flush=True)

    def cache_key(self, **parts: Any) -> str:
        """A stable key over canonicalized inputs.

        An earlier version used Python's built-in `hash()`, which is randomized
        per process for strings: the same deck produced a different key on every
        run, so the cache never hit and the documented speed-up did not exist.

        Every input that can change the answer is bound in — including the prompt
        epoch, so upgrading DeckScope does not silently replay stale analysis.
        """
        payload = {
            "epoch": CACHE_EPOCH,
            "agent": self.name,
            "provider": self.provider.name,
            "model": self.provider.model,
            **parts,
        }
        blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        digest = key if len(key) == 64 else hashlib.sha256(
            key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{self.name}_{digest[:32]}.json"

    def cached_json(self, key: str, produce: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        path = self._cache_path(key)
        if path and path.exists():
            try:
                age = time.time() - path.stat().st_mtime
                if age > self.cache_ttl:
                    self.emit(f"cached result is {age / 86400:.0f} days old — rerunning")
                    path.unlink(missing_ok=True)
                else:
                    self.emit("using cached result")
                    return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - a corrupt cache entry is not fatal
                pass
        started = time.time()
        result = produce()
        self.emit(f"done in {time.time() - started:.1f}s")
        if path:
            try:
                path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        return result

    def track(self, completion) -> None:
        """Record token usage. Safe to pass as `complete_json(on_usage=...)`."""
        if getattr(completion, "usage", None):
            self.usage["input"] += completion.usage.get("input", 0)
            self.usage["output"] += completion.usage.get("output", 0)
        self.calls += 1

    def complete_json(self, system: str, user: str, **kw: Any) -> Dict[str, Any]:
        """Provider call with usage accounting attached."""
        return self.provider.complete_json(system, user, on_usage=self.track, **kw)
