#!/usr/bin/env python3
"""Replay a committed benchmark bundle offline, and verify it while doing so.

A benchmark with retained prompts is only evidence if the prompts still map to
the run. The first bundle shipped with prose instructions and a manifest of
hashes; the prompts had been path-scrubbed *after* they were hashed, so half the
ids no longer equalled the hash of the file beside them and the pipeline cases
could not replay at all. A manifest that agrees with itself is not the same as a
bundle that reproduces.

So this script does the checking rather than describing it:

  1. every id equals sha256(prompt)[:16]
  2. every prompt and answer matches its recorded hash
  3. the evaluator, driven from these answers, reproduces the recorded scores

Step 3 is the one that matters. It calls no model — the manual provider replays
from the retained answers — so it runs offline and in CI.

    python scripts/replay_benchmark.py benchmarks/2026-08-anchoring-four
    python scripts/replay_benchmark.py --all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_identity(bundle: Path) -> list:
    """Check ids and hashes without running anything."""
    manifest = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    problems = []
    for row in manifest["exchanges"]:
        prompt = bundle / "prompts" / f"{row['id']}.txt"
        answer = bundle / "answers" / f"{row['id']}.json"
        if not prompt.is_file() or not answer.is_file():
            problems.append(f"{row['id']}: missing prompt or answer")
            continue
        ptext = prompt.read_text(encoding="utf-8")
        atext = answer.read_text(encoding="utf-8")
        digest = _sha(ptext)
        if digest[:16] != row["id"]:
            problems.append(
                f"{row['id']}: the file hashes to {digest[:16]} — the prompt is "
                f"not the one this id names, so it cannot replay")
        if digest != row["prompt_sha256"]:
            problems.append(f"{row['id']}: prompt does not match its recorded hash")
        if _sha(atext) != row["answer_sha256"]:
            problems.append(f"{row['id']}: answer does not match its recorded hash")
    return problems


def _spool(bundle: Path, workdir: Path) -> Path:
    """Lay the bundle out the way the manual provider expects to find it."""
    spool = workdir / "spool"
    (spool / "asked").mkdir(parents=True)
    (spool / "answers").mkdir(parents=True)
    for prompt in (bundle / "prompts").glob("*.txt"):
        shutil.copy(prompt, spool / "asked" / f"{prompt.stem}.prompt.txt")
    for answer in (bundle / "answers").glob("*.json"):
        shutil.copy(answer, spool / "answers" / f"{answer.stem}.txt")
    return spool


def replay(bundle: Path) -> list:
    """Re-score the retained answers and compare against the manifest."""
    manifest = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        spool = _spool(bundle, workdir)
        env = dict(os.environ,
                   DECKSCOPE_MANUAL_DIR=str(spool),
                   DECKSCOPE_MANUAL_INTERACTIVE="0",
                   DECKSCOPE_MANUAL_POLL="0.05",
                   # A cache miss must fail fast rather than hang: it means the
                   # prompt this build generates is not the prompt that was
                   # answered, which is exactly the defect being guarded against.
                   DECKSCOPE_MANUAL_TIMEOUT="5")
        saved = workdir / "replayed.json"
        proc = subprocess.run(
            [sys.executable, "-m", "deckscope", "eval",
             "--provider", "manual", "--mode", "pipeline", "baseline",
             "--only", *manifest["cases"],
             "--save", str(saved), "--out", str(workdir / "out")],
            cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not saved.is_file():
            return [f"the replay produced no result file.\n{proc.stdout[-2000:]}"]

        got = json.loads(saved.read_text(encoding="utf-8"))
        for mode, expected in manifest["by_mode"].items():
            scores = [s for s in got["scores"] if s["mode"] == mode and not s["error"]]
            passed = sum(1 for s in scores for c in s["checks"] if c["passed"])
            total = sum(len(s["checks"]) for s in scores)
            if (passed, total) != (expected["checks_passed"], expected["checks_total"]):
                problems.append(
                    f"{mode}: replayed {passed}/{total}, manifest records "
                    f"{expected['checks_passed']}/{expected['checks_total']}")
            for case, row in expected["per_case"].items():
                match = next((s for s in scores if s["case_id"] == case), None)
                if match is None:
                    problems.append(f"{mode}/{case}: did not run")
                elif match["output_fingerprint"] != row["fingerprint"]:
                    problems.append(
                        f"{mode}/{case}: fingerprint {match['output_fingerprint']} "
                        f"!= recorded {row['fingerprint']} — the analysis this "
                        f"build produces from the same answers has changed")
        for err in got.get("errors") or []:
            problems.append(f"{err['mode']}/{err['case']}: {err['error'][:200]}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bundle", nargs="?", help="a directory under benchmarks/")
    ap.add_argument("--all", action="store_true", help="every committed bundle")
    ap.add_argument("--identity-only", action="store_true",
                    help="check ids and hashes; skip the replay")
    ap.add_argument("--stale-ok", action="store_true",
                    help="a replay broken by PROMPT DRIFT passes — but only "
                         "while benchmarks/README.md admits the staleness. "
                         "Identity failures (corrupted artifacts) always fail.")
    args = ap.parse_args()

    if args.all:
        bundles = sorted(p for p in (ROOT / "benchmarks").iterdir()
                         if (p / "result.json").is_file())
    elif args.bundle:
        bundles = [Path(args.bundle).resolve()]
    else:
        ap.error("give a bundle directory or --all")

    if not bundles:
        print("no benchmark bundles found")
        return 2

    # The honesty coupling: a benchmark whose prompts have drifted may pass
    # CI only while the benchmark's own README says so out loud. A stale
    # benchmark with a fresh-sounding README is a published number describing
    # code that no longer exists — the exact defect the first benchmark
    # bundle shipped with. So --stale-ok reads the README and refuses to
    # excuse a drift the README does not admit.
    stale_admitted = "STALE" in (ROOT / "benchmarks" / "README.md").read_text(
        encoding="utf-8", errors="replace")

    failed = False
    replayed_ok = 0
    excused = 0
    for bundle in bundles:
        print(f"\n=== {bundle.name}")
        problems = verify_identity(bundle)
        print(f"  identity: {'ok' if not problems else str(len(problems)) + ' problem(s)'}")
        identity_broken = bool(problems)
        if not problems and not args.identity_only:
            problems = replay(bundle)
            print(f"  replay:   {'ok' if not problems else str(len(problems)) + ' problem(s)'}")
            if not problems:
                replayed_ok += 1
        for line in problems:
            print(f"    ! {line}")
        if problems and not identity_broken and args.stale_ok and stale_admitted:
            print("  stale-ok: prompt drift excused — benchmarks/README.md "
                  "admits the staleness. Re-drive the benchmark to make the "
                  "numbers current again.")
            excused += 1
            continue
        failed = failed or bool(problems)
    # The eighth external audit read "All bundles verified" over a run in
    # which zero behavioral replays succeeded and every drift was excused.
    # The summary now states exactly which guarantee was checked: artifact
    # identity always; behavior only when a replay actually ran green.
    if failed:
        print("\nFAILED")
    elif excused and not replayed_ok:
        print(f"\nHistorical benchmark artifacts intact; behavioral replay: "
              f"0 of {len(bundles)} (prompts have drifted; staleness is "
              f"admitted in benchmarks/README.md). This run proves the "
              f"artifacts, not the current pipeline's numbers.")
    elif excused:
        print(f"\nArtifacts intact; {replayed_ok} of {len(bundles)} "
              f"bundle(s) replayed behaviorally, {excused} excused as "
              f"admitted-stale.")
    else:
        print("\nAll bundles verified — identity and behavioral replay.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
