"""Runner dispatch for verticals with their own execution paths.

The deck vertical dispatches straight to the existing pipeline in
`commands/analyze.py`; verticals that arrive with their own runners
(grants, nonprofits) register them here by name. An unknown runner is a
refusal with the remedy named — never a silent fall-through to a runner
built for a different document type.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from . import Vertical

_RUNNERS: Dict[str, Callable[[Vertical, Path, Any], int]] = {}


def register_runner(name: str,
                    fn: Callable[[Vertical, Path, Any], int]) -> None:
    _RUNNERS[name] = fn


def dispatch(vertical: Vertical, path: Path, args: Any) -> int:
    _bootstrap()
    fn = _RUNNERS.get(vertical.runner)
    if fn is None:
        import sys

        from ..console import out as _out

        _out(f"{vertical.label} declares runner {vertical.runner!r}, and "
             f"no such runner is registered — the declaration is ahead of "
             f"the engine. Registered: {', '.join(sorted(_RUNNERS)) or 'none'}",
             file=sys.stderr)
        return 2
    return fn(vertical, path, args)


_BOOTSTRAPPED = False


def _bootstrap() -> None:
    """Import the modules that register runners. Grants and nonprofits
    add theirs here as they land."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True
    from . import grants, nonprofits

    register_runner("grants_pipeline", grants.run_grants)
    register_runner("nonprofits_pipeline", nonprofits.run_nonprofits)
