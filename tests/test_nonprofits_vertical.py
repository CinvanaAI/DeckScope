"""The nonprofits vertical: declaration coupling, the ProPublica client
against the recorded capture, the fiscal-basis law, the reconciliation's
arithmetic and refusals, the self-filing law, and the offline run.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
CAPTURE = (ROOT / "recorded" / "phase0" /
           "propublica_org_363673599_feeding_america.json")


def _record():
    from deckscope.research import nonprofitsources as nps

    return nps.parse_org(json.loads(CAPTURE.read_text(encoding="utf-8")),
                         request_url="https://example.invalid/replay")


class _Registry:
    """Just enough of SourceRegistry for reconcile()."""

    def __init__(self):
        self.results = []
        self.n = 0

    def add_results(self, results, backend=""):
        out = []
        for r in results:
            self.n += 1
            src = types.SimpleNamespace(sid=f"S{self.n}", title=r.title,
                                        url=r.url, reliability="unknown")
            self.results.append(src)
            out.append(src)
        return out


# ------------------------------------------------------ declaration truth

def test_nonprofits_is_declared_ungraded_until_it_earns_the_flag():
    from deckscope.verticals import get

    n = get("nonprofits")
    assert n is not None and n.runner == "nonprofits_pipeline"
    assert n.graded is False
    assert set(n.publicly_checkable) <= set(n.claim_types)


def test_the_declared_evidence_home_has_a_client():
    from deckscope.research import nonprofitsources as nps
    from deckscope.verticals import get

    assert get("nonprofits").evidence_homes == ("propublica",)
    assert callable(nps.search_orgs) and callable(nps.org_record)


def test_the_sample_appeal_classifies_as_nonprofits():
    from deckscope.verticals import classify_document

    text = (ROOT / "deckscope" / "examples" /
            "sample_nonprofit_appeal.md").read_text(encoding="utf-8")
    cls = classify_document(text)
    assert cls.matched and cls.vertical.name == "nonprofits"


# ------------------------------- the client against the RECORDED capture

def test_parse_org_reads_the_recorded_extract_exactly():
    rec = _record()
    assert rec.ein == 363673599
    assert rec.name == "Feeding America"
    assert len(rec.filings) == 12
    latest = rec.filings[0]
    # The figures below are the RECORDED IRS extract values, verified by
    # 990 component arithmetic at capture time (recorded/phase0/README).
    assert latest.tax_prd_yr == 2023
    assert latest.total_revenue == 4_916_912_461
    assert latest.total_expenses == 4_933_690_967
    assert latest.contributions == 4_752_844_795
    assert latest.officer_comp == 7_068_165
    assert latest.pdf_url.startswith("https://")
    assert [f.tax_prd_yr for f in rec.filings] == sorted(
        (f.tax_prd_yr for f in rec.filings), reverse=True)


def test_the_fiscal_basis_law_labels_every_figure():
    from deckscope.research.nonprofitsources import Filing

    fiscal = _record().filings[0]
    assert fiscal.basis_label == "fiscal year ending 06/2023", (
        "tax_prd 202306 is the fiscal year ENDING June 2023 — calling it "
        "'2023' unqualified is the chimera class")
    dec = Filing(tax_prd_yr=2023, fiscal_end_month=12)
    assert dec.basis_label == "calendar year 2023"


def test_resolve_ein_prefers_the_document_and_refuses_ambiguity(monkeypatch):
    from deckscope.research import nonprofitsources as nps

    # A stated EIN wins outright — no network consulted.
    monkeypatch.setattr(nps, "search_orgs",
                        lambda name, limit=5: (_ for _ in ()).throw(
                            AssertionError("must not search")))
    assert nps.resolve_ein("brief for EIN 36-3673599 ok", "Whoever") \
        == 363673599
    assert nps.resolve_ein("their Tax ID is 363673599 today", "Whoever") \
        == 363673599, "bare digits count WITH tax-id wording nearby"
    monkeypatch.setattr(nps, "search_orgs", lambda name, limit=5: [])
    assert nps.resolve_ein("serial 123456789 in the appendix", "") \
        is None, (
        "a bare 9-digit run without EIN context must not be read as "
        "one — misattributing filings is the failure this resolver "
        "exists to prevent")

    # No EIN: only an unambiguous top search hit is accepted.
    cands = [nps.OrgCandidate(ein=1, name="Feeding America", score=50.0),
             nps.OrgCandidate(ein=2, name="Feeding America of X",
                              score=48.0)]
    monkeypatch.setattr(nps, "search_orgs", lambda name, limit=5: cands)
    assert nps.resolve_ein("no ein here", "Feeding America") == 1, (
        "exact name match is unambiguous")
    assert nps.resolve_ein("no ein here", "Feeding Americans") is None, (
        "close scores and no exact match: refuse to attribute rather "
        "than misattribute filings")
    monkeypatch.setattr(nps, "search_orgs", lambda name, limit=5: [])
    assert nps.resolve_ein("no ein here", "Nobody At All") is None


# --------------------------------------------------- deterministic parsing

def test_dollar_anchored_parsing_never_reads_the_year_as_the_amount():
    from deckscope.verticals.nonprofits import claimed_dollars

    amount, half_ulp = claimed_dollars(
        "In fiscal 2023 revenue reached $5.2 billion")
    assert amount == 5.2e9
    assert half_ulp == 0.05e9, (
        "'$5.2 billion' asserts to the nearest $0.1B — the figure "
        "carries its own precision")
    exact, ulp = claimed_dollars("expenses of $4,933,690,967")
    assert exact == 4_933_690_967 and ulp == 0.0
    assert claimed_dollars("grew a lot in 2023") is None, (
        "a bare year is not a claimed amount")


def test_a_true_but_rounded_claim_is_not_contradicted():
    from deckscope.verticals.nonprofits import reconcile

    # Filed 2019 revenue is $2,831,620,652 — 1.13% from $2.8B, outside
    # a flat 1% but inside the claim's own rounding. Calling this
    # contradicted would be the engine making a false accusation.
    rows = reconcile([{"id": "C1", "type": "financials",
                       "claim": "Revenue was $2.8 billion in fiscal "
                                "2019."}], _record(), _Registry())
    assert rows[0]["status"] == "matched"
    assert "precision" in rows[0]["because"]


def test_a_claim_without_a_stated_fiscal_basis_is_flagged():
    from deckscope.verticals.nonprofits import reconcile

    rows = reconcile([{"id": "C1", "type": "financials",
                       "claim": "Total revenue reached $5.2 billion "
                                "in 2023."}], _record(), _Registry())
    assert rows[0]["status"] == "contradicted"
    assert "states no fiscal basis" in rows[0]["because"], (
        "a calendar-sounding claim compared to a June fiscal filing "
        "must say so — the basis difference is part of the finding")


def test_growth_claims_parse_to_ratio_and_base_year():
    from deckscope.verticals.nonprofits import growth_claim

    assert growth_claim("Revenue has more than doubled since fiscal "
                        "2019.") == (2.0, 2019)
    assert growth_claim("revenue grew 40% since 2020") == (1.4, 2020)
    assert growth_claim("revenue doubled recently") is None, (
        "no base year, no computation")


# --------------------------------------- the reconciliation's arithmetic

def _claims():
    return [
        {"id": "C1", "type": "financials",
         "claim": "Total revenue reached $5.2 billion in fiscal 2023."},
        {"id": "C2", "type": "financials",
         "claim": "The organization held total expenses to $4.93 billion "
                  "in fiscal 2023."},
        {"id": "C3", "type": "financials",
         "claim": "Revenue has more than doubled since fiscal 2019."},
        {"id": "C4", "type": "program-ratio",
         "claim": "92 cents of every dollar goes directly to programs."},
        {"id": "C5", "type": "compensation",
         "claim": "The chief executive officer's compensation was "
                  "$1.2 million."},
        {"id": "C6", "type": "impact",
         "claim": "The network serves tens of millions of people."},
    ]


def test_reconcile_computes_the_filed_verdicts():
    from deckscope.verticals.nonprofits import reconcile

    rows = reconcile(_claims(), _record(), _Registry())
    by = {r["claim_id"]: r for r in rows if r["claim_id"]}

    assert by["C1"]["status"] == "contradicted"
    assert "4,916,912,461" in by["C1"]["because"]
    assert "fiscal year ending 06/2023" in by["C1"]["because"], (
        "every reconciled figure travels with its fiscal basis")

    assert by["C2"]["status"] == "matched"  # $4.93B vs $4,933,690,967

    assert by["C3"]["status"] == "contradicted"
    assert "1.74x" in by["C3"]["because"]
    assert "2,831,620,652" in by["C3"]["because"], (
        "the growth check shows both filed endpoints")
    assert len(by["C3"]["source_ids"]) == 2, "both filings cited"

    assert by["C4"]["status"] == "not-computable"
    assert "PDF" in by["C4"]["because"], (
        "the ratio is refused with the real source named, never "
        "approximated from fields that do not measure it")

    assert by["C5"]["status"] == "not-computable"
    assert "7,068,165" in by["C5"]["because"]
    assert "Part VII" in by["C5"]["because"], (
        "CEO pay vs all-officer total would be a real number on the "
        "wrong subject")

    assert "C6" not in by, "impact claims are not the checker's to judge"


def test_the_checker_volunteers_the_deficit_the_document_omits():
    from deckscope.verticals.nonprofits import reconcile

    rows = reconcile(_claims(), _record(), _Registry())
    obs = [r for r in rows if r["status"] == "observation"]
    assert len(obs) == 1
    assert "16,778,506" in obs[0]["because"], (
        "expenses exceeded revenue in FY2023 by exactly this amount — "
        "filed, computable, and unmentioned")
    assert obs[0]["source_ids"], "the observation cites the filing"


def test_filings_register_lazily_and_as_primary_sources():
    from deckscope.verticals.nonprofits import reconcile

    reg = _Registry()
    reconcile(_claims(), _record(), reg)
    assert len(reg.results) == 2, (
        "only the two filings actually consulted (2023, 2019) become "
        "sources — not all twelve on record")
    assert all(s.reliability == "primary" for s in reg.results)


# ------------------------------------------------- the self-filing law

def test_the_law_overrules_a_softening_synthesist():
    from deckscope.verticals.nonprofits import apply_self_filing_law

    recon = [{"claim_id": "C1", "status": "contradicted",
              "because": "claimed X vs filed Y", "source_ids": ["S1"]},
             {"claim_id": "C2", "status": "matched",
              "because": "within 1%", "source_ids": ["S1"]},
             {"claim_id": "C4", "status": "not-computable",
              "because": "not in the extract", "source_ids": ["S1"]}]
    comp = {"claim_audit": [
        {"id": "C1", "assessment": "partially-supported",
         "so_what": "directionally consistent", "source_ids": []},
        {"id": "C2", "assessment": "contradicted", "source_ids": []},
        {"id": "C4", "assessment": "supported",
         "so_what": "widely reported", "source_ids": []},
        {"id": "C6", "assessment": "unverifiable", "source_ids": []}]}

    assert apply_self_filing_law(comp, recon) == 3
    rows = {r["id"]: r for r in comp["claim_audit"]}
    assert rows["C1"]["assessment"] == "contradicted"
    assert "directionally" not in rows["C1"]["so_what"], (
        "the softened commentary must not survive under the corrected "
        "verdict — a row must not argue with itself")
    assert rows["C1"]["evidence_quality"] == "strong"
    assert rows["C1"]["source_ids"] == ["S1"]
    assert rows["C2"]["assessment"] == "supported", (
        "the law cuts both ways: a synthesist inventing a contradiction "
        "the filings refute is corrected too")
    assert rows["C4"]["assessment"] == "unverifiable"
    assert rows["C6"]["assessment"] == "unverifiable", "untouched"
    assert "reconciled" not in rows["C6"]


# ------------------------------------------------ offline end-to-end run

def test_the_demo_run_is_honest_end_to_end(tmp_path):
    from deckscope.verticals import get
    from deckscope.verticals.nonprofits import run_nonprofits

    args = types.SimpleNamespace(demo=True, nda=False, provider=None,
                                 config=None, out=str(tmp_path))
    rc = run_nonprofits(get("nonprofits"),
                        ROOT / "deckscope" / "examples" /
                        "sample_nonprofit_appeal.md", args)
    assert rc == 0
    record = json.loads(
        (tmp_path / "sample_nonprofit_appeal_full.json").read_text(
            encoding="utf-8"))
    assert record["config"]["vertical"] == "nonprofits"
    assert record["deck"]["company"]["name"] == "Feeding America"
    comp = record["comparisons"]["funder"]
    assert "ungraded_notice" in comp
    rows = {r["id"]: r for r in comp["claim_audit"]}
    # The deliberately-off claims land where the filings put them:
    assert rows["C1"]["assessment"] == "contradicted"  # $5.2B revenue
    assert rows["C4"]["assessment"] == "contradicted"  # "doubled"
    assert rows["C2"]["assessment"] == "supported"     # contributions
    assert rows["C3"]["assessment"] == "supported"     # expenses
    assert rows["C5"]["assessment"] == "unverifiable"  # 92% ratio
    assert rows["C6"]["assessment"] == "unverifiable"  # CEO pay
    obs = [r for r in record["market"]["reconciliation"]
           if r["status"] == "observation"]
    assert obs and "deficit" in obs[0]["because"]

    md = (tmp_path / "sample_nonprofit_appeal_funder.md").read_text(
        encoding="utf-8")
    assert "Claims vs. Filed Record" in md
    assert "fiscal year ending 06/2023" in md
    assert "Ask the organization:" in md
    assert "Ask the founder" not in md, (
        "a nonprofit report must not speak deck vocabulary")
    assert "TAM claimed" not in md, (
        "the deck-shaped annex table has no business on this report")
    assert "Not financial or giving advice." in md


def test_nda_refuses_hosted_models_before_reading_the_document(tmp_path):
    from deckscope.verticals import get
    from deckscope.verticals.nonprofits import run_nonprofits

    args = types.SimpleNamespace(demo=False, nda=True,
                                 provider="anthropic", config=None,
                                 out=str(tmp_path))
    rc = run_nonprofits(get("nonprofits"),
                        ROOT / "deckscope" / "examples" /
                        "sample_nonprofit_appeal.md", args)
    assert rc == 4


def test_nda_with_a_local_model_skips_the_lookup_entirely(tmp_path):
    from deckscope.verticals import get
    from deckscope.verticals.nonprofits import run_nonprofits

    args = types.SimpleNamespace(demo=True, nda=True, provider=None,
                                 config=None, out=str(tmp_path))
    rc = run_nonprofits(get("nonprofits"),
                        ROOT / "deckscope" / "examples" /
                        "sample_nonprofit_appeal.md", args)
    assert rc == 0
    record = json.loads(
        (tmp_path / "sample_nonprofit_appeal_full.json").read_text(
            encoding="utf-8"))
    assert record["market"]["reconciliation"] == [], (
        "under --nda the lookup names the organization, so it must not "
        "run — even against the recorded replay, for consistency of the "
        "privacy contract")
    assert "--nda" in record["market"]["record_note"], (
        "the synthesist is told the checks were SKIPPED for privacy, "
        "not that there was nothing to check")
    assert record.get("privacy", {}).get("local_only") is True
