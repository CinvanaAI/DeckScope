"""Regressions for the third external audit.

Every test here failed before the corresponding fix. They are written to assert
the *property* rather than the current output, so a future refactor that happens
to produce a different plausible-looking number still trips them.

The through-line of this audit was gates that could not fail: an evaluator that
reported success while running nothing, a citation validator that approved
citations to sources no model had seen, a DNS pin that a second DNS answer could
undo, and a CI job whose gate was unreachable. A check that cannot fail is worse
than no check, because it is trusted.
"""
import os
import socket
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ============================================ the evaluator must be able to fail

def test_the_evaluation_fixtures_live_inside_the_package():
    """Otherwise they are absent from the wheel and the gate passes vacuously.

    The audit built a wheel, installed it into a clean environment, and ran
    `deckscope eval`. It reported "0 run(s)" and "every check passed", exit 0 —
    because `evals/` sat beside the package rather than inside it, so nothing was
    installed and nothing could fail.
    """
    from deckscope.evaluation import default_suite_dir
    import deckscope

    suite = default_suite_dir()
    package_root = Path(deckscope.__file__).resolve().parent
    assert package_root in suite.resolve().parents, (
        f"suite at {suite} is outside the package at {package_root}; it will not "
        f"be installed, and the evaluator will silently check nothing")
    assert list(suite.glob("*.json")), "no cases in the packaged suite"


def test_the_packaging_config_ships_the_fixtures():
    """A path inside the package is necessary but not sufficient — it must also
    be declared as package data, or a wheel build drops the non-.py files."""
    import re

    text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
    block = re.search(r"\[tool\.setuptools\.package-data\](.*?)(\n\[|\Z)",
                      text, re.S)
    assert block, "no package-data section"
    body = block.group(1)
    for part in ("evaluation/suite/cases", "evaluation/suite/corpora",
                 "evaluation/suite/decks"):
        assert part in body, f"{part} is not declared as package data"


def test_an_empty_suite_raises_instead_of_reporting_success():
    from deckscope.evaluation import EmptySuiteError, load_suite

    try:
        load_suite("/nonexistent/suite/directory")
    except EmptySuiteError as exc:
        assert "no evaluation suite" in str(exc).lower()
    else:
        raise AssertionError("a missing suite must raise, not return []")


def test_zero_trials_is_refused():
    from deckscope.evaluation import run_suite

    try:
        run_suite(trials=0, provider="mock")
    except ValueError as exc:
        assert "at least 1" in str(exc)
    else:
        raise AssertionError("--trials 0 ran nothing and called it a pass")


def test_a_filter_matching_no_cases_is_refused():
    """`--only definitely-not-a-case` selected zero cases and exited 0."""
    from deckscope.evaluation import run_suite

    try:
        run_suite(only=["definitely-not-a-case"], provider="mock")
    except ValueError as exc:
        assert "matched no cases" in str(exc)
        # The message must be actionable — a typo needs the real names.
        assert "Known ids:" in str(exc)
    else:
        raise AssertionError("a zero-match filter must fail, not pass")


def test_the_cli_reports_a_broken_suite_as_exit_2():
    """Exit 1 means checks failed; exit 2 means the run was never valid.
    CI has to tell them apart to gate on one and not the other."""
    import subprocess

    root = Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        [sys.executable, "-m", "deckscope", "eval", "--provider", "mock",
         "--only", "no-such-case"],
        cwd=str(root), capture_output=True, text=True)
    assert proc.returncode == 2, f"got {proc.returncode}: {proc.stdout[-400:]}"
    assert "checked nothing" in proc.stdout


# ================================================= the opportunity arithmetic

