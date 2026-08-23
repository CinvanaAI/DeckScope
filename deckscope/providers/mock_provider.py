"""Deterministic fake model. Powers `deckscope demo` and the test suite.

Produces schema-shaped output with no network calls, so a new user can see the
whole pipeline end to end before they have configured any AI at all.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

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

    def _usage(self, system, messages, out: str) -> dict:
        """Rough token counts, so usage accounting is exercised offline.

        Real providers report these; the mock reporting zero meant the accounting
        path was never tested and a regression there would have been invisible.
        """
        chars_in = len(system) + sum(len(m.content) for m in messages)
        return {"input": max(1, chars_in // 4), "output": max(1, len(out) // 4)}

    @staticmethod
    def _available_sids(prompt: str) -> set:
        """The S-IDs actually offered in this prompt's bibliography."""
        return {f"S{n}" for n in re.findall(r"^\[S(\d{1,3})\]", prompt, re.M)}

    @classmethod
    def _clamp_citations(cls, node: Any, allowed: set) -> Any:
        """Drop any citation to a source this prompt did not offer.

        The mock's fixtures are written against a three-source bibliography, but
        a case can supply fewer — the thin-evidence case supplies exactly one.
        Emitting S2 and S3 anyway made the mock fabricate citations, which is a
        real defect and was scored as one the moment citation checking stopped
        looking only at `claim_audit`. A competent analyst does not cite what it
        was not given, and the mock has to clear the structural bar it exists to
        measure. Prose references are rewritten too, so the text cannot disagree
        with the structured field beside it.
        """
        if isinstance(node, dict):
            return {k: (sorted({s for s in v if str(s).upper() in allowed},
                               key=lambda s: int(str(s)[1:]))
                        if k == "source_ids" and isinstance(v, list)
                        else cls._clamp_citations(v, allowed))
                    for k, v in node.items()}
        if isinstance(node, list):
            return [cls._clamp_citations(v, allowed) for v in node]
        if isinstance(node, str):
            return re.sub(r"\[S(\d{1,3})\]",
                          lambda m: m.group(0) if f"S{m.group(1)}" in allowed else "",
                          node)
        return node

    def complete(self, system, messages, *, max_tokens=None, temperature=None,
                 tools=None) -> Completion:
        self.calls += 1
        joined = " ".join(m.content for m in messages)
        if "JSON array of strings only" in system or "search queries" in system:
            body = json.dumps([
                "workflow automation market size 2026 independent estimate",
                "Zapier Make n8n pricing comparison mid-market",
                "RPA vendor consolidation 2026 funding rounds",
            ])
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "Deck Analyst" in system:
            body = json.dumps(_deck_extraction(joined))
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "mapping a market from scratch" in system:
            body = json.dumps(_COLD_MARKET)
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "You write search queries to map a market" in system:
            body = json.dumps([
                "workflow automation who actually sells to mid-market ops teams",
                "workflow automation projects that failed and why",
                "where do mid-market ops budgets actually go",
            ])
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "Market Analyst" in system:
            allowed = self._available_sids(joined)
            body = json.dumps(self._clamp_citations(_market_analysis(joined), allowed))
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "evaluating a pitch deck against its market" in system:
            # A deliberately thinner answer than the pipeline's: fewer claims
            # examined and fewer blind spots, so the comparison has something to
            # show. Real models may of course do better or worse.
            import copy
            thin = copy.deepcopy(self._compare(joined))
            thin["claim_audit"] = thin["claim_audit"][:2]
            thin["alignment"]["blind_spots"] = thin["alignment"]["blind_spots"][:1]
            thin["risks"] = thin["risks"][:1]
            body = json.dumps(self._clamp_citations(
                thin, self._available_sids(joined)))
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "Comparison Synthesist" in system:
            body = json.dumps(self._clamp_citations(
                self._compare(joined), self._available_sids(joined)))
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "one member of a panel" in system:
            body = json.dumps(self._review())
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "final version of your analysis" in system:
            revised = self._compare()
            revised["revision_log"] = [{
                "field": "scorecard: Competitive position",
                "from": str(revised["scorecard"][1]["score"]),
                "to": str(min(10, revised["scorecard"][1]["score"] + 1)),
                "reason": "A peer cited a source on incumbent bundling that I had missed.",
                "prompted_by": "Panelist A"}]
            revised["scorecard"][1]["score"] = min(10, revised["scorecard"][1]["score"] + 1)
            body = json.dumps(self._clamp_citations(
                revised, self._available_sids(joined)))
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "extract listing facts" in system:
            body = json.dumps(_LISTING_FOR(joined))
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "published base rates" in system:
            body = json.dumps(_BASE_RATES)
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "ranking the other panelists" in system:
            body = json.dumps(self._ballot(joined))
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        if "chair of a panel" in system:
            body = json.dumps(_CONSENSUS)
            return Completion(text=body, model=self.model,
                              usage=self._usage(system, messages, body))
        body = json.dumps({"note": "mock", "echo": joined[:200]})
        return Completion(text=body, model=self.model,
                          usage=self._usage(system, messages, body))

    def _compare(self, prompt: str = "") -> dict:
        """A copy of the base comparison, nudged so panelists actually differ."""
        import copy

        out = copy.deepcopy(_COMPARE)
        audit = _claim_audit_for(prompt)
        if audit:
            out["claim_audit"] = audit
        if self.seed == 0:
            return out
        delta = -2 if self.seed == 1 else 1
        for row in out["scorecard"]:
            row["score"] = max(1, min(10, int(row["score"]) + delta))
        # Guard the indexes: a sparse deck can yield fewer claims than the canned
        # fixture had, and a demo fixture must never crash a real run.
        audit = out.get("claim_audit") or []
        if self.seed == 1:
            out["verdict"]["call"] = "LEAN NO"
            out["verdict"]["confidence"] = "low"
            out["headline"] = ("Traction is real, but the incumbent bundling risk is "
                               "unaddressed and the market framing is inflated.")
            if len(audit) > 1:
                audit[1]["assessment"] = "contradicted"
        else:
            out["verdict"]["confidence"] = "high"
            if audit:
                audit[0]["assessment"] = "contradicted"
        return out

    def _ballot(self, prompt: str) -> dict:
        """Rank whichever panelists appear in the prompt, seeded by model name.

        Deterministic but not identical across panelists, so the tally has
        something real to work with in tests.
        """
        import re

        seen = []
        for label in re.findall(r"Panelist [A-H]", prompt):
            if label not in seen:
                seen.append(label)
        if self.seed == 1:
            seen = list(reversed(seen))
        elif self.seed == 2 and len(seen) > 1:
            seen = seen[1:] + seen[:1]
        return {"ranking": [{"panelist": label,
                             "reason": "traceable figures and an honest confidence level"}
                            for label in seen],
                "note": "The panel under-weighted incumbent bundling across the board."}

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
        "differentiation_axes": ["Reliability/observability", "Connector depth", "Compliance"],
        "saturation": {
            "funded_competitors_known": 14,
            "new_entrants_trend": "slowing",
            "pricing_direction": "compressing",
            "consolidation_activity": "Two acquisitions of seed-stage tools by iPaaS "
                                       "incumbents in the last 18 months.",
            "lifecycle_stage": "maturing",
            "room_for_a_new_entrant": "a defensible niche remains",
            "why": "Entrant flow has slowed while acquisitions have picked up, which "
                   "usually marks the turn from land-grab to consolidation. The "
                   "compliance-gated mid-market slice is still thinly served."}},
    "absorption_risk": {
        "verdict": "contested",
        "horizon": "3-5 years",
        "confidence": "medium",
        "likely_absorbers": [
            {"name": "Microsoft", "why_them": "Already owns the identity, the desktop "
                                               "and the E5 licence this buyer pays for.",
             "mechanism": "bundle into an existing suite",
             "signals_already_visible": ["Power Automate agent features shipped in the "
                                          "last two releases",
                                         "Bundled at no incremental cost in E5"],
             "source_ids": ["S2"]},
            {"name": "Foundation-model vendors",
             "why_them": "A workflow runtime is a thin layer over tool-calling, which "
                         "they already ship natively.",
             "mechanism": "model-vendor native feature",
             "signals_already_visible": ["Native agent runtimes announced by two major "
                                          "model vendors"],
             "source_ids": []}],
        "precedents": [
            {"category": "Antivirus", "absorbed_by": "Operating system vendors",
             "how_long_it_took": "roughly a decade",
             "why_it_is_comparable": "A genuinely useful category that buyers stopped "
                                      "paying for separately once it shipped by default.",
             "source_ids": []},
            {"category": "File sync and share", "absorbed_by": "Microsoft and Google",
             "how_long_it_took": "about five years",
             "why_it_is_comparable": "Standalone leaders survived by moving upmarket "
                                      "into workflow, not by defending the core feature.",
             "source_ids": []}],
        "what_would_prevent_it": [
            "Compliance and audit depth that a bundled feature will not reach",
            "Connector coverage outside the Microsoft estate",
            "A buyer who deliberately avoids consolidating on one vendor"],
        "notes": "The approval-gate wedge is the part least likely to be bundled "
                  "cheaply, and is therefore where a durable position would have to be."},
    "open_source_landscape": {
        "applicable": True,
        "projects": [
            {"name": "n8n", "url": "https://n8n.io",
             "maturity": "production-ready", "adoption_signal": "widely self-hosted; "
                                                                 "large connector library",
             "governance": "single-vendor", "commercially_backed_by": "n8n GmbH, which "
                                                                       "sells cloud hosting",
             "source_ids": ["S1"]},
            {"name": "Apache Airflow", "url": None, "maturity": "category-leading",
             "adoption_signal": "the default for scheduled data workflows",
             "governance": "foundation", "commercially_backed_by": "Astronomer",
             "source_ids": []}],
        "closest_project": "n8n",
        "capability_gap": "approaching parity",
        "gap_trend": "narrowing",
        "evidence_for_the_gap": "n8n ships an agent runtime, a comparable connector "
                                 "count and human-approval steps. What it does not "
                                 "ship is audit-grade approval trails or SOC2 "
                                 "attestation for the hosted product.",
        "what_commercial_still_provides": [
            {"capability": "Audit-grade approval trails and attestation",
             "type": "compliance", "durable": True,
             "why": "Slow and expensive to reproduce, and the thing this buyer is "
                    "actually procuring."},
            {"capability": "Managed hosting and upgrades", "type": "operational",
             "durable": False,
             "why": "A platform vendor can fund this indefinitely."},
            {"capability": "Connector breadth", "type": "integrations", "durable": False,
             "why": "n8n's community library is closing this quickly."}],
        "pricing_pressure": "significant",
        "company_relationship_to_oss": "competes with it",
        "strip_mining_risk": None,
        "notes": "The compliance layer is the only thing here a platform vendor would "
                  "find genuinely slow to reproduce, which makes it the whole "
                  "defensible position rather than one feature among several."},
    "adjacent_markets": [
        {"market": "Enterprise iPaaS", "relationship": "converging with this one",
         "size_note": "$8-12B", "why_it_matters": "The same buyer, and incumbents are "
                                                   "extending into agentic execution.",
         "source_ids": ["S1"]},
        {"market": "Business process outsourcing",
         "relationship": "substitute", "size_note": None,
         "why_it_matters": "Mid-market ops teams often buy people instead of software "
                            "for exactly these workflows.",
         "source_ids": []},
        {"market": "Compliance and audit tooling",
         "relationship": "expansion opportunity", "size_note": None,
         "why_it_matters": "The approval-gate feature is a natural bridge, and is a "
                            "harder thing for a platform to bundle.",
         "source_ids": []}],
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


