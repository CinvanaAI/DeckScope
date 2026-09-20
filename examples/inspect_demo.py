"""Trace one synthetic demo claim through the actual generated JSON report."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from deckscope.findings import collect


def inspect(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report["config"]["provider"]["name"] != "mock":
        raise ValueError("Use the bundled mock demo; this projection is not for live reports.")
    comparison = report["comparisons"]["investor"]
    findings = collect(comparison)
    sources = {source["sid"]: source for source in report["references"]["sources"]}
    claim = next(row for row in comparison["claim_audit"] if row["id"] == "C1")
    evidence = []
    for sid in claim["source_ids"]:
        source = sources[sid]
        if sid not in report["references"]["admitted"] or source["backend"] != "demo_fixture":
            raise ValueError("The selected claim must resolve to admitted synthetic fixture evidence.")
        evidence.append({key: source[key] for key in ("sid", "title", "snippet", "backend", "status")})
    counts = findings.counts
    expected = {"claims_examined": 6, "contested": 2, "omissions": 2, "unverified": 2}
    for key, value in expected.items():
        assert counts[key] == value, (key, counts)
    assert evidence, "C1 must carry a traceable source"
    return {
        "synthetic": True,
        "live_research_calls": 0,
        "counts": counts,
        "trace": {"claim": {key: claim[key] for key in ("id", "claim", "assessment", "delta", "source_ids")}, "evidence": evidence},
        "interpretation": "These are fixture claims and fixture evidence, not established market facts. Counts are computed by the findings layer; the assessment originates in mock analysis.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="acme_flow_full.json from deckscope demo --format json")
    print(json.dumps(inspect(parser.parse_args().report), indent=2, ensure_ascii=False))
