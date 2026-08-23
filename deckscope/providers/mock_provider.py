"""Deterministic fake model. Powers `deckscope demo` and the test suite.

Produces schema-shaped output with no network calls, so a new user can see the
whole pipeline end to end before they have configured any AI at all.
"""
from __future__ import annotations

import json
from typing import Optional

from ..config import ProviderConfig
from .base import Completion, LLMProvider


class MockProvider(LLMProvider):
    name = "mock"
    default_model = "mock-1"
    catalog = [("mock-1", "Offline demo — no AI needed, fake but realistic output")]

    def __init__(self, config: Optional[ProviderConfig] = None) -> None:
        super().__init__(config)
        self.calls = 0
        # A panel of mocks must not be unanimous, or the panel code paths never
        # get exercised. The model name seeds a small, deterministic divergence.
        self.seed = sum(ord(c) for c in (self.model or "mock-1")) % 3

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        self.calls += 1
        joined = " ".join(m.content for m in messages)
        if "JSON array of strings only" in system or "search queries" in system:
            return Completion(text=json.dumps([
                "workflow automation market size 2026 independent estimate",
                "Zapier Make n8n pricing comparison mid-market",
                "RPA vendor consolidation 2026 funding rounds",
            ]))
        if "Deck Analyst" in system:
            return Completion(text=json.dumps(_DECK))
        if "Market Analyst" in system:
            return Completion(text=json.dumps(_MARKET))
        if "Comparison Synthesist" in system:
            return Completion(text=json.dumps(self._compare()))
        if "one member of a panel" in system:
            return Completion(text=json.dumps(self._review()))
        if "final version of your analysis" in system:
            revised = self._compare()
            revised["revision_log"] = [{
                "field": "scorecard: Competitive position",
                "from": str(revised["scorecard"][1]["score"]),
                "to": str(min(10, revised["scorecard"][1]["score"] + 1)),
                "reason": "A peer cited a source on incumbent bundling that I had missed.",
                "prompted_by": "Panelist A"}]
            revised["scorecard"][1]["score"] = min(10, revised["scorecard"][1]["score"] + 1)
            return Completion(text=json.dumps(revised))
        if "chair of a panel" in system:
            return Completion(text=json.dumps(_CONSENSUS))
        return Completion(text=json.dumps({"note": "mock", "echo": joined[:200]}))

    def _compare(self) -> dict:
        """A copy of the base comparison, nudged so panelists actually differ."""
        import copy

        out = copy.deepcopy(_COMPARE)
        if self.seed == 0:
            return out
        delta = -2 if self.seed == 1 else 1
        for row in out["scorecard"]:
            row["score"] = max(1, min(10, int(row["score"]) + delta))
        if self.seed == 1:
            out["verdict"]["call"] = "LEAN NO"
            out["verdict"]["confidence"] = "low"
            out["headline"] = ("Traction is real, but the incumbent bundling risk is "
                               "unaddressed and the market framing is inflated.")
            out["claim_audit"][1]["assessment"] = "contradicted"
        else:
            out["verdict"]["confidence"] = "high"
            out["claim_audit"][0]["assessment"] = "contradicted"
        return out

    def _review(self) -> dict:
        return {
            "peer_reviews": [{
                "panelist": "Panelist A",
                "agreements": ["Traction is strong for the stage"],
                "disagreements": [{
                    "topic": "How much the TAM overstatement matters",
                    "their_position": "It is a framing error only",
                    "your_position": "It signals weak diligence habits",
                    "who_has_better_evidence": "neither", "why":
                        "Neither of us has evidence about the founders' process.",
                    "source_ids": ["S1"]}],
                "errors_found": [{
                    "severity": "material",
                    "what": "Treated a vendor-sponsored 2030 projection as a 2026 figure",
                    "why_it_is_wrong": "The source is a roll-up across three categories.",
                    "source_ids": ["S1"]}],
                "evidence_they_have_that_you_lack": ["A bottom-up sizing source"],
                "blind_spots_they_caught": ["Incumbent bundling inside E5 licences"],
                "overall": "comparable to mine",
                "notes": "Reached a similar place by a different route."}],
            "position_changes": [{
                "what_changes": "Competitive position score",
                "from": "5", "to": "6",
                "prompted_by": "Panelist A",
                "evidence": "They cited a source on bundling economics I had not seen.",
                "source_ids": ["S2"]}],
            "positions_held": [{
                "position": "The TAM figure is materially overstated",
                "challenged_by": "Panelist C",
                "why_you_hold_it": "The challenge asserted a different number without "
                                   "citing a source that contains it."}],
            "will_revise": "true",
            "self_assessment": "My first pass leaned on the deck's own category "
                               "definition instead of setting my own boundary.",
        }