#: Deterministic stand-in for a market-data lookup, so the opportunity-cost path
#: is exercised offline. Two listed, one private, one unknown — the four states
#: the renderer has to handle.
_LISTINGS = {
    "microsoft power automate": {
        "listed": True, "ticker": "MSFT", "exchange": "NASDAQ",
        "market_cap_usd": 3.1e12, "revenue_usd": 2.45e11, "revenue_growth_pct": 15.0,
        "total_return_5y_multiple": 2.4, "total_return_1y_multiple": 1.2,
        "as_of": "2026-08",
        "note": "Power Automate is a product line, not separately listed — this is "
                "Microsoft, its parent."},
    "uipath": {
        "listed": True, "ticker": "PATH", "exchange": "NYSE",
        "market_cap_usd": 6.4e9, "revenue_usd": 1.4e9, "revenue_growth_pct": 9.0,
        "total_return_5y_multiple": 0.6, "total_return_1y_multiple": 0.9,
        "as_of": "2026-08", "note": ""},
    "zapier": {"listed": False, "ticker": None, "note": "privately held"},
}


def _LISTING_FOR(prompt: str) -> dict:
    low = prompt.lower()
    for key, payload in _LISTINGS.items():
        if key in low:
            return payload
    return {"listed": None, "ticker": None,
            "note": "could not determine whether this company is publicly traded"}


