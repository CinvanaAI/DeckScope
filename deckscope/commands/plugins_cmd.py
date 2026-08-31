"""`deckscope plugins` — list, verify, and scaffold verified connectors.

`connect <service>` is the flywheel's entry point: it writes a plugin
scaffold plus a complete WORK_ORDER.md — the contract, the manifest, the
laws, and the self-check command — for a coding agent (Claude Code,
Codex, any of them) to fill in against access the operator already
holds. The scaffold is deliberately agent-agnostic: this tool does not
puppet another agent's session and call it integration; it publishes the
contract and enforces it. The harness is the gate either way — code
nobody verified never loads, whoever or whatever wrote it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..console import out as _out
from ..plugins import MANIFEST_NAME, discover, plugins_dir
from ..plugins.harness import verify


def _err(msg: str) -> None:
    _out(msg, file=sys.stderr)


# ------------------------------------------------------------------ list

def cmd_list(args: Any) -> int:
    rows = discover()
    if not rows:
        _out(f"No plugins installed. Directory: {plugins_dir()}")
        _out("Scaffold one:  deckscope plugins connect <service>")
        return 0
    for r in rows:
        state = ("VERIFIED" if r["verified"] else
                 f"NOT VERIFIED — {r.get('problem', 'run: deckscope plugins verify ' + r['name'])}")
        m = r.get("manifest") or {}
        _out(f"  {r['name']:20s} {state}")
        if m:
            _out(f"    kind={m.get('kind')} hosts={','.join(m.get('hosts', []))} "
                 f"needs_key={m.get('needs_key')} ({m.get('key_env') or '-'})")
    return 0


# ---------------------------------------------------------------- verify

def cmd_verify(args: Any) -> int:
    target = Path(args.name)
    plugin_dir = target if target.is_dir() else plugins_dir() / args.name
    if not plugin_dir.is_dir():
        _err(f"No plugin at {plugin_dir}")
        return 2
    report = verify(plugin_dir, live=bool(getattr(args, "live", False)))
    for note in report.notes:
        _out(f"  · {note}")
    if report.passed:
        _out(f"\n{report.plugin}: VERIFIED. Use it with "
             f"--research {report.plugin} (or research.name in config).")
        return 0
    _out(f"\n{report.plugin}: FAILED — {len(report.problems)} problem(s):")
    for p in report.problems:
        _out(f"  ! {p}")
    _out("\nNothing was approved; the loader will refuse this plugin "
         "until a clean verify.")
    return 1


# --------------------------------------------------------------- connect

_MANIFEST_TEMPLATE = {
    "name": "{service}",
    "kind": "researcher",
    "module": "connector.py",
    "hosts": ["TODO.example.com"],
    "needs_key": True,
    "key_env": "{SERVICE}_API_KEY",
    "description": "TODO: what this connector retrieves, in one sentence",
}

_STUB = '''"""Connector for {service} — written against the DeckScope contract.

Fill in search() below. The conformance harness (`deckscope plugins
verify {service}`) is the gate: read WORK_ORDER.md in this directory for
every rule it will hold this file to.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import List

from deckscope.research.base import Researcher, SearchResult


class {cls}(Researcher):
    name = "{service}"
    needs_key = True
    key_env = "{SERVICE}_API_KEY"
    blurb = "TODO: one line about the data this reaches"

    def _key(self) -> str:
        key = os.environ.get(self.key_env, "")
        if not key:
            raise RuntimeError(
                f"{{self.name}}: {{self.key_env}} is not set. This "
                f"connector refuses to run without credentials rather "
                f"than improvise results.")
        return key

    def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        key = self._key()
        raise NotImplementedError("TODO: implement against the vendor API "
                                  "per WORK_ORDER.md")

    def health_check(self) -> dict:
        return {{"ok": False, "backend": self.name,
                 "note": "TODO: one cheap authenticated request"}}
