"""Where DeckScope keeps the answers you gave the setup wizard.

Config lives at ~/.deckscope/config.yaml (or %APPDATA%\\DeckScope on Windows).
API keys are stored in a sibling `.env` with owner-only permissions, never inside
the config file, so the config can be shared or committed without leaking secrets.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Dict, Optional


def app_dir() -> Path:
    """The per-user settings directory, created on demand."""
    override = os.getenv("DECKSCOPE_HOME")
    if override:
        p = Path(override)
    elif os.name == "nt":
        p = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "DeckScope"
    else:
        p = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "deckscope"
        if (Path.home() / ".deckscope").exists():
            p = Path.home() / ".deckscope"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return app_dir() / "config.yaml"


def env_path() -> Path:
    return app_dir() / ".env"


def default_cache_dir() -> Path:
    """Private per-user cache.

    Cache entries hold cleartext deck extractions and model output, so they belong
    beside the settings rather than in whatever directory the command was run
    from — which is frequently a repository or a synced folder.
    """
    d = app_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    try:
        restrict_dir_to_owner(d)
    except Exception:  # noqa: BLE001
        pass
    return d


def restrict_dir_to_owner(path: Path) -> bool:
    """Owner-only on a directory, with a real ACL on Windows."""
    import stat as _stat

    try:
        os.chmod(path, _stat.S_IRWXU)
    except Exception:  # noqa: BLE001
        pass
    if os.name != "nt":
        try:
            return (path.stat().st_mode & 0o077) == 0
        except OSError:
            return False
    user = os.environ.get("USERNAME") or os.environ.get("USER")
    if not user:
        return False
    try:
        import subprocess
        res = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F"],
            capture_output=True, text=True, timeout=15)
        return res.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def default_output_dir() -> Path:
    d = Path.home() / "Documents" / "DeckScope Reports"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        d = app_dir() / "reports"
        d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------ config

def load_settings() -> Dict[str, Any]:
    p = config_path()
    if not p.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        import json
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}


def save_settings(data: Dict[str, Any]) -> Path:
    p = config_path()
    try:
        import yaml
        p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                     encoding="utf-8")
    except ImportError:
        import json
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


def is_configured() -> bool:
    return config_path().exists() and bool(load_settings().get("provider"))


# -------------------------------------------------------------------- keys

def load_env(into_environ: bool = True) -> Dict[str, str]:
    """Read the saved key file. Existing environment variables always win."""
    p = env_path()
    out: Dict[str, str] = {}
    if not p.exists():
        return out
    for raw in p.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        out[k] = v
        if into_environ and not os.getenv(k):
            os.environ[k] = v
    return out


def save_key(name: str, value: str) -> Path:
    """Store one secret, owner-readable only."""
    p = env_path()
    existing = load_env(into_environ=False)
    existing[name] = value
    body = ("# DeckScope secrets — keep this file private.\n"
            "# Delete a line to remove that key.\n"
            + "".join(f"{k}={v}\n" for k, v in existing.items()))
    p.write_text(body, encoding="utf-8")
    restrict_to_owner(p)
    os.environ[name] = value
    return p


def restrict_to_owner(path: Path) -> bool:
    """Make a file readable only by its owner. Returns True if that was achieved.

    `os.chmod(0600)` is close to a no-op on Windows — the mode bits map onto the
    read-only attribute, not onto an ACL — so a key file there stayed readable by
    other accounts on the machine while the docs claimed otherwise. On Windows we
    ask icacls to strip inheritance and grant the current user alone.
    """
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:  # noqa: BLE001
        pass

    if os.name != "nt":
        try:
            return (path.stat().st_mode & 0o077) == 0
        except OSError:
            return False

    user = os.environ.get("USERNAME") or os.environ.get("USER")
    if not user:
        return False
    try:
        import subprocess

        # /inheritance:r drops inherited ACEs; /grant:r replaces any existing
        # grant for this user rather than adding to it.
        res = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
            capture_output=True, text=True, timeout=15)
        return res.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def forget_key(name: str) -> None:
    existing = load_env(into_environ=False)
    existing.pop(name, None)
    env_path().write_text(
        "# DeckScope secrets — keep this file private.\n"
        + "".join(f"{k}={v}\n" for k, v in existing.items()), encoding="utf-8")
    os.environ.pop(name, None)


def has_key(name: str) -> bool:
    return bool(os.getenv(name) or load_env(into_environ=False).get(name))


def masked(value: str) -> str:
    if not value:
        return "(not set)"
    return value[:6] + "…" + value[-4:] if len(value) > 14 else "…" + value[-3:]


# ---------------------------------------------------------------- to config

def settings_to_runconfig(overrides: Optional[Dict[str, Any]] = None):
    """Turn saved settings into a RunConfig, applying CLI overrides on top."""
    from .config import load_config

    load_env()
    data = load_settings()
    data.pop("_wizard", None)
    # `panel` is read by the CLI, not by RunConfig.
    data.pop("panel", None)
    merged: Dict[str, Any] = dict(data)
    for k, v in (overrides or {}).items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return load_config(None, **merged)