_BASE_RATES = {
    "base_rates": [
        {"statement": "Seed-stage software companies that return at least invested "
                      "capital", "value": "~35%",
         "population": "US seed rounds, 2015-2020 vintages",
         "source": "Illustrative analyst composite", "year": "2026",
         "source_ids": ["S1"],
         "caveat": "Survivorship: companies that never raised again are "
                   "under-represented in most datasets."},
        {"statement": "Seed-stage companies reaching a $100M+ outcome",
         "value": "~4%", "population": "US seed, B2B software",
         "source": "Illustrative analyst composite", "year": "2026",
         "source_ids": ["S1"],
         "caveat": "Concentrated in a small number of vintages and categories."},
        {"statement": "An uncited figure that must be dropped", "value": "90%",
         "population": "everyone", "source": "common knowledge", "source_ids": []},
    ],
    "not_found": ["Typical seed-to-exit dilution for this specific category"],
}


#: What an analyst handed only the CATEGORY finds — deliberately overlapping but
#: not identical to `_MARKET`, because the point of the cold pass is the things
#: nobody thought to ask about. ServiceNow, the systems integrators and internal
#: IT are all real competitors for this budget that a startup deck would never
#: list, and none of them appear in the claim-directed view.
_COLD_MARKET = {
    "market_definition": {
        "category": "Workflow automation for mid-market operations",
        "boundary_notes": "In practice this budget is contested by software, by "
                           "systems integrators and by simply hiring people.",
        "how_analysts_segment_it": ["iPaaS", "RPA", "workflow/BPM", "services"]},
    "sizing": {
        "tam_estimates": [
            {"value": "$16-21B", "year": "2026", "source": "Cold composite",
             "methodology": "bottom-up from seat and services spend", "url": None,
             "source_ids": ["S1"]}],
        "consensus_view": "Software-only view understates how much of this budget "
                           "goes to services rather than licences.",
        "cagr_range": "12-18%", "sizing_confidence": "medium",
        "why_estimates_diverge": "Whether integrator fees count as market spend."},
    "demand_signals": {
        "tailwinds": ["Agent budgets moving from pilot to line item"],
        "headwinds": [
            "Most failed deployments fail on process definition, not on tooling — "
            "a software purchase does not fix an undefined process",
            "Mid-market ops teams frequently lack anyone to own an automation "
            "programme after go-live"],
        "buyer_budget_reality": "Substitution from headcount and integrator spend, "
                                 "not new budget.",
        "adoption_stage": "early-majority"},
    "competitive_landscape": {
        "incumbents": [
            {"name": "Microsoft Power Automate", "position": "Bundled with E5",
             "funding_or_scale": "Public", "threat_level": "high", "url": None,
             "source_ids": ["S1"]},
            {"name": "ServiceNow", "position": "Owns the workflow layer in any "
                                                "company that already runs ITSM",
             "funding_or_scale": "Public", "threat_level": "high", "url": None,
             "source_ids": ["S2"]},
            {"name": "Systems integrators and BPO firms",
             "position": "Deliver the same outcome as a service, and already hold "
                          "the relationship",
             "funding_or_scale": "Fragmented but large", "threat_level": "medium",
             "url": None, "source_ids": []}],
        "challengers": [
            {"name": "n8n", "position": "Open-source, developer-led",
             "funding_or_scale": "Series B", "threat_level": "medium", "url": None,
             "source_ids": []},
            {"name": "Internal platform teams",
             "position": "Build it in-house on existing cloud primitives",
             "funding_or_scale": "n/a", "threat_level": "medium", "url": None,
             "source_ids": []}],
        "adjacent_threats": ["ERP vendors extending workflow into ops"],
        "concentration": "consolidating",
        "differentiation_axes": ["Process expertise", "Reliability", "Compliance"],
        "saturation": {
            "funded_competitors_known": 19,
            "new_entrants_trend": "slowing",
            "pricing_direction": "compressing",
            "consolidation_activity": "Several tuck-in acquisitions by ITSM vendors.",
            "lifecycle_stage": "maturing",
            "room_for_a_new_entrant": "a defensible niche remains",
            "why": "Entrant flow has slowed and the services share of spend is "
                   "growing, which usually marks a maturing category."}},
    "economics": {"typical_pricing": "$1-4k/mo plus implementation",
                   "typical_gross_margin": "60-75% once services are included",
                   "typical_cac_payback": "16-24 months", "capital_intensity": "medium"},
    "funding_environment": {"recent_rounds": [], "valuation_norms": "Compressed "
                             "relative to 2021", "exit_comps": [],
                             "investor_appetite": "cooling",
                             "notes": "Buyers of these companies are increasingly "
                                       "ITSM and ERP vendors rather than iPaaS."},
    "regulatory_and_structural": {"factors": ["Audit requirements in regulated ops"],
                                   "risk_level": "medium"},
    "absorption_risk": {
        "verdict": "contested", "horizon": "3-5 years", "confidence": "medium",
        "likely_absorbers": [
            {"name": "Microsoft", "why_them": "Already owns the licence",
             "mechanism": "bundle into an existing suite",
             "signals_already_visible": ["Agent features shipped in Power Automate"],
             "source_ids": []},
            {"name": "ServiceNow", "why_them": "Already owns the workflow layer and "
                                                "the ops relationship",
             "mechanism": "acquisition",
             "signals_already_visible": ["Tuck-in acquisitions in this category"],
             "source_ids": ["S2"]}],
        "precedents": [], "what_would_prevent_it": ["Depth outside the ITSM estate"],
        "notes": ""},
    "open_source_landscape": {"applicable": True, "projects": [], "closest_project": "n8n",
                               "capability_gap": "approaching parity",
                               "gap_trend": "narrowing",
                               "what_commercial_still_provides": [], "notes": ""},
    "adjacent_markets": [
        {"market": "IT service management", "relationship": "converging with this one",
         "size_note": None, "why_it_matters": "ServiceNow already sells workflow to "
                                               "this buyer.", "source_ids": ["S2"]},
        {"market": "Business process outsourcing", "relationship": "substitute",
         "size_note": None, "why_it_matters": "The default alternative is to pay "
                                               "people to do it.", "source_ids": []}],
    "sources": [], "research_gaps": ["No public data on failure rates by category"],
    "injection_findings": [],
}


