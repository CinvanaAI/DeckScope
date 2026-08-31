"""The fifth external audit's analytical findings, pinned.

The stop-ship items live in test_nda_enforcement.py; this file pins the
comparison-layer chimera and its relatives: a $6B claim "contradicted" by
evidence saying $6-8B, because the median of two findings selected the $41B
whole-category value and displayed it beside the other finding's range text.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.claims import Claim, ClaimRegister
from deckscope.compare import assess_claims
from deckscope.research.findings import FindingRegistry


def _register(claim_text, value_text):
    register = ClaimRegister()
    register.claims.append(Claim(id="C1", text=claim_text,
                                 value_text=value_text))
    return register


def _findings(rows):
    findings = FindingRegistry()
    for statement, value_text, sids in rows:
        findings.add(statement, value_text=value_text, question_id="Q1",
                     unit="USD", beat="sizing", source_ids=sids,
                     claims=["C1"])
    return findings


def test_a_claim_inside_the_evidence_range_is_supported():
    """The audit's exact reproduction: $6B claimed, one finding of $6-8B
    (stored midpoint $7B) and one $41B whole-category figure. The old code
    contradicted the claim at "6.8x below" while printing $6-8B beside the
    verdict."""
    out = assess_claims(
        _register("SAM: $6B (mid-market North America)", "$6B"),
        _findings([
            ("The mid-market addressable segment is $6-8B.", "$6-8B",
             ["S1"]),
            ("The whole category, under a wider definition, is $41B.",
             "$41B", ["S2"]),
        ]))
    a = out[0]
    assert a.assessment == "supported", (a.assessment, a.because)
    assert "6.8" not in (a.gap_text or "")


def test_the_displayed_evidence_and_the_ratio_come_from_one_finding():
    """A genuinely contradicted claim must print the SAME finding it
    measured against — never one finding's ratio beside another's text."""
    out = assess_claims(
        _register("TAM is $47B", "$47B"),
        _findings([
            ("Independent estimates put the category at $18-24B.",
             "$18-24B", ["S1"]),
        ]))
    a = out[0]
    assert a.assessment == "contradicted"
    assert "$18-24B" in a.because
    # ratio measured to the NEAREST BOUND (24B), not a midpoint: 47/24 ≈ 2.0
    assert a.ratio is not None and 1.9 < a.ratio < 2.1, a.ratio


def test_a_claim_below_a_range_measures_against_the_lower_bound():
    out = assess_claims(
        _register("The market is $2B", "$2B"),
        _findings([("Estimates cluster at $6-8B.", "$6-8B", ["S1"])]))
    a = out[0]
    assert a.assessment == "contradicted"
    assert a.ratio is not None and 2.9 < a.ratio < 3.1, (
        "the gap is to the range's nearest edge (6B), not its midpoint")


def test_a_wildly_different_boundary_is_not_a_contradiction():
    """The nearest finding still rules: when even it is orders of magnitude
    away, the honest reading stays 'measuring different things'."""
    out = assess_claims(
        _register("ARR is $520k", "$520k"),
        _findings([("The category is $2.6-3.0B.", "$2.6-3.0B", ["S1"])]))
    a = out[0]
    assert a.assessment == "partially-supported"
    assert "not checked rather than judged" in a.because


def test_sentence_openers_never_become_organizations():
    """The demo told a founder their deck failed to mention organizations
    called "Report", "State", "Typical" and "Average" — each a capitalized
    sentence opener the stoplist happened not to contain. Form decides now,
    not list membership."""
    from deckscope.compare import _subjects

    for s in ("Report is named in the research as active in this market.",
              "State licensing applies. Typical margins are 60%.",
              "Average contract values cluster near $19k."):
        assert _subjects(s) == [], s


def test_real_names_still_generate_omissions():
    from deckscope.compare import _subjects

    got = _subjects("The buyer evaluated Microsoft Power Automate for this.")
    assert "Microsoft" in got
    assert "Workato" in _subjects("Deals are lost to Workato in this segment.")


def test_barrier_trend_is_unknown_when_only_one_vintage_was_read():
    """"Steady" is a specific empirical claim; one vintage supports no
    direction at all."""
    from marketreport.structure import barriers

    graded = barriers(startup_cost=50_000)
    assert graded.trend == "unknown"
    assert "unknown" in graded.because


def test_lifecycle_refuses_establishment_count_growth():
    """Q4's own statement warns that location counts and revenue can move in
    opposite directions; the lifecycle agent then declared the market
    'mature' from that count anyway."""
    import marketreport.agents  # noqa: F401
    from marketreport.report import MarketDefinition, build

    answers = build(MarketDefinition(label="Landscaping", naics="561730",
                                     state_fips="04", demo=True),
                    on_event=lambda m: None)
    q10 = answers.get("Q10")
    assert not q10.answered
    assert "wrong quantity" in q10.unanswered_because


def test_closure_accepts_an_established_not_identifiable():
    """The report correctly establishes that CR4 cannot be known from
    establishment data; its completeness gate must not hold the report
    hostage for the number it just explained cannot exist."""
    import marketreport.agents  # noqa: F401
    from marketreport.report import MarketDefinition, build

    answers = build(MarketDefinition(label="Landscaping", naics="561730",
                                     state_fips="04", demo=True),
                    on_event=lambda m: None)
    closure = answers.closure()
    open_cr4 = [o for o in closure["open"]
                if "cr4" in str(o.get("needs", ""))]
    assert not open_cr4, (
        "a reasoned not-identifiable answers the follow-up: "
        f"{open_cr4}")


def test_dispersion_prose_names_locations_and_its_own_estimation():
    from marketreport.structure import shape

    form = shape({"1-4": 5000, "1000+": 2})
    assert "firms" not in form.reading
    assert "establishments" in form.reading or "locations" in form.reading \
        or "sole-operator" in form.reading
    assert "estimated from size-band midpoints" in form.because