_DECK = {
    "company": {"name": "Acme Flow", "one_liner": "AI agents that run back-office workflows",
                "stage": "seed", "founded": "2024", "location": "Austin, TX", "website": None},
    "problem": {"statement": "Ops teams stitch together brittle no-code automations",
                "who_has_it": "Mid-market ops leaders, 200-2000 employees",
                "evidence_given": ["Cites 14 customer interviews", "No third-party data"]},
    "solution": {"description": "Agentic workflow runtime with human approval gates",
                 "how_it_works": "LLM planner plus deterministic executors over connectors",
                 "differentiators": ["Approval gates", "Self-healing retries"],
                 "technical_moat_claimed": "Proprietary execution graph"},
    "product": {"maturity": "beta", "demo_evidence": "Screenshots only, no live metrics"},
    "market": {"category": "Workflow automation / agentic RPA", "sub_category": "Mid-market ops",
               "tam_claimed": "$47B", "sam_claimed": "$6B", "som_claimed": "$400M",
               "tam_methodology": "top-down", "growth_rate_claimed": "23% CAGR",
               "geography": "North America first", "customer_segments": ["Mid-market ops", "Finance ops"]},
    "business_model": {"pricing": "$2k/mo platform + usage", "unit_economics": "Not shown",
                       "acv_or_arpu": "$28k", "cac_claimed": None, "ltv_claimed": None,
                       "gross_margin_claimed": "78%"},
    "traction": {"revenue": "$340k ARR", "growth": "18% MoM for 4 months",
                 "customers": "11 paying", "logos": ["Two mid-market logos shown"],
                 "pipeline": "$1.2M claimed", "retention": "Not disclosed",
                 "other_metrics": ["3 design partners converted"]},
    "competition": {"named_competitors": ["Zapier", "Make"],
                    "positioning_claim": "More reliable than no-code, cheaper than RPA",
                    "competitors_omitted_suspicion": ["UiPath", "Microsoft Power Automate", "n8n"]},
    "gtm": {"channels": ["Founder-led sales", "Ops communities"],
            "sales_motion": "Inbound plus outbound", "partnerships": []},
    "team": {"founders": [{"name": "A. Rivera", "role": "CEO", "background": "Ex-ops lead"},
                          {"name": "J. Park", "role": "CTO", "background": "Ex-infra eng"}],
             "headcount": "7", "notable_advisors": []},
    "ask": {"amount": "$4M seed", "valuation": "$24M post", "use_of_funds": ["8 hires", "GTM"],
            "milestones_promised": ["$2M ARR in 18 months"], "runway_claimed": "22 months"},
    "claims": [
        {"id": "C1", "claim": "$47B TAM growing 23% CAGR", "type": "market-size", "slide": 5,
         "verifiability": "verifiable", "load_bearing": "high"},
        {"id": "C2", "claim": "More reliable than no-code incumbents", "type": "competition",
         "slide": 8, "verifiability": "partially-verifiable", "load_bearing": "high"},
        {"id": "C3", "claim": "18% MoM growth", "type": "traction", "slide": 10,
         "verifiability": "verifiable", "load_bearing": "high"},
        {"id": "C4", "claim": "78% gross margin", "type": "financial", "slide": 11,
         "verifiability": "partially-verifiable", "load_bearing": "medium"}],
    "deck_quality": {"missing_sections": ["Retention", "CAC"], "vague_language": ["'enterprise-grade'"],
                     "unsupported_numbers": ["$1.2M pipeline"], "narrative_coherence": 7,
                     "notes": "Clear story, thin on evidence for the economics."},
    "research_agenda": {"search_queries": ["workflow automation TAM 2026"],
                        "key_uncertainties": ["Whether $47B is the right denominator"]},
}