# ---------------------------------------------------------------- deck-aware
#
# The mock returns canned analysis, which is the point — it is a stand-in, not an
# analyst. But a stand-in that ignores its input entirely cannot exercise the
# evaluation harness, because every scored expectation is about THIS deck.
#
# So the mock reads back what it was given: it pulls the quantitative claims out
# of the deck text and echoes any evidence it was handed. The assessments it
# produces are mechanical, not intelligent. A score obtained with the mock
# provider measures whether the harness works, and says nothing at all about
# analysis quality.

_CLAIM_RX = re.compile(
    r"[^.\n]*?(?:\$\s?\d[\d,.]*\s*(?:[kKmMbB]|billion|million|thousand)?"
    r"|\d+(?:\.\d+)?\s*%)[^.\n]*", re.I)


def _deck_lines(prompt: str) -> str:
    """The deck body, as handed to the deck agent inside its fence."""
    start = prompt.find("BEGIN PITCH DECK CONTENT")
    if start == -1:
        start = prompt.find("--- Slide 1 ---")
    end = prompt.find("<<<END", start if start != -1 else 0)
    return prompt[max(0, start): end if end != -1 else len(prompt)]


def _extract_claims(prompt: str, limit: int = 6) -> list:
    """Quantitative sentences from the deck, in order of appearance."""
    body = _deck_lines(prompt)
    seen, claims = set(), []
    for match in _CLAIM_RX.finditer(body):
        text = " ".join(match.group(0).split())
        text = re.sub(r"^-+\s*Slide \d+\s*-+\s*", "", text).strip(" -")
        if len(text) < 12 or text.lower() in seen:
            continue
        seen.add(text.lower())
        claims.append(text[:160])
        if len(claims) >= limit:
            break
    return claims


