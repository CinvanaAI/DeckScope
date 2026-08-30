"""Check the project's documented claims against what the code actually does.

Three external audits in a row found the same class of defect wearing
different clothes: a document asserting something the code no longer did —
a cost multiple from an older measurement, a storage path the code had
moved away from, "all gates pass" written ahead of the run that decides it,
a surface documented on one interface and missing from another. Each was
fixed by hand and pinned by a test about that one claim. This script is the
class-level fix: the claims that have drifted before, or are of the shape
that drifts, are re-derived from the current tree on every run.

Every check reads BOTH sides from the tree — the document and the code — so
a change to either side that breaks the correspondence fails CI, whichever
direction the drift ran.

Run: python scripts/check_claims.py
Exit 0 when every claim holds; 1 with a list of the ones that do not.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, List

ROOT = Path(__file__).resolve().parent.parent


def audit_gate_language(root: Path) -> List[str]:
    """SYSTEM_AUDIT.md's own standing rule, enforced on its own prose.

    The rule: gate status is the hosted run's status for the exact commit,
    and the document may never announce passed gates ahead of that run. The
    first draft after writing the rule broke it — "On this branch the gates
    pass" in the Verdict, directly below a CI table saying "hosted run
    pending". Caught while building this checker, which is the argument for
    the checker.
    """
    doc = root / "docs" / "SYSTEM_AUDIT.md"
    text = doc.read_text(encoding="utf-8")
    problems = []
    if "Hosted CI has the last word" not in text:
        problems.append(
            "SYSTEM_AUDIT.md no longer says 'Hosted CI has the last word' — "
            "the standing rule's anchor sentence is gone")
    for i, line in enumerate(text.splitlines(), 1):
        # The blockquote IS the rule stating the forbidden phrase; prose
        # elsewhere quoting an auditor gets no such pass — an audit quote
        # asserting green gates is exactly the claim the rule forbids.
        if line.lstrip().startswith(">"):
            continue
        if re.search(r"gates\s+pass", line):
            problems.append(
                f"SYSTEM_AUDIT.md:{i} says 'gates pass' outside the standing "
                f"rule — forbidden ahead of the hosted run: {line.strip()!r}")
    return problems


def benchmark_staleness_admitted(root: Path) -> List[str]:
    """If CI excuses benchmark prompt drift, the README must admit it.

    ci.yml runs the replay with --stale-ok; that flag only excuses drift
    while benchmarks/README.md contains the STALE marker (the coupling lives
    in replay_benchmark.py). This closes the remaining gap: someone
    "cleaning up" the README's STALE paragraph without re-driving the
    benchmark would leave CI green and the published numbers describing
    prompts that no longer exist.
    """
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    if "--stale-ok" not in ci:
        return []  # CI demands a fresh replay; no admission needed
    readme = root / "benchmarks" / "README.md"
    if not readme.is_file():
        return ["ci.yml uses --stale-ok but benchmarks/README.md is missing"]
    if "STALE" not in readme.read_text(encoding="utf-8", errors="replace"):
        return [
            "ci.yml excuses benchmark prompt drift (--stale-ok) but "
            "benchmarks/README.md no longer contains the STALE admission — "
            "either re-drive the benchmark and drop the flag, or restore "
            "the admission"]
    return []


def storage_under_app_dir(root: Path) -> List[str]:
    """INSTALL.md's one-location table: panels live under the app dir.

    The second external audit found panels in an undocumented
    ~/.deckscope/panels while the docs promised one location. Re-derived
    here by importing the actual functions in a clean subprocess with
    DECKSCOPE_HOME pointed at a temp dir — not by grepping the source for
    a path literal that a refactor could route around.
    """
    code = (
        "import os, sys\n"
        "from deckscope.settings import app_dir\n"
        "from marketreport.library import default_dir\n"
        "app, panels = str(app_dir()), default_dir()\n"
        "ok = os.path.abspath(panels).startswith(os.path.abspath(app))\n"
        "print('OK' if ok else f'panels at {panels!r}, app dir {app!r}')\n")
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=str(root), text=True,
            capture_output=True, encoding="utf-8",
            env={**__import__("os").environ, "DECKSCOPE_HOME": tmp,
                 "PYTHONDONTWRITEBYTECODE": "1"})
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return [f"storage check could not run: {(proc.stderr or '')[-300:]}"]
    if out != "OK":
        return [f"INSTALL.md documents panels under the app dir, but "
                f"the code disagrees: {out}"]
    return []


def panel_cost_multiple(root: Path) -> List[str]:
    """The prose cost figure must match the measured table it points at.

    PANEL.md's prose says "roughly N× the single-run input tokens (the
    table below shows the exact multiple from the last measured run)" and
    FAQ.md repeats the figure. The measured multiple lives in PANEL.md's
    results table. An earlier draft said "3-4×" from arithmetic while the
    table measured 12.7× — the audit caught it; this keeps it caught.
    """
    panel = (root / "docs" / "PANEL.md").read_text(encoding="utf-8")
    faq = (root / "docs" / "FAQ.md").read_text(encoding="utf-8")
    measured = re.search(
        r"^\|\s*panel[^|]*\|[^|]*\|[^|]*\|\s*([\d.]+)×\s*\|", panel, re.M)
    if not measured:
        return ["PANEL.md's results table no longer has a measured panel "
                "cost multiple — the prose '12×' now points at nothing"]
    exact = float(measured.group(1))
    problems = []
    # README repeats the same table; its multiple must be the same number.
    # The fourth audit caught README saying 12.7x while a fresh eval
    # measured 10.7x — and this checker passing, because it only coupled
    # PANEL.md's prose to PANEL.md's table.
    readme_path = root / "README.md"
    rm = None
    if readme_path.is_file():
        rm = re.search(
            r"panel \(three panelists\)[^|]*\|[^|]*\|[^|]*\|\s*([\d.]+)×",
            readme_path.read_text(encoding="utf-8"))
    if rm and abs(float(rm.group(1)) - exact) > 0.05:
        problems.append(
            f"README.md's panel table says {rm.group(1)}× but PANEL.md's "
            f"measures {exact:g}× — same table, two numbers")
    for name, text in (("PANEL.md", panel), ("FAQ.md", faq)):
        for claim in re.finditer(
                r"(\d+(?:\.\d+)?)×\s+the\s+single-run\s+input\s+tokens", text):
            said = float(claim.group(1))
            if abs(said - exact) > 1.0:
                problems.append(
                    f"{name} says {said:g}× the single-run input tokens, but "
                    f"PANEL.md's table measures {exact:g}× — one of them is "
                    f"describing a run that no longer exists")
    return problems


def mcp_surface_alignment(root: Path) -> List[str]:
    """SYSTEM_AUDIT claims MCP analyze_deck accepts market_reports.

    The third audit's surface-alignment finding: the CLI and the app had
    the option, the MCP tool did not. The doc now claims parity; hold the
    code to it — the schema must declare the input and the handler must
    both read it and return the result.
    """
    src = (root / "deckscope" / "mcp_server.py").read_text(encoding="utf-8")
    problems = []
    if '"market_reports"' not in src:
        problems.append(
            "SYSTEM_AUDIT.md claims MCP analyze_deck accepts market_reports, "
            "but deckscope/mcp_server.py never mentions it")
    elif src.count("market_reports") < 3:
        problems.append(
            "mcp_server.py mentions market_reports fewer than three times — "
            "expected schema + handler read + payload return; the surface "
            "parity SYSTEM_AUDIT.md claims looks partial")
    return problems


def deck_formats_as_documented(root: Path) -> List[str]:
    """FIRST_RUN.md: 'PDF, PPTX, DOCX, and Markdown decks all work.'

    Each named format must be in the loader's SUPPORTED_EXTENSIONS — the
    doc is the promise a first-time user acts on with their own deck in
    hand, which makes it the worst possible place for drift.
    """
    sys.path.insert(0, str(root))
    try:
        from deckscope.ingest import SUPPORTED_EXTENSIONS
    finally:
        sys.path.pop(0)
    doc = (root / "docs" / "FIRST_RUN.md").read_text(encoding="utf-8")
    claim = re.search(r"([A-Z][A-Za-z, ]+) decks all work", doc)
    if not claim:
        return ["FIRST_RUN.md no longer states which deck formats work — "
                "the first-run promise this check pins has been removed, "
                "not just moved (update this check if it moved)"]
    named = {w.strip().lower() for w in
             re.split(r",| and ", claim.group(1)) if w.strip()}
    exts = {e.lstrip(".") for e in SUPPORTED_EXTENSIONS}
    aliases = {"markdown": "md"}
    missing = {n for n in named if aliases.get(n, n) not in exts}
    if missing:
        return [f"FIRST_RUN.md promises formats the loader does not "
                f"support: {sorted(missing)} (loader has {sorted(exts)})"]
    return []


def runner_reports_the_split(root: Path) -> List[str]:
    """SYSTEM_AUDIT claims the runner prints the function/class split.

    That line exists so a collection regression (419 tests silently not
    running) is visible on every run. If someone simplifies the summary
    line away, the claim and the alarm both die silently.
    """
    src = (root / "scripts" / "run_tests.py").read_text(encoding="utf-8")
    if "functions" not in src or "class methods" not in src:
        return ["scripts/run_tests.py no longer prints the functions/"
                "class-methods split that SYSTEM_AUDIT.md claims makes "
                "collection regressions visible"]
    return []


def lead_claims_match(root: Path) -> List[str]:
    """pyproject's description and README's lead must tell one story.

    The third audit found pyproject describing 'a pitch-deck analyzer'
    while the README led with market reports. Both now lead with the
    evidence-first framing; keep the load-bearing words shared.
    """
    desc = re.search(r'^description\s*=\s*"(.+)"',
                     (root / "pyproject.toml").read_text(encoding="utf-8"),
                     re.M)
    if not desc:
        return ["pyproject.toml has no description"]
    lead = "\n".join((root / "README.md").read_text(
        encoding="utf-8").splitlines()[:10]).lower()
    problems = []
    for word in ("market report", "traceable", "deck"):
        if word not in desc.group(1).lower() or word not in lead:
            problems.append(
                f"pyproject description and README lead no longer both "
                f"carry {word!r} — the one-story alignment the third "
                f"audit asked for has drifted")
    return problems


def storage_inventory_is_complete(root: Path) -> List[str]:
    """INSTALL.md's storage table claims to be the complete inventory.

    The fourth external audit falsified it: the web app wrote uploaded deck
    copies to uploads/ and the table did not mention them. This re-derives
    the inventory from the code — every `app_dir() / "name"` (and the
    os.path.join spelling) across both packages — and requires each name to
    appear in INSTALL.md. A new write location without a documentation row
    is now a red build, not a finding for auditor number five.
    """
    pattern1 = re.compile(r'app_dir\(\)\s*/\s*"([^"\.][^"]*)"')
    pattern2 = re.compile(r'os\.path\.join\(str\(app_dir\(\)\),\s*"([^"]+)"')
    names = set()
    for pkg in ("deckscope", "marketreport"):
        for f in (root / pkg).rglob("*.py"):
            src = f.read_text(encoding="utf-8", errors="replace")
            names.update(pattern1.findall(src))
            names.update(pattern2.findall(src))
    install = (root / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    problems = []
    for name in sorted(names):
        if name not in install:
            problems.append(
                f"the code writes to <app dir>/{name} but docs/INSTALL.md "
                f"never mentions it — the storage table claims completeness")
    return problems


CHECKS: List[Callable[[Path], List[str]]] = [
    audit_gate_language,
    benchmark_staleness_admitted,
    storage_under_app_dir,
    panel_cost_multiple,
    mcp_surface_alignment,
    deck_formats_as_documented,
    runner_reports_the_split,
    lead_claims_match,
    storage_inventory_is_complete,
]


def run(root: Path = ROOT) -> List[str]:
    problems: List[str] = []
    for check in CHECKS:
        try:
            found = check(root)
        except Exception as exc:  # noqa: BLE001 - a broken check is a failure
            found = [f"{check.__name__} itself raised "
                     f"{type(exc).__name__}: {exc}"]
        status = "ok" if not found else f"{len(found)} problem(s)"
        print(f"  {check.__name__}: {status}")
        for line in found:
            print(f"    ! {line}")
        problems.extend(found)
    return problems


def main() -> int:
    print("checking documented claims against the tree…")
    problems = run()
    if problems:
        print(f"\n{len(problems)} claim(s) no longer hold. A document and "
              f"the code disagree; decide which is right and fix that one.")
        return 1
    print("\nevery checked claim holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
