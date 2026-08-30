"""Regressions for the fourth external audit: the evidence ledger.

The theme was the most serious one this product can have. Its whole promise is
that a reader can open the evidence behind any statement — so a citation that
resolves to the *wrong* source is worse than no citation at all. It converts an
unsupported claim into an apparently evidenced one, and it does so invisibly.

Three separate paths could break source identity:

* Cold discovery renumbered sources after the model output citing them existed.
* The registry's admitted-source ledger was dropped on serialization, silently
  widening what counted as citable.
* Validation covered the fields somebody had remembered to list, so any new
  source-bearing field escaped checking entirely.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.sources import (SourceRegistry, audit_citations, merge_into,
                               rewrite_citations)


def _registry(titles, host, snippet="x" * 80):
    reg = SourceRegistry()
    reg.add_results([SimpleNamespace(title=t, url=f"https://{host}/{i}",
                                     snippet=snippet, published=None,
                                     source_query="q")
                     for i, t in enumerate(titles)])
    return reg


# ============================ a citation must point at the source it is about

def test_merging_a_registry_returns_the_map_needed_to_rewrite_citations():
    """The merge renumbers; the caller must be able to follow. Returning the map
    rather than mutating silently is what makes the obligation impossible to
    miss."""
    main = _registry(["Market sizing", "Pricing benchmarks"], "main.example")
    cold = _registry(["Microsoft bundles Power Automate",
                      "ServiceNow owns ITSM"], "cold.example")

    remap = merge_into(main, cold, note="cold pass")
    assert remap == {"S1": "S3", "S2": "S4"}
    assert len(main.sources) == 4


def test_renumbering_without_rewriting_is_what_broke_and_rewriting_fixes_it():
    """Reproduces the exact failure: a claim about Microsoft citing a market
    sizing document, because the cold pass's local S1 became the main
    registry's S1."""
    main = _registry(["Market sizing composite"], "main.example")
    cold = _registry(["Microsoft bundles Power Automate into E5"], "cold.example")
    output = {"competitors": [{"name": "Microsoft Power Automate",
                               "source_ids": ["S1"]}]}

    remap = merge_into(main, cold)
    # Before rewriting, the citation resolves to the WRONG document.
    assert main.find("S1").title == "Market sizing composite"

    rewrite_citations(output, remap)
    cited = output["competitors"][0]["source_ids"][0]
    assert "Microsoft" in main.find(cited).title, (
        "the citation must resolve to the source the claim is actually about")


def test_a_source_both_passes_found_is_merged_not_duplicated():
    main = _registry(["Shared source"], "same.example")
    cold = _registry(["Shared source"], "same.example")
    remap = merge_into(main, cold)
    assert len(main.sources) == 1
    assert remap == {"S1": "S1"}


def test_merging_carries_admitted_state_across_the_new_id():
    main = _registry(["A"], "main.example")
    cold = _registry(["B"], "cold.example")
    cold.prompt_block()                      # cold's S1 was shown to a model
    remap = merge_into(main, cold)
    assert remap["S1"] in main.admitted_ids


# ================================ the ledger must survive being written down

def test_admitted_state_survives_serialization():
    """A round-trip used to forget which sources had reached a prompt, which
    silently widened what counted as citable."""
    reg = _registry([f"S{i}" for i in range(3)], "e.example", snippet="x" * 3000)
    reg.prompt_block(char_budget=3600)       # only the first fits
    assert reg.citable_ids == ["S1"]

    restored = SourceRegistry.from_dict(reg.to_dict())
    assert restored.citable_ids == ["S1"], "unadmitted sources became citable again"
    assert sorted(restored.admitted_ids) == sorted(reg.admitted_ids)
    assert len(restored.omitted_for_length) == 2


def test_no_prompt_yet_and_prompt_with_nothing_in_it_are_different_states():
    """An empty admitted set meant both, and they are opposite trust positions:
    "nothing ruled out yet" versus "nothing qualified"."""
    fresh = _registry(["A", "B"], "e.example")
    assert fresh.citable_ids == ["S1", "S2"], "before any prompt, all are candidates"

    starved = _registry(["A"], "e.example", snippet="y" * 99_999)
    starved.prompt_block(char_budget=50)
    assert starved.citable_ids == [], "a prompt that fit nothing admits nothing"
    assert SourceRegistry.from_dict(starved.to_dict()).citable_ids == []


# =========================== every citation is checked, not the listed fields

class _Result:
    def __init__(self, **kw):
        self.market = kw.get("market", {})
        self.comparisons = kw.get("comparisons", {})
        self.opportunity = kw.get("opportunity", {})
        self.discovery_delta = kw.get("discovery_delta", {})
        self.cold_market = kw.get("cold_market", {})


