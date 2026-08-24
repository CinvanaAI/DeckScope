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
import unittest
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

# The runner is part of the advertised install check, so it must survive a
# default Windows console just like the CLI does.
from deckscope import console  # noqa: E402
console.enable()

#: Modules whose order matters, run first. Everything else is discovered.
#:
#: This used to be the complete list, hand-maintained — which meant a new test
#: file was not run until someone remembered to add it here, and nothing failed
#: if they forgot. Adding tests that silently never execute is the same class of
#: defect as an evaluator that reports success while checking nothing, so the
#: list is now a hint about ordering rather than the source of truth.
PREFERRED_ORDER = ["test_security", "test_pipeline", "test_providers", "test_panel",
                   "test_audit_regressions", "test_panel_mechanics",
                   "test_opportunity",
                   "test_bundling",
                   "test_audit2_regressions",
                   "test_evidence_design",
                   "test_evaluation"]


def discover() -> list:
    """Every test_*.py beside this runner, preferred ones first."""
    found = sorted(p.stem for p in ROOT.glob("test_*.py"))
    ordered = [m for m in PREFERRED_ORDER if m in found]
    ordered += [m for m in found if m not in PREFERRED_ORDER]
    return ordered


MODULES = discover()


def collect(mod) -> list:
    """Every test in a module, as (name, callable).

    Two styles are supported because the suite grew both. Bare `test_*`
    functions came first; `unittest.TestCase` classes arrived later, and this
    runner silently ignored them — a file of forty-five tests reported "0 tests"
    and the run still said OK. That is the same defect as the hand-maintained
    module list this discovery replaced, so both shapes are collected and a
    module contributing nothing is now an error rather than a quiet zero.
    """
    tests = [(n, f) for n, f in vars(mod).items()
             if n.startswith("test_") and inspect.isfunction(f)]

    for cls_name, cls in vars(mod).items():
        if not (inspect.isclass(cls) and issubclass(cls, unittest.TestCase)
                and cls is not unittest.TestCase):
            continue
        for method in sorted(dir(cls)):
            if not method.startswith("test"):
                continue
            tests.append((f"{cls_name}.{method}", _case_runner(cls, method)))
    return tests


def _case_runner(cls, method):
    """Run one TestCase method with its setUp/tearDown, outside unittest."""
    def run():
        case = cls(method)
        result = unittest.TestResult()
        case.run(result)
        if result.skipped:
            return
        for _case, tb in result.failures + result.errors:
            raise AssertionError(tb)
    return run


def main() -> int:
    passed = failed = 0
    failures = []
    empty = []

    for modname in MODULES:
        mod = __import__(modname)
        tests = collect(mod)
        console.out(f"\n{modname}  ({len(tests)} tests)")
        if not tests:
            empty.append(modname)
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
    if empty:
        failed += len(empty)
        console.out(f"\nThese files matched test_*.py but contributed no tests, "
                    f"which almost always means the runner cannot see them rather "
                    f"than that they are empty: {', '.join(empty)}")
    console.out(f"{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
