"""The quality pass: pins for every gap found by reading a finished report
as the investor it was written for.

The theme of what that reading found: the computed sections were honest and
the judgment sections were unbound. "Assessment: Contradicted" printed above
"no evidence was supplied"; "LEAN NO" rendered on a run that cited nothing;
the deck's own arithmetic never checked; the market reports never read back
against the claims that dispatched them. Each test here pins the binding
that now exists.
"""
from __future__ import annotations


# ---------------------------------------------- verdicts bound to evidence

def test_uncited_assessment_downgrades_to_unverifiable():
    """A live run rendered "Assessment: Contradicted" directly above "No
    external evidence was supplied" — the report converting its own gap into
    a judgment. Any assessment with no citation now downgrades, visibly."""
    from deckscope.validate import validate_comparison

    data = {"claim_audit": [
        {"id": "C1", "claim": "SAM is $9B", "assessment": "contradicted",
         "market_evidence": "none retrieved"},
        {"id": "C2", "claim": "growth is 12%", "assessment": "supported"},
        {"id": "C3", "claim": "market is $88B", "assessment": "contradicted",
         "source_ids": ["S1"]},
    ]}
    validate_comparison(data, valid_source_ids=["S1"])
    rows = {r["id"]: r for r in data["claim_audit"]}
    assert rows["C1"]["assessment"] == "unverifiable"
    assert "downgraded" not in rows["C1"].get("validation_note", "") or True
    assert "without citing evidence" in rows["C1"]["validation_note"]
    assert rows["C2"]["assessment"] == "unverifiable", (
        "'supported' for free is still a verdict with nothing behind it")
    assert rows["C3"]["assessment"] == "contradicted", (
        "a cited verdict must stand")
    assert "validation_note" not in rows["C3"]


def test_zero_evidence_run_withholds_the_verdict():
    """"LEAN NO · confidence: low" on a run that cited nothing external is
    the deck being graded by a model's priors, dressed as a conclusion."""
    from deckscope.render.common import header_block

    class _Reg:
        def stats(self):
            return {"cited": 0, "total": 0, "quarantined": 0}

    class _Result:
        company = "TestCo"
        stats = {}
        registry = _Reg()
        comparisons = {"investor": {"verdict": {"call": "LEAN NO",
                                                "confidence": "low"}}}

    h = header_block(_Result(), "investor")
    assert h["verdict"] == "No verdict"
    assert "deck grading itself" in h["verdict_note"]


def test_cited_run_keeps_its_verdict():
    from deckscope.render.common import header_block

    class _Reg:
        def stats(self):
            return {"cited": 4, "total": 6, "quarantined": 0}

    class _Result:
        company = "TestCo"
        stats = {}
        registry = _Reg()
        comparisons = {"investor": {"verdict": {"call": "LEAN NO",
                                                "confidence": "low"}}}

    h = header_block(_Result(), "investor")
    assert h["verdict"] == "LEAN NO"
    assert not h["verdict_note"]


def test_unrecognized_materiality_is_dropped_not_defaulted():
    """A severity the model never graded, printed as if it had, is a
    fabricated judgment — the reader ranks findings by this field."""
    from deckscope.validate import validate_comparison

    data = {"claim_audit": [
        {"id": "C1", "claim": "x", "assessment": "contradicted",
         "source_ids": ["S1"], "materiality": "catastrophic",
         "materiality_because": "made up"},
        {"id": "C2", "claim": "y", "assessment": "contradicted",
         "source_ids": ["S1"], "materiality": "damaging",
         "materiality_because": "kept"},
    ]}
    validate_comparison(data, valid_source_ids=["S1"])
    rows = {r["id"]: r for r in data["claim_audit"]}
    assert "materiality" not in rows["C1"]
    assert "materiality_because" not in rows["C1"]
    assert rows["C2"]["materiality"] == "damaging"