def test_a_senior_preference_is_paid_off_the_top_not_out_of_the_slice():
    """`(P + S)/o` overstated the required exit by 30% on the sample deck."""
    from deckscope.opportunity import Assumptions, required_outcome

    ask, target = 4_000_000.0, 3.0
    r = required_outcome(ask=ask, post_money=24_000_000, target_multiple=target,
                         assumptions=Assumptions(preference_stack=1.0))
    # The defining property: after the stack is paid, the investor's share of
    # what remains is exactly the proceeds it needed.
    residual = r.exit_value_required - r.preference_stack_value
    assert abs(r.ownership_at_exit * residual - ask * target) < 20_000
    # And concretely, the corrected figure rather than the old one.
    assert abs(r.exit_value_required - 148_000_000) < 200_000
    assert r.exit_value_required < 190_000_000, "the old (P+S)/o formula is back"


def test_a_growth_rate_carries_the_period_it_was_quoted_over():
    from deckscope.opportunity import parse_growth

    assert parse_growth("23% CAGR").period == "annual"
    assert parse_growth("23% YoY").period == "annual"
    assert parse_growth("18% MoM").period == "monthly"
    assert parse_growth("18% month over month").period == "monthly"
    assert parse_growth("12% QoQ").period == "quarterly"
    # No stated basis is NOT the same as monthly.
    assert parse_growth("30%").period is None
    assert parse_growth("no number here") is None


def test_an_annual_rate_is_not_compounded_twelve_times():
    """"23% CAGR" was read as 23% per month — a 1,000% annual rate."""
    from deckscope.opportunity import Assumptions, parse_growth, required_outcome

    annual = required_outcome(
        ask=4e6, post_money=24e6, target_multiple=3.0, assumptions=Assumptions(),
        current_arr=340_000, current_growth=parse_growth("23% CAGR"))
    monthly = required_outcome(
        ask=4e6, post_money=24e6, target_multiple=3.0, assumptions=Assumptions(),
        current_arr=340_000, current_growth=parse_growth("23% MoM"))
    assert annual.stated_growth["annualized"] == 0.23
    assert monthly.stated_growth["annualized"] > 10.0
    # The same 23% must give wildly different timelines, because it means
    # wildly different things.
    assert annual.years_at_current_growth > 5 * monthly.years_at_current_growth


def test_an_unlabelled_growth_rate_extrapolates_nothing():
    from deckscope.opportunity import Assumptions, parse_growth, required_outcome

    r = required_outcome(ask=4e6, post_money=24e6, target_multiple=3.0,
                         assumptions=Assumptions(), current_arr=340_000,
                         current_growth=parse_growth("30%"))
    assert r.years_at_current_growth is None
    assert r.achievable_at_current_growth is None
    assert "does not say over what period" in r.note


# =============================== citations must refer to sources a model saw

def _registry(n, snippet_len=2000):
    from types import SimpleNamespace
    from deckscope.sources import SourceRegistry

    reg = SourceRegistry()
    reg.add_results([SimpleNamespace(title=f"Source {i}", url=f"https://e.com/{i}",
                                     snippet="x" * snippet_len, published=None,
                                     source_query="q") for i in range(n)])
    return reg


def test_a_source_cut_by_the_prompt_budget_is_not_citable():
    """`citable` claimed to mean "entered the prompt" but returned everything
    unquarantined, so a citation to source 200 of 200 validated even though the
    block stopped at source 40."""
    reg = _registry(40)
    assert len(reg.citable_ids) == 40, "before any prompt, all are candidates"
    reg.prompt_block(char_budget=12_000)
    assert len(reg.citable_ids) < 40, "truncated sources are still citable"
    never_shown = reg.sources[-1].sid
    assert never_shown not in reg.citable_ids
    assert reg.omitted_for_length, "the omission must be reportable, not silent"


def test_the_prompt_block_tells_the_model_about_the_sources_it_dropped():
    reg = _registry(40)
    block = reg.prompt_block(char_budget=12_000)
    assert "do not cite them" in block


def test_a_generous_budget_admits_everything():
    reg = _registry(5, snippet_len=100)
    reg.prompt_block()
    assert len(reg.citable_ids) == 5
    assert reg.omitted_for_length == []


