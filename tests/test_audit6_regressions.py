"""Regressions for the sixth external audit: externally visible guarantees.

The theme was that the promises a stranger can check from outside — protocol
conformance, a replayable benchmark, a model catalogue, a green build — were the
ones that failed when actually exercised. Internal design held up; the surface
did not.

The benchmark finding is the one worth internalising. The bundle shipped with a
manifest of hashes and a test that checked the manifest against its own files, so
the check passed while the property it existed to guarantee was false: prompts
had been path-scrubbed *after* they were hashed, so the ids no longer named the
prompts the pipeline generates and half the bundle could not replay. A check
that verifies a document against itself proves nothing about the world.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent

#: Assembled rather than written literally, so this detector does not
#: report itself.
_POSIX_TMP = "/" + "tmp"


# ============================================ MCP 2026-07-28 wire conformance

def _rpc(*messages):
    """Drive the stdio server and return {id: result-or-error}."""
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    proc = subprocess.run([sys.executable, "-m", "deckscope.mcp_server"],
                          input=payload, capture_output=True, text=True,
                          cwd=str(ROOT), timeout=180)
    out = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        out[msg.get("id")] = msg
    return out


MODERN = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}


def test_discovery_carries_the_cache_hints_the_revision_requires():
    """`server/discover` returned a bare result. DeckScope advertised
    `2026-07-28` while speaking the older envelope, so a strict client was
    entitled to reject a server claiming to speak its protocol — and the MCP
    smoke test could not catch it, because it only checked that a version came
    back and that a tool ran."""
    got = _rpc({"jsonrpc": "2.0", "id": 1, "method": "server/discover",
                "params": {}})
    result = got[1]["result"]
    assert result["resultType"] == "complete"
    assert "ttlMs" in result and "cacheScope" in result
    assert result["cacheScope"] in ("public", "private")
    assert "2026-07-28" in result["supportedVersions"]


def test_list_results_are_cacheable_under_the_modern_revision():
    got = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                "params": dict(MODERN)})
    result = got[2]["result"]
    assert result["tools"], "no tools listed"
    for field in ("resultType", "ttlMs", "cacheScope"):
        assert field in result, f"tools/list is missing {field}"


def test_every_modern_result_carries_a_result_type():
    got = _rpc({"jsonrpc": "2.0", "id": 3, "method": "ping",
                "params": dict(MODERN)},
               {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": dict(MODERN, name="scan_deck_security",
                               arguments={"deck_path": "does-not-exist.md"})})
    assert got[3]["result"]["resultType"] == "complete"
    # A tool that failed is still a *result* with `isError`, not a JSON-RPC
    # error, so it is stamped like any other.
    call = got[4]["result"]
    assert call["resultType"] == "complete"
    # `ping` is not a list method and must not pretend to be cacheable.
    assert "ttlMs" not in got[3]["result"]


def test_the_legacy_handshake_is_not_given_modern_fields():
    """Old revisions have no `resultType`; a strict old client should not get
    one. Stamping everywhere would trade one conformance break for another."""
    got = _rpc({"jsonrpc": "2.0", "id": 5, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"}})
    result = got[5]["result"]
    assert "protocolVersion" in result
    for field in ("resultType", "ttlMs", "cacheScope"):
        assert field not in result, f"legacy initialize carries {field}"


def test_an_unsupported_version_is_refused_with_what_is_supported():
    got = _rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/list",
                "params": {"_meta": {
                    "io.modelcontextprotocol/protocolVersion": "1999-01-01"}}})
    error = got[6]["error"]
    assert error["code"] == -32022
    assert "2026-07-28" in json.dumps(error["data"])


# ================================== prompts are portable, so benchmarks replay

def test_a_deck_path_never_reaches_the_prompt():
    """The prompt carried the operator's full path to the deck. It is useless to
    the model, it leaks directory layout to a third party, and it made every
    prompt machine-specific — which is what stopped the committed benchmark
    prompts from replaying anywhere but the machine that made them."""
    from deckscope.agents.deck_agent import _source_label

    assert _source_label("/home/me/decks/inflated_tam.md") == "inflated_tam.md"
    assert _source_label(r"C:\Users\example\Desktop\deck.pptx") == "deck.pptx"
    # A URL is the identity of a remote deck, not a fact about a filesystem.
    assert _source_label("https://example.com/a/deck.pdf") == \
        "https://example.com/a/deck.pdf"
    assert _source_label("") == "unknown"


def test_the_manual_provider_canonicalizes_before_it_hashes():
    from deckscope.providers.manual_provider import ManualProvider

    text = ("Deck source: /sessions/abc/mnt/DeckScope/decks/x.md\n"
            "Windows: C:\\Users\\von\\deck.pptx\n"
            "Keep: https://research.example.org/recon-sizing-2026\n"
            "Keep: a ratio 3/4 and a date 2026/08/23")
    canon = ManualProvider.canonicalize(text)
    assert "/sessions/" not in canon and "C:\\Users" not in canon
    assert "x.md" in canon and "deck.pptx" in canon
    assert "https://research.example.org/recon-sizing-2026" in canon
    assert "3/4" in canon and "2026/08/23" in canon
    assert ManualProvider.canonicalize(canon) == canon, "must be idempotent"


def _bundles():
    return [d for d in sorted((ROOT / "benchmarks").glob("*"))
            if (d / "result.json").is_file()]


def test_every_benchmark_id_is_the_hash_of_the_prompt_beside_it():
    """The check that shipped compared the manifest against its own files, which
    both agreed and meant nothing. This is the property that matters: the id is
    the cache key, so if it is not the hash of the prompt, the prompt cannot be
    replayed."""
    bundles = _bundles()
    assert bundles, "no benchmark artifacts are committed"
    offenders = []
    for bundle in bundles:
        manifest = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
        for row in manifest["exchanges"]:
            prompt = bundle / "prompts" / f"{row['id']}.txt"
            digest = hashlib.sha256(
                prompt.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            if digest[:16] != row["id"]:
                offenders.append(f"{bundle.name}/{row['id']} hashes to {digest[:16]}")
            if digest != row["prompt_sha256"]:
                offenders.append(f"{bundle.name}/{row['id']} manifest hash differs")
    assert not offenders, "; ".join(offenders[:8])


def test_benchmark_prompts_contain_no_machine_paths():
    """And they are not scrubbed to achieve it — the generator refuses to write
    one, so a path here means the pipeline regressed."""
    for bundle in _bundles():
        for prompt in (bundle / "prompts").glob("*.txt"):
            text = prompt.read_text(encoding="utf-8")
            for marker in ("/sessions/", "C:\\Users\\", "/home/"):
                assert marker not in text, f"{prompt} contains {marker}"


def test_git_never_rewrites_a_content_addressed_file():
    """Line-ending normalization would break the hash the filename *is*.

    `.gitattributes` sets `* text=auto`, which stores text with LF and checks it
    out with CRLF on Windows. The benchmark prompts are named after the sha256 of
    their own contents, so under that rule a fresh Windows clone would hold
    prompts that no longer hash to their own names: the replay would fail there
    and pass on Linux. A platform-dependent hash is the worst version of the bug
    the bundle exists to prevent.
    """
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    rules = [line.split("#")[0].strip() for line in text.splitlines()]
    rules = [r for r in rules if r]
    protecting = [r for r in rules
                  if r.startswith("benchmarks/") and "-text" in r]
    assert protecting, (
        "benchmarks/ must be marked `-text` so git never rewrites a file whose "
        "name is the hash of its contents")
    # Later rules win in gitattributes, so the protection has to come after any
    # rule that would otherwise match a file inside the bundle. Only patterns
    # that actually match one count — `*.png binary` is later and irrelevant.
    conflicting = {"*", "*.txt", "*.json", "*.md"}
    last_conflict = max((i for i, r in enumerate(rules)
                         if r.split()[0] in conflicting), default=-1)
    assert rules.index(protecting[0]) > last_conflict, (
        "a rule matching benchmark files appears after the benchmarks rule and "
        "overrides it")


def test_no_committed_benchmark_file_contains_carriage_returns():
    """Belt and braces: if one ever gets normalized, the bytes say so."""
    for bundle in _bundles():
        for path in list((bundle / "prompts").glob("*.txt")) + \
                    list((bundle / "answers").glob("*.json")):
            assert b"\r\n" not in path.read_bytes(), (
                f"{path.name} has CRLF line endings; its hash no longer matches "
                f"the hash recorded on other platforms")


def test_benchmarks_record_how_they_were_generated():
    """"a frontier model; see answered_by" is not provenance. An auditor needs
    the model, the date, who answered, and what that independence does and does
    not cover."""
    for bundle in _bundles():
        manifest = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
        gen = manifest.get("generation") or {}
        assert manifest.get("date") and manifest.get("provider")
        assert manifest.get("model") and "see answered_by" not in manifest["model"]
        assert gen.get("answered_by") and gen.get("authored_by"), (
            "the manifest must say who answered AND who authored — they are "
            "different independence claims")


def test_the_replay_script_verifies_rather_than_describes():
    """Prose instructions were what shipped last time. The check has to be
    executable, and it has to actually re-score rather than re-hash."""
    script = ROOT / "scripts" / "replay_benchmark.py"
    assert script.is_file()
    proc = subprocess.run([sys.executable, str(script), "--all",
                           "--identity-only"],
                          capture_output=True, text=True, cwd=str(ROOT),
                          timeout=300)
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert "identity: ok" in proc.stdout


def test_ci_runs_the_replay():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "replay_benchmark.py" in workflow, (
        "a benchmark nobody replays goes stale silently")


# ================================================ citations past three digits

def test_source_ids_do_not_stop_working_at_s999():
    """The registry mints IDs without a ceiling, but the parser and the lookup
    both capped at three digits. Past S999 a structured citation survived the
    audit while the inline form was ignored and the lookup failed — the
    bibliography then filed the source as uncited. A panel is deliberately
    unbounded, so a large merged registry is reachable."""
    from types import SimpleNamespace

    from deckscope.sources import (SourceRegistry, audit_citations,
                                   prose_citations, resolve_citations)

    reg = SourceRegistry()
    reg.add_results([SimpleNamespace(title=f"S{i}", url=f"https://e.example/{i}",
                                     snippet="x" * 40, published=None,
                                     source_query="q") for i in range(1001)])
    reg.prompt_block(char_budget=10 ** 9)
    assert reg.sources[-1].sid == "S1001"
    assert reg.find("S1000") is not None
    assert prose_citations("supported [S1000]") == ["S1000"]

    class Result:
        market = {}
        comparisons = {"investor": {"summary": "sized at $4B [S1000]",
                                    "claim_audit": [{"source_ids": ["S1000"]}]}}
        opportunity = discovery_delta = cold_market = {}

    result = Result()
    assert audit_citations(result, reg, strip=True).ok
    assert "[S1000]" in result.comparisons["investor"]["summary"]
    assert resolve_citations(result, reg).find("S1000").status == "cited"


def test_merging_carries_the_prompt_built_flag_not_only_the_admitted_set():
    """An incoming registry that built a prompt and admitted nothing — because
    nothing fit the budget — left the target believing no prompt had been built,
    which flips `citable_ids` from "only what a model saw" back to "everything"."""
    from types import SimpleNamespace

    from deckscope.sources import SourceRegistry, merge_into

    def registry(title, snippet):
        reg = SourceRegistry()
        reg.add_results([SimpleNamespace(title=title, url=f"https://e.example/{title}",
                                         snippet=snippet, published=None,
                                         source_query="q")])
        return reg

    target = registry("a", "q" * 99)
    incoming = registry("b", "z" * 9999)
    incoming.prompt_block(char_budget=50)          # built; nothing fitted
    assert incoming._prompt_built and not incoming.admitted_ids

    merge_into(target, incoming)
    assert target._prompt_built, "the flag was lost in the merge"
    assert target.citable_ids == [], (
        "a source no model was shown became citable through a merge")


# =================================================== catalogue and portability

def test_no_catalogue_offers_a_model_with_no_first_party_page():
    """Two of the three OpenAI models offered were invented by pattern-matching
    on `gpt-5.2`; the small variants are `gpt-5-mini` and `gpt-5-nano`. Pin the
    exact names so a plausible-looking guess cannot slip back in."""
    from deckscope.providers.openai_provider import OpenAIProvider

    names = [m for m, _ in OpenAIProvider.catalog]
    assert names == ["gpt-5.2", "gpt-5-mini", "gpt-5-nano"], names
    assert OpenAIProvider.default_model in names
    for bad in ("gpt-5.2-mini", "gpt-5.2-nano"):
        assert bad not in names, f"{bad} is not a documented model ID"
        assert bad not in OpenAIProvider.retired_models.values()


def test_a_provider_can_be_asked_what_it_actually_serves():
    """A hard-coded catalogue is a maintenance promise nobody keeps. It must not
    be the only answer available."""
    from deckscope.providers.openai_provider import OpenAIProvider

    assert hasattr(OpenAIProvider, "available_models")


def test_workflows_pin_actions_to_immutable_commits():
    """A moving major tag is a promise from whoever controls the tag."""
    import re

    for name in ("ci.yml", "release.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        for ref in re.findall(r"uses:\s*(\S+)", text):
            _, _, version = ref.partition("@")
            assert re.fullmatch(r"[0-9a-f]{40}", version), (
                f"{name} uses {ref}; pin the full commit SHA")


def test_packaging_metadata_uses_the_current_license_form():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "MIT"' in text, "the deprecated license table is back"
    assert "license-files" in text
    assert "License :: OSI Approved" not in text, (
        "the license classifier is deprecated alongside the table")


def test_the_unix_installer_describes_everything_it_touches():
    """It said nothing outside the folder and Desktop changed, while creating a
    symlink in ~/.local/bin or /usr/local/bin."""
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "Nothing outside this folder and your Desktop is changed" not in text
    banner = text[:text.index("# ---------- 1. Python")]
    assert ".local/bin" in banner or "/usr/local/bin" in banner, (
        "the banner must mention the PATH symlink it may create")
    assert ".config/deckscope" in banner, "and the settings directory"


def test_no_test_hard_codes_a_posix_temporary_directory():
    """`/tmp` resolves to an unwritable drive-relative path on Windows, which
    took three CI jobs red for a reason unrelated to what was being tested."""
    import ast

    offenders = []
    for path in sorted((ROOT / "tests").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for node in ast.walk(ast.parse(text)):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if not node.value.startswith(_POSIX_TMP):
                continue
            # A test asserting on a Linux-only CI job may name the path it
            # expects to find there; it is not using it.
            line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
            if "posix-ci-only" in line:
                continue
            offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "use tempfile.gettempdir(); these break on Windows: " + "; ".join(offenders))