_MARKET = {
    "market_definition": {"category": "Agentic workflow automation",
                          "boundary_notes": "Overlaps iPaaS, RPA, and agent platforms; the $47B figure usually spans all three.",
                          "how_analysts_segment_it": ["iPaaS", "RPA", "Agent platforms"]},
    "sizing": {"tam_estimates": [
        {"value": "$18-24B", "year": "2026", "source": "Independent analyst composite",
         "methodology": "bottom-up seat and usage build", "url": None,
         "source_ids": ["S1", "S2"]},
        {"value": "$47B", "year": "2030", "source": "Vendor-sponsored report",
         "methodology": "top-down category roll-up", "url": None,
         "source_ids": ["S3"]}],
        "consensus_view": "Serviceable mid-market slice is closer to $3-5B today [S1][S2].",
        "cagr_range": "15-22%", "sizing_confidence": "medium",
        "why_estimates_diverge": "Whether legacy RPA seats are counted in the same bucket."},
    "demand_signals": {"tailwinds": ["Agent budgets moving from experiment to line item"],
                       "headwinds": ["Incumbent bundling", "Buyer fatigue with pilots"],
                       "buyer_budget_reality": "Mid-market ops budgets are flat; spend is substitution, not net-new.",
                       "adoption_stage": "early-adopters"},
    "competitive_landscape": {
        "incumbents": [{"name": "Microsoft Power Automate", "position": "Bundled with E5",
                        "funding_or_scale": "Public", "threat_level": "high", "url": None,
                        "source_ids": ["S2"]},
                       {"name": "UiPath", "position": "Enterprise RPA incumbent moving to agents",
                        "funding_or_scale": "Public", "threat_level": "high", "url": None}],
        "challengers": [{"name": "Zapier", "position": "SMB long tail", "funding_or_scale": "Late-stage",
                         "threat_level": "medium", "url": None},
                        {"name": "n8n", "position": "Open-source, developer-led",
                         "funding_or_scale": "Series B", "threat_level": "medium", "url": None}],
        "adjacent_threats": ["Foundation-model vendors shipping native agent runtimes"],
        "concentration": "consolidating",
        "differentiation_axes": ["Reliability/observability", "Connector depth", "Compliance"]},
    "economics": {"typical_pricing": "$1-4k/mo platform plus usage",
                  "typical_gross_margin": "65-80% once inference is loaded in",
                  "typical_cac_payback": "14-20 months mid-market", "capital_intensity": "medium"},
    "funding_environment": {"recent_rounds": [
        {"company": "Comparable A", "round": "Seed", "amount": "$5M", "date": "2026-02", "url": None}],
        "valuation_norms": "$18-30M post at seed with early revenue",
        "exit_comps": ["Strategic acquisitions by iPaaS incumbents at 6-10x ARR"],
        "investor_appetite": "steady", "notes": "Agent infra is funded; agent apps face show-me-the-retention pressure."},
    "regulatory_and_structural": {"factors": ["SOC2 expected at first enterprise deal"], "risk_level": "low"},
    "sources": [{"title": "Independent analyst composite", "url": "https://example.org/report",
                 "date": "2026-03", "reliability": "secondary"}],
    "research_gaps": ["No public retention benchmarks for agentic workflow tools."],
}