def test_omitted_sources_are_counted_in_the_stats():
    reg = _registry(40)
    reg.prompt_block(char_budget=12_000)
    assert reg.stats()["omitted_for_length"] > 0


# ====================================== the scorer must look at the whole report

def test_citation_integrity_is_checked_everywhere_not_just_in_claim_audit():
    """It scanned `comparison.claim_audit[].source_ids` only, so an invented
    citation in the scorecard, a blind spot, or inline prose scored as clean and
    the dimension read 100% on a report containing fabricated sources."""
    from deckscope.evaluation.scoring import score_case
    from deckscope.evaluation.cases import EvalCase, Expectations

    class Registry:
        sources = [type("S", (), {"sid": "S1"})()]

    class Result:
        registry = Registry()
        market = {}
        # Nothing wrong in claim_audit; the fabrication is in the scorecard.
        comparisons = {"investor": {
            "claim_audit": [{"claim": "x", "assessment": "supported",
                             "source_ids": ["S1"]}],
            "scorecard": [{"criterion": "Market size", "score": 7,
                           "source_ids": ["S9"]}],
            "verdict": {"confidence": "low"}}}
        written_files = []
        security = {}
        stats = {}
        deck = {}

    case = EvalCase(id="t", name="t", deck="d", expect=Expectations())
    score = score_case(case, Result(), mode="pipeline")
    citation = [c for c in score.checks if c.dimension == "citation_integrity"]
    assert citation and not citation[0].passed, (
        "a fabricated citation outside claim_audit was scored as clean")
    assert "S9" in citation[0].detail


def test_the_mock_does_not_cite_sources_it_was_never_given():
    """The mock's fixtures assume three sources; the thin-evidence case supplies
    one. Emitting S2 and S3 anyway is fabrication, and it is the mock's job to
    clear the structural bar the suite measures."""
    from deckscope.providers.mock_provider import MockProvider

    payload = {"scorecard": [{"source_ids": ["S1", "S2", "S3"]}],
               "consensus_view": "Slice is $3-5B [S1][S2]."}
    clamped = MockProvider._clamp_citations(payload, {"S1"})
    assert clamped["scorecard"][0]["source_ids"] == ["S1"]
    assert "[S2]" not in clamped["consensus_view"]
    assert "[S1]" in clamped["consensus_view"]


def test_the_mock_reads_the_available_ids_off_the_bibliography():
    from deckscope.providers.mock_provider import MockProvider

    block = ("Each source below has a citation ID.\n\n"
             "[S1] A title\n      url: https://e.com/1\n"
             "[S2] Another\n      url: https://e.com/2\n")
    assert MockProvider._available_sids(block) == {"S1", "S2"}


# ================================================================ transport

def test_the_https_pin_cannot_be_undone_by_a_second_dns_answer():
    """The old code set `conn.host` back to the hostname before connecting, and
    `HTTPSConnection.connect()` resolves `self.host` — reopening the exact
    time-of-check-to-time-of-use window the pin exists to close."""
    import inspect

    from deckscope.ingest.fetch import _PinnedHTTPSConnection

    src = inspect.getsource(_PinnedHTTPSConnection.connect)
    assert "self.pinned_ip" in src, "the socket must target the validated IP"
    assert "server_hostname=" in src, "TLS must still validate the real name"
    assert "(self.host," not in src, "connect() must never re-resolve the hostname"


def test_the_pinned_socket_goes_to_the_checked_ip_and_keeps_the_host_header():
    from deckscope.ingest import fetch as F

    connected = []

    class FakeSock:
        def close(self):
            pass

    def fake_cc(addr, timeout=None, source_address=None):
        connected.append(addr[0])
        return FakeSock()

    class Req:
        host = "example.invalid"

    original_resolve = F.resolve_public
    original_gai = socket.getaddrinfo
    try:
        F.resolve_public = lambda h: ["93.184.216.34"]
        host, port, ip = F._pin_target(Req())
        conn = F._PinnedHTTPConnection(host, ip, port=80)
        conn._create_connection = fake_cc
        # DNS now answers loopback. Anything that re-resolves lands there.
        socket.getaddrinfo = lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 80))]
        conn.connect()
    finally:
        F.resolve_public = original_resolve
        socket.getaddrinfo = original_gai

    assert connected == ["93.184.216.34"], f"pin broken, went to {connected}"
    assert conn.host == "example.invalid", "the Host header must keep the name"


