"""The bring-your-own-model provider, and the spool mode that made a real
evaluation possible without an API key.

Two things drove this. The copy-paste provider was unusable for anything longer
than a couple of steps, because closing the terminal threw away every answer
already given and a re-run started from step one. And every number DeckScope had
ever reported about its own architecture came from the mock — a fixture — because
answering "is the three-agent pipeline better than one prompt?" appeared to
require an API key and money.

Content-addressed answers fix both. A prompt is identified by the hash of its own
text, so re-running replays what has been answered and stops at the first new
question, and anything that can watch a directory can drive the whole pipeline.
"""
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.config import ProviderConfig
from deckscope.providers.base import Message, ProviderError
from deckscope.providers.manual_provider import ManualProvider


def _provider(tmp_path, **extra):
    cfg = ProviderConfig(name="manual", extra={
        "exchange_dir": str(tmp_path), "interactive": False,
        "poll_seconds": 0.02, "timeout_seconds": 2, **extra})
    return ManualProvider(cfg)


def _answer(tmp_path, text="{}"):
    """Answer whichever prompt is currently waiting."""
    asked = tmp_path / "asked"
    for _ in range(400):
        pending = [p for p in asked.glob("*.prompt.txt")
                   if not (tmp_path / "answers" / f"{p.name[:-11]}.txt").exists()]
        if pending:
            key = pending[0].name[: -len(".prompt.txt")]
            (tmp_path / "answers" / f"{key}.txt").write_text(text, encoding="utf-8")
            return key
        time.sleep(0.01)
    raise AssertionError("no prompt was ever written to the spool")


# ======================================= a prompt nobody answers must be an error

def test_an_unanswered_prompt_raises_rather_than_returning_empty_text(tmp_path):
    """Returning "" fed the JSON repair loop, which retried twice more and then
    reported a parse failure — an error message about the wrong problem, three
    calls after the actual one."""
    p = _provider(tmp_path)
    try:
        p.complete("sys", [Message("user", "hello")])
    except ProviderError as exc:
        assert "No answer appeared" in str(exc)
        assert "resumes here" in str(exc), "the error must say the work is not lost"
    else:  # pragma: no cover - the failure we are guarding against
        raise AssertionError("an unanswered prompt returned a completion")


def test_the_prompt_is_written_where_the_error_says_it_is(tmp_path):
    p = _provider(tmp_path)
    try:
        p.complete("sys", [Message("user", "hello")])
    except ProviderError:
        pass
    written = list((tmp_path / "asked").glob("*.prompt.txt"))
    assert len(written) == 1
    text = written[0].read_text(encoding="utf-8")
    assert "sys" in text and "hello" in text


# ================================================ answers survive across runs

def test_an_answered_prompt_is_replayed_instead_of_asked_again(tmp_path):
    """The whole point: a copy-paste run of the pipeline is a dozen exchanges,
    and before this every one of them was lost when the process ended."""
    first = _provider(tmp_path)
    t = threading.Thread(target=_answer, args=(tmp_path, '{"a": 1}'))
    t.start()
    out = first.complete("sys", [Message("user", "q1")])
    t.join()
    assert out.text == '{"a": 1}'
    assert out.raw == {"cached": False}

    # A completely new provider — as a re-run of the command would create.
    second = _provider(tmp_path)
    again = second.complete("sys", [Message("user", "q1")])
    assert again.text == '{"a": 1}', "the answer was not replayed"
    assert again.raw == {"cached": True}
    assert second.replayed == 1


def test_the_same_question_at_a_different_step_is_not_asked_again(tmp_path):
    """A panel asks several panelists the same question. Numbering by step would
    put it to the operator once per panelist; hashing the text asks once."""
    p = _provider(tmp_path)
    t = threading.Thread(target=_answer, args=(tmp_path, "reused"))
    t.start()
    p.complete("sys", [Message("user", "same question")])
    t.join()

    out = p.complete("sys", [Message("user", "same question")])
    assert out.text == "reused" and out.raw == {"cached": True}
    assert p.step == 2, "it was a second call, served from the cache"


def test_a_different_prompt_is_a_different_question(tmp_path):
    p = _provider(tmp_path)
    t = threading.Thread(target=_answer, args=(tmp_path, "first"))
    t.start()
    p.complete("sys", [Message("user", "q1")])
    t.join()
    try:
        p.complete("sys", [Message("user", "q2")])
    except ProviderError:
        pass
    else:  # pragma: no cover
        raise AssertionError("an unrelated prompt was answered from the cache")