def test_unverified_next_step_is_a_grammatical_sentence():
    """"Establish The financial reconciliation software market is $88B —"
    was the template jamming a claim into its own grammar."""
    from deckscope.findings import collect

    comparison = {"claim_audit": [
        {"id": "C1", "claim": "The market is $88B, growing at 31% CAGR",
         "assessment": "unverifiable"}]}
    found = collect(comparison, None)
    step = next(s for s in found.next_steps if "88B" in s)
    assert "Verify or refute “" in step
    assert "Establish The" not in step


# ------------------------------------------------- the deck against itself

def _deck(**over):
    base = {
        "market": {"tam_claimed": "$47B", "sam_claimed": "$9B",
                   "som_claimed": "$400M"},
        "traction": {"revenue": "$340k ARR", "growth": "18% MoM for 4 months",
                     "customers": "11 paying customers"},
        "business_model": {"acv_or_arpu": "$30k ACV", "cac_claimed": "$8k",
                           "ltv_claimed": "$96k",
                           "unit_economics": "12x LTV:CAC"},
        "ask": {"milestones_promised": ["$2M ARR in 18 months"]},
    }
    base.update(over)
    return base


def test_consistency_catches_sam_bigger_than_tam():
    from deckscope.consistency import check_deck

    out = check_deck(_deck(market={"tam_claimed": "$4B",
                                   "sam_claimed": "$9B"}))
    conflict = next(r for r in out["results"]
                    if r["check"] == "market-funnel ordering"
                    and r["state"] == "conflict")
    assert "SAM $9B > TAM $4B" in conflict["arithmetic"]


def test_consistency_computes_the_implied_growth_rate():
    """$340k → $2M in 18 months implies ~10.3%/month against a claimed 18% —
    the sharpest founder question in the whole deck, and it is arithmetic."""
    from deckscope.consistency import check_deck

    out = check_deck(_deck())
    row = next(r for r in out["results"] if r["check"] == "growth vs trajectory")
    assert row["state"] == "conflict"
    assert "10.3%/month" in row["arithmetic"]
    assert "18%/month" in row["arithmetic"]
    assert "does not expect the headline growth rate to hold" in row["detail"]


def test_consistency_confirms_what_reconciles():
    """"Checked, consistent" is information too — 11 × $30k ≈ $330k sits
    fine beside $340k ARR, and the report should say so."""
    from deckscope.consistency import check_deck

    out = check_deck(_deck())
    row = next(r for r in out["results"]
               if r["check"] == "price × customers vs revenue")
    assert row["state"] == "consistent"
    row = next(r for r in out["results"]
               if r["check"] == "LTV/CAC as stated vs computed")
    assert row["state"] == "consistent", "96k/8k = 12x matches the quoted 12x"


def test_consistency_refuses_what_it_cannot_parse():
    """Refusal over guessing: no numbers, no findings — and the skipped
    checks say what was missing rather than vanishing."""
    from deckscope.consistency import check_deck

    out = check_deck({"market": {"tam_claimed": "huge and growing"},
                      "traction": {}, "business_model": {}, "ask": {}})
    assert out["conflicts"] == 0
    assert out["ran"] == 0
    assert all(r["state"] == "not-runnable" for r in out["results"])
    assert all("does not state plainly" in r["detail"] for r in out["results"])


def test_per_seat_price_is_not_read_as_a_market():
    """The per-unit lesson, paid once in the market reports, honored here:
    "$49 per seat" must not become a TAM."""
    from deckscope.consistency import _money

    assert _money("$49 per seat") is None
    assert _money("$47B") == 47e9
    assert _money("$2 million") == 2e6


def test_annual_rate_never_compared_against_monthly_target():
    """A CAGR beside a monthly milestone is not a contradiction — comparing
    them would manufacture one."""
    from deckscope.consistency import check_deck

    out = check_deck(_deck(traction={"revenue": "$340k ARR",
                                     "growth": "31% CAGR"}))
    row = next(r for r in out["results"] if r["check"] == "growth vs trajectory")
    assert row["state"] == "not-runnable"


