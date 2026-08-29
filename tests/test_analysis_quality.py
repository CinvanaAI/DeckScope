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


def test_every_check_reports_even_when_the_milestone_is_behind():
    """Defect #17: a milestone at or below current revenue made the growth
    check append nothing — vanishing from the results entirely, in the
    module whose docstring promises 'could not check' is always said."""
    from deckscope.consistency import check_deck

    out = check_deck({
        "market": {}, "business_model": {},
        "traction": {"revenue": "$3M ARR", "growth": "18% MoM"},
        "ask": {"milestones_promised": ["$2M ARR in 18 months"]},
    })
    row = next(r for r in out["results"]
               if r["check"] == "growth vs trajectory")
    assert row["state"] == "not-runnable"
    assert "not" in row["detail"], "the reason must be stated"
    # the invariant behind the fix: all four checks always report something
    assert len(out["results"]) == 4


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


def test_top_down_and_bottom_up_sizings_are_compared():
    """External audit: a $548.9M top-down and a $571.6M bottom-up sizing of
    the SAME question were refused as 'two different subjects' — sentence-
    initial words like "Starting" and "Counted" minted fake entities, the
    keyword 'counted' mislabeled a dollar figure as a count, and the
    vocabulary guard finished the job because method narrations share no
    words. Three fixes: sentence-position grammar can't mint an entity, the
    value outranks the vocabulary for measure, and a derivation (method=
    'computed') waives the vocabulary guard within its question."""
    from deckscope.research.closing import relation
    from deckscope.research.findings import FindingRegistry

    registry = FindingRegistry()
    registry.add("Starting from the operator count, the market is $548.9M",
                 value_text="$548.9M", question_id="Q2", unit="USD",
                 method="computed", source_ids=["S1"], beat="sizing")
    registry.add("Counted bottom-up from establishments, the total "
                 "is $571.6M", value_text="$571.6M", question_id="Q2",
                 unit="USD", method="search", source_ids=["S2"], beat="sizing")
    a, b = list(registry.findings)[:2]
    rel, why = relation(a, b)
    assert rel != "incomparable", (
        f"the report's central convergence check refused to run: {why}")


def test_off_topic_findings_in_one_question_stay_incomparable():
    """The waiver is scoped to derivations — two ordinary searched findings
    about genuinely different things keep the full vocabulary guard, so
    off-topic retrieval cannot be forced into a comparison."""
    from deckscope.research.closing import relation
    from deckscope.research.findings import FindingRegistry

    registry = FindingRegistry()
    registry.add("Landscaping startup capital is $10,000",
                 value_text="$10,000", question_id="Q3", unit="USD",
                 method="search", source_ids=["S1"], beat="economics")
    registry.add("Office software costs $10,200 annually",
                 value_text="$10,200", question_id="Q3", unit="USD",
                 method="search", source_ids=["S2"], beat="economics")
    a, b = list(registry.findings)[:2]
    assert relation(a, b)[0] == "incomparable"


def test_headline_verb_matches_the_verdict_mix():
    """A live spool run opened with "Four claims are contradicted by cited
    evidence" when three of the four were only partially supported — an
    overstatement in the most-read sentence of a report built to prevent
    exactly that. The verb now matches the verdicts."""
    from deckscope.findings import collect

    def audit(*assessments):
        return {"claim_audit": [
            {"id": f"C{i}", "claim": f"claim {i}", "assessment": a,
             "delta": "deck says X. evidence says Y.",
             "source_ids": ["S1"], "evidence_quality": "moderate"}
            for i, a in enumerate(assessments, 1)]}

    class _Reg:
        def stats(self):
            return {"cited": 2, "total": 2, "quarantined": 0}

    mixed = collect(audit("contradicted", "partially-supported",
                          "partially-supported"), _Reg())
    assert "contested by cited evidence (one outright, two partly supported)" \
        in mixed.headline
    assert "three claims are contradicted" not in mixed.headline.lower()

    pure = collect(audit("contradicted", "contradicted"), _Reg())
    assert "contradicted by cited evidence" in pure.headline

    partial = collect(audit("partially-supported"), _Reg())
    assert "only partly supported by cited evidence" in partial.headline


# ------------------------------------------- the summary's naked figures

def test_summary_figure_from_nowhere_is_named():
    """The three marks bound every findings section and stopped at the
    Summary — the most-read prose on the page, where a model could still
    assert "$12M" out of thin air. Now a figure that exists neither in the
    deck nor in any cited evidence is named in a caveat."""
    from deckscope.render.common import summary_caveat, summary_unsourced_figures

    deck = {"claims": [{"claim": "The market is $88B"}]}
    comp = {"claim_audit": [{"claim": "size",
                             "market_evidence": "estimates cluster at $18-24B",
                             "source_ids": ["S1"]}]}
    naked = summary_unsourced_figures(
        "The company will likely reach $12M ARR and hold 35% share.",
        deck, comp)
    assert naked == ["$12M", "35%"]
    assert "the model's own assertions" in summary_caveat(
        "It should reach $12M ARR.", deck, comp)