_COMPARE = {
    "headline": "Real early traction in a real market, but the deck sizes the wrong denominator and ignores the incumbent that ships this in a bundle.",
    "verdict": {"call": "YES WITH CONDITIONS", "confidence": "medium",
                "confidence_rationale": "Traction is verifiable; retention and CAC are not disclosed."},
    "scorecard": [
        {"dimension": "Market size & timing", "score": 7, "weight": 5,
         "rationale": "Category is real and growing, but the serviceable slice is roughly an order of magnitude below the claimed TAM.",
         "evidence": ["Independent composite puts mid-market slice at $3-5B [S1]"],
         "source_ids": ["S1", "S2"]},
        {"dimension": "Competitive position", "score": 5, "weight": 5,
         "rationale": "Power Automate's bundling is unaddressed and is the likeliest reason a deal dies.",
         "evidence": ["Deck names only Zapier and Make"]},
        {"dimension": "Product & moat", "score": 6, "weight": 4,
         "rationale": "Approval gates are a genuine wedge; the 'proprietary execution graph' is asserted, not shown.", "evidence": []},
        {"dimension": "Business model", "score": 6, "weight": 3,
         "rationale": "78% margin is plausible but only if inference is loaded in, which the deck never states.", "evidence": []},
        {"dimension": "Traction vs. stage", "score": 8, "weight": 5,
         "rationale": "$340k ARR with 18% MoM is strong for seed; retention silence is the caveat.", "evidence": []},
        {"dimension": "Team", "score": 7, "weight": 3, "rationale": "Domain-credible founding pair.", "evidence": []},
        {"dimension": "Ask & plan", "score": 7, "weight": 3,
         "rationale": "$4M on $24M post is at market; the $2M ARR milestone implies a step-change in sales efficiency.", "evidence": []}],
    "claim_audit": [
        {"id": "C1", "claim": "$47B TAM growing 23% CAGR",
         "market_evidence": "The $47B figure is a 2030 vendor-sponsored roll-up spanning iPaaS, RPA, and agents; independent 2026 estimates land at $18-24B, and the mid-market slice at $3-5B.",
         "assessment": "partially-supported",
         "delta": "Roughly 10x overstatement of the addressable denominator.",
         "so_what": "The $400M SOM survives; the framing does not. Reframe around the $3-5B slice.",
         "source_ids": ["S1", "S2"], "evidence_quality": "moderate",
         "sources": []},
        {"id": "C2", "claim": "More reliable than no-code incumbents",
         "market_evidence": "Reliability is a real differentiation axis, but no public benchmark exists.",
         "assessment": "unverifiable", "delta": "Directionally right, unproven.",
         "so_what": "Publish a reliability metric from live customers.", "sources": []},
        {"id": "C3", "claim": "18% MoM growth",
         "market_evidence": "Consistent with seed comps raising in this category.",
         "assessment": "supported", "delta": "None.", "so_what": "This is the strongest slide.",
         "source_ids": ["S2"], "evidence_quality": "moderate", "sources": []},
        {"id": "C4", "claim": "78% gross margin",
         "market_evidence": "Category norm is 65-80% once inference costs are included.",
         "assessment": "partially-supported", "delta": "Top of range; depends on whether inference is in COGS.",
         "so_what": "State the COGS definition explicitly.", "sources": []}],
    "alignment": {
        "where_deck_matches_market": ["Growth rate is at or above seed comps",
                                      "Reliability is genuinely how buyers choose here"],
        "where_deck_overstates": ["TAM by roughly an order of magnitude",
                                  "Pipeline figure has no stated definition"],
        "where_deck_understates": ["Approval gates map directly to a compliance requirement buyers already have budget for"],
        "blind_spots": ["Microsoft Power Automate arriving free inside E5",
                        "Buyer budgets are substitution, not net-new"]},
    "risks": [
        {"risk": "Incumbent bundling compresses price before scale", "severity": "high",
         "likelihood": "high", "mitigation_or_test": "Win two deals against Power Automate and document why."},
        {"risk": "Retention unknown", "severity": "high", "likelihood": "medium",
         "mitigation_or_test": "Disclose logo and net-revenue retention for the first cohort."}],
    "integrity_note": None,
    "questions": ["What is net revenue retention on the first 11 customers?",
                  "How many deals were competitive against Power Automate, and what happened?",
                  "Is inference cost inside the 78% margin?"],
    "actions": [{"action": "Reframe market slide around the $3-5B serviceable slice", "owner": "Founders", "priority": "P0"},
                {"action": "Add a slide addressing Power Automate directly", "owner": "Founders", "priority": "P0"},
                {"action": "Disclose retention and CAC payback", "owner": "Founders", "priority": "P1"}],
    "summary": "Acme Flow is pitching into a market that genuinely exists and is genuinely growing, which is more than can be said for most agentic-workflow decks. The traction is the strongest part of the story: $340k ARR with four consecutive months of 18% growth is above the median seed comp in this category, and it is a number an investor can verify quickly.\n\nThe market slide is where the deck and the evidence part company. The $47B figure is a 2030 projection from a vendor-sponsored roll-up that bundles legacy RPA seats, iPaaS, and agent platforms into one number. Independent 2026 estimates put the whole category at $18-24B, and the slice a mid-market agentic tool can actually serve at $3-5B. That is roughly a tenfold gap. Notably, the company's own $400M SOM survives this correction intact, which means the overstatement buys them nothing and costs them credibility with anyone who checks.\n\nThe more serious omission is competitive. The deck names Zapier and Make and stops there. The market evidence points squarely at Microsoft Power Automate, which arrives bundled inside E5 licenses that this exact buyer already pays for, and at UiPath, which is moving its enterprise base toward agents. An investor who has seen five of these decks this quarter will ask about bundling in the first ten minutes, and the deck has no answer prepared.\n\nWhat the deck understates is its own wedge. Approval gates are not a feature footnote — they map onto a compliance requirement that mid-market finance ops already have budget for, and reliability is one of the three axes buyers in this category actually decide on. That argument is stronger than the TAM argument the deck leads with.\n\nOn balance: the market is real, the traction is real, the framing is inflated, and the competitive picture is incomplete. Two disclosures would resolve most of the uncertainty — net revenue retention on the first cohort, and the outcome of any deal contested against Power Automate.",
}