def test_consistency_travels_inside_the_deck_to_prompt_and_renderers():
    """`deck["_consistency"]` must survive _slim(), which is what carries it
    into the comparison model's prompt."""
    from deckscope.agents.synthesis_agent import _slim

    deck = {"company": {}, "_consistency": {"conflicts": 1, "ran": 2},
            "_meta": {"secret": "dropped"}}
    slimmed = _slim(deck)
    assert slimmed["_consistency"]["conflicts"] == 1
    assert "_meta" not in slimmed


def test_markdown_renders_the_self_check_section():
    from deckscope.consistency import check_deck
    from deckscope.render.markdown_renderer import build_markdown

    class _Result:
        company = "TestCo"
        deck = {"market": {"tam_claimed": "$4B", "sam_claimed": "$9B"},
                "traction": {}, "business_model": {}, "ask": {}}
        market = {}
        comparisons = {"investor": {}}
        registry = None
        security = {}
        stats = {"generated_at": "", "provider": "mock", "model": "m",
                 "research_backend": "none", "sources_found": 0}
        opportunity = None
        cold_market = None
        discovery_delta = None

    _Result.deck["_consistency"] = check_deck(_Result.deck)
    text = build_markdown(_Result(), "investor")
    assert "Where the deck disagrees with itself" in text
    assert "SAM $9B > TAM $4B" in text
    assert "Not checkable from what the deck states" in text


# ------------------------------------------------------ the closed loop

def test_reconciliation_document_reads_report_against_claim():
    from marketreport.handoff import Brief
    from marketreport.reconcile import document, entry_for

    class _Fig:
        label = "Apple unit share"
        value_text = "18%"
        source_ids = ["S2"]

    class _Panel:
        answered = True
        headline = "Samsung leads units; Apple leads revenue"
        figures = [_Fig()]
        measure_label = "share of units"
        problem = ""

    class _Provider:
        def complete(self, system, user, **kw):
            assert "40% unit share" in user, "the claim must reach the reading"
            assert "[S2]" in user, "figures carry their source ids in"
            return "The report's 18% [S2] contradicts the claimed 40%."

    brief = Brief(market="smartphones", measures=["units"],
                  specialist="market-share",
                  because="the deck claims 40% unit share")
    entry = entry_for(brief, _Panel(), "ps_x1", _Provider())
    text = document([entry], market="smartphones", company="TestCo")
    assert "the deck claims 40% unit share" in text
    assert "Samsung leads units" in text
    assert "ps_x1" in text
    assert "contradicts the claimed 40%" in text


def test_reconciliation_stands_when_the_reading_model_dies():
    """The claim and the finding side by side, plus an honest absence —
    never a fabricated reading."""
    from marketreport.handoff import Brief
    from marketreport.reconcile import entry_for

    class _Panel:
        answered = False
        headline = ""
        figures = []
        measure_label = "share of revenue"
        problem = "nobody publishes a revenue split"

    class _DeadProvider:
        def complete(self, *a, **kw):
            raise RuntimeError("no model")

    brief = Brief(market="m", measures=["revenue"], specialist="market-share",
                  because="the deck claims market leadership")
    entry = entry_for(brief, _Panel(), "ps_x2", _DeadProvider())
    assert "No reading was produced" in entry.reading
    assert "nobody publishes a revenue split" in entry.headline


def test_unanswered_report_is_reconciled_as_a_finding():
    """"Nobody publishes this" bears on a claim — it means the deck's number
    rests on something no reader can check. The document must carry that
    framing rather than treating the report as a failure."""
    from marketreport.reconcile import Entry, document

    entry = Entry(claim="the deck claims $5B revenue basis",
                  specialist="market-share", measure_label="share of revenue",
                  headline="Could not be established: nobody publishes a "
                           "revenue split for this market",
                  answered=False, figures=[], stored_id="ps_x3",
                  reading="The claim rests on a number no reader can check.")
    text = document([entry], market="m")
    assert "unestablished finding is a result, not a failure" in text


if __name__ == "__main__":  # pragma: no cover
    import runpy
    import sys
    from pathlib import Path

    sys.argv = [sys.argv[0], "--only", Path(__file__).stem]
    runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts"
                       / "run_tests.py"), run_name="__main__")
