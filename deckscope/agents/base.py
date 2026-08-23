"""Shared agent plumbing: caching, logging, timing."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..providers.base import LLMProvider


class Agent:
    """Base class. Subclasses implement `run()` and set `name`."""

    name = "agent"
    label = "Agent"

    def __init__(self, provider: LLMProvider, *, cache_dir: Optional[str] = None,
                 on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 verbose: bool = True) -> None:
        self.provider = provider
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.on_event = on_event or (lambda *_: None)
        self.verbose = verbose
        self.usage: Dict[str, int] = {"input": 0, "output": 0}

    # ---------------------------------------------------------------- utils
    def emit(self, message: str, **data: Any) -> None:
        self.on_event(message, {"agent": self.name, **data})
        if self.verbose:
            print(f"  [{self.label}] {message}", flush=True)

    def _cache_path(self, key: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        return self.cache_dir / f"{self.name}_{digest}.json"

    def cached_json(self, key: str, produce: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        path = self._cache_path(key)
        if path and path.exists():
            try:
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
        if getattr(completion, "usage", None):
            self.usage["input"] += completion.usage.get("input", 0)
            self.usage["output"] += completion.usage.get("output", 0)