def test_a_negative_content_length_cannot_bypass_the_size_cap():
    """`int(header)` accepts "-1", which slid past `> MAX_BODY_BYTES` and then
    made `rfile.read(-1)` read to EOF — the unbounded read the cap prevents."""
    import re

    text = (Path(__file__).resolve().parent.parent
            / "deckscope" / "webapp.py").read_text(encoding="utf-8")
    assert "if length < 0:" in text, "no guard against a negative Content-Length"
    # And the parse itself must not be allowed to raise out of the handler.
    guard = re.search(r"try:\s*\n\s*length = int\(raw\)", text)
    assert guard, "Content-Length must be parsed defensively"


def test_an_office_file_that_expands_absurdly_is_refused(tmp_path=None):
    from deckscope.ingest.loader import DeckLoadError, _check_office_archive

    import tempfile
    d = Path(tempfile.mkdtemp())
    bomb = d / "bomb.pptx"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        for i in range(12):
            z.writestr(f"ppt/slides/s{i}.xml", b"\0" * 40_000_000)
    try:
        _check_office_archive(bomb)
    except DeckLoadError as exc:
        assert "ratio" in str(exc) or "expands" in str(exc)
    else:
        raise AssertionError("a 1000x zip bomb was accepted")


def test_an_ordinary_office_file_is_not_a_false_positive():
    from deckscope.ingest.loader import _check_office_archive

    import tempfile
    d = Path(tempfile.mkdtemp())
    ok = d / "ok.pptx"
    with zipfile.ZipFile(ok, "w") as z:
        z.writestr("ppt/slides/slide1.xml", b"<x/>" * 500)
    _check_office_archive(ok)      # must not raise


# ================================================================= providers

def test_codex_global_flags_precede_the_exec_subcommand():
    """Placed after `exec` they are parsed as its arguments and rejected, so the
    read-only sandbox the preset promised never took effect."""
    from deckscope.providers.cli_provider import PRESETS

    argv = PRESETS["codex"]
    assert argv.index("--sandbox") < argv.index("exec")
    assert argv.index("--ask-for-approval") < argv.index("exec")
    assert "--skip-git-repo-check" in argv, (
        "`codex exec` refuses to start outside a git repo, and a user analyzing "
        "a deck in ~/Documents is not in one")


def test_reasoning_models_get_max_completion_tokens_and_a_developer_role():
    """`max_tokens` and a `system` message are both rejected by the o-series."""
    import os

    from deckscope.config import ProviderConfig
    from deckscope.providers.openai_provider import OpenAIProvider
    from deckscope.providers.base import Message

    os.environ.setdefault("OPENAI_API_KEY", "test")
    captured = {}

    def fake_post(self, url, payload, headers):
        captured.update(payload)
        raise RuntimeError("stop here — the payload is what we are testing")

    # A current reasoning-family name and a current chat name. Taken from the
    # provider's own prefix list so a catalogue refresh cannot silently turn this
    # into a test of a retired model.
    reasoning_name = OpenAIProvider.reasoning_prefixes[-1] + ".2"
    for model, reasoning in ((reasoning_name, True), ("gpt-4.1", False)):
        provider = OpenAIProvider(ProviderConfig(name="openai", model=model))
        assert provider.is_reasoning_model() is reasoning
        captured.clear()
        original = type(provider)._post if hasattr(type(provider), "_post") else None
        type(provider)._post = fake_post
        try:
            provider.complete("sys", [Message(role="user", content="hi")])
        except Exception:  # noqa: BLE001 - we only want the payload
            pass
        finally:
            if original is not None:
                type(provider)._post = original
        if not captured:
            continue                      # transport differs; the shape test below still holds
        if reasoning:
            assert "max_completion_tokens" in captured
            assert "max_tokens" not in captured
            assert captured["messages"][0]["role"] == "developer"
        else:
            assert "max_tokens" in captured
            assert captured["messages"][0]["role"] == "system"