_CONSENSUS = {
    "headline": "The panel agrees the traction is real and the market framing is "
                "inflated; it splits on whether incumbent bundling is fatal.",
    "consensus_verdict": {
        "call": "YES WITH CONDITIONS", "confidence": "medium", "agreement": "majority",
        "rationale": "Two of three panelists reached this call independently, and the "
                     "dissent rests on a risk none of them could size with the "
                     "available evidence."},
    "where_all_agree": [
        {"point": "The claimed $47B TAM is the wrong denominator for this company",
         "why_it_is_robust": "Every panelist reached it independently, and two cited "
                             "separate sources [S1][S2]."},
        {"point": "$340k ARR at 18% MoM is strong for seed",
         "why_it_is_robust": "No panelist challenged it at any point."}],
    "contested": [{
        "topic": "Whether Microsoft's bundling is fatal or merely compressive",
        "positions": [
            {"panelist": "Panelist A", "position": "Compressive — it caps price, not access",
             "evidence_quality": "moderate", "source_ids": ["S2"]},
            {"panelist": "Panelist B", "position": "Fatal at this stage — the buyer "
                                                    "already owns the licence",
             "evidence_quality": "weak", "source_ids": []}],
        "resolution": "The available evidence supports price compression; nobody produced "
                      "win/loss data, which is what the question actually turns on.",
        "what_would_settle_it": "The outcome of the deals contested against Power "
                                "Automate, with reasons."}],
    "claim_consensus": [
        {"id": "C1", "claim": "$47B TAM growing 23% CAGR",
         "assessments": {"Panelist A": "partially-supported", "Panelist B": "contradicted"},
         "consensus": "partially-supported", "confidence": "medium",
         "note": "Disagreement is about severity, not direction."},
        {"id": "C3", "claim": "18% MoM growth",
         "assessments": {"Panelist A": "supported", "Panelist B": "supported"},
         "consensus": "supported", "confidence": "high",
         "note": "Unanimous, and reached before any cross-review."}],
    "minority_report": [{
        "panelist": "Panelist B",
        "position": "A seed company selling automation into a buyer who already owns "
                    "Power Automate is selling against zero marginal cost, and no amount "
                    "of reliability advantage survives that at renewal.",
        "why_it_deserves_a_hearing": "It is the only position that would be falsified "
                                     "quickly by data the company already has."}],
    "reliability": {
        "what_agreement_means_here": "The panel converged on the market-sizing point "
                                     "before cross-review, from the same two sources. "
                                     "That is agreement about a source, not independent "
                                     "corroboration.",
        "shared_blind_spots": ["All panelists relied on the same bibliography",
                               "No panelist had access to private win/loss data"],
        "caution": "Treat the unanimous points as well-supported, not as proven. The "
                   "contested point is where your own diligence should go first."},
    "summary": "Three models analyzed the same deck without seeing each other's work, "
               "then read each other and revised. They converged quickly on two things: "
               "the traction is real for the stage, and the $47B market figure is the "
               "wrong denominator [S1][S2].\n\nThey split on the competitive question. "
               "Two read Microsoft's bundling as price compression; one read it as an "
               "access problem that ends the company at renewal. That split did not "
               "close after cross-review, because neither position rests on evidence the "
               "panel could obtain — it turns on win/loss data only the company has.\n\n"
               "The most useful output here is not the verdict but the location of the "
               "disagreement. Every panelist independently arrived at the same question, "
               "and none could answer it. That is where diligence should start."
}
