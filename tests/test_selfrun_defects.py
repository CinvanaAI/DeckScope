"""Pins for the four defects found by driving the app as its own model.

The first live agent-driven run (Claude answering the manual-provider spool)
hit all four inside twenty minutes: the --provider flag refused at the setup
gate, the provider's designed pause reported as a crash three times, an
18-item "What to do next" wall that duplicated a section above it, and the
report's two most-read lines saying the same sentence twice. None of the
900+ existing tests noticed any of them, because none of them USED the
product — the argument for keeping a live-drive in the release routine.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECK = ROOT / "deckscope" / "examples" / "sample_deck.md"


def _cli(tmp_path, *args, env_extra=None, timeout=180):
    env = {**os.environ, "DECKSCOPE_HOME": str(tmp_path / "home"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("DECKSCOPE_PROVIDER", None)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-m", "deckscope", *args], cwd=str(ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=timeout)


# ------------------------------------------------- A: the flag is configuration

def test_run_with_an_explicit_provider_is_not_sent_to_the_wizard(tmp_path):
    """`deckscope run <deck> --provider mock` on a machine with no config
    answered "DeckScope isn't set up yet" — refusing on the flag what
    is_configured already accepts from the environment. The flag states the
    same fact more explicitly."""
    proc = _cli(tmp_path, "run", str(DECK), "--provider", "mock",
                "--research", "none", "--format", "md",
                "--out", str(tmp_path / "out"))
    assert "isn't set up yet" not in proc.stdout, proc.stdout[-500:]
    assert proc.returncode == 0, proc.stdout[-800:]
    assert (tmp_path / "out").is_dir()


# ------------------------------------ B: a designed pause is not a crash

def test_a_spool_wait_exits_calmly_with_no_crash_report(tmp_path):
    """With --provider manual and an unanswered spool, the run used to write
    a crash file and say 'Run deckscope doctor' — three times in one live
    run, for the exact workflow the provider exists to enable. It is a
    pause: exit 75, resume instructions, no crash artifact."""
    spool = tmp_path / "spool"
    proc = _cli(tmp_path, "run", str(DECK), "--provider", "manual",
                "--research", "none", "--format", "md",
                "--out", str(tmp_path / "out"),
                env_extra={"DECKSCOPE_MANUAL_DIR": str(spool),
                           "DECKSCOPE_MANUAL_INTERACTIVE": "0",
                           "DECKSCOPE_MANUAL_POLL": "0.05",
                           "DECKSCOPE_MANUAL_TIMEOUT": "0.3"})
    assert proc.returncode == 75, (proc.returncode, proc.stdout[-500:])
    assert "Waiting on a spooled answer" in proc.stdout
    assert "resumes here rather than starting over" in proc.stdout
    assert "doctor" not in proc.stdout
    crashes = list((tmp_path / "home").glob("crash-*.log"))
    assert not crashes, "a designed pause must not produce a crash report"
    assert list(spool.glob("asked/*.prompt.txt")), (
        "the prompt must be spooled so the caller can answer and resume")


def test_a_provider_outage_gets_doctor_advice_but_no_crash_file():
    """An unreachable API is the environment's failure, not a DeckScope bug;
    `doctor` is right, a crash report is wrong."""
    from deckscope.providers.base import ProviderError, WaitingForAnswer
    assert issubclass(WaitingForAnswer, ProviderError), (
        "the pause must still be catchable as a ProviderError by callers "
        "that treat all provider trouble alike")


# --------------------------- C: next steps must not rebuild a section above

def _comparison(actions, questions, unverifiable_claims):
    return {
        "actions": actions,
        "questions": questions,
        "claim_audit": [
            {"id": f"C{i}", "claim": c, "assessment": "unverifiable"}
            for i, c in enumerate(unverifiable_claims, 1)],
    }


def test_many_unverified_claims_collapse_into_one_step():
    """A live run produced an 18-item 'What to do next': every unverified
    claim restated as its own step, duplicating 'What could not be checked'
    printed two screens up."""
    from deckscope.findings import collect

    found = collect(_comparison(
        [{"action": "Pull the revenue ledger", "priority": "P0"}],
        ["Which growth rate is real?"],
        [f"Claim number {i}" for i in range(1, 6)]), None)
    verify = [s for s in found.next_steps if "Verify or refute" in s]
    assert len(verify) == 1
    assert "5 claims" in verify[0]
    assert "What could not be checked" in verify[0]


def test_a_single_unverified_claim_keeps_its_own_sentence():
    from deckscope.findings import collect

    found = collect(_comparison([], [], ["The market is $88B"]), None)
    assert any("Verify or refute “The market is $88B”" in s
               for s in found.next_steps)


def test_founder_questions_are_labelled_as_questions():
    """Questions rendered as numbered to-dos indistinguishable from
    diligence actions; the owner is the founder meeting, and the step
    should say so."""
    from deckscope.findings import collect

    found = collect(_comparison(
        [{"action": "Call references", "priority": "P0"}],
        ["The deck shows 18% but the plan implies 10% — which is real?"],
        []), None)
    q = next(s for s in found.next_steps if "18%" in s)
    assert q.startswith("Ask the founder: ")


# ------------------- D: the two most-read lines must not say the same thing

def test_the_no_evidence_note_adds_the_fix_instead_of_repeating_the_headline():
    """With zero sources the headline already leads with 'nothing was
    tested'; the italic line under it repeated the same sentence. It now
    says the one thing the headline does not: how to get evidence."""
    from deckscope.findings import collect

    class _Reg:
        def stats(self):
            return {"total": 0, "cited": 0, "quarantined": 0}

    found = collect(_comparison(
        [], [], ["TAM is $47B"]), _Reg())
    assert "No external evidence was retrieved" in found.headline
    assert "deckscope setup" in found.evidence_state
    assert "checked against anything outside the deck" not in found.evidence_state


def test_the_wizard_offers_every_setup_the_registry_ships():
    """The user asked: 'wasn't it supposed to offer MCP and CLI and local
    models, not just an Anthropic key?' The registry shipped seven backends;
    the wizard menu offered six of them — MCP existed, registered, documented,
    and unreachable through setup. The menu must cover the registry."""
    from deckscope.wizard import PROVIDER_MENU

    offered = {key for key, _, _ in PROVIDER_MENU}
    for expected in ("anthropic", "openai", "gemini", "cli",
                     "openai_compatible", "openrouter", "mcp",
                     "manual", "mock"):
        assert expected in offered, f"wizard menu is missing {expected}"