def _three_source_registry():
    reg = _registry(["One", "Two", "Three"], "e.example")
    reg.prompt_block()
    return reg


def test_a_citation_to_a_nonexistent_source_is_caught_wherever_it_hides():
    """Absorbers, precedents, open-source projects and adjacent markets all
    carry sources in the schema and none of them were validated."""
    reg = _three_source_registry()
    result = _Result(market={
        "absorption": {"likely_absorbers": [{"name": "X", "source_ids": ["S99"]}],
                       "precedents": [{"what": "y", "source_ids": ["S98"]}]},
        "open_source_landscape": {"projects": [{"name": "n8n",
                                                "source_ids": ["S97"]}]},
        "adjacent_markets": [{"name": "iPaaS", "source_ids": ["S96"]}]})

    audit = audit_citations(result, reg, strip=True)
    assert len(audit.dangling) == 4, audit.dangling
    assert not audit.ok
    # And they are removed rather than displayed.
    assert result.market["absorption"]["likely_absorbers"][0]["source_ids"] == []
    assert result.market["adjacent_markets"][0]["source_ids"] == []


def test_optional_passes_are_covered_too():
    reg = _three_source_registry()
    result = _Result(
        opportunity={"base_rates": [{"rate": "4%", "source_ids": ["S77"]}]},
        discovery_delta={"only_cold": [{"name": "Z", "source_ids": ["S88"]}]})
    audit = audit_citations(result, reg, strip=True)
    assert {sid for _, sid in audit.dangling} == {"S77", "S88"}


def test_inline_prose_citations_are_checked_and_stripped():
    reg = _three_source_registry()
    result = _Result(comparisons={"investor": {
        "summary": "The slice is $3-5B [S1] and rising [S42]."}})
    audit = audit_citations(result, reg, strip=True)
    assert [sid for _, sid in audit.dangling] == ["S42"]
    text = result.comparisons["investor"]["summary"]
    assert "[S1]" in text, "a valid citation must survive"
    assert "S42" not in text, "an invalid one must not be displayed"


def test_a_quarantined_source_cannot_be_cited():
    reg = _three_source_registry()
    reg.mark_dropped("https://e.example/1", "hostile")
    result = _Result(comparisons={"investor": {
        "claim_audit": [{"claim": "x", "source_ids": ["S2"]}]}})
    audit = audit_citations(result, reg, strip=True)
    assert audit.quarantined, "the security screen's decision must be final"
    assert result.comparisons["investor"]["claim_audit"][0]["source_ids"] == []


def test_a_source_no_model_saw_cannot_be_cited():
    reg = _registry(["A", "B"], "e.example", snippet="x" * 3000)
    reg.prompt_block(char_budget=3400)       # only S1 admitted
    result = _Result(comparisons={"investor": {
        "claim_audit": [{"claim": "x", "source_ids": ["S1", "S2"]}]}})
    audit = audit_citations(result, reg, strip=True)
    assert [sid for _, sid in audit.unadmitted] == ["S2"]
    assert result.comparisons["investor"]["claim_audit"][0]["source_ids"] == ["S1"]


def test_a_clean_result_passes_and_says_how_many_it_checked():
    reg = _three_source_registry()
    result = _Result(comparisons={"investor": {
        "claim_audit": [{"claim": "x", "source_ids": ["S1", "S2"]}]}})
    audit = audit_citations(result, reg)
    assert audit.ok
    assert audit.checked == 2
    assert "resolve to admitted sources" in audit.summary()


# ================================= omissions must carry their own provenance

def test_an_omission_with_no_source_is_not_promoted_to_a_headline_finding():
    """A blind spot goes straight to the top of the report as "the deck omits X".
    Asserting that without evidence made the most prominent line the least
    checkable one."""
    from deckscope.findings import collect

    sourced = collect({"alignment": {"blind_spots": [
        {"what": "Power Automate ships inside E5", "source_ids": ["S1"]}]}})
    assert sourced.omissions[0].severity == "high"
    assert sourced.omissions[0].source_ids == ["S1"]

    bare = collect({"alignment": {"blind_spots": ["Something asserted"]}})
    assert bare.omissions[0].severity == "low", (
        "an unsourced omission must not carry the weight of an evidenced one")
    assert bare.omissions[0].source_ids == []


# ===================================== the demo must not contradict its corpus

