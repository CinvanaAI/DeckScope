"""Delegator to the canonical zero-dependency runner.

Two runners coexisted here: this one (which collected class-based tests but
could not supply monkeypatch) and scripts/run_tests.py (which supplied every
fixture but collected only module-level functions — 505 of 924 tests, while
printing a confident green total). CI ran this one; the developer ran the
other; each was green about a different subset, and an external audit had to
point out that neither was green about the suite. One canonical runner now
lives in scripts/run_tests.py; this path survives because CI and the install
docs point here.
"""
import runpy
import sys
from pathlib import Path

sys.exit(runpy.run_path(
    str(Path(__file__).resolve().parent.parent / "scripts" / "run_tests.py"),
    run_name="__main__"))