def test_two_runs_sharing_a_spool_do_not_read_each_other_s_answers(tmp_path):
    """Parallel runs against one spool is how a whole suite gets answered at
    once. Step-numbered filenames would have crossed the answers over."""
    a = _provider(tmp_path, run_tag="alpha")
    b = _provider(tmp_path, run_tag="beta")
    t = threading.Thread(target=_answer, args=(tmp_path, "for-alpha"))
    t.start()
    a.complete("sys", [Message("user", "alpha question")])
    t.join()

    try:
        b.complete("sys", [Message("user", "beta question")])
    except ProviderError:
        pass
    else:  # pragma: no cover
        raise AssertionError("beta's first call was served alpha's answer")


# ============================================== configuration and accounting

def test_the_environment_configures_it_because_eval_cannot_pass_extra(tmp_path):
    """`deckscope eval` builds its own ProviderConfig, so without this an agent
    driving the suite would have no way to point it at a spool."""
    keys = ("DECKSCOPE_MANUAL_DIR", "DECKSCOPE_MANUAL_INTERACTIVE",
            "DECKSCOPE_MANUAL_TIMEOUT", "DECKSCOPE_MANUAL_TAG")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ.update({"DECKSCOPE_MANUAL_DIR": str(tmp_path / "spool"),
                       "DECKSCOPE_MANUAL_INTERACTIVE": "0",
                       "DECKSCOPE_MANUAL_TIMEOUT": "7",
                       "DECKSCOPE_MANUAL_TAG": "from-env"})
    try:
        p = ManualProvider(ProviderConfig(name="manual"))
        assert p.dir == tmp_path / "spool"
        assert p.interactive is False
        assert p.timeout == 7
        assert p.run_tag == "from-env"
        assert (tmp_path / "spool" / "answers").is_dir()
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_token_usage_is_reported_and_labelled_as_an_estimate(tmp_path):
    """Reporting nothing made every manual run cost zero, which flatters the
    expensive modes. Reporting a guess without saying so would be worse."""
    p = _provider(tmp_path)
    t = threading.Thread(target=_answer, args=(tmp_path, "x" * 400))
    t.start()
    out = p.complete("sys", [Message("user", "y" * 800)])
    t.join()
    assert out.usage["input"] > 0 and out.usage["output"] > 0
    assert out.usage["estimated"] is True, (
        "a character-based count must not be passed off as a token count")


def test_a_partially_written_answer_is_not_read(tmp_path):
    """A file exists from its first byte. Reading it half-written looks exactly
    like a model emitting broken JSON, and sends whoever debugs it after the
    wrong problem. The guard is a settle window, and it is deliberately tied to
    a wall-clock floor: an earlier version waited one poll tick, so a fast poll
    shrank the protection to nothing and this test caught it."""
    p = _provider(tmp_path, timeout_seconds=5)

    def writer():
        asked = tmp_path / "asked"
        key = None
        while key is None:
            found = list(asked.glob("*.prompt.txt"))
            key = found[0].name[: -len(".prompt.txt")] if found else None
            time.sleep(0.01)
        target = tmp_path / "answers" / f"{key}.txt"
        target.write_text('{"partial": ', encoding="utf-8")
        time.sleep(ManualProvider.SETTLE_SECONDS / 2)
        target.write_text('{"partial": false}', encoding="utf-8")

    t = threading.Thread(target=writer)
    t.start()
    text = p.complete("sys", [Message("user", "q")]).text
    t.join()
    assert text == '{"partial": false}'


def test_the_settle_window_does_not_collapse_when_polling_is_fast(tmp_path):
    """The specific defect: the window was `min(poll, 1.0)`, so a 20ms poll gave
    a 20ms guard. It must not depend on how often we look."""
    p = _provider(tmp_path, poll_seconds=0.001)
    assert p.SETTLE_SECONDS >= 0.25
    assert p.poll < p.SETTLE_SECONDS


def test_spool_mode_reports_healthy_without_a_person_present(tmp_path):
    p = _provider(tmp_path)
    health = p.health_check()
    assert health["ok"] is True
    assert str(tmp_path) in health["reply"]