'''

_WORK_ORDER = """# Work order: write the `{service}` connector

You are implementing a DeckScope research connector. The scaffold in this
directory is yours to complete. A deterministic conformance harness — not
a human mood — decides whether your work is accepted. Run it yourself
until it passes:

    deckscope plugins verify {service}

## What a connector is

One class implementing `deckscope.research.base.Researcher`:

- `name` — exactly `{service}` (must match manifest.json).
- `needs_key` / `key_env` — must match manifest.json.
- `search(query, max_results=8) -> List[SearchResult]` — query the
  vendor's API and return results. Each `SearchResult` carries `title`,
  `url`, `snippet` (the actual evidence text — what you put here is what
  the analysis can cite), optional `published` (ISO date).
- `health_check() -> dict` — one cheap authenticated request proving the
  connection works; return `{{"ok": True/False, ...}}`.

## The laws the harness enforces (do not fight them)

1. Manifest complete and truthful; `hosts` lists EVERY host you contact.
2. No `subprocess`, `socket`, `ctypes`, `pickle`, `threading`,
   `importlib`, `eval`/`exec`/`compile`, `os.system`-family, or file
   WRITES. Use `urllib.request` for HTTP. Retrieve and return — nothing
   else.
3. Every URL in source is `https://` on a declared host. No dynamic host
   construction.
4. The API key comes ONLY from `os.environ[{key_env!r}]`. No literals
   that look like credentials.
5. Without the key, `search()` must RAISE. Fabricating results instead
   of refusing is the one unforgivable behavior in this codebase.
6. Timeouts on every request (pass `timeout=` to urlopen). Vendor errors
   become raised exceptions or `SearchResult.failure(...)` rows — never
   invented content.

## Facts you must verify, not assume

The vendor's real endpoint paths, parameter names, auth header shape,
and response fields. Read their documentation; do not guess. If a fact
cannot be established from documentation you can actually read, leave a
TODO naming exactly what is missing — an honest gap beats a plausible
guess here, always.

## Definition of done

`deckscope plugins verify {service}` passes clean, and (with the
operator's key set) `deckscope plugins verify {service} --live` shows a
truthful health_check.
"""


def cmd_connect(args: Any) -> int:
    service = (args.service or "").strip().lower().replace(" ", "_")
    if not service.replace("_", "").isalnum():
        _err("Service name must be alphanumeric/underscores.")
        return 2
    target = plugins_dir() / service
    if target.exists() and any(target.iterdir()):
        _err(f"{target} already exists and is not empty. Verify it, or "
             f"remove it to re-scaffold.")
        return 2
    target.mkdir(parents=True, exist_ok=True)

    env_name = f"{service.upper()}_API_KEY"
    manifest = dict(_MANIFEST_TEMPLATE)
    manifest["name"] = service
    manifest["key_env"] = env_name
    (target / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    cls = "".join(w.capitalize() for w in service.split("_")) + "Researcher"
    (target / "connector.py").write_text(
        _STUB.format(service=service, SERVICE=service.upper(), cls=cls),
        encoding="utf-8")
    (target / "WORK_ORDER.md").write_text(
        _WORK_ORDER.format(service=service, key_env=env_name),
        encoding="utf-8")

    _out(f"Scaffolded {target}")
    _out("\nHand the work order to a coding agent from that directory — "
         "for example:")
    _out(f'  cd "{target}"')
    _out('  claude "Complete this connector per WORK_ORDER.md"   # or codex')
    _out("\nThen gate it (nothing loads until this passes):")
    _out(f"  deckscope plugins verify {service}")
    _out("\nFill hosts/needs_key in manifest.json truthfully first — the "
         "harness holds the code to the manifest, so a wrong manifest "
         "fails, it does not excuse.")
    return 0


def command(args: Any) -> int:
    sub = getattr(args, "plugins_cmd", None)
    if sub == "list":
        return cmd_list(args)
    if sub == "verify":
        return cmd_verify(args)
    if sub == "connect":
        return cmd_connect(args)
    _err("Usage: deckscope plugins {list|verify <name> [--live]|connect <service>}")
    return 2
