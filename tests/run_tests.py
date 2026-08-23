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

MODULES = ["test_security", "test_pipeline", "test_providers", "test_panel"]


def main() -> int:
    passed = failed = 0
    failures = []

    for modname in MODULES:
        mod = __import__(modname)
        tests = [(n, f) for n, f in vars(mod).items()
                 if n.startswith("test_") and callable(f)]
        print(f"\n{modname}  ({len(tests)} tests)")
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
                print(f"  FAIL  {name}")
            else:
                passed += 1
                print(f"  ok    {name}")

    print("\n" + "─" * 60)
    for modname, name, tb in failures:
        print(f"\n{modname}::{name}\n{tb}")
    print(f"{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