def _research_block(prompt: str) -> str:
    """The evidence supplied to this call, wherever it appears in the prompt."""
    for marker in ("RESEARCH MATERIAL", "MARKET ANALYSIS (what the evidence shows)",
                   "SHARED BIBLIOGRAPHY"):
        idx = prompt.find(marker)
        if idx != -1:
            return prompt[idx:]
    return ""


def _market_analysis(prompt: str) -> dict:
    """A market picture that echoes the evidence actually supplied.

    The canned view was fixed regardless of input, which meant the corpus never
    reached the comparison stage and every claim scored the same way no matter
    what the sources said. Echoing the supplied figures back is what lets the
    evaluation harness exercise the whole path.
    """
    import copy

    out = copy.deepcopy(_MARKET)
    evidence = _research_block(prompt)
    if not evidence.strip():
        out["sizing"]["consensus_view"] = ("No external evidence was supplied for "
                                           "this run.")
        out["sizing"]["sizing_confidence"] = "low"
        out["sizing"]["tam_estimates"] = []
        out["competitive_landscape"]["incumbents"] = []
        out["competitive_landscape"]["challengers"] = []
        return out

    # Ranges like "$6-8B" or "$900M-1.3B" are what an analyst would quote.
    ranges = re.findall(r"\$\s?\d[\d,.]*\s*[-–]\s*\d[\d,.]*\s*"
                        r"(?:[kKmMbB]|billion|million)?", evidence)
    singles = re.findall(r"\$\s?\d[\d,.]*\s*(?:[kKmMbB]|billion|million)",
                         evidence)
    figures = ranges or singles
    if figures:
        out["sizing"]["tam_estimates"] = [
            {"value": f.strip(), "year": "2026", "source": "Supplied research",
             "methodology": "as stated in the source", "url": None,
             "source_ids": ["S1"]}
            for f in figures[:3]]
        out["sizing"]["consensus_view"] = (
            f"The supplied research puts this at {figures[0].strip()}"
            + (f", with a narrower slice at {figures[1].strip()}"
               if len(figures) > 1 else "") + " [S1].")
    growth = re.findall(r"\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?\s*%", evidence)
    if growth:
        out["sizing"]["cagr_range"] = growth[0]

    # Capitalised multi-word names in the evidence are the competitors an analyst
    # would pick out. Crude, but it is what makes blind-spot scoring meaningful.
    stop = {"The", "This", "That", "Independent", "Growth", "Those", "Both",
            "Adoption", "Finance", "Net", "Per", "Open", "Customer", "Small",
            "Standalone", "Their", "There", "Zendesk's", "Its"}
    # Skip the fence notice, which is deliberately shouty and would otherwise be
    # read as a list of companies called RESEARCH, MATERIAL and DATA.
    # Begin at the first numbered source. Everything before it is the trust
    # notice and the citation instructions, which are shouty and full of
    # capitalised words that would otherwise be read as company names.
    body = evidence
    first_source = re.search(r"\[S\d+\]", body)
    if first_source:
        body = body[first_source.start():]
    names, seen = [], set()
    for match in re.finditer(r"\b([A-Z][a-z][A-Za-z0-9.]*(?:\.com)?)\b", body):
        name = match.group(1)
        if name in stop or len(name) < 3 or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)
    out["competitive_landscape"]["incumbents"] = [
        {"name": n, "position": "Named in the supplied research",
         "funding_or_scale": None, "threat_level": "medium", "url": None,
         "source_ids": ["S1"]}
        for n in names[:6]]
    out["competitive_landscape"]["challengers"] = []
    return out