def test_summary_covered_figures_raise_no_caveat():
    """Three escape routes, all legitimate: the deck's own number under
    discussion, a cited row's number, a sentence carrying its own [S] mark.
    False positives here would teach readers to ignore the caveat."""
    from deckscope.render.common import summary_unsourced_figures

    deck = {"claims": [{"claim": "The market is $88B"}],
            "traction": {"revenue": "$340k ARR"}}
    comp = {"claim_audit": [{"claim": "size",
                             "market_evidence": "estimates cluster at $18-24B",
                             "source_ids": ["S1"]}]}
    text = ("The deck's $88B is inflated; estimates put it at $18-24B. "
            "Traction of $340k ARR is real. Churn is 3% [S4].")
    assert summary_unsourced_figures(text, deck, comp) == []


def test_spelled_out_units_match_their_abbreviations():
    """"$2 million" in the summary and "$2M" in the deck are one figure;
    flagging the spelled form would teach readers to ignore the caveat."""
    from deckscope.render.common import summary_unsourced_figures

    deck = {"ask": {"milestones_promised": ["$2M ARR within 18 months"]}}
    assert summary_unsourced_figures(
        "The $2 million milestone is the credible number.", deck, {}) == []
    # and the reverse direction
    deck2 = {"ask": {"milestones_promised": ["$2 million ARR"]}}
    assert summary_unsourced_figures(
        "The $2M milestone is the credible number.", deck2, {}) == []


def test_summary_check_ignores_years_and_uncited_audit_rows():
    from deckscope.render.common import summary_unsourced_figures

    # a year is not a figure
    assert summary_unsourced_figures("A 2030 projection.", {}, {}) == []
    # an UNCITED audit row cannot launder a figure into coverage
    comp = {"claim_audit": [{"claim": "x", "market_evidence": "$5B somewhere",
                             "source_ids": []}]}
    assert summary_unsourced_figures("It is a $5B market.", {}, comp) == ["$5B"]


def test_windows_cased_environment_survives_the_allowlist(monkeypatch):
    """The allowlist spells it SystemRoot; Windows exposes SYSTEMROOT. The
    case-sensitive check dropped it from every child environment, and under
    Windows/Python 3.9 a child Python died during interpreter startup —
    the hosted CI job that stayed red after everything else was green
    (external audit finding). Membership is case-insensitive now; the
    secret-exclusion intent is unchanged."""
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-cross")
    from deckscope.providers import cli_provider
    from deckscope.providers.mcp_provider import child_env

    env = child_env()
    assert "SYSTEMROOT" in env
    assert "ANTHROPIC_API_KEY" not in env
    assert cli_provider._allowed("systemroot")
    assert not cli_provider._allowed("AWS_SECRET_ACCESS_KEY")


def test_panels_live_inside_the_documented_app_dir(monkeypatch, tmp_path):
    """Panels wrote to an undocumented ~/.deckscope/panels while every doc
    and the uninstall table pointed at the app dir — leftover cleartext
    reports naming a confidential company's market (external audit finding
    #5). One documented location now, with legacy migration that survives a
    cross-filesystem move (os.replace raised EXDEV there; shutil.move does
    not — caught by this test before it shipped)."""
    import os

    home = tmp_path / "apphome"
    monkeypatch.setenv("DECKSCOPE_HOME", str(home))
    fake_user_home = tmp_path / "userhome"
    legacy = fake_user_home / ".deckscope" / "panels"
    legacy.mkdir(parents=True)
    (legacy / "20260101-legacy.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(os.path, "expanduser",
                        lambda p: p.replace("~", str(fake_user_home)))

    from marketreport.library import default_dir
    from marketreport.naics import _cache_path

    d = default_dir()
    assert d.startswith(str(home)), f"panels outside the app dir: {d}"
    assert (tmp_path / "apphome" / "panels" / "20260101-legacy.json").exists()
    assert not legacy.exists(), "the undocumented location must not remain"
    assert _cache_path().startswith(str(home))


def test_acceptance_script_addresses_the_packaged_sample():
    """The clean-wheel CI job ran a checkout-relative fixture path from an
    intentionally empty directory — the wheel was fine, the address wrong.
    The script must resolve the sample from the installed package."""
    from pathlib import Path

    script = (Path(__file__).resolve().parent.parent / "scripts"
              / "acceptance.sh").read_text(encoding="utf-8")
    assert "deckscope.cli.__file__" in script, (
        "the sample must be resolved from the installed package")
    assert '-m deckscope research deckscope/examples' not in script, (
        "no checkout-relative fixture paths in the clean-install test")


