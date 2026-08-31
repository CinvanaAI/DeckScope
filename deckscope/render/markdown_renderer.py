"""Markdown report — the canonical text other renderers build from."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

from .common import (ASSESSMENT_WORD, SEVERITY_WORD, alignment_text, as_list,
                     findings_for, header_block, safe_url, summary_caveat, txt)


def build_markdown(result, lens: str) -> str:
    comp = result.comparisons.get(lens, {})
    deck, market = result.deck, result.market
    h = header_block(result, lens)
    L: List[str] = []
    add = L.append

    found = findings_for(result, lens)

    add(f"# {h['company']} — Deck vs. Market Analysis")
    add("")
    add(f"**{h['lens']}**")
    add("")

    # ------------------------------------------------------- the findings
    # This report used to open with a verdict and a weighted score. It now opens
    # with what the reader is actually trying to learn: which claims did not
    # survive contact with evidence, what the deck left out, and what to go and
    # ask. The verdict still exists, further down, framed as one reading rather
    # than the answer. See deckscope/findings.py for why.
    add(f"> **{found.headline}**")
    add("")
    add(f"*{found.evidence_state}*")
    add("")
    if comp.get("integrity_note"):
        add(f"> **Integrity note.** {comp['integrity_note']}")
        add("")

    if found.contested:
        add("## What the evidence contests")
        add("")
        add("Claims the deck makes that retrieved evidence pushes back on. "
            "Sourced items link to the bibliography; unsourced ones are readings, "
            "not findings.")
        add("")
        for f in found.contested:
            cites = (" ".join(f"[{s}]" for s in f.source_ids)
                     if f.source_ids else "_no source_")
            add(f"- **{txt(f.text)}** — {SEVERITY_WORD.get(f.severity, f.severity)}. "
                f"{txt(f.delta or f.why)} {cites}")
        add("")

    # ------------------------------- the deck against its own numbers
    # Deterministic arithmetic, not model judgment — the strongest findings
    # in the report because the founder cannot argue with either number:
    # both are theirs. Rendered even when everything reconciles, since
    # "checked, consistent" and "could not check" are different facts.
    consistency = (deck or {}).get("_consistency") or {}
    conflicts = [r for r in (consistency.get("results") or [])
                 if r.get("state") == "conflict"]
    if consistency.get("ran"):
        add("## Where the deck disagrees with itself")
        add("")
        add("Arithmetic over the deck's own numbers — no outside source "
            "involved, so no outside source can be wrong.")
        add("")
        if conflicts:
            for r in conflicts:
                add(f"- **{txt(r.get('detail'))}.** {txt(r.get('arithmetic'))}")
                for ref in (r.get("refs") or []):
                    add(f"  - {ref}")
        else:
            ran = consistency.get("ran", 0)
            add(f"- The {ran} check(s) the deck's numbers allowed all "
                f"reconcile.")
        skipped = [r for r in (consistency.get("results") or [])
                   if r.get("state") == "not-runnable"]
        if skipped:
            add("")
            add("Not checkable from what the deck states: "
                + "; ".join(f"{r.get('check')} ({r.get('detail')})"
                            for r in skipped) + ".")
        add("")

    if found.omissions:
        add("## What the deck leaves out")
        add("")
        add("Present in the market evidence, absent from the deck.")
        add("")
        for f in found.omissions:
            cites = (" ".join(f"[{s}]" for s in f.source_ids) if f.source_ids
                     else "_no source — the analysis asserts this without evidence_")
            add(f"- **{txt(f.text)}** {cites}")
        add("")

    if found.unverified:
        add("## What could not be checked")
        add("")
        add("Neither confirmed nor refuted by the evidence retrieved. These are "
            "research tasks, **not** marks against the company — an analysis must "
            "not convert its own gaps into a negative signal.")
        add("")
        for f in found.unverified:
            add(f"- {txt(f.text)}")
        add("")

    if found.next_steps:
        add("## What to do next")
        add("")
        for i, step in enumerate(found.next_steps, 1):
            add(f"{i}. {txt(step)}")
        add("")

    # ---------------------------------------------------------- summary
    add("## Summary")
    add("")
    caveat = summary_caveat(comp.get("summary") or "", deck, comp)
    if caveat:
        add(f"> _{caveat}_")
        add("")
    add(comp.get("summary") or "_No summary produced._")
    add("")

    # ------------------------------------------- the advisor's read
    # Opinion beside the evidence, never wearing its badge: everything above
    # is audited; this is one analyst's committed point of view, printed
    # under a frame that says exactly that. The frame is the renderer's —
    # deterministic — so no model output can soften it.
    if (comp.get("advisor_read") or "").strip():
        add("## The advisor's read — judgment, not evidence")
        add("")
        frame = ("Everything above this line is audited against the run's "
                 "evidence. This section is one analyst's opinion, written "
                 "after reading it — allowed to reason beyond the record, "
                 "required to say when it does.")
        if found.evidence_too_thin:
            frame += (" This run retrieved no cited evidence, so the read "
                      "rests on the deck and the model's priors alone.")
        add(f"> _{frame}_")
        add("")
        add(comp["advisor_read"].strip())
        add("")

    # ------------------------------------------------- verdict, demoted
    add("## What this adds up to, for this lens")
    add("")
    if h.get("verdict_note"):
        add(f"**{h['verdict']}**")
        add("")
        add(f"*{h['verdict_note']}*")
        add("")
    else:
        add(f"**{h['verdict']}** · confidence: {h['confidence']}")
        add("")
        rationale = (comp.get("verdict") or {}).get("confidence_rationale")
        if rationale:
            add(f"*Confidence basis: {rationale}*")
            add("")
        add("A verdict is one reader's reading of the findings above, through "
            "one lens. The findings are the durable part; this line is not.")
        add("")

    # -------------------------------------------------------- scorecard
    rows = comp.get("scorecard") or []
    if rows:
        add("## Scorecard")
        add("")
        add("Per-dimension, each with the reasoning behind it. There is "
            "deliberately no headline total: a weighted average of seven "
            "subjective scores is the one figure in this report that cannot be "
            "traced to a source.")
        add("")
        add("| Dimension | Score | Weight | Why |")
        add("|---|:--:|:--:|---|")
        for r in rows:
            add(f"| {txt(r.get('dimension'))} | **{txt(r.get('score'))}**/10 | "
                f"{txt(r.get('weight'))} | {txt(r.get('rationale'))} |")
        add("")

    # ------------------------------------------------------ claim audit
    audit = comp.get("claim_audit") or []
    if audit:
        add("## Claim-by-claim audit")
        add("")
        add("Each claim the deck makes, set against what the market evidence shows.")
        add("")
        for c in audit:
            verdict = ASSESSMENT_WORD.get(c.get("assessment", ""), txt(c.get("assessment")))
            add(f"### {txt(c.get('id'))} · {txt(c.get('claim'))}")
            add("")
            add(f"**Assessment:** {verdict}")
            add("")
            if c.get("validation_note"):
                add(f"*({c['validation_note']})*")
                add("")
            add(f"**Market evidence:** {txt(c.get('market_evidence'))}")
            add("")
            if c.get("delta"):
                add(f"**Gap:** {c['delta']}")
                add("")
            if c.get("materiality"):
                because = txt(c.get("materiality_because"), dash="")
                add(f"**If corrected:** {c['materiality']}"
                    + (f" — {because}" if because else ""))
                add("")
            if c.get("so_what"):
                add(f"**So what:** {c['so_what']}")
                add("")
            if c.get("evidence_quality"):
                add(f"**Evidence quality:** {c['evidence_quality']}")
                add("")
            cites = _cite_links(c.get("source_ids"), c.get("sources"), result)
            add(f"**Sources:** {cites}")
            add("")
            # The structural join: reports the scoper dispatched FOR this
            # claim, attached by code. Their sources render here as the
            # report's evidence, distinct from the row's own citations.
            for rep in (c.get("checked_by_reports") or []):
                ids = " ".join(f"[{s}]" for s in (rep.get("source_ids") or []))
                add(f"**Independently checked by the {rep.get('specialist')} "
                    f"report"
                    + (f" ({rep['measure']})" if rep.get("measure") else "")
                    + f":** {rep.get('finding')} {ids}".rstrip()
                    + (f" — stored as `{rep['stored_as']}`"
                       if rep.get("stored_as") else ""))
                add("")

    # --------------------------------------------------------- alignment
    align = comp.get("alignment") or {}
    if any(align.values()):
        add("## Where the deck and the market agree — and don't")
        add("")
        for key, title in [
            ("where_deck_matches_market", "Deck matches the market"),
            ("where_deck_overstates", "Deck overstates"),
            ("where_deck_understates", "Deck understates"),
            ("blind_spots", "Blind spots the deck never addresses"),
        ]:
            items = as_list(align.get(key))
            if items:
                add(f"### {title}")
                add("")
                for i in items:
                    add(f"- {alignment_text(i)}")
                add("")

    # ------------------------------------------------------------ risks
    risks = comp.get("risks") or []
    if risks:
        add("## Risks")
        add("")
        add("| Risk | Severity | Likelihood | Test or mitigation |")
        add("|---|:--:|:--:|---|")
        for r in risks:
            add(f"| {txt(r.get('risk'))} | {txt(r.get('severity'))} | "
                f"{txt(r.get('likelihood'))} | {txt(r.get('mitigation_or_test'))} |")
        add("")

    # Questions and actions are not repeated here: both were consolidated into
    # "What to do next" at the top, and printing them twice was how the reader
    # ended up assembling the report themselves. The owner/priority detail that
    # only the actions table carried is kept below.
    acts = comp.get("actions") or []
    if acts:
        add("## Who does what")
        add("")
        add("| Priority | Action | Owner |")
        add("|:--:|---|---|")
        for a in sorted(acts, key=lambda x: str(x.get("priority", "P9"))):
            add(f"| {txt(a.get('priority'))} | {txt(a.get('action'))} | {txt(a.get('owner'))} |")
        add("")

    # ----------------------------------------------------- market annex
    add("---")
    add("")
    add("## Annex A — What the market evidence shows")
    add("")
    sizing = market.get("sizing") or {}
    add(f"**Category:** {txt((market.get('market_definition') or {}).get('category'))}")
    add("")
    add(f"**Consensus sizing view:** {txt(sizing.get('consensus_view'))}  ")
    add(f"**CAGR range:** {txt(sizing.get('cagr_range'))}  ")
    add(f"**Confidence in sizing:** {txt(sizing.get('sizing_confidence'))}")
    add("")
    ests = sizing.get("tam_estimates") or []
    if ests:
        add("| Estimate | Year | Methodology | Source |")
        add("|---|:--:|---|---|")
        for e in ests:
            src = txt(e.get("source"))
            if e.get("url"):
                src = f"[{src}]({safe_url(e['url'])})" if safe_url(e["url"]) else src
            add(f"| {txt(e.get('value'))} | {txt(e.get('year'))} | "
                f"{txt(e.get('methodology'))} | {src} |")
        add("")
    if sizing.get("why_estimates_diverge"):
        add(f"*Why estimates diverge: {sizing['why_estimates_diverge']}*")
        add("")

    land = market.get("competitive_landscape") or {}
    if land:
        add("### Competitive landscape")
        add("")
        add(f"Market structure: **{txt(land.get('concentration'))}**. "
            f"Companies compete on: {txt(land.get('differentiation_axes'))}.")
        add("")
        for group, title in (("incumbents", "Incumbents"), ("challengers", "Challengers")):
            rows2 = land.get(group) or []
            if rows2:
                add(f"**{title}**")
                add("")
                add("| Company | Position | Scale | Threat |")
                add("|---|---|---|:--:|")
                for c in rows2:
                    nm = txt(c.get("name"))
                    if c.get("url"):
                        nm = f"[{nm}]({safe_url(c['url'])})" if safe_url(c["url"]) else nm
                    add(f"| {nm} | {txt(c.get('position'))} | "
                        f"{txt(c.get('funding_or_scale'))} | {txt(c.get('threat_level'))} |")
                add("")
        adj = as_list(land.get("adjacent_threats"))
        if adj:
            add("**Adjacent threats:** " + "; ".join(str(a) for a in adj))
            add("")

    dem = market.get("demand_signals") or {}
    if dem:
        add("### Demand signals")
        add("")
        for k, t in (("tailwinds", "Tailwinds"), ("headwinds", "Headwinds")):
            items = as_list(dem.get(k))
            if items:
                add(f"**{t}:**")
                for i in items:
                    add(f"- {alignment_text(i)}")
                add("")
        if dem.get("buyer_budget_reality"):
            add(f"**Buyer budget reality:** {dem['buyer_budget_reality']}")
            add("")
        if dem.get("adoption_stage"):
            add(f"**Adoption stage:** {dem['adoption_stage']}")
            add("")

    fund = market.get("funding_environment") or {}
    if fund.get("recent_rounds") or fund.get("valuation_norms"):
        add("### Funding environment")
        add("")
        add(f"Investor appetite: **{txt(fund.get('investor_appetite'))}**. "
            f"Valuation norms: {txt(fund.get('valuation_norms'))}")
        add("")
        rounds = fund.get("recent_rounds") or []
        if rounds:
            add("| Company | Round | Amount | Date |")
            add("|---|---|---|---|")
            for r in rounds:
                add(f"| {txt(r.get('company'))} | {txt(r.get('round'))} | "
                    f"{txt(r.get('amount'))} | {txt(r.get('date'))} |")
            add("")

    gaps = as_list(market.get("research_gaps"))
    if gaps:
        add("### What could not be verified")
        add("")
        for g in gaps:
            add(f"- {g}")
        add("")

    # ------------------------------------------------------- deck annex
    add("---")
    add("")
    add("## Annex B — What the deck claims")
    add("")
    co, mk, tr, ask = (deck.get("company") or {}, deck.get("market") or {},
                       deck.get("traction") or {}, deck.get("ask") or {})
    add(f"**{txt(co.get('name'))}** — {txt(co.get('one_liner'))}  ")
    add(f"Stage: {txt(co.get('stage'))} · Founded: {txt(co.get('founded'))} · "
        f"Location: {txt(co.get('location'))}")
    add("")
    add("| Field | Deck says |")
    add("|---|---|")
    add(f"| Problem | {txt((deck.get('problem') or {}).get('statement'))} |")
    add(f"| Solution | {txt((deck.get('solution') or {}).get('description'))} |")
    add(f"| TAM claimed | {txt(mk.get('tam_claimed'))} ({txt(mk.get('tam_methodology'))}) |")
    add(f"| SAM / SOM | {txt(mk.get('sam_claimed'))} / {txt(mk.get('som_claimed'))} |")
    add(f"| Growth claimed | {txt(mk.get('growth_rate_claimed'))} |")
    add(f"| Revenue | {txt(tr.get('revenue'))} |")
    add(f"| Growth | {txt(tr.get('growth'))} |")
    add(f"| Customers | {txt(tr.get('customers'))} |")
    add(f"| Retention | {txt(tr.get('retention'))} |")
    add(f"| Competitors named | {txt((deck.get('competition') or {}).get('named_competitors'))} |")
    add(f"| Ask | {txt(ask.get('amount'))} at {txt(ask.get('valuation'))} |")
    add("")

    dq = deck.get("deck_quality") or {}
    if any(dq.values()):
        add("### Deck quality notes")
        add("")
        if dq.get("narrative_coherence"):
            add(f"Narrative coherence: **{dq['narrative_coherence']}/10**")
            add("")
        for k, t in (("missing_sections", "Missing sections"),
                     ("unsupported_numbers", "Numbers presented without support"),
                     ("vague_language", "Vague language")):
            items = as_list(dq.get(k))
            if items:
                add(f"**{t}:** " + "; ".join(str(i) for i in items))
                add("")
        if dq.get("notes"):
            add(dq["notes"])
            add("")

    # ------------------------------------- what the deck steered us away from
    add(_discovery_markdown(result))

    # ------------------------------------------------- market structure
    add(_saturation_markdown(market))
    add(_absorption_markdown(market))
    add(_open_source_markdown(market))

    # ------------------------------------------------- opportunity cost
    add(_opportunity_markdown(result))

    # -------------------------------------------------------- references
    add("---")
    add("")
    add(_references_markdown(result))

    # ---------------------------------------------------------- security
    add(_security_markdown(result))

    add("---")
    add("")
    add(f"*Generated by DeckScope · "
        f"{h['model']} · {h['research']}. AI-generated analysis: verify every figure "
        f"before relying on it. Not investment advice.*")
    return "\n".join(L)


def _discovery_markdown(result) -> str:
    """What a cold reading of the market found that the directed pass missed."""
    delta = getattr(result, "discovery_delta", None) or {}
    if not delta or not delta.get("ran"):
        return ""

    L = ["## What the deck steered the research away from", ""]
    L.append("The market analysis above was given the deck's claims — it has to be, it "
             "is checking them — so its searches were shaped by what the deck raises. "
             "That finds errors well and finds omissions badly: nobody searches for "
             "what they were not prompted to consider.")
    L.append("")
    L.append("So the category was **also researched cold**, by a pass that received "
             "only the category name and the company name and never saw a single "
             "claim. Everything below appeared on that route and not on the other one.")
    L.append("")

    if not delta.get("anything_found"):
        L += ["Nothing. Researching the category from scratch surfaced no competitor, "
              "headwind or absorber that the claim-directed pass had missed.", "",
              "That is a meaningful result rather than an empty section: it suggests "
              "the deck's framing did not steer the research away from anything "
              "material.", ""]
        return "\n".join(L)

    L += [f"*Overlap between the two routes: "
          f"{float(delta.get('agreement') or 0):.0%} of the competitors named.*", ""]

    only_cold = delta.get("competitors_only_cold") or []
    if only_cold:
        L += ["### Competitors found only when the deck was out of the room", "",
              "| Competitor | Position | Threat |", "|---|---|:--:|"]
        for c in only_cold:
            L.append(f"| **{txt(c.get('name'))}** | {txt(c.get('position'))} | "
                     f"{txt(c.get('threat_level'))} |")
        L.append("")

    absorbers = delta.get("absorbers_only_cold") or []
    if absorbers:
        L += [f"**Potential absorbers the directed pass did not raise:** "
              f"{', '.join(str(a) for a in absorbers)}", ""]

    headwinds = delta.get("headwinds_only_cold") or []
    if headwinds:
        L += ["**Headwinds surfaced only by the cold pass**", ""]
        L += [f"- {h}" for h in headwinds]
        L.append("")

    adjacent = delta.get("adjacent_only_cold") or []
    if adjacent:
        L += [f"**Adjacent markets missed:** {', '.join(str(a) for a in adjacent)}", ""]

    sizing = delta.get("sizing") or {}
    if sizing.get("cold_consensus") and \
            sizing.get("cold_consensus") != sizing.get("directed_consensus"):
        L += ["**The two routes sized it differently**", "",
              f"- Claim-directed: {txt(sizing.get('directed_consensus'))} "
              f"*(confidence: {txt(sizing.get('directed_confidence'))})*",
              f"- Cold: {txt(sizing.get('cold_consensus'))} "
              f"*(confidence: {txt(sizing.get('cold_confidence'))})*", ""]

    concentration = delta.get("concentration") or {}
    if concentration and not concentration.get("agree"):
        L += [f"**Market structure read differently:** directed says "
              f"*{txt(concentration.get('directed'))}*, cold says "
              f"*{txt(concentration.get('cold'))}*.", ""]

    L += ["> These are not necessarily errors in the analysis above — the cold pass "
          "may be wrong, and it has no way to know which of these matters to this "
          "company. What it does establish is that the deck's framing narrowed the "
          "search, and by how much.", ""]
    return "\n".join(L)


def _saturation_markdown(market: Any) -> str:
    """How crowded, and moving which way."""
    land = market.get("competitive_landscape") or {}
    sat = land.get("saturation") or {}
    if not any(sat.values()):
        return ""
    L = ["### Saturation", ""]
    L.append("| | |")
    L.append("|---|---|")
    for label, key in (("Funded competitors found", "funded_competitors_known"),
                       ("New entrants", "new_entrants_trend"),
                       ("Pricing", "pricing_direction"),
                       ("Consolidation", "consolidation_activity"),
                       ("Lifecycle stage", "lifecycle_stage"),
                       ("Room for a new entrant", "room_for_a_new_entrant")):
        L.append(f"| **{label}** | {txt(sat.get(key))} |")
    L.append("")
    if sat.get("why"):
        L += [sat["why"], ""]
    return "\n".join(L)


def _open_source_markdown(market: Any) -> str:
    """Open-source parity as the leading indicator of bundling."""
    oss = market.get("open_source_landscape") or {}
    assessment = market.get("bundling_assessment") or {}
    if not oss and not assessment:
        return ""
    if assessment.get("applicable") is False:
        return ""

    L = ["### Open source, and what it predicts", ""]
    level = str(assessment.get("level") or "unknown").upper()
    L.append(f"**Bundling risk from commoditization: {level}**")
    L.append("")
    if assessment.get("reasoning"):
        L += [assessment["reasoning"], ""]

    projects = oss.get("projects") or []
    if projects:
        L += ["| Project | Maturity | Governance | Adoption | Backed by |",
              "|---|---|---|---|---|"]
        for pr in projects:
            name = txt(pr.get("name"))
            url = safe_url(pr.get("url"))
            if url:
                name = f"[{name}]({url})"
            L.append(f"| {name} | {txt(pr.get('maturity'))} | "
                     f"{txt(pr.get('governance'))} | {txt(pr.get('adoption_signal'))} | "
                     f"{txt(pr.get('commercially_backed_by'))} |")
        L.append("")

    if oss.get("capability_gap"):
        L.append(f"**Capability gap:** {txt(oss.get('capability_gap'))} "
                 f"and {txt(oss.get('gap_trend'))}"
                 + (f" · closest: {oss['closest_project']}"
                    if oss.get("closest_project") else ""))
        L.append("")
    if oss.get("evidence_for_the_gap"):
        L += [f"*{oss['evidence_for_the_gap']}*", ""]

    provides = oss.get("what_commercial_still_provides") or []
    if provides:
        L += ["**What commercial products still provide once open source arrives**", "",
              "This is what decides the outcome. Capability parity only matters to the "
              "extent that what is left can be cheaply reproduced by a platform vendor "
              "that already owns the customer.", "",
              "| Capability | Kind | Hard to replicate? |", "|---|---|:--:|"]
        for item in provides:
            durable = str(item.get("durable")).lower() in ("true", "yes")
            L.append(f"| {txt(item.get('capability'))} | {txt(item.get('type'))} | "
                     f"{'yes' if durable else 'no'} |")
        L.append("")

    durable = assessment.get("durable") or []
    replicable = assessment.get("replicable") or []
    if durable:
        L += ["**Genuinely defensible:** " + "; ".join(str(x) for x in durable), ""]
    if replicable:
        L += ["**A platform could reproduce cheaply:** "
              + "; ".join(str(x) for x in replicable), ""]

    if oss.get("pricing_pressure"):
        L += [f"**Pricing pressure from the free alternative:** "
              f"{txt(oss.get('pricing_pressure'))}", ""]
    if oss.get("company_relationship_to_oss"):
        L += [f"**This company's relationship to open source:** "
              f"{txt(oss.get('company_relationship_to_oss'))}", ""]
    if oss.get("strip_mining_risk"):
        L += [f"**If it is built on open source:** {oss['strip_mining_risk']}", ""]

    for c in assessment.get("caveats") or []:
        L += [f"> {c}", ""]
    if oss.get("notes"):
        L += [txt(oss.get("notes")), ""]
    return "\n".join(L)


def _absorption_markdown(market: Any) -> str:
    """Whether this category survives as a standalone market."""
    ab = market.get("absorption_risk") or {}
    adj = market.get("adjacent_markets") or []
    if not any(ab.values()) and not adj:
        return ""
    L = ["### Is this a product or a feature?", ""]
    if ab.get("verdict"):
        L.append(f"**{txt(ab.get('verdict')).upper()}** · absorption horizon: "
                 f"{txt(ab.get('horizon'))} · confidence: {txt(ab.get('confidence'))}")
        L.append("")
        L.append("Categories are regularly built out by startups, proven useful, and "
                 "then bundled into a platform that already owns the customer. When "
                 "that happens the market stops existing separately, and the companies "
                 "in it were not out-competed so much as made redundant.")
        L.append("")

    absorbers = ab.get("likely_absorbers") or []
    if absorbers:
        L += ["**Who could absorb it**", ""]
        for a in absorbers:
            L.append(f"- **{txt(a.get('name'))}** — {txt(a.get('mechanism'))}  ")
            L.append(f"  {txt(a.get('why_them'))}")
            signals = as_list(a.get("signals_already_visible"))
            if signals:
                L.append(f"  *Already visible:* {'; '.join(str(x) for x in signals)}")
        L.append("")

    precedents = ab.get("precedents") or []
    if precedents:
        L += ["**Precedents**", "",
              "| Category | Absorbed by | How long | Why comparable |",
              "|---|---|---|---|"]
        for pr in precedents:
            L.append(f"| {txt(pr.get('category'))} | {txt(pr.get('absorbed_by'))} | "
                     f"{txt(pr.get('how_long_it_took'))} | "
                     f"{txt(pr.get('why_it_is_comparable'))} |")
        L.append("")

    prevent = as_list(ab.get("what_would_prevent_it"))
    if prevent:
        L += ["**What would keep this a standalone market**", ""]
        L += [f"- {x}" for x in prevent]
        L.append("")
    if ab.get("notes"):
        L += [txt(ab.get("notes")), ""]

    if adj:
        L += ["### Adjacent markets", "",
              "| Market | Relationship | Why it matters |", "|---|---|---|"]
        for m in adj:
            L.append(f"| {txt(m.get('market'))} | {txt(m.get('relationship'))} | "
                     f"{txt(m.get('why_it_matters'))} |")
        L.append("")
    return "\n".join(L)


def _opportunity_markdown(result) -> str:
    """What buying the listed alternative would require instead."""
    opp = getattr(result, "opportunity", None) or {}
    if not opp or opp.get("error"):
        return ""
    L = ["---", "", "## Compared to what?", ""]
    if opp.get("headline"):
        L += [f"> {opp['headline']}", ""]

    L.append("An investment is a choice against alternatives, and when a named "
             "competitor is publicly traded the alternative is concrete: you could "
             "simply buy it. What follows is **not a forecast**. It is the outcome "
             "this company would have to reach to match each benchmark, under stated "
             "assumptions you can change.")
    L.append("")

    comps = opp.get("comparables") or []
    if comps:
        L += ["### The named competitors, and whether you could buy them instead", "",
              "| Competitor | Listed | Market cap | Revenue | 5-year return | Source |",
              "|---|:--:|---|---|:--:|:--:|"]
        for c in comps:
            ret = (f"{c['total_return_5y']}x" if c.get("total_return_5y") else "—")
            listed = (f"**{c['ticker']}**" if c.get("ticker") else "private")
            src = ", ".join(c.get("source_ids") or []) or "—"
            L.append(f"| {txt(c.get('name'))} | {listed} | "
                     f"{txt(c.get('market_cap_display'))} | "
                     f"{txt(c.get('revenue_display'))} | {ret} | {src} |")
        L.append("")
        unsourced = [c for c in comps if c.get("ticker") and not c.get("source_ids")]
        if unsourced:
            L += [f"*{len(unsourced)} listing(s) could not be traced to a source and "
                  f"should be verified before use.*", ""]

    reqs = opp.get("requirements") or {}
    if reqs:
        L += ["### What this company would have to reach", "",
              "| To match | Exit value needed | Implied revenue | Multiple of today |",
              "|---|---|---|:--:|"]
        for label, r in reqs.items():
            L.append(f"| {label} | {txt(r.get('exit_value_required_display'))} | "
                     f"{txt(r.get('implied_arr_required_display'))} | "
                     f"{txt(r.get('growth_multiple_required'))}x |")
        L.append("")
        first = next(iter(reqs.values()), {})
        if first.get("entry_ownership") is not None:
            L.append(f"*Ownership: {first['entry_ownership']:.1%} at entry, "
                     f"{first['ownership_at_exit']:.1%} after assumed dilution.*")
            L.append("")
        note = next((r.get("note") for r in reqs.values() if r.get("note")), "")
        if note:
            L += [f"> {note}", ""]

    a = opp.get("assumptions") or {}
    if a:
        L += ["<details><summary>The assumptions every number above rests on</summary>",
              "",
              f"- Future dilution: **{a.get('future_dilution', 0):.0%}** before exit",
              f"- Exit revenue multiple: **{a.get('exit_revenue_multiple')}x**",
              f"- Horizon: **{a.get('horizon_years')} years**",
              f"- Liquidation preference ahead of this round: "
              f"**{a.get('preference_stack')}x**",
              "",
              "Change any of these and every figure changes. They are conventional "
              "defaults, not authoritative ones.", "", "</details>", ""]

    rates = opp.get("base_rates") or []
    if rates:
        L += ["### Base rates", "",
              "How companies in this position have historically done. Every rate "
              "below is sourced; rates that could not be traced were dropped.", "",
              "| Rate | Figure | Population | Source | Caveat |",
              "|---|---|---|---|---|"]
        for r in rates:
            src = ", ".join(r.get("source_ids") or []) or txt(r.get("source"))
            L.append(f"| {txt(r.get('statement'))} | {txt(r.get('value'))} | "
                     f"{txt(r.get('population'))} | {src} | {txt(r.get('caveat'))} |")
        L.append("")
    else:
        L += ["*No base rates could be sourced for this stage and category, so there "
              "is no denominator to read the requirement against.*", ""]

    for u in opp.get("unavailable") or []:
        L += [f"*{u}*", ""]

    L += [f"> {opp.get('disclaimer', '')}", ""]
    return "\n".join(L)


def _cite_links(source_ids: Any, urls: Any, result) -> str:
    """Render citations as resolvable IDs with their URLs."""
    reg = getattr(result, "registry", None)
    parts: List[str] = []
    seen = set()
    for sid in as_list(source_ids):
        src = reg.find(str(sid)) if reg else None
        if src and src.sid not in seen:
            seen.add(src.sid)
            parts.append(f"[{src.sid}]({safe_url(src.url)})" if safe_url(src.url) else src.sid)
    for u in as_list(urls):
        if not u:
            continue
        src = reg.find(str(u)) if reg else None
        if src and src.sid in seen:
            continue
        if src:
            seen.add(src.sid)
            parts.append(f"[{src.sid}]({safe_url(src.url)})" if safe_url(src.url) else src.sid)
        else:
            parts.append(f"<{u}>")
    return ", ".join(parts) if parts else "_none cited — this assessment rests on no source_"


def _references_markdown(result) -> str:
    """Every source consulted, cited or not. This is the audit trail."""
    reg = getattr(result, "registry", None)
    L: List[str] = ["## References", ""]
    if not reg or not reg.sources:
        backend = (result.stats or {}).get("research_backend", "none")
        L += [f"No external sources were retrieved for this analysis "
              f"(research backend: `{backend}`). Every statement above therefore rests "
              f"on the model's training knowledge and on the deck itself, and should be "
              f"treated as unverified.", ""]
        return "\n".join(L)

    st = reg.stats()
    L += [f"{st['total']} sources were retrieved and screened. "
          f"{st['cited']} are cited in the analysis above; "
          f"{st['consulted_uncited']} were consulted without being cited; "
          f"{st['quarantined']} were dropped by the security screen.",
          "",
          "Every source retrieved is listed here, including the ones that did not "
          "support a conclusion — so the absence of evidence is as visible as its "
          "presence.", ""]

    def rows(sources, title, note=""):
        if not sources:
            return
        L.append(f"### {title}")
        L.append("")
        if note:
            L.append(f"*{note}*")
            L.append("")
        # Retrieved-when matters because a URL is a pointer, not evidence:
        # live pages move on (the demo's recorded IDC snippet no longer
        # matches its landing page). The capture date plus the snippet hash
        # in the JSON export let a reader tell "the page changed since" from
        # "the report misquoted the page".
        L.append("| ID | Source | Published | Retrieved | Reliability | Supports |")
        L.append("|---|---|---|---|---|---|")
        for s in sources:
            link = (f"[{s.title or s.domain or s.url}]({safe_url(s.url)})"
                    if safe_url(s.url) else (s.title or s.url or "—"))
            supports = "; ".join(s.cited_by[:4]) or "—"
            retrieved = (getattr(s, "retrieved_at", "") or "—")[:10]
            L.append(f"| **{s.sid}** | {link} | {s.published or '—'} | "
                     f"{retrieved} | {s.reliability} | {supports} |")
        L.append("")

    rows(reg.cited, "Cited in this analysis")
    rows(reg.consulted, "Consulted, not cited",
         "Retrieved by the research queries but did not end up supporting any "
         "specific conclusion.")
    if reg.quarantined:
        L.append("### Dropped by the security screen")
        L.append("")
        L.append("| ID | Source | Reason |")
        L.append("|---|---|---|")
        for s in reg.quarantined:
            L.append(f"| **{s.sid}** | {s.url or s.title} | {s.note or 'flagged as hostile'} |")
        L.append("")

    queries = ((result.market.get("_meta") or {}).get("queries")) or []
    if queries:
        L += ["<details><summary>Search queries that produced these sources</summary>", ""]
        L += [f"- `{q}`" for q in queries]
        L += ["", "</details>", ""]
    return "\n".join(L)


def _security_markdown(result) -> str:
    """What the injection screen found in the deck and in the web sources."""
    sec = getattr(result, "security", None) or {}
    if not sec:
        return ""
    L: List[str] = ["---", "", "## Input integrity screen", ""]
    risk = sec.get("overall_risk", "clean")
    L += [f"**Overall risk: {risk.upper()}** · mode: `{sec.get('mode', 'balanced')}`", ""]
    if risk == "clean":
        L += ["Both the pitch deck and every web source were screened for content "
              "written to influence the AI rather than inform a human reader — hidden "
              "text, invisible characters, fake system messages, instructions to alter "
              "the verdict. Nothing was found.", ""]
        return "\n".join(L)

    L += ["The deck and the web sources are both third-party content, so both are "
          "screened before analysis for text aimed at the AI rather than the reader.", ""]
    for key, title in (("deck", "Pitch deck"), ("web_sources", "Web sources")):
        block = sec.get(key) or {}
        findings = block.get("findings") or []
        if not findings:
            continue
        L += [f"### {title} — {block.get('risk', 'clean').upper()}", ""]
        L += ["| Severity | Where | What was found | Action |", "|---|---|---|---|"]
        for f in findings[:40]:
            L.append(f"| {f.get('severity')} | {f.get('where')} | {f.get('detail')} | "
                     f"{f.get('action')} |")
        L.append("")
        samples = [f for f in findings if f.get("excerpt")][:5]
        if samples:
            L += ["<details><summary>Defanged excerpts of the flagged content</summary>", ""]
            for f in samples:
                L.append(f"- **{f.get('where')}** — `{str(f.get('excerpt'))[:240]}`")
            L += ["", "</details>", ""]
    L += ["> Hidden or AI-directed content in a pitch deck is itself a finding about "
          "the company, independent of what the text says.", ""]
    return "\n".join(L)


def render(result, out_dir: Path, base: str, **kw: Any) -> List[str]:
    paths = []
    for lens in result.comparisons:
        p = out_dir / f"{base}_{lens}.md"
        p.write_text(build_markdown(result, lens), encoding="utf-8")
        paths.append(str(p))
    return paths