def _deck_extraction(prompt: str) -> dict:
    """A DECK_SCHEMA-shaped extraction of whichever deck was actually supplied.

    Built by copying the canned structure and replacing the parts that depend on
    the deck: the company name, the market figures and the claim list. Everything
    else stays generic, because the mock is a fixture and not an analyst.
    """
    import copy

    out = copy.deepcopy(_DECK)
    body = _deck_lines(prompt)

    first = next((ln.strip() for ln in body.splitlines()
                  if ln.strip() and not ln.strip().startswith("-")
                  and "PITCH DECK" not in ln), "")
    if first:
        out["company"]["name"] = first[:60]

    money = re.findall(r"\$\s?\d[\d,.]*\s*(?:[kKmMbB]|billion|million)?", body)
    out["market"]["tam_claimed"] = money[0].strip() if money else None
    growth = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:CAGR|a year|annually|growth)",
                       body, re.I)
    out["market"]["growth_rate_claimed"] = growth.group(0) if growth else None

    sentences = _extract_claims(prompt)
    out["claims"] = [
        {"id": f"C{i}", "claim": text, "type": "market-size" if "$" in text
         else "traction", "slide": None, "verifiability": "verifiable",
         "load_bearing": "high" if i <= 2 else "medium"}
        for i, text in enumerate(sentences, 1)]
    return out