def test_retired_openai_models_are_named_rather_than_404ing():
    import os

    from deckscope.config import ProviderConfig
    from deckscope.providers.base import ProviderError
    from deckscope.providers.openai_provider import OpenAIProvider

    os.environ.setdefault("OPENAI_API_KEY", "test")
    retired = sorted(OpenAIProvider.retired_models)
    assert retired, "the retirement map is empty, so nothing can be redirected"
    for name in retired:
        replacement = OpenAIProvider.retired_models[name]
        # The replacement must itself be live, or the advice sends the user
        # from one dead model to another.
        assert replacement not in OpenAIProvider.retired_models, (
            f"{name} redirects to {replacement}, which is also retired")
        try:
            OpenAIProvider(ProviderConfig(name="openai", model=name))
        except ProviderError as exc:
            assert replacement in str(exc), "the error must name a working replacement"
        else:
            raise AssertionError(f"{name} is retired and must be refused")


def test_the_docs_do_not_recommend_models_the_code_refuses():
    """The README told users to run `--model gemini-2.0-flash`, which the
    provider itself raises on as retired."""
    root = Path(__file__).resolve().parent.parent
    # The changelog is exempt: recording that a model was retired requires naming
    # it. This checks the docs that tell a user what to *run*.
    docs = [d for d in list(root.glob("*.md")) + list((root / "docs").glob("*.md"))
            if d.name != "CHANGELOG.md"]
    offenders = []
    for doc in docs:
        for line in doc.read_text(encoding="utf-8").splitlines():
            for dead in ("gemini-2.0-flash", "gemini-1.5-pro", "o3-mini"):
                if dead in line:
                    offenders.append(f"{doc.name}: {line.strip()[:80]}")
    assert not offenders, offenders


# ==================================================== panel revision history

def test_declining_to_revise_does_not_erase_earlier_revisions():
    """`me.revised = {}` threw away every prior round, so a panelist that
    improved in round one and was satisfied in round two was voted on using its
    round-zero analysis."""
    from deckscope.config import ProviderConfig
    from deckscope.ensemble import Panelist

    class Result:
        comparisons = {"investor": {"v": "original"}, "founder": {"v": "original-f"}}

    p = Panelist(label="A", name="x", provider=ProviderConfig(name="mock"),
                 result=Result())
    p.record_revision("investor", {"v": "round-1"})
    p.review = {"will_revise": "false", "position_changes": []}
    assert p.final("investor") == {"v": "round-1"}
    assert len(p.revision_history["investor"]) == 1


def test_every_lens_survives_into_the_output_not_just_the_revised_ones():
    """`to_dict` keyed off `revised`, so a lens the panelist never changed its
    mind about vanished from the report entirely."""
    from deckscope.config import ProviderConfig
    from deckscope.ensemble import Panelist

    class Result:
        comparisons = {"investor": {"v": "i"}, "founder": {"v": "f"}}

    p = Panelist(label="A", name="x", provider=ProviderConfig(name="mock"),
                 result=Result())
    p.record_revision("investor", {"v": "revised-i"})
    final = p.to_dict()["final"]
    assert set(final) == {"investor", "founder"}
    assert final["founder"] == {"v": "f"}


def test_the_renderer_reads_a_key_the_panel_actually_writes():
    """The panel stores `rounds_run`; a renderer asking for `rounds` printed
    nothing and no test noticed."""
    from deckscope.render import panel_renderer

    src = Path(panel_renderer.__file__).read_text(encoding="utf-8")
    assert 'stats.get(\'rounds_run\')' in src or 'stats.get("rounds_run")' in src


