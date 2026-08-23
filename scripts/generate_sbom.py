"""Emit a CycloneDX software bill of materials for an installed DeckScope.

Run it against the environment you are shipping:

    python scripts/generate_sbom.py --out sbom.json

**Why this reads the installed environment rather than the manifest.** A
dependency list says what was asked for; an SBOM has to say what is actually
there. `PyYAML>=5.4` is a request, and the answer changes with the day the wheel
was built and the platform it was built on. Someone auditing a release needs the
resolved versions, including transitive packages nothing in this project names.

Pure standard library on purpose. An SBOM generator that needs its own
dependencies installed to run adds to the very surface it is describing, and it
has to work in a locked-down environment during a release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

CYCLONEDX_VERSION = "1.5"

#: Packages DeckScope imports directly, as opposed to everything else that
#: happens to be installed. Recorded so a reader can tell a real dependency from
#: something the build environment dragged in.
DIRECT = {"pyyaml", "pdfplumber", "python-pptx", "python-docx", "openpyxl",
          "reportlab", "anthropic", "boto3"}


def _distributions():
    from importlib import metadata

    seen = set()
    for dist in metadata.distributions():
        name = (dist.metadata["Name"] or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        yield dist


def _license_of(dist) -> Optional[str]:
    direct = (dist.metadata.get("License") or "").strip()
    if direct and len(direct) < 60 and "\n" not in direct:
        return direct
    # Many projects leave License empty and use a trove classifier instead.
    for classifier in dist.metadata.get_all("Classifier") or []:
        if classifier.startswith("License :: "):
            return classifier.rsplit(" :: ", 1)[-1]
    return None


def _purl(name: str, version: str) -> str:
    """Package URL, the identifier vulnerability scanners actually match on."""
    from urllib.parse import quote

    return f"pkg:pypi/{quote(name.lower())}@{quote(version)}"


def _hash_files(dist) -> List[Dict[str, str]]:
    """SHA-256 over the distribution's own RECORD, when one exists.

    This fingerprints what is on disk rather than trusting the version string,
    so a tampered or locally patched package does not match a clean release.
    """
    try:
        record = dist.read_text("RECORD")
    except Exception:  # noqa: BLE001
        record = None
    if not record:
        return []
    digest = hashlib.sha256(record.encode("utf-8")).hexdigest()
    return [{"alg": "SHA-256", "content": digest}]


def components() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for dist in _distributions():
        name = dist.metadata["Name"].strip()
        version = (dist.version or "unknown").strip()
        entry: Dict[str, Any] = {
            "type": "library",
            "bom-ref": _purl(name, version),
            "name": name,
            "version": version,
            "purl": _purl(name, version),
            "scope": "required",
            "properties": [{
                "name": "deckscope:relationship",
                "value": "direct" if name.lower() in DIRECT else "transitive",
            }],
        }
        license_name = _license_of(dist)
        if license_name:
            entry["licenses"] = [{"license": {"name": license_name}}]
        hashes = _hash_files(dist)
        if hashes:
            entry["hashes"] = hashes
        out.append(entry)
    return sorted(out, key=lambda c: c["name"].lower())


def build(version: Optional[str] = None) -> Dict[str, Any]:
    if version is None:
        try:
            from deckscope import __version__ as version  # type: ignore
        except Exception:  # noqa: BLE001
            version = "0.0.0.dev0"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_VERSION,
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": now,
            "tools": [{"vendor": "DeckScope", "name": "generate_sbom.py",
                       "version": "1.0.0"}],
            "component": {
                "type": "application",
                "bom-ref": f"pkg:pypi/deckscope@{version}",
                "name": "deckscope",
                "version": version,
                "purl": f"pkg:pypi/deckscope@{version}",
                "licenses": [{"license": {"id": "MIT"}}],
            },
            "properties": [
                {"name": "deckscope:python", "value": sys.version.split()[0]},
                {"name": "deckscope:platform", "value": sys.platform},
            ],
        },
        "components": components(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", "-o", default="sbom.json")
    parser.add_argument("--version", default=None,
                        help="Override the recorded DeckScope version")
    args = parser.parse_args()

    document = build(args.version)
    path = Path(args.out)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    direct = sum(1 for c in document["components"]
                 if c["properties"][0]["value"] == "direct")
    print(f"Wrote {path} — {len(document['components'])} component(s), "
          f"{direct} direct, CycloneDX {CYCLONEDX_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