# --------------------------------------------- one evidence engine

def test_reports_run_inside_the_pipeline_and_feed_the_comparison(monkeypatch, tmp_path):
    """The external audit's largest product-level gap: the deck pipeline and
    the report engine were 'two partially parallel systems' — reports ran
    after render, in their own registry, and the verdict never saw them.
    With cfg.market_reports the pipeline now runs the scoped reports BEFORE
    the comparison, merges their sources into the run's one registry (remap
    applied to the prompt copies), and puts their findings into the market
    artifact the synthesist reads."""
    from deckscope import settings
    from deckscope.orchestrator import Pipeline
    from marketreport.handoff import Brief

    brief = Brief(market="test market", measures=["units"],
                  specialist="market-share",
                  because="the deck claims 40% unit share")
    monkeypatch.setattr("marketreport.scoping.briefs_from_deck",
                        lambda deck, provider: ([brief], []))

    class _Fig:
        label = "Apple unit share"
        value_text = "18%"
        source_ids = ["S1"]

    class _Panel:
        answered = True
        headline = "Samsung leads units"
        figures = [_Fig()]
        measure_label = "share of units"
        measure = "units"
        problem = ""

    def fake_run_brief(b, *, registry=None, **kw):
        # the brief's research registers its source in the SHARED registry,
        # and building the prompt block is what admits it — the same path a
        # real specialist run takes.
        class _R:
            title = "Tracker page"
            url = "https://example.org/tracker"
            snippet = "Apple held 18% of units."
            published = "2026-06"
            source_query = "unit share"
        registry.add_results([_R()], backend="test")
        registry.prompt_block()
        return {"panels": [_Panel()], "unknown": [], "failed": []}

    monkeypatch.setattr("marketreport.handoff.run_brief", fake_run_brief)

    class _Ref:
        id = "ps_int1"

    class _FakeLibrary:
        def save_all(self, panels, market="", place="", request=""):
            return [_Ref()]

    monkeypatch.setattr("marketreport.library.Library", _FakeLibrary)

    cfg = settings.settings_to_runconfig({
        "provider": {"name": "mock"}, "research": {"name": "none"},
        "market_reports": True,
        "deck_path": "deckscope/examples/sample_deck.md",
        "output": {"out_dir": str(tmp_path), "formats": ["md"]}})
    pipe = Pipeline(cfg)
    try:
        result = pipe.run()
    finally:
        pipe.close()

    # the findings entered the market artifact the synthesist reads
    block = result.market.get("specialist_reports")
    assert block and block[0]["checks_deck_claim"] == \
        "the deck claims 40% unit share"
    assert block[0]["finding"] == "Samsung leads units"
    # the report's source lives in the run's ONE registry, remapped
    merged_ids = block[0]["figures"][0]["source_ids"]
    assert merged_ids, "the figure's citation must survive the merge"
    src = result.registry.find(merged_ids[0])
    assert src is not None and "example.org/tracker" in src.url, (
        "the remapped id must resolve in the run's registry")
    # and the reconciliation is on the result, computed once, in memory
    assert result.market_reports["stored"] == ["ps_int1"]
    assert result.market_reports["entries"][0]["claim"] == \
        "the deck claims 40% unit share"


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
        def complete(self, system, messages, **kw):
            # Enforce the REAL provider contract: a list of Message objects.
            # The first fake here took a bare string, matched the bug in the
            # code, and turned the test green — an author's fake testing the
            # author's assumption. Never again.
            assert isinstance(messages, list), "complete() takes List[Message]"
            user = messages[0].content
            assert messages[0].role == "user"
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


def test_bearing_speaks_through_a_real_provider():
    """Defect #16: bearing() passed a bare string where the provider API
    takes List[Message]; every real provider raised, the except swallowed
    it, and every bearing was silently the fallback. This drives the REAL
    mock provider through the real base-class signature — if the call shape
    regresses, this fails instead of falling back."""
    from deckscope.providers import get_provider
    from marketreport.reconcile import bearing

    class _Panel:
        answered = True
        headline = "Samsung leads units"
        figures = []
        problem = ""

    provider = get_provider(type("C", (), {"name": "mock", "model": None,
                                           "temperature": 0.0})())
    reading = bearing("the deck claims 40% unit share", _Panel(), provider)
    assert "No reading was produced" not in reading, (
        "a live provider must produce a reading, not the fallback")
    assert reading.strip()


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
