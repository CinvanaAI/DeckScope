"""Check the S-1 corpus against its recorded provenance.

Every excerpt in `market-corpus/` is listed in `meta/sources.md` with a checksum
and an EDGAR accession URL. This confirms the files on disk are the ones the
schema was derived from.

It deliberately does NOT re-download. A corpus that silently refreshes itself
from the network is not a fixed reference — the schema was derived from specific
bytes on a specific day, and if those bytes change the right response is to
notice, not to absorb it.

    python scripts/verify_corpus.py
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "market-corpus"
MANIFEST = CORPUS / "meta" / "sources.md"

ROW = re.compile(
    r"^\|\s*`([^`]+)`\s*\|"      # file
    r"[^|]*\|[^|]*\|[^|]*\|"      # company, cik, accession
    r"[^|]*\|[^|]*\|[^|]*\|"      # form, filed, sic
    r"\s*`([0-9a-f]+)`\s*\|"      # checksum
    r"\s*([\d,]+)\s*\|", re.M)


def main() -> int:
    if not MANIFEST.exists():
        print(f"No manifest at {MANIFEST}")
        return 2

    rows = ROW.findall(MANIFEST.read_text(encoding="utf-8"))
    if not rows:
        print("The manifest lists no files. That is a defect in the manifest, "
              "not a clean result — a checker that checks nothing must not "
              "report success.")
        return 2

    problems = 0
    for rel, digest, size in rows:
        path = CORPUS / rel
        if not path.exists():
            print(f"MISSING  {rel}")
            problems += 1
            continue
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()[:len(digest)]
        expected_size = int(size.replace(",", ""))
        if actual != digest:
            print(f"CHANGED  {rel}\n         recorded {digest}, on disk {actual}")
            problems += 1
        elif len(data) != expected_size:
            print(f"SIZE     {rel}: recorded {expected_size:,}, "
                  f"on disk {len(data):,}")
            problems += 1
        else:
            print(f"ok       {rel}")

    print()
    if problems:
        print(f"{problems} problem(s). If a file was changed deliberately, "
              f"update the checksum in {MANIFEST.relative_to(ROOT)} in the same "
              f"commit — the manifest is the citation trail for SCHEMA.md.")
        return 1
    print(f"{len(rows)} file(s) match their recorded provenance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
