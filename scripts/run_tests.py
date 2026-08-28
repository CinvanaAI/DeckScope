#!/usr/bin/env python3
"""Run the whole test suite with no dependencies — not even pytest.

Two reasons this exists, both learned the hard way on the same day.

**The environment that most needs the tests may not have pytest.** This
repository's own development sandbox cannot reach PyPI, so for a full working
day every change to eleven core modules shipped with exactly one of
thirty-five test files ever executing. "The suite is green" meant "the one
file I could run is green."

**The one runnable file was skipping most of itself.** Its `if __name__`
runner sat mid-file, and tests appended after it — thirty-one of forty-seven —
never executed, while the runner printed `0 failed`. A gate that runs part of
itself and reports a verdict on all of itself is the exact defect shape that
file exists to pin: two situations the system cannot tell apart, the worse one
rendered as the better. This runner collects from the module *after* importing
it completely, so a test's position in the file cannot silently exempt it.

What it supports is exactly what the suite uses, measured rather than assumed:
`tmp_path` and `monkeypatch` arguments, `pytest.raises`, and plain `assert`
functions. Zero fixtures, zero parametrize, zero marks are defined in
`tests/` — if someone adds one, the shim fails loudly with the feature's name
rather than pretending. When real pytest IS importable, none of the shims
engage and this is just a collector.
"""
from __future__ import annotations

import contextlib
import importlib.util
import inspect
import os
import sys
import tempfile
import traceback
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Sentinel for "no previous value", defined ABOVE the classes that use it as
#: a default argument — defaults are evaluated at class-definition time, and
#: the first cut had this at the bottom of the file. scripts/lint.py did not
#: catch that NameError because its scope check is deliberately position-blind
#: (a name bound anywhere in a scope counts as bound everywhere), which is the
#: documented price of never crying wolf. This is the price being paid.
_MISSING = object()


class _Raises:
    """`pytest.raises` — the one context manager the suite uses."""

    def __init__(self, expected, match=None):
        self.expected = expected
        self.match = match
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(
                f"expected {self.expected.__name__} and nothing was raised")
        if not issubclass(exc_type, self.expected):
            return False        # wrong exception: let it propagate
        self.value = exc
        if self.match is not None:
            import re
            if not re.search(self.match, str(exc)):
                raise AssertionError(
                    f"exception text {str(exc)!r} does not match "
                    f"{self.match!r}")
        return True


class _MonkeyPatch:
    """The subset of pytest's monkeypatch the suite uses, undone after."""

    def __init__(self):
        self._undo = []

    def setattr(self, target, name, value=_MISSING):
        # Both pytest forms: setattr(obj, "attr", value) and the string form
        # setattr("pkg.mod.attr", value). The first cut of this raised on the
        # string form with logic that never worked — and the suite's only
        # monkeypatch user calls exactly that form, so the shim's first full
        # run errored on all eight of its tests. A shim gap is fine; broken
        # shim code pretending to be a gap is not.
        if isinstance(target, str):
            import importlib
            module_path, _, attr = target.rpartition(".")
            value = name
            target = importlib.import_module(module_path)
            name = attr
        if value is _MISSING:
            raise TypeError("monkeypatch.setattr needs a value")
        old = getattr(target, name, _MISSING)
        self._undo.append((target, name, old))
        setattr(target, name, value)

    def setenv(self, name, value):
        old = os.environ.get(name, _MISSING)
        self._undo.append((os.environ, name, old))
        os.environ[name] = str(value)

    def delenv(self, name, raising=True):
        old = os.environ.get(name, _MISSING)
        if old is _MISSING and raising:
            raise KeyError(name)
        self._undo.append((os.environ, name, old))
        os.environ.pop(name, None)

    def setitem(self, mapping, key, value):
        old = mapping.get(key, _MISSING)
        self._undo.append((mapping, key, old))
        mapping[key] = value

    def undo(self):
        while self._undo:
            target, name, old = self._undo.pop()
            if isinstance(target, (dict, os._Environ)):
                if old is _MISSING:
                    target.pop(name, None)
                else:
                    target[name] = old
            elif old is _MISSING:
                with contextlib.suppress(AttributeError):
                    delattr(target, name)
            else:
                setattr(target, name, old)


