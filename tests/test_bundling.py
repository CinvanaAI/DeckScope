"""Open-source parity as a bundling signal.

The assessment is deterministic on purpose, so it can be tested against the real
cases it was modelled on rather than against its own output. The discriminating
property is that OSS parity alone must NOT decide the answer — what remains once
open source arrives has to decide it, because that is what actually happened.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.bundling import LEVELS, assess


def _oss(gap, provides, trend="stable", **kw):
    base = {"applicable": True, "closest_project": "Project X",
            "capability_gap": gap, "gap_trend": trend,
            "what_commercial_still_provides": provides}
    base.update(kw)
    return base


# ============================================== the cases this models

def test_parity_plus_a_distribution_moat_is_the_worst_case():
    """Kubernetes reached parity; Docker's residual moat was distribution."""
    a = assess(_oss("at parity", [
        {"capability": "Registry and desktop packaging", "type": "packaging",
         "durable": False},
        {"capability": "Enterprise distribution", "type": "distribution",
         "durable": False}], trend="closed"))
    assert a.level == "severe"
    assert "platform vendor already owns" in a.reasoning


def test_parity_with_an_operational_moat_is_not_the_worst_case():
    """Open-source warehouses existed throughout Snowflake's rise.

    Same open-source position as the case above, materially different reading —
    which is the whole point of separating parity from what remains.
    """
    a = assess(_oss("approaching parity", [
        {"capability": "Zero-ops elasticity at scale", "type": "operational",
         "durable": True},
        {"capability": "Governance and sharing", "type": "data-network",
         "durable": True}], trend="narrowing"))
    assert a.level in ("low", "moderate", "elevated")
    assert LEVELS.index(a.level) < LEVELS.index("severe")


def test_open_source_far_behind_reads_as_a_healthy_market():
    a = assess(_oss("far behind", [
        {"capability": "The product itself", "type": "workflow-depth",
         "durable": True}]))
    assert a.level == "low"
    assert "differentiated on capability" in a.reasoning


def test_the_same_gap_with_different_residuals_gives_different_answers():
    """The discriminating property, stated directly."""
    fragile = assess(_oss("at parity", [
        {"capability": "Nicer packaging", "type": "packaging", "durable": False}]))
    defensible = assess(_oss("at parity", [
        {"capability": "Audit-grade compliance", "type": "compliance",
         "durable": True}]))
    assert LEVELS.index(fragile.level) > LEVELS.index(defensible.level)


def test_a_single_durable_moat_is_enough():
    """A company survives on its best defence, not its average one."""
    a = assess(_oss("at parity", [
        {"capability": "Packaging", "type": "packaging", "durable": False},
        {"capability": "Distribution", "type": "distribution", "durable": False},
        {"capability": "Compliance depth", "type": "compliance", "durable": True}]))
    assert LEVELS.index(a.level) <= LEVELS.index("elevated")
    assert any("compliance" in d for d in a.durable)


# ================================================== trend and caveats

def test_a_narrowing_gap_raises_the_reading():
    stable = assess(_oss("approaching parity", [
        {"capability": "Ops", "type": "operational", "durable": True}], trend="stable"))
    narrowing = assess(_oss("approaching parity", [
        {"capability": "Ops", "type": "operational", "durable": True}],
        trend="narrowing"))
    assert LEVELS.index(narrowing.level) > LEVELS.index(stable.level)


def test_a_widening_gap_lowers_the_reading():
    stable = assess(_oss("approaching parity", [
        {"capability": "Packaging", "type": "packaging", "durable": False}],
        trend="stable"))
    widening = assess(_oss("approaching parity", [
        {"capability": "Packaging", "type": "packaging", "durable": False}],
        trend="widening"))
    assert LEVELS.index(widening.level) < LEVELS.index(stable.level)


def test_naming_no_remaining_differentiation_is_itself_a_finding():
    a = assess(_oss("at parity", []))
    assert any("nothing to name" in c for c in a.caveats)


def test_significant_pricing_pressure_is_flagged():
    a = assess(_oss("approaching parity", [
        {"capability": "Ops", "type": "operational", "durable": True}],
        pricing_pressure="severe"))
    assert any("precedes bundling" in c for c in a.caveats)


def test_disagreement_with_the_market_agent_is_surfaced():
    """A derived signal that contradicts the model's own verdict must say so."""
    a = assess(_oss("at parity", [
        {"capability": "Packaging", "type": "packaging", "durable": False}]),
        {"verdict": "product"})
    assert any("disagree" in c for c in a.caveats)


# ==================================================== absence and gaps

def test_a_category_with_no_open_source_dimension_says_so():
    a = assess({"applicable": False})
    assert a.applicable is False
    assert a.level == "not applicable"
    assert "says nothing about it either way" in a.reasoning


def test_an_unknown_gap_is_not_treated_as_safe():
    a = assess({"applicable": True, "projects": [{"name": "X"}],
                "capability_gap": "who knows"})
    assert a.level == "unknown"
    assert "not the same as low risk" in a.reasoning


def test_missing_input_does_not_raise():
    for payload in (None, {}, {"applicable": True}):
        assert assess(payload) is not None


# ========================================================== end to end

def test_the_assessment_reaches_the_report(tmp_path):
    from deckscope.config import (OutputConfig, ProviderConfig, ResearchConfig,
                                  RunConfig)
    from deckscope.orchestrator import Pipeline

    deck = Path(__file__).resolve().parent.parent / "deckscope" / "examples" / "sample_deck.md"
    cfg = RunConfig(deck_path=str(deck), provider=ProviderConfig(name="mock"),
                    research=ResearchConfig(name="none"),
                    output=OutputConfig(formats=["md"], out_dir=str(tmp_path)),
                    cache_dir=None, verbose=False)
    pipe = Pipeline(cfg)
    result = pipe.run()
    pipe.render(result)
    pipe.close()

    assessment = result.market.get("bundling_assessment")
    assert assessment and assessment.get("level")
    text = Path(result.written_files[0]).read_text(encoding="utf-8")
    assert "Open source, and what it predicts" in text
    assert "Bundling risk from commoditization" in text
    assert "What commercial products still provide" in text