def _claims_from_extraction(prompt: str) -> list:
    """The claim list the deck agent produced, recovered from the prompt JSON."""
    marker = '"claims"'
    idx = prompt.find(marker)
    if idx == -1:
        return []
    start = prompt.find("[", idx)
    if start == -1:
        return []
    depth, end = 0, None
    for i in range(start, min(len(prompt), start + 40_000)):
        if prompt[i] == "[":
            depth += 1
        elif prompt[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return []
    try:
        rows = json.loads(prompt[start:end])
    except Exception:  # noqa: BLE001
        return []
    return [str(r.get("claim")) for r in rows
            if isinstance(r, dict) and r.get("claim")]


def _figure_supported(claim: str, evidence: str) -> bool:
    """Does a figure in the claim fall inside a range the evidence states?

    A literal substring test would call "$2.8B" contradicted when the evidence
    says "$2.6-3.0B", which is the opposite of the truth and would make the
    control case unscoreable. Ranges are what analyst sources actually quote, so
    the rule has to read them.
    """
    def scale(unit: str) -> float:
        unit = (unit or "").lower()
        return {"k": 1e3, "m": 1e6, "million": 1e6,
                "b": 1e9, "bn": 1e9, "billion": 1e9}.get(unit, 1.0)

    claim_values = [float(n.replace(",", "")) * scale(u)
                    for n, u in re.findall(
                        r"\$?\s?(\d[\d,]*(?:\.\d+)?)\s*"
                        r"(k|m|b|bn|million|billion)?", claim, re.I)
                    if n.replace(",", "").replace(".", "").isdigit()]
    if not claim_values:
        return False

    for lo, hi, unit in re.findall(
            r"\$?\s?(\d[\d,]*(?:\.\d+)?)\s*[-–]\s*(\d[\d,]*(?:\.\d+)?)\s*"
            r"(k|m|b|bn|million|billion)?", evidence, re.I):
        try:
            low = float(lo.replace(",", "")) * scale(unit)
            high = float(hi.replace(",", "")) * scale(unit)
        except ValueError:
            continue
        for value in claim_values:
            if low <= value <= high:
                return True
    # Percentages are quoted bare, so check those against ranges too.
    for value in claim_values:
        for lo, hi in re.findall(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*%",
                                 evidence):
            if float(lo) <= value <= float(hi):
                return True
    return False


def _claim_audit_for(prompt: str) -> list:
    """A claim audit over the claims the deck agent actually extracted.

    The assessment rule is deliberately crude: a claim whose figures also appear
    in the supplied evidence is called supported, one that conflicts is called
    contradicted, and anything hedged is called unverifiable. It is a fixture,
    not a judgement.
    """
    claims = _claims_from_extraction(prompt) or _extract_claims(prompt)
    if not claims:
        return []
    evidence = _research_block(prompt).lower()
    audit = []
    for i, text in enumerate(claims, 1):
        numbers = re.findall(r"\d[\d,.]*", text)
        echoed = any(n in evidence for n in numbers if len(n) > 1)
        hedged = any(w in text.lower() for w in
                     ("believe", "we think", "large and underserved", "only"))
        if hedged:
            assessment, quality = "unverifiable", "none"
        elif echoed:
            assessment, quality = "supported", "moderate"
        elif evidence:
            assessment, quality = "contradicted", "moderate"
        else:
            assessment, quality = "unverifiable", "none"
        audit.append({
            "id": f"C{i}", "claim": text,
            "market_evidence": ("The supplied research addresses this figure."
                                if echoed else
                                "The supplied research does not support this figure."
                                if evidence else
                                "No external evidence was supplied for this run."),
            "assessment": assessment,
            "delta": "" if assessment == "supported" else
                     "The evidence points elsewhere.",
            "so_what": "Check this against the cited source before relying on it.",
            "source_ids": ["S1"] if evidence else [],
            "evidence_quality": quality,
            "sources": [],
        })
    return audit
