"""The engineer pass: the crash shield, the flight recorder, the receipt.

The client's question, verbatim: "As a software developer and engineer, what do I
think about this program's design, architecture, safety…? Does it do logs
and runtime tracking?" These pin the answers that pass added:

- An unhandled exception anywhere under `main()` becomes one calm sentence,
  a crash file with the full story, and exit 70 — never a 40-line traceback
  at a guest. DECKSCOPE_RAW_ERRORS restores the traceback for debugging.
- Every pipeline run appends its narration to `run.log` beside the outputs,
  because the console scrolls away and the app keeps 400 lines in memory:
  when a run surprises somebody an hour later, the log is the answer.
- The terminal summary states what the run cost — seconds, model, tokens.
  The numbers were always in `result.stats`; the person paying for the API
  calls simply never saw them.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _crash_env(tmp_home: str, raw: str = "") -> dict:
    env = dict(os.environ)
    env.update({"DECKSCOPE_HOME": tmp_home, "PYTHONPATH": str(REPO),
                "PYTHONDONTWRITEBYTECODE": "1"})
    env.pop("DECKSCOPE_RAW_ERRORS", None)
    if raw:
        env["DECKSCOPE_RAW_ERRORS"] = raw
    return env


_BOOM = """
import sys, deckscope.cli as cli
def boom(argv=None): raise KeyError('simulated bug')
cli._main = boom
sys.exit(cli.main([]))
"""


def test_unhandled_bug_becomes_calm_line_plus_crash_file():
    home = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, "-c", _BOOM], capture_output=True,
                       text=True, env=_crash_env(home), cwd=str(REPO))
    assert r.returncode == 70, "EX_SOFTWARE distinguishes 'the tool broke'"
    assert "Traceback" not in r.stdout, "no stack at the guest"
    assert "did not expect" in r.stdout
    crashes = list(Path(home).glob("crash-*.log"))
    assert len(crashes) == 1, "exactly one crash file"
    body = crashes[0].read_text(encoding="utf-8")
    for needed in ("Traceback", "KeyError", "version:", "python:"):
        assert needed in body, f"crash file must carry {needed!r}"


def test_raw_errors_escape_hatch_reraises():
    home = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, "-c", _BOOM], capture_output=True,
                       text=True, env=_crash_env(home, raw="1"), cwd=str(REPO))
    assert r.returncode != 70
    assert "Traceback" in r.stderr, "the debugger asked for the real thing"
    assert not list(Path(home).glob("crash-*.log"))


def test_normal_exits_pass_through_the_shield():
    """argparse's SystemExit and the commands' own exit codes must be
    untouched — the shield is for bugs, not for outcomes."""
    from deckscope.cli import main

    assert main(["providers"]) == 0


def test_run_log_is_written_beside_the_outputs(tmp_path, monkeypatch):
    from deckscope import settings
    from deckscope.orchestrator import Pipeline

    monkeypatch.setenv("DECKSCOPE_PROVIDER", "mock")
    monkeypatch.setenv("DECKSCOPE_RESEARCH", "none")
    cfg = settings.settings_to_runconfig({
        "provider": {"name": "mock"}, "research": {"name": "none"},
        "deck_path": "unused", "output": {"out_dir": str(tmp_path)}})
    pipe = Pipeline(cfg)
    try:
        pipe._log("first breadcrumb")
        pipe._log("second breadcrumb")
    finally:
        pipe.close()
    log = tmp_path / "run.log"
    assert log.exists(), "the flight recorder must land beside the outputs"
    body = log.read_text(encoding="utf-8")
    assert "first breadcrumb" in body and "second breadcrumb" in body
    assert "=== deckscope run" in body, "each run opens a dated section"
    assert "mock" in body, "the header names the model that ran"


def test_logging_failure_never_sinks_the_analysis(tmp_path, monkeypatch):
    """A full disk costs the flight recorder, not the flight."""
    from deckscope import settings
    from deckscope.orchestrator import Pipeline

    cfg = settings.settings_to_runconfig({
        "provider": {"name": "mock"}, "research": {"name": "none"},
        "deck_path": "unused",
        "output": {"out_dir": str(tmp_path / "made" / "here")}})
    pipe = Pipeline(cfg)
    try:
        pipe._log("opens the log")

        class _Dead:
            def write(self, *_):
                raise OSError("disk full")

            def flush(self):
                raise OSError("disk full")

            def close(self):
                pass

        pipe._run_log = _Dead()
        pipe._log("must not raise")          # first failure switches it off
        assert pipe._run_log is False
        pipe._log("and stays off quietly")   # no reopen loop on every event
        assert pipe._run_log is False
    finally:
        pipe.close()


def test_terminal_summary_states_the_cost(monkeypatch):
    """elapsed · provider/model · tokens — on the receipt the user reads."""
    from deckscope import cli

    lines = []
    monkeypatch.setattr("deckscope.cli._out",
                        lambda *a, **k: lines.append(" ".join(str(x) for x in a)))

    class _R:
        company = "TestCo"
        comparisons = {}
        registry = None
        security = {}
        stats = {"elapsed_seconds": 42.5, "provider": "anthropic",
                 "model": "claude-x", "token_usage": {"input": 1200,
                                                      "output": 300}}

    cli._print_summary(_R(), [])
    shown = "\n".join(lines)
    assert "42.5s" in shown
    assert "anthropic/claude-x" in shown
    assert "1200 tokens in / 300 out" in shown


if __name__ == "__main__":  # pragma: no cover
    import runpy

    sys.argv = [sys.argv[0], "--only", Path(__file__).stem]
    runpy.run_path(str(REPO / "scripts" / "run_tests.py"), run_name="__main__")
