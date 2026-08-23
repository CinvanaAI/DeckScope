"""What can this install actually talk to, and does the picker tell the truth?

`deckscope providers` lists the catalogue. That is not the same as what will work
when the user presses go, and presenting one as the other is how a picker sends
somebody confidently into a failure.

These tests pin the distinctions that make the difference: an env var that is set
is not the same as a key that works; a CLI binary on PATH is not the same as a
signed-in session; a cached pass earned by one key must not survive that key
being rotated.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope import availability as av


def _clear(*names):
    for n in names:
        os.environ.pop(n, None)


# ============================================ states mean different things

def test_a_missing_key_is_needs_setup_with_the_variable_named():
    _clear("ANTHROPIC_API_KEY")
    cap = av.inspect("anthropic", "claude-sonnet-5")
    assert cap.state == av.NEEDS_SETUP
    assert "ANTHROPIC_API_KEY" in cap.reasons[0]
    assert cap.fix, "a missing prerequisite must come with what to do about it"
    assert not cap.usable


def test_a_present_key_is_unverified_not_ready():
    """Having a key is not evidence the key works. Rounding that up to 'ready'
    is the whole failure this module exists to prevent."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-not-a-real-key"
    try:
        cap = av.inspect("anthropic", "claude-sonnet-5")
        assert cap.state == av.UNVERIFIED
        assert cap.usable, "unverified is still offerable — it may well work"
        assert not cap.verified_live
    finally:
        _clear("ANTHROPIC_API_KEY")


def test_dependency_free_providers_are_ready_without_a_probe():
    for provider in ("mock", "manual"):
        assert av.inspect(provider, "x").state == av.READY


def test_a_retired_model_is_named_and_redirected():
    cap = av.inspect("openai", "o3-mini")
    assert cap.state == av.RETIRED
    assert not cap.usable
    assert "o4-mini" in cap.fix


# ================================================= cached probes and rotation

def _probe_record(fingerprint, ok=True, error=""):
    import time
    rec = {"ok": ok, "epoch": time.time(), "fingerprint": fingerprint, "at": "now"}
    if error:
        rec["error"] = error
    return rec


def test_a_successful_probe_makes_it_ready_and_marked_live():
    os.environ["OPENAI_API_KEY"] = "sk-a"
    try:
        probes = {"openai:gpt-4o": _probe_record(av.credential_fingerprint("openai"))}
        cap = av.inspect("openai", "gpt-4o", probes)
        assert cap.state == av.READY
        assert cap.verified_live
    finally:
        _clear("OPENAI_API_KEY")


def test_rotating_the_key_invalidates_a_cached_pass():
    """Otherwise a pass earned by an old key vouches for a new one."""
    os.environ["OPENAI_API_KEY"] = "sk-old"
    old = av.credential_fingerprint("openai")
    probes = {"openai:gpt-4o": _probe_record(old)}
    assert av.inspect("openai", "gpt-4o", probes).state == av.READY

    os.environ["OPENAI_API_KEY"] = "sk-new"
    try:
        assert av.inspect("openai", "gpt-4o", probes).state == av.UNVERIFIED
    finally:
        _clear("OPENAI_API_KEY")


def test_an_expired_probe_is_not_trusted():
    os.environ["OPENAI_API_KEY"] = "sk-a"
    try:
        stale = _probe_record(av.credential_fingerprint("openai"))
        stale["epoch"] = 0          # 1970
        assert av.inspect("openai", "gpt-4o", {"openai:gpt-4o": stale}).state \
            == av.UNVERIFIED
    finally:
        _clear("OPENAI_API_KEY")


def test_a_failed_probe_reports_the_reason_rather_than_hiding_it():
    os.environ["OPENAI_API_KEY"] = "sk-a"
    try:
        rec = _probe_record(av.credential_fingerprint("openai"), ok=False,
                            error="401 invalid x-api-key")
        cap = av.inspect("openai", "gpt-4o", {"openai:gpt-4o": rec})
        assert cap.state == av.FAILED
        assert "401" in cap.reasons[0]
        assert not cap.usable
    finally:
        _clear("OPENAI_API_KEY")


def test_the_fingerprint_never_contains_the_key_itself():
    os.environ["OPENAI_API_KEY"] = "sk-super-secret-value"
    try:
        assert "super-secret" not in av.credential_fingerprint("openai")
    finally:
        _clear("OPENAI_API_KEY")


# ============================================ per-connection-type requirements

def test_cli_providers_require_their_own_binary():
    reqs = av._cli_requirements("codex")
    assert any(r.kind == "binary" and r.name == "codex" for r in reqs)


def test_ollama_requires_a_running_daemon_not_just_a_binary():
    """Binary present, daemon down, model not pulled are three different
    failures, and only the first is what `which` answers."""
    reqs = av._cli_requirements("ollama")
    kinds = {r.kind for r in reqs}
    assert "binary" in kinds and "daemon" in kinds


def test_bedrock_needs_more_than_a_key():
    """Model access is granted per-account in the AWS console, so credentials
    alone prove nothing — the fix text has to say so."""
    reqs = av.requirements_for("bedrock")
    assert any(r.kind == "python_package" for r in reqs)
    assert any("per-model" in r.fix or "per-account" in r.fix for r in reqs)


def test_an_optional_requirement_does_not_block():
    reqs = av.requirements_for("openai_compatible")
    assert reqs and reqs[0].optional
    _clear("OPENAI_COMPATIBLE_API_KEY")
    assert av.inspect("openai_compatible", "llama3.1:8b").usable


# ============================================================== the survey

def test_the_survey_covers_every_registered_provider():
    from deckscope.providers.registry import list_providers

    seen = {c.provider for c in av.survey()}
    assert seen >= set(list_providers())


def test_the_survey_sorts_problems_first():
    caps = av.survey()
    order = [av.STATE_ORDER.get(c.state, 9) for c in caps]
    assert order == sorted(order), "whatever needs attention must not be buried"


def test_filtering_to_usable_hides_what_cannot_be_used():
    everything = av.survey(include_unusable=True)
    usable = av.survey(include_unusable=False)
    assert len(usable) <= len(everything)
    assert all(c.usable for c in usable)


# ============================================================== diversity

def test_one_model_is_described_as_not_a_panel():
    d = av.diversity(["anthropic:claude-sonnet-5"])
    assert d["panelists"] == 1
    assert not d["independent"]
    assert "not a panel" in d["note"]


def test_a_single_provider_panel_is_flagged_as_correlated():
    d = av.diversity(["anthropic:a", "anthropic:b", "anthropic:c"])
    assert d["provider_count"] == 1
    assert not d["independent"]
    assert "correlated" in d["note"]


def test_a_multi_provider_panel_reads_as_independent():
    d = av.diversity(["anthropic:a", "openai:b", "gemini:c"])
    assert d["provider_count"] == 3
    assert d["independent"]


def test_diversity_is_advisory_and_never_refuses():
    """Selecting three models from one vendor is a legitimate choice — comparing
    within a family is a real use. Warn, do not block."""
    d = av.diversity(["anthropic:a", "anthropic:b"])
    assert "note" in d and d["note"]
    assert "refus" not in d["note"].lower()
    assert "cannot" not in d["note"].lower()


# ================================================================ the CLI

def test_models_command_exists_with_the_flags_that_matter():
    from deckscope.cli import build_parser

    args = build_parser().parse_args(["models", "--check"])
    assert args.check
    args = build_parser().parse_args(["models", "--select", "a:b", "c:d"])
    assert args.select == ["a:b", "c:d"]
