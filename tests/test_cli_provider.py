"""What the CLI provider does when the CLI fails.

These exist because of a defect found by running the real thing. `claude -p`
with no login exits 1, writes "Not logged in - Please run /login" to **stdout**,
and leaves stderr empty. The provider reported stderr only, so the user got
"`claude` exited 1:" — the exit code preserved and the entire diagnosis thrown
away, on the first command anyone would run after connecting a CLI.

The empty-stdout case is the more dangerous one and is the reason it raises
rather than returning. An empty completion flows into the reader, parses to
nothing, yields no findings, and the section reports "nothing could be
established" — which reads as a fact about the market rather than an outage in
the model connection. That is the failure shape this repo keeps producing, so
it gets a test rather than a comment.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.config import ProviderConfig
from deckscope.providers.base import Message, ProviderError
from deckscope.providers.cli_provider import CLIProvider


def _provider(monkeypatch, *, stdout="", stderr="", returncode=0):
    """A CLIProvider whose subprocess is a fixed transcript."""
    monkeypatch.setattr("shutil.which", lambda _exe: "/usr/local/bin/claude")
    provider = CLIProvider(ProviderConfig(name="cli", model="claude"))

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return provider


def _ask(provider):
    return provider.complete("sys", [Message(role="user", content="hi")])


def test_diagnosis_on_stdout_is_not_discarded(monkeypatch):
    """The exact transcript of Claude Code 2.1.246 with no login."""
    provider = _provider(monkeypatch, returncode=1, stderr="",
                         stdout="Not logged in · Please run /login")
    with pytest.raises(ProviderError) as caught:
        _ask(provider)
    assert "Not logged in" in str(caught.value)


def test_not_logged_in_says_how_to_fix_it(monkeypatch):
    provider = _provider(monkeypatch, returncode=1,
                         stdout="Not logged in · Please run /login")
    with pytest.raises(ProviderError) as caught:
        _ask(provider)
    message = str(caught.value)
    # The point of the hint: the credential is the CLI's, never DeckScope's.
    assert "DeckScope never sees the credential" in message
    assert "sign in" in message.lower()


def test_stderr_still_wins_when_there_is_some(monkeypatch):
    provider = _provider(monkeypatch, returncode=2, stdout="partial output",
                         stderr="fatal: bad flag")
    with pytest.raises(ProviderError) as caught:
        _ask(provider)
    assert "fatal: bad flag" in str(caught.value)


def test_silent_failure_says_it_was_silent(monkeypatch):
    """An exit code with no words is still better than pretending to explain."""
    provider = _provider(monkeypatch, returncode=137, stdout="", stderr="")
    with pytest.raises(ProviderError) as caught:
        _ask(provider)
    message = str(caught.value)
    assert "137" in message
    assert "said nothing about why" in message


def test_usage_limit_is_named_as_a_limit(monkeypatch):
    provider = _provider(
        monkeypatch, returncode=1,
        stdout="Claude usage limit reached. Resets at 5pm.")
    with pytest.raises(ProviderError) as caught:
        _ask(provider)
    assert "subscription limit" in str(caught.value)


def test_empty_success_raises_instead_of_answering_nothing(monkeypatch):
    """Exit 0 and no output is an outage, not an empty market."""
    provider = _provider(monkeypatch, returncode=0, stdout="   \n")
    with pytest.raises(ProviderError) as caught:
        _ask(provider)
    assert "printed nothing" in str(caught.value)


def test_empty_success_surfaces_whatever_stderr_held(monkeypatch):
    provider = _provider(monkeypatch, returncode=0, stdout="",
                         stderr="warning: model overloaded, giving up")
    with pytest.raises(ProviderError) as caught:
        _ask(provider)
    assert "model overloaded" in str(caught.value)


def test_a_real_answer_still_comes_back(monkeypatch):
    provider = _provider(monkeypatch, returncode=0, stdout='{"ok": true}')
    result = _ask(provider)
    assert result.text == '{"ok": true}'
    assert result.model.startswith("cli:")
