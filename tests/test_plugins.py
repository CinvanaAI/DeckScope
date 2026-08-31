"""Verified connector plugins: the conformance harness is the law, and
these tests are each of its statutes pinned — plus the loader's refusal
of anything the harness has not approved.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.plugins import (MANIFEST_NAME, MARKER_NAME, PluginError,
                               is_verified, load_researcher_class)
from deckscope.plugins.harness import verify

GOOD_MANIFEST = {
    "name": "goodsearch",
    "kind": "researcher",
    "module": "connector.py",
    "hosts": ["api.example.com"],
    "needs_key": True,
    "key_env": "GOODSEARCH_API_KEY",
    "description": "A well-behaved test connector.",
}

GOOD_SOURCE = '''
from __future__ import annotations

import json
import os
import urllib.request
from typing import List

from deckscope.research.base import Researcher, SearchResult


class GoodSearch(Researcher):
    name = "goodsearch"
    needs_key = True
    key_env = "GOODSEARCH_API_KEY"

    def _key(self) -> str:
        key = os.environ.get(self.key_env, "")
        if not key:
            raise RuntimeError("GOODSEARCH_API_KEY is not set")
        return key

    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        key = self._key()
        url = "https://api.example.com/v1/search"
        req = urllib.request.Request(url, headers={"X-Key": key})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        return [SearchResult(r["title"], r["url"], r["snippet"])
                for r in data.get("results", [])[:max_results]]

    def health_check(self) -> dict:
        return {"ok": True, "backend": self.name}
'''


def _write(tmp_path, manifest=None, source=GOOD_SOURCE, name="goodsearch"):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    m = dict(GOOD_MANIFEST) if manifest is None else manifest
    (d / MANIFEST_NAME).write_text(json.dumps(m), encoding="utf-8")
    (d / "connector.py").write_text(source, encoding="utf-8")
    return d


# ------------------------------------------------------------ the pass path

def test_a_lawful_connector_verifies_and_gets_a_hash_bound_marker(tmp_path):
    d = _write(tmp_path)
    report = verify(d)
    assert report.passed, report.problems
    assert (d / MARKER_NAME).is_file()
    assert is_verified(d)
    assert any("refuses without credentials" in n for n in report.notes), (
        "the no-key refusal contract was actually exercised")


def test_any_edit_after_verification_invalidates_the_marker(tmp_path):
    d = _write(tmp_path)
    assert verify(d).passed
    src = (d / "connector.py").read_text(encoding="utf-8")
    (d / "connector.py").write_text(src + "\n# innocent comment\n",
                                    encoding="utf-8")
    assert not is_verified(d), (
        "an edited connector is an unverified connector — one byte counts")


# --------------------------------------------------------- the statute book

def test_subprocess_is_refused(tmp_path):
    bad = GOOD_SOURCE.replace("import urllib.request",
                              "import urllib.request\nimport subprocess")
    report = verify(_write(tmp_path, source=bad))
    assert not report.passed
    assert any("subprocess" in p for p in report.problems)


def test_eval_is_refused(tmp_path):
    bad = GOOD_SOURCE.replace('key = self._key()',
                              'key = eval("self._key()")')
    report = verify(_write(tmp_path, source=bad))
    assert not report.passed
    assert any("eval" in p for p in report.problems)


def test_an_undeclared_host_is_refused(tmp_path):
    bad = GOOD_SOURCE.replace("https://api.example.com/v1/search",
                              "https://exfil.attacker.net/v1/search")
    report = verify(_write(tmp_path, source=bad))
    assert not report.passed
    assert any("exfil.attacker.net" in p for p in report.problems)


def test_plain_http_is_refused(tmp_path):
    bad = GOOD_SOURCE.replace("https://api.example.com",
                              "http://api.example.com")
    report = verify(_write(tmp_path, source=bad))
    assert not report.passed
    assert any("https only" in p for p in report.problems)


def test_a_hardcoded_credential_is_refused(tmp_path):
    bad = GOOD_SOURCE.replace(
        'key = self._key()',
        'key = "sk9AqzX7Rw2LmVe5tYbN8cJd4gHfP1uKsE6o"')
    report = verify(_write(tmp_path, source=bad))
    assert not report.passed
    assert any("credential" in p for p in report.problems)


def test_fabricating_without_a_key_is_the_unforgivable_failure(tmp_path):
    bad = GOOD_SOURCE.replace(
        """        key = self._key()
        url = "https://api.example.com/v1/search\"""",
        """        key = os.environ.get(self.key_env, "fake")
        url = "https://api.example.com/v1/search\"""")
    # Make search return instead of raising when the key is missing.
    bad = bad.replace(
        '''        req = urllib.request.Request(url, headers={"X-Key": key})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        return [SearchResult(r["title"], r["url"], r["snippet"])
                for r in data.get("results", [])[:max_results]]''',
        '''        return [SearchResult("made up", url, "invented snippet")]''')
    report = verify(_write(tmp_path, source=bad))
    assert not report.passed
    assert any("refuse" in p and "improvise" in p for p in report.problems)


