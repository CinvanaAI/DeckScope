"""Markdown report — the canonical text other renderers build from."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .common import ASSESSMENT_WORD, as_list, header_block, lens_title, txt


def build_markdown(result, lens: str) -> str:
    comp = result.comparisons.get(lens, {})
    deck, market = result.deck, result.market
    h = header_block(result, lens)
    L: List[str] = []
    add = L.append

    add(f"# {h['company']} — Deck vs. Market Analysis")
    add("")
    add(f"**{h['lens']}**")
    add("")
    if h["headline"]:
        add(f"> {h['headline']}")
        add("")
    add(f"| | |")
    add(f"|---|---|")
    add(f"| **Verdict** | {h['verdict']} |")
    add(f"| **Confidence** | {h['confidence']} |")
    add(f"| **Weighted score** | {h['score']} / 100 |")
    add(f"| **Analyzed** | {h['generated']} |")
    add(f"| **Model** | {h['model']} |")
    add(f"| **Research** | {h['research']} |")
    add("")
    rationale = (comp.get("verdict") or {}).get("confidence_rationale")
    if rationale:
        add(f"*Confidence basis: {rationale}*")
        add("")

    # ---------------------------------------------------------- summary
    add("## Summary")
    add("")
    add(comp.get("summary") or "_No summary produced._")
    add("")
    if comp.get("integrity_note"):
        add(f"> **Integrity note.** {comp['integrity_note']}")
        add("")

    # -------------------------------------------------------- scorecard
    rows = comp.get("scorecard") or []
    if rows:
        add("## Scorecard")
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
            add(f"**Market evidence:** {txt(c.get('market_evidence'))}")
            add("")
            if c.get("delta"):
                add(f"**Gap:** {c['delta']}")
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
                    add(f"- {i}")
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

    # -------------------------------------------------------- questions
    qs = as_list(comp.get("questions"))
    if qs:
        add("## Questions this raises")
        add("")
        for q in qs:
            add(f"- {q}")
        add("")

    acts = comp.get("actions") or []
    if acts:
        add("## Recommended actions")
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
                src = f"[{src}]({e['url']})"
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
                        nm = f"[{nm}]({c['url']})"
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
                    add(f"- {i}")
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

    # -------------------------------------------------------- references
    add("---")
    add("")
    add(_references_markdown(result))

    # ---------------------------------------------------------- security
    add(_security_markdown(result))

    add("---")
    add("")
    add(f"*Generated by DeckScope {result.stats.get('deckscope_version', '')} · "
        f"{h['model']} · {h['research']}. AI-generated analysis: verify every figure "
        f"before relying on it. Not investment advice.*")
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
            parts.append(f"[{src.sid}]({src.url})" if src.url else f"{src.sid}")
    for u in as_list(urls):
        if not u:
            continue
        src = reg.find(str(u)) if reg else None
        if src and src.sid in seen:
            continue
        if src:
            seen.add(src.sid)
            parts.append(f"[{src.sid}]({src.url})" if src.url else src.sid)
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
        L.append("| ID | Source | Published | Reliability | Supports |")
        L.append("|---|---|---|---|---|")
        for s in sources:
            link = f"[{s.title or s.domain or s.url}]({s.url})" if s.url else (s.title or "—")
            supports = "; ".join(s.cited_by[:4]) or "—"
            L.append(f"| **{s.sid}** | {link} | {s.published or '—'} | "
                     f"{s.reliability} | {supports} |")
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