class _ShimGap(RuntimeError):
    """A pytest feature the shim does not cover, named rather than faked."""


def _fake_pytest() -> types.ModuleType:
    module = types.ModuleType("pytest")
    module.raises = _Raises

    def _unsupported(feature):
        def _raise(*_a, **_k):
            raise _ShimGap(
                f"pytest.{feature} is used but real pytest is not installed "
                f"and the shim does not cover it. Either avoid it in tests/ "
                f"(nothing else there uses it) or extend scripts/run_tests.py "
                f"deliberately.")
        return _raise

    module.fixture = _unsupported("fixture")
    module.skip = _unsupported("skip")
    module.approx = _unsupported("approx")

    class _Mark:
        def __getattr__(self, name):
            return _unsupported(f"mark.{name}")()

    module.mark = _Mark()
    module.main = lambda *a, **k: 0
    return module


def _load(path: Path) -> types.ModuleType:
    name = f"_suite_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so intra-file imports resolve, and removed on
    # failure so a broken module does not poison a retry.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _call(test) -> None:
    """Invoke one test, supplying the two arguments the suite uses."""
    kwargs = {}
    patch = None
    for parameter in inspect.signature(test).parameters.values():
        if parameter.name == "tmp_path":
            kwargs["tmp_path"] = Path(tempfile.mkdtemp(prefix="dstest_"))
        elif parameter.name == "monkeypatch":
            patch = _MonkeyPatch()
            kwargs["monkeypatch"] = patch
        elif parameter.default is inspect.Parameter.empty:
            raise _ShimGap(
                f"test wants a {parameter.name!r} fixture the shim does not "
                f"provide")
    try:
        test(**kwargs)
    finally:
        if patch is not None:
            patch.undo()


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    only = ""
    if "--only" in args:
        only = args[args.index("--only") + 1]

    sys.path.insert(0, str(ROOT))
    have_pytest = importlib.util.find_spec("pytest") is not None
    if not have_pytest:
        sys.modules["pytest"] = _fake_pytest()

    files = sorted((ROOT / "tests").glob("test_*.py"))
    if only:
        files = [f for f in files if only.lower() in f.name.lower()]

    ran = failed = errored = 0
    broken_files = []
    for path in files:
        try:
            module = _load(path)
        except BaseException as exc:  # noqa: BLE001 - a file that will not
            errored += 1              # import is a result, not a stop
            broken_files.append((path.name, exc))
            print(f"IMPORT ERROR  {path.name}: {type(exc).__name__}: "
                  f"{str(exc)[:140]}")
            continue

        # Collected from the module AFTER it is fully imported, in definition
        # order. Position in the file cannot exempt a test — see the module
        # docstring for the day that rule was earned.
        tests = [(name, obj) for name, obj in vars(module).items()
                 if name.startswith("test_") and callable(obj)]
        for name, test in tests:
            ran += 1
            try:
                _call(test)
            except AssertionError as exc:
                failed += 1
                print(f"FAIL   {path.name}::{name}")
                line = str(exc).strip().splitlines()
                if line:
                    print(f"       {line[0][:160]}")
            except BaseException as exc:  # noqa: BLE001
                errored += 1
                print(f"ERROR  {path.name}::{name}: "
                      f"{type(exc).__name__}: {str(exc)[:140]}")
                tail = traceback.format_exc().strip().splitlines()
                for frame in tail[-3:-1]:
                    print(f"       {frame.strip()[:160]}")

    print(f"\n{ran} ran, {failed} failed, {errored} errored, "
          f"{len(files)} file(s)"
          + ("" if have_pytest else "  [pytest shim]"))
    return 0 if failed == 0 and errored == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
