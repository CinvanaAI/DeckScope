"""Verified connector plugins: licensed-access research backends that the
operator installs, a coding agent may write, and the harness must approve.

The problem this solves: no tool can pre-build a connector for every data
subscription an operator might hold (Counterpoint, Bloomberg, a trade
association's portal). The flywheel answer is that a coding agent writes
the connector against a published contract — and because agent-written
code is model output, it is never trusted, only verified. The rules:

- A plugin lives in its own directory under the documented app dir
  (``app_dir()/plugins/<name>/``) with a ``manifest.json`` and one module.
- ``deckscope plugins verify <name>`` runs the deterministic conformance
  harness (see ``harness.py``) and, only on a clean pass, writes a
  ``.verified`` marker binding the SHA-256 of exactly what was checked.
- The loader refuses anything unverified, and any edit after verification
  invalidates the marker — re-verify or it will not load.
- Credentials never live in plugin code: the manifest names ``key_env``
  and the connector reads it from the environment, exactly like the
  built-in backends.
- Plugin researchers are web backends, so NDA mode excludes them the same
  way it excludes every researcher: under ``--nda`` research is off, and
  no plugin is consulted.

v1 supports the ``researcher`` kind only — the ``Researcher`` interface in
``deckscope/research/base.py``. A ``dataset`` kind (the structured-backend
protocol) is a declared follow-up, refused by the harness until it exists
rather than half-accepted.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

MANIFEST_NAME = "manifest.json"
MARKER_NAME = ".verified"
SUPPORTED_KINDS = ("researcher",)

#: Manifest fields, all required. Kept deliberately small: a manifest is a
#: declaration the harness can hold the code to, not a configuration file.
MANIFEST_FIELDS = ("name", "kind", "module", "hosts", "needs_key",
                   "key_env", "description")


class PluginError(RuntimeError):
    """A plugin problem the caller should show to the operator verbatim."""


def plugins_dir() -> Path:
    from ..settings import app_dir

    return app_dir() / "plugins"


def load_manifest(plugin_dir: Path) -> Dict[str, Any]:
    path = plugin_dir / MANIFEST_NAME
    if not path.is_file():
        raise PluginError(f"{plugin_dir.name}: no {MANIFEST_NAME}")
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise PluginError(f"{plugin_dir.name}: manifest is not valid JSON "
                          f"({exc})") from exc
    missing = [f for f in MANIFEST_FIELDS if f not in m]
    if missing:
        raise PluginError(f"{plugin_dir.name}: manifest missing "
                          f"{', '.join(missing)}")
    if m["kind"] not in SUPPORTED_KINDS:
        raise PluginError(
            f"{plugin_dir.name}: kind {m['kind']!r} is not supported — "
            f"v1 supports {', '.join(SUPPORTED_KINDS)} only. A 'dataset' "
            f"kind is a declared follow-up, not a silent accept.")
    if not isinstance(m["hosts"], list) or not all(
            isinstance(h, str) and h for h in m["hosts"]):
        raise PluginError(f"{plugin_dir.name}: 'hosts' must be a non-empty "
                          "list of hostnames the connector may contact")
    if not m["hosts"]:
        raise PluginError(f"{plugin_dir.name}: a connector that contacts "
                          "no hosts retrieves nothing — declare them")
    if m["needs_key"] and not str(m.get("key_env", "")).strip():
        raise PluginError(f"{plugin_dir.name}: needs_key without key_env — "
                          "the harness cannot hold the code to an unnamed "
                          "credential rule")
    module = plugin_dir / m["module"]
    if not module.is_file() or module.suffix != ".py":
        raise PluginError(f"{plugin_dir.name}: module {m['module']!r} is "
                          "missing or not a .py file")
    return m


def content_hash(plugin_dir: Path, manifest: Dict[str, Any]) -> str:
    """SHA-256 over exactly what verification examined: manifest + module.

    Any byte of drift after verification invalidates the marker — an
    edited connector is an unverified connector.
    """
    h = hashlib.sha256()
    h.update((plugin_dir / MANIFEST_NAME).read_bytes())
    h.update((plugin_dir / manifest["module"]).read_bytes())
    return h.hexdigest()


def is_verified(plugin_dir: Path) -> bool:
    marker = plugin_dir / MARKER_NAME
    if not marker.is_file():
        return False
    try:
        manifest = load_manifest(plugin_dir)
    except PluginError:
        return False
    recorded = marker.read_text(encoding="utf-8").strip()
    return recorded == content_hash(plugin_dir, manifest)


def discover() -> List[Dict[str, Any]]:
    """Every plugin directory, with its manifest and verification state.

    Never raises for a broken plugin — a broken directory is a row with
    its problem stated, because `plugins list` must be able to show the
    operator what is wrong.
    """
    root = plugins_dir()
    rows: List[Dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        row: Dict[str, Any] = {"dir": str(child), "name": child.name}
        try:
            manifest = load_manifest(child)
            row["manifest"] = manifest
            row["verified"] = is_verified(child)
        except PluginError as exc:
            row["manifest"] = None
            row["verified"] = False
            row["problem"] = str(exc)
        rows.append(row)
    return rows


def load_researcher_class(name: str) -> Optional[type]:
    """Import a VERIFIED plugin's Researcher subclass, or None.

    The import happens only after the marker's hash matches the current
    bytes — code that was never harness-approved, or was edited since,
    never executes. Called by the researcher registry as a fallback when
    a requested backend name is not built in.
    """
    plugin_dir = plugins_dir() / name
    if not plugin_dir.is_dir():
        return None
    try:
        manifest = load_manifest(plugin_dir)
    except PluginError:
        return None
    if not is_verified(plugin_dir):
        raise PluginError(
            f"plugin '{name}' exists but is not verified (or was edited "
            f"since verification). Run: deckscope plugins verify {name}")

    import importlib.util

    from ..research.base import Researcher

    spec = importlib.util.spec_from_file_location(
        f"deckscope_plugin_{name}", plugin_dir / manifest["module"])
    if spec is None or spec.loader is None:
        raise PluginError(f"plugin '{name}': module could not be loaded")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for obj in vars(mod).values():
        if (isinstance(obj, type) and issubclass(obj, Researcher)
                and obj is not Researcher):
            return obj
    raise PluginError(f"plugin '{name}': no Researcher subclass found in "
                      f"{manifest['module']}")