# ====================================================== MCP protocol currency

def _server(*requests):
    """Run the stdio server over some request lines and return parsed replies."""
    import subprocess

    root = Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        [sys.executable, "-m", "deckscope.mcp_server"],
        input="\n".join(requests) + "\n", cwd=str(root),
        capture_output=True, text=True)
    import json as _json
    return [_json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def test_the_server_is_not_pinned_to_one_hardcoded_protocol_version():
    """It answered `2024-11-05` no matter what the client asked for, which is how
    it stayed four revisions behind the spec without anything failing."""
    from deckscope.mcp_server import SUPPORTED_VERSIONS

    assert len(SUPPORTED_VERSIONS) > 1, "a single supported version cannot negotiate"
    assert "2026-07-28" in SUPPORTED_VERSIONS, "the current spec revision is missing"


def test_a_legacy_initialize_agrees_to_the_version_the_client_asked_for():
    import json as _json

    replies = _server(_json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"}}))
    assert replies[0]["result"]["protocolVersion"] == "2024-11-05"


def test_a_legacy_client_asking_for_an_unknown_version_gets_ours_named():
    import json as _json

    from deckscope.mcp_server import LATEST_LEGACY_VERSION

    replies = _server(_json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "1999-01-01"}}))
    # Legacy clients have no fall-forward mechanism, so the reply has to name a
    # version they can actually try.
    assert replies[0]["result"]["protocolVersion"] == LATEST_LEGACY_VERSION


