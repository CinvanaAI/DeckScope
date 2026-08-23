"""Zero-dependency test runner.

`pytest tests/` is the normal way to run these. This runner exists so the suite
also works on a machine with nothing installed but Python — which is exactly the
machine a first-time user has.

    python tests/run_tests.py
"""
from __future__ import annotations

import inspect
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

# The runner is part of the advertised install check, so it must survive a
# default Windows console just like the CLI does.
from deckscope import console  # noqa: E402
console.enable()

MODULES = ["test_security", "test_pipeline", "test_providers", "test_panel",
           "test_audit_regressions", "test_panel_mechanics",
           "test_opportunity",
           "test_bundling",
           "test_audit2_regressions",
           "test_evidence_design",
           "test_evaluation"]


def main() -> int:
    passed = failed = 0
    failures = []

    for modname in MODULES:
        mod = __import__(modname)
        tests = [(n, f) for n, f in vars(mod).items()
                 if n.startswith("test_") and callable(f)]
        console.out(f"\n{modname}  ({len(tests)} tests)")
        for name, fn in tests:
            try:
                if "tmp_path" in inspect.signature(fn).parameters:
                    with tempfile.TemporaryDirectory() as td:
                        fn(Path(td))
                else:
                    fn()
            except Exception:  # noqa: BLE001
                failed += 1
                failures.append((modname, name, traceback.format_exc()))
                console.out(f"  FAIL  {name}")
            else:
                passed += 1
                console.out(f"  ok    {name}")

    console.out("\n" + "-" * 60)
    for modname, name, tb in failures:
        console.out(f"\n{modname}::{name}\n{tb}")
    console.out(f"{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