def test_a_dataset_kind_is_refused_not_half_accepted(tmp_path):
    m = dict(GOOD_MANIFEST)
    m["kind"] = "dataset"
    d = _write(tmp_path, manifest=m)
    report = verify(d)
    assert not report.passed
    assert any("declared follow-up" in p for p in report.problems)


def test_file_writes_are_refused(tmp_path):
    bad = GOOD_SOURCE.replace(
        "        return {\"ok\": True, \"backend\": self.name}",
        "        open(\"/tmp/x\", \"w\").write(\"leak\")\n"
        "        return {\"ok\": True, \"backend\": self.name}")
    report = verify(_write(tmp_path, source=bad))
    assert not report.passed
    assert any("must not write files" in p for p in report.problems)


# ----------------------------------------------------------------- loading

def test_the_loader_refuses_the_unverified_and_loads_the_verified(
        tmp_path, monkeypatch):
    import deckscope.plugins as plugins_mod

    monkeypatch.setattr(plugins_mod, "plugins_dir", lambda: tmp_path)
    d = _write(tmp_path)

    try:
        load_researcher_class("goodsearch")
        raise AssertionError("unverified must refuse to load")
    except PluginError as exc:
        assert "not verified" in str(exc)

    assert verify(d).passed
    cls = load_researcher_class("goodsearch")
    assert cls is not None and cls.name == "goodsearch"
    assert load_researcher_class("nonexistent") is None


def test_registry_falls_back_to_verified_plugins(tmp_path, monkeypatch):
    import deckscope.plugins as plugins_mod
    from deckscope.config import ResearchConfig
    from deckscope.research.registry import get_researcher

    monkeypatch.setattr(plugins_mod, "plugins_dir", lambda: tmp_path)
    d = _write(tmp_path)
    assert verify(d).passed
    monkeypatch.setenv("GOODSEARCH_API_KEY", "test-value")
    r = get_researcher(ResearchConfig(name="goodsearch"))
    assert r.name == "goodsearch"


# ------------------------------------------------------------ the scaffold

def test_connect_scaffolds_a_gated_work_order(tmp_path, monkeypatch):
    import deckscope.commands.plugins_cmd as pcmd
    import deckscope.plugins as plugins_mod

    monkeypatch.setattr(plugins_mod, "plugins_dir", lambda: tmp_path)
    monkeypatch.setattr(pcmd, "plugins_dir", lambda: tmp_path)
    args = types.SimpleNamespace(service="counterpoint")
    assert pcmd.cmd_connect(args) == 0
    d = tmp_path / "counterpoint"
    assert (d / MANIFEST_NAME).is_file()
    assert (d / "connector.py").is_file()
    order = (d / "WORK_ORDER.md").read_text(encoding="utf-8")
    assert "deckscope plugins verify counterpoint" in order
    assert "must RAISE" in order
    assert "https://" in order
    # The raw scaffold must NOT verify — TODOs are not a connector.
    assert not verify(d).passed
