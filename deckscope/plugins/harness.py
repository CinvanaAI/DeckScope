"""The conformance harness: the deterministic law a connector must pass.

Agent-written code is model output, and this repository's one rule about
model output is that it is never trusted, only verified. The harness is
that verification for connectors, and it runs entirely offline:

1. **Manifest law** — required fields, supported kind, declared hosts,
   named credential env var (``deckscope.plugins.load_manifest``).
2. **Static safety scan (AST)** — the module must not import or invoke
   process/system escape hatches. Forbidden outright: ``subprocess``,
   ``socket``, ``ctypes``, ``pickle``, ``marshal``, ``shutil``,
   ``multiprocessing``, ``eval``, ``exec``, ``compile``, ``__import__``,
   ``os.system``/``os.popen``/``os.exec*``/``os.spawn*``, and writing
   files (``open(..., 'w')``). A connector retrieves and returns; it does
   not run things or persist things.
3. **Egress law** — every URL literal in the source must point at a host
   the manifest declares (subdomains of a declared host count), and only
   ``https``. A connector that builds hosts dynamically fails the scan,
   because a host the harness cannot see is a host nobody approved.
4. **Credential law** — no hardcoded secrets (long high-entropy string
   literals fail), and if ``needs_key`` the source must read exactly the
   manifest's ``key_env`` from the environment.
5. **Interface law** — imported only after 1-4 pass: exactly one
   ``Researcher`` subclass; its ``name`` matches the manifest; class
   attributes ``needs_key``/``key_env`` match; and when ``needs_key``,
   calling ``search()`` without the env var set must RAISE — a connector
   that fabricates results instead of refusing without credentials is the
   exact failure this product exists to prevent.

What the harness cannot check, it says so: it proves the code obeys the
contract, not that the vendor's API returns good data — that is what
``verify --live`` (one health_check call) and the per-run citation audit
are for.
"""
from __future__ import annotations

import ast
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from . import MARKER_NAME, PluginError, content_hash, load_manifest

FORBIDDEN_IMPORTS = {"subprocess", "socket", "ctypes", "pickle", "marshal",
                     "shutil", "multiprocessing", "asyncio", "threading",
                     "importlib"}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_OS_ATTRS = {"system", "popen", "execv", "execve", "execvp",
                      "spawnl", "spawnv", "fork", "remove", "unlink",
                      "rmdir", "rename", "chmod"}


@dataclass
class VerificationReport:
    plugin: str
    problems: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: Dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    return -sum((n / len(s)) * math.log2(n / len(s)) for n in freq.values())


def _host_allowed(host: str, declared: List[str]) -> bool:
    host = host.lower()
    for d in declared:
        d = d.lower()
        if host == d or host.endswith("." + d):
            return True
    return False


def _scan_source(tree: ast.Module, source: str,
                 manifest: Dict[str, Any], report: VerificationReport) -> None:
    say = report.problems.append

    for node in ast.walk(tree):
        # -------- forbidden imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_IMPORTS:
                    say(f"line {node.lineno}: import {alias.name} — a "
                        f"connector retrieves and returns; it does not "
                        f"need {root}")
        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FORBIDDEN_IMPORTS:
                say(f"line {node.lineno}: from {node.module} import ... — "
                    f"{root} is forbidden in connectors")

        # -------- forbidden calls
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_CALLS:
                say(f"line {node.lineno}: {fn.id}() is forbidden")
            if isinstance(fn, ast.Attribute):
                if (isinstance(fn.value, ast.Name) and fn.value.id == "os"
                        and fn.attr in FORBIDDEN_OS_ATTRS):
                    say(f"line {node.lineno}: os.{fn.attr}() is forbidden")
                if fn.attr in FORBIDDEN_CALLS:
                    say(f"line {node.lineno}: .{fn.attr}() is forbidden")
            # open() for writing
            if isinstance(fn, ast.Name) and fn.id == "open":
                mode = ""
                if len(node.args) > 1 and isinstance(node.args[1],
                                                     ast.Constant):
                    mode = str(node.args[1].value)
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = str(kw.value.value)
                if any(c in mode for c in "wax+"):
                    say(f"line {node.lineno}: open(..., {mode!r}) — a "
                        f"connector must not write files")

        # -------- URL literals: https only, declared hosts only
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            for m in re.finditer(r"https?://[^\s\"']+", text):
                url = m.group(0)
                parsed = urlparse(url)
                if parsed.scheme != "https":
                    say(f"line {node.lineno}: {url} — https only")
                host = (parsed.hostname or "").strip()
                if host and not _host_allowed(host, manifest["hosts"]):
                    say(f"line {node.lineno}: contacts {host}, which the "
                        f"manifest does not declare. Every host must be "
                        f"declared so the operator approved it.")
            # -------- hardcoded-secret heuristic
            compact = text.strip()
            if (len(compact) >= 28 and " " not in compact
                    and "/" not in compact and "." not in compact
                    and _entropy(compact) > 4.2):
                say(f"line {node.lineno}: string literal looks like a "
                    f"credential (long, high-entropy). Keys come from the "
                    f"environment variable named in the manifest, never "
                    f"from source.")

    # -------- credential law: needs_key -> reads exactly key_env
    if manifest.get("needs_key"):
        env_name = manifest["key_env"]
        if env_name not in source:
            report.problems.append(
                f"manifest declares needs_key with key_env={env_name!r} "
                f"but the source never references it — the connector "
                f"cannot be obeying the credential rule")

    # -------- egress presence: at least one declared-host URL is used
    if not any(h in source for h in manifest["hosts"]):
        report.problems.append(
            "no declared host appears in the source — either the "
            "connector builds hosts dynamically (forbidden: an invisible "
            "host is an unapproved host) or it contacts nothing")