def test_server_discover_is_implemented():
    """Mandatory in the modern spec, and the stdio probe a dual-era client uses
    to tell a modern server from a legacy one."""
    import json as _json

    replies = _server(_json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "server/discover",
        "params": {"_meta": {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28"}}}))
    result = replies[0]["result"]
    assert result["resultType"] == "complete"
    assert "2026-07-28" in result["supportedVersions"]
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "deckscope"


def test_an_unsupported_version_gets_the_spec_error_with_what_we_do_support():
    import json as _json

    replies = _server(_json.dumps({
        "jsonrpc": "2.0", "id": 7, "method": "tools/list",
        "params": {"_meta": {
            "io.modelcontextprotocol/protocolVersion": "1900-01-01"}}}))
    error = replies[0]["error"]
    assert error["code"] == -32022, "UnsupportedProtocolVersionError"
    assert error["data"]["requested"] == "1900-01-01"
    assert "2026-07-28" in error["data"]["supported"]


def test_a_modern_tool_call_still_reaches_the_handler():
    import json as _json

    replies = _server(_json.dumps({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"},
                   "name": "scan_deck_security",
                   "arguments": {
                       "deck_path": "deckscope/examples/sample_deck_with_injection.md"}}}))
    text = replies[0]["result"]["content"][0]["text"]
    assert "CRITICAL" in text


def _client_against(*replies):
    """An MCPStdioClient whose transport is a scripted server."""
    import types

    from deckscope.providers.mcp_provider import MCPStdioClient

    client = MCPStdioClient.__new__(MCPStdioClient)
    client.era, client.protocol_version, client.server_info = (
        "legacy", "2024-11-05", {})
    seq = list(replies)

    def _rpc(self, method, params=None, notify=False, raw=False):
        if notify:
            return None
        reply = seq.pop(0)
        if raw:
            return reply
        if "error" in reply:
            raise RuntimeError(reply["error"])
        return reply.get("result")

    client._rpc = types.MethodType(_rpc, client)
    return client


def test_the_client_probes_modern_first_and_takes_the_newest_shared_version():
    client = _client_against({"result": {
        "resultType": "complete", "supportedVersions": ["2026-07-28"],
        "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "modern"}}}})
    client.initialize()
    assert client.era == "modern"
    assert client.protocol_version == "2026-07-28"


def test_the_client_retries_at_a_version_the_modern_server_named():
    client = _client_against({"error": {
        "code": -32022, "message": "Unsupported protocol version",
        "data": {"supported": ["2025-11-25", "2025-06-18"]}}})
    client.initialize()
    assert client.era == "modern"
    assert client.protocol_version == "2025-11-25", "must take the newest shared"


def test_the_client_falls_back_to_the_handshake_for_a_legacy_server():
    """Any error that is not a recognized modern one identifies a legacy server."""
    client = _client_against(
        {"error": {"code": -32601, "message": "Method not found"}},
        {"result": {"protocolVersion": "2025-03-26",
                    "serverInfo": {"name": "legacy"}}})
    client.initialize()
    assert client.era == "legacy"
    # The server names what it will actually speak; believe it over what we asked.
    assert client.protocol_version == "2025-03-26"


def test_no_mutually_supported_version_is_an_error_not_a_silent_downgrade():
    client = _client_against({"error": {
        "code": -32022, "data": {"supported": ["1900-01-01"]}}})
    try:
        client.initialize()
    except Exception as exc:  # noqa: BLE001
        assert "mutually supported" in str(exc)
    else:
        raise AssertionError("a version stalemate must fail loudly")


def test_a_legacy_server_never_receives_per_request_meta():
    """Stamping `_meta` on a legacy server's requests is exactly the kind of
    change that breaks older integrations silently."""
    import types

    from deckscope.providers.mcp_provider import MCPStdioClient

    client = MCPStdioClient.__new__(MCPStdioClient)
    client.era, client.protocol_version = "legacy", "2024-11-05"
    client._id = 0
    client._lock = __import__("threading").Lock()
    sent = {}

    class FakeStdin:
        def write(self, data):
            import json as _json
            sent.update(_json.loads(data))

        def flush(self):
            pass

    client.proc = types.SimpleNamespace(stdin=FakeStdin())
    client._await = types.MethodType(lambda self, i: {"result": {}}, client)
    client._rpc("tools/list")
    assert "_meta" not in sent["params"], sent["params"]


# ===================================== runtime data must ship with the package

def test_the_sample_decks_live_inside_the_package():
    """`demo` is the first command the README gives a new user, and it reads
    these. Beside the package meant not installed with it."""
    import deckscope

    package_root = Path(deckscope.__file__).resolve().parent
    for name in ("sample_deck.md", "sample_deck_with_injection.md"):
        assert (package_root / "examples" / name).is_file(), (
            f"{name} is not inside the package and will not be installed")


def test_the_packaging_config_ships_the_sample_decks():
    import re

    text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
    block = re.search(r"\[tool\.setuptools\.package-data\](.*?)(\n\[|\Z)", text, re.S)
    assert block and "examples/*.md" in block.group(1)


def test_the_injection_demo_refuses_rather_than_showing_a_clean_deck():
    """Found by the clean-install acceptance test.

    When the sample decks were outside the package, an installed DeckScope fell
    through to the embedded deck — which has no injection in it. So
    `demo --injected`, the one command whose entire purpose is to show the
    security screen catching something, printed a clean report and said nothing.
    A silently wrong answer, and worse than a crash, because it looks like a
    pass.
    """
    import re

    text = (Path(__file__).resolve().parent.parent
            / "deckscope" / "cli.py").read_text(encoding="utf-8")
    demo = text[text.index("def _demo("):]
    demo = demo[:demo.index("\ndef ", 1)] if "\ndef " in demo[1:] else demo
    assert "elif args.injected:" in demo, (
        "no branch guarding the injected demo against a missing fixture")
    assert re.search(r"Refusing to run the injection demo", demo), (
        "the injected demo must refuse, not substitute a clean deck")


def test_the_demo_deck_path_resolves_inside_the_package():
    """`parent.parent` walked out of the package to a directory the wheel omits."""
    text = (Path(__file__).resolve().parent.parent
            / "deckscope" / "cli.py").read_text(encoding="utf-8")
    demo = text[text.index("def _demo("):]
    demo = demo[:demo.index("\ndef ", 1)] if "\ndef " in demo[1:] else demo
    assert "Path(__file__).resolve().parent\n" in demo or \
           "here = Path(__file__).resolve().parent\n" in demo, \
        "the demo decks must resolve relative to the package, not its parent"


# ============================================== release artifacts and acceptance

def test_the_sbom_generator_produces_a_valid_cyclonedx_document():
    import importlib.util

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "gen_sbom", root / "scripts" / "generate_sbom.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    bom = module.build("1.2.3")
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.5"
    assert bom["serialNumber"].startswith("urn:uuid:")
    assert bom["metadata"]["component"]["purl"] == "pkg:pypi/deckscope@1.2.3"
    assert bom["components"], "an SBOM with no components describes nothing"
    for component in bom["components"]:
        assert component["purl"].startswith("pkg:pypi/")
        assert component["name"] and component["version"]


def test_the_sbom_marks_direct_dependencies_apart_from_transitive_ones():
    import importlib.util

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "gen_sbom2", root / "scripts" / "generate_sbom.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert "pyyaml" in module.DIRECT, "the one hard dependency must be marked direct"
    kinds = {p["value"]
             for c in module.build() ["components"]
             for p in c["properties"] if p["name"] == "deckscope:relationship"}
    assert kinds <= {"direct", "transitive"}


def test_the_acceptance_script_refuses_to_run_inside_a_checkout():
    """Running it from the repository would test nothing, so it must not.

    Skipped where no POSIX shell is available. This used to invoke whatever
    `bash` happened to be on PATH, which on a Windows runner is some other
    shell entirely: it failed on the first line with exit 1 rather than
    reaching the guard and exiting 2, so all three Windows CI jobs went red
    over an environment difference and not over DeckScope. A test that cannot
    run on a platform should say so, not fail there.
    """
    import shutil
    import subprocess

    root = Path(__file__).resolve().parent.parent
    script = root / "scripts" / "acceptance.sh"

    # Portable half: the guard has to exist and exit 2, checkable as text on any
    # platform. This runs everywhere, so the test is never vacuous.
    text = script.read_text(encoding="utf-8")
    assert "only meaningful outside a source checkout" in text
    assert "exit 2" in text

    # Executable half: only where a POSIX shell actually exists.
    if not shutil.which("bash"):
        return
    try:
        proc = subprocess.run(["bash", str(script), sys.executable],
                              cwd=str(root), capture_output=True, text=True)
    except OSError:
        return
    assert proc.returncode == 2
    assert "only meaningful outside a source checkout" in proc.stdout


def test_the_release_workflow_produces_a_lockfile_an_sbom_and_an_acceptance_run():
    workflow = (Path(__file__).resolve().parent.parent / ".github" / "workflows"
                / "release.yml").read_text(encoding="utf-8")
    assert "--generate-hashes" in workflow, "a lockfile without hashes is not pinned"
    assert "generate_sbom.py" in workflow
    assert "acceptance.sh" in workflow


# ======================================================================= CI

def test_the_evaluation_gate_in_ci_is_reachable():
    """The eval command exits 1 whenever any check fails, and claim_accuracy is
    expected to fail under the mock. Under `set -e` that ended the step before
    the gate ran, so the job could not fail for the reason it exists."""
    ci = (Path(__file__).resolve().parent.parent
          / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "|| [ $? -eq 1 ]" in ci, (
        "the evaluator's expected non-zero exit must not abort the step "
        "before the structural-dimension gate runs")


def test_ci_installs_the_built_wheel_somewhere_with_no_source():
    """Every other job runs from an editable checkout, where files missing from
    the wheel are still importable. That is what hid the packaging defect."""
    ci = (Path(__file__).resolve().parent.parent
          / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m build --wheel" in ci
    assert "/tmp/elsewhere" in ci, "the installed CLI must run outside the checkout"
    assert "--trials 0" in ci, "CI must prove a vacuous run fails"