def _demo_result(tmp_path):
    import subprocess

    root = Path(__file__).resolve().parent.parent
    out = str(tmp_path / "demo")
    subprocess.run([sys.executable, "-m", "deckscope", "demo",
                    "--format", "json", "--out", out],
                   cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return json.loads(next(Path(out).glob("*.json")).read_text(encoding="utf-8"))


def _assessment_of(audit, needle):
    for row in audit:
        if isinstance(row, dict) and needle in str(row.get("claim", "")):
            return str(row.get("assessment", ""))
    return None


def test_the_demo_agrees_with_its_own_corpus(tmp_path):
    """The showcase is a product acceptance test, not sample text.

    It previously called the deck's inflated "$47B, 23% CAGR" *supported* — by a
    corpus sentence written to refute it — while leading with a different claim
    as its headline contradiction.
    """
    data = _demo_result(tmp_path)
    audit = list(data["comparisons"].values())[0].get("claim_audit") or []

    assert _assessment_of(audit, "$47B") == "contradicted", (
        "the corpus says $18-24B, 'not the $45-50B figures' — the deck's $47B "
        "sits inside the range the evidence explicitly disputes")
    assert _assessment_of(audit, "18% month-over-month") == "supported", (
        "the corpus calls sustained 18% monthly growth above median")


def test_the_demo_never_manufactures_a_contradiction_from_silence(tmp_path):
    """A serviceable slice the evidence does not discuss is unverifiable, not
    contradicted. Reporting silence as disagreement is the failure this product
    exists to prevent."""
    data = _demo_result(tmp_path)
    audit = list(data["comparisons"].values())[0].get("claim_audit") or []
    assert _assessment_of(audit, "SAM: $6B") == "unverifiable"


def test_the_demo_report_has_no_dangling_citations(tmp_path):
    data = _demo_result(tmp_path)
    known = {s["sid"] for s in (data.get("references") or {}).get("sources", [])}
    bad = []

    def walk(node, where):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "source_ids" and isinstance(value, list):
                    bad.extend((where, v) for v in value if str(v) not in known)
                else:
                    walk(value, f"{where}.{key}")
        elif isinstance(node, list):
            for item in node:
                walk(item, where)

    for section in ("market", "comparisons", "opportunity", "discovery_delta"):
        walk(data.get(section), section)
    assert not bad, bad


def test_the_run_records_its_own_citation_audit(tmp_path):
    data = _demo_result(tmp_path)
    audit = (data.get("stats") or {}).get("citation_audit") or {}
    assert audit.get("ok") is True, audit
    assert audit.get("checked", 0) > 0, "an audit that checked nothing proves nothing"


# ================================================ panel divergence is honest

def test_analysts_differ_only_where_the_evidence_is_genuinely_ambiguous():
    """Honest divergence: same evidence, two defensible readings.

    Where the evidence both supports and refutes a figure, a strict reader calls
    it contradicted and a lenient one calls it partly supported. Where the
    evidence is clear, both agree — and a panel that agrees on clear evidence is
    working correctly, not broken.
    """
    from deckscope.providers.mock_provider import _assess

    mixed = ("An ACV of $28,000 is achievable at the top of the range. "
             "Gross margins of 78% are not the norm once inference is loaded in.")
    strict, _ = _assess("Average contract value: $28,000. Gross margin: 78%",
                        mixed.lower(), strictness=1)
    lenient, _ = _assess("Average contract value: $28,000. Gross margin: 78%",
                         mixed.lower(), strictness=0)
    # The fourth audit corrected the old pin here: mixed evidence IS what
    # "partially-supported" means, at every strictness — stamping
    # "contradicted" on it manufactured findings in the flagship demo.
    # Panelists still diverge honestly on the supported threshold below.
    assert strict == "partially-supported"
    assert lenient == "partially-supported"

    # The honest divergence between analysts now lives on the SUPPORTED
    # threshold: purely corroborating evidence for a multi-figure claim is
    # "supported" to a lenient reader and not yet to a strict one.
    corroborating = ("an acv of $28,000 is typical for this segment. "
                     "margins of 78% are the norm for this class of product.")
    two_figures = "Average contract value: $28,000. Gross margin: 78%"
    assert (_assess(two_figures, corroborating, 0)[0]
            != _assess(two_figures, corroborating, 1)[0]), (
        "ambiguity about sufficiency must still admit two readings")

    clear = "independent estimates put the category at $18-24b, not the $45-50b."
    claim = "The market is $47B"
    assert (_assess(claim, clear, 1)[0] == _assess(claim, clear, 0)[0]
            == "contradicted"), "unambiguous evidence must not admit two readings"


def test_panel_divergence_never_falsifies_an_evidence_assessment():
    """Panelists must differ, but not by overwriting a claim's assessment. That
    replaced a reading derived from the corpus with a fabricated one."""
    import re

    source = (Path(__file__).resolve().parent.parent / "deckscope" / "providers"
              / "mock_provider.py").read_text(encoding="utf-8")
    compare = source[source.index("def _compare("):]
    compare = compare[:compare.index("\n    def ", 1)]
    assert not re.search(r'audit\[\d+\]\["assessment"\]\s*=', compare), (
        "divergence must come from scoring and framing, not from rewriting "
        "what the evidence was found to say")