def verify(plugin_dir: Path, live: bool = False) -> VerificationReport:
    """Run the whole harness. Writes the ``.verified`` marker ONLY on a
    clean pass; removes any stale marker on a failing one."""
    plugin_dir = Path(plugin_dir)
    report = VerificationReport(plugin=plugin_dir.name)
    marker = plugin_dir / MARKER_NAME

    try:
        manifest = load_manifest(plugin_dir)
    except PluginError as exc:
        report.problems.append(str(exc))
        if marker.exists():
            marker.unlink()
        return report

    source = (plugin_dir / manifest["module"]).read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        report.problems.append(f"module does not parse: {exc}")
        if marker.exists():
            marker.unlink()
        return report

    _scan_source(tree, source, manifest, report)

    # -------- interface law (import only after the static laws pass)
    if not report.problems:
        import importlib.util

        from ..research.base import Researcher

        spec = importlib.util.spec_from_file_location(
            f"deckscope_plugin_verify_{plugin_dir.name}",
            plugin_dir / manifest["module"])
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - a crashing import is a finding
            report.problems.append(f"module import failed: "
                                   f"{type(exc).__name__}: {exc}")
        else:
            classes = [obj for obj in vars(mod).values()
                       if isinstance(obj, type)
                       and issubclass(obj, Researcher)
                       and obj is not Researcher]
            if len(classes) != 1:
                report.problems.append(
                    f"expected exactly one Researcher subclass, found "
                    f"{len(classes)}")
            else:
                cls = classes[0]
                if getattr(cls, "name", "") != manifest["name"]:
                    report.problems.append(
                        f"class name attribute {getattr(cls, 'name', '')!r} "
                        f"!= manifest name {manifest['name']!r}")
                if bool(getattr(cls, "needs_key", False)) != bool(
                        manifest["needs_key"]):
                    report.problems.append(
                        "class needs_key does not match the manifest")
                if manifest["needs_key"]:
                    if getattr(cls, "key_env", "") != manifest["key_env"]:
                        report.problems.append(
                            "class key_env does not match the manifest")
                    # The refusal contract: no key -> raise, never invent.
                    saved = os.environ.pop(manifest["key_env"], None)
                    try:
                        inst = cls()
                        try:
                            inst.search("harness contract probe",
                                        max_results=1)
                            report.problems.append(
                                "search() without the key returned instead "
                                "of raising — a connector must refuse "
                                "without credentials, never improvise")
                        except Exception:  # noqa: BLE001 - raising IS the pass
                            report.notes.append(
                                "refuses without credentials: ok")
                    finally:
                        if saved is not None:
                            os.environ[manifest["key_env"]] = saved
                if live and not manifest["needs_key"]:
                    try:
                        health = cls().health_check()
                        report.notes.append(f"live health_check: {health}")
                    except Exception as exc:  # noqa: BLE001
                        report.problems.append(
                            f"live health_check failed: {exc}")

    if report.passed:
        marker.write_text(content_hash(plugin_dir, manifest),
                          encoding="utf-8")
        report.notes.append("verified marker written (hash-bound; any "
                            "edit invalidates it)")
    elif marker.exists():
        marker.unlink()
    return report
