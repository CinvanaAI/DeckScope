"""Self-contained HTML report — one file, no external assets, prints cleanly."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List

from .common import (ASSESSMENT_WORD, as_list, header_block, safe_url,
                     score_color, theme, txt)


def _e(v: Any) -> str:
    return html.escape(str(v if v not in (None, "") else "—"))


def _link(url: Any, label: str) -> str:
    """An anchor when the URL is safe, inert text when it is not.

    `safe_url` drops anything that is not http(s)/mailto. Rendering the label as
    plain text in that case is better than emitting <a href="">, which would
    silently reload the report when clicked.
    """
    href = safe_url(url)
    if not href:
        return f'{label} <span style="color:var(--muted);font-size:12px">'\
               f'(link withheld — unsafe URL scheme)</span>' if url else label
    return f'<a href="{html.escape(href)}" rel="noopener noreferrer">{label}</a>' 


def _bar(score: Any, weight: Any, t: Dict[str, str]) -> str:
    try:
        pct = max(0, min(100, float(score) * 10))
    except (TypeError, ValueError):
        pct = 0
    return (f'<div class="bar"><span style="width:{pct}%;'
            f'background:{score_color(score, t)}"></span></div>')


def build_html(result, lens: str, theme_name: str = "slate") -> str:
    t = theme(theme_name)
    comp = result.comparisons.get(lens, {})
    deck, market = result.deck, result.market
    h = header_block(result, lens)
    P: List[str] = []
    add = P.append

    add(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(h['company'])} — Deck vs. Market</title><style>
:root{{--accent:{t['accent']};--ink:{t['ink']};--muted:{t['muted']};--bg:{t['bg']};
--panel:{t['panel']};--line:{t['line']};--good:{t['good']};--warn:{t['warn']};--bad:{t['bad']}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:940px;margin:0 auto;padding:48px 24px 96px}}
header{{border-bottom:3px solid var(--accent);padding-bottom:24px;margin-bottom:32px}}
.eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:12px;color:var(--muted);font-weight:600}}
h1{{font-size:34px;line-height:1.2;margin:8px 0 4px;letter-spacing:-.02em}}
h2{{font-size:22px;margin:48px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
h3{{font-size:17px;margin:26px 0 8px}}
.headline{{font-size:19px;line-height:1.5;color:var(--ink);background:var(--panel);
border-left:4px solid var(--accent);padding:16px 20px;border-radius:0 6px 6px 0;margin:20px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}}
.stat{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px}}
.stat .k{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600}}
.stat .v{{font-size:19px;font-weight:650;margin-top:4px;line-height:1.25}}
table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:14.5px}}
th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:650}}
.tw{{overflow-x:auto}}
.bar{{height:7px;background:var(--line);border-radius:4px;overflow:hidden;min-width:80px;margin-top:6px}}
.bar span{{display:block;height:100%;border-radius:4px}}
.claim{{border:1px solid var(--line);border-radius:9px;padding:18px 20px;margin:14px 0;background:var(--panel)}}
.claim h4{{margin:0 0 10px;font-size:16px}}
.tag{{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.05em;
text-transform:uppercase;padding:3px 9px;border-radius:20px;color:#fff}}
.t-supported{{background:var(--good)}}.t-partially-supported{{background:var(--warn)}}
.t-contradicted{{background:var(--bad)}}.t-unverifiable{{background:var(--muted)}}
.kv{{margin:8px 0}}.kv b{{color:var(--muted);font-weight:650;font-size:13px;
text-transform:uppercase;letter-spacing:.05em;display:block;margin-bottom:2px}}
ul{{padding-left:20px}}li{{margin:5px 0}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
@media(max-width:720px){{.cols{{grid-template-columns:1fr}}}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:16px 20px}}
.sev-high{{color:var(--bad);font-weight:650}}.sev-medium{{color:var(--warn);font-weight:650}}
.sev-low{{color:var(--good);font-weight:650}}
footer{{margin-top:64px;padding-top:20px;border-top:1px solid var(--line);
font-size:12.5px;color:var(--muted)}}
details{{margin:14px 0}}summary{{cursor:pointer;color:var(--accent);font-weight:600}}
a{{color:var(--accent)}}
@media print{{.wrap{{max-width:none;padding:0}}h2{{page-break-after:avoid}}
.claim{{page-break-inside:avoid}}}}
</style></head><body><div class="wrap">""")

    add(f"""<header>
<div class="eyebrow">{_e(h['lens'])}</div>
<h1>{_e(h['company'])}</h1>
<div style="color:var(--muted)">Pitch deck claims measured against market evidence</div>
</header>""")

    if h["headline"]:
        add(f'<div class="headline">{_e(h["headline"])}</div>')

    add('<div class="grid">')
    for k, v in (("Verdict", h["verdict"]), ("Confidence", h["confidence"]),
                 ("Weighted score", f"{h['score']}/100"),
                 ("Sources reviewed", str(result.stats.get("sources_found", 0)))):
        add(f'<div class="stat"><div class="k">{_e(k)}</div><div class="v">{_e(v)}</div></div>')
    add("</div>")

    rationale = (comp.get("verdict") or {}).get("confidence_rationale")
    if rationale:
        add(f'<p style="color:var(--muted);font-size:14px">'
            f'<b>Confidence basis:</b> {_e(rationale)}</p>')

    if comp.get("integrity_note"):
        add(f'<div class="headline" style="border-left-color:var(--bad)">'
            f'<b>Integrity note.</b> {_e(comp["integrity_note"])}</div>')

    add("<h2>Summary</h2>")
    for para in (comp.get("summary") or "").split("\n"):
        if para.strip():
            add(f"<p>{_e(para.strip())}</p>")

    rows = comp.get("scorecard") or []
    if rows:
        add("<h2>Scorecard</h2><div class='tw'><table><tr><th>Dimension</th>"
            "<th style='width:120px'>Score</th><th>Weight</th><th>Why</th></tr>")
        for r in rows:
            add(f"<tr><td><b>{_e(r.get('dimension'))}</b></td>"
                f"<td><b>{_e(r.get('score'))}</b>/10{_bar(r.get('score'), r.get('weight'), t)}</td>"
                f"<td>{_e(r.get('weight'))}</td><td>{_e(r.get('rationale'))}</td></tr>")
        add("</table></div>")

    audit = comp.get("claim_audit") or []
    if audit:
        add("<h2>Claim-by-claim audit</h2>")
        for c in audit:
            a = (c.get("assessment") or "unverifiable").lower()
            add(f'<div class="claim"><h4>{_e(c.get("id"))} · {_e(c.get("claim"))} '
                f'<span class="tag t-{html.escape(a)}">{_e(ASSESSMENT_WORD.get(a, a))}</span></h4>'
                f'<div class="kv"><b>Market evidence</b>{_e(c.get("market_evidence"))}</div>')
            if c.get("delta"):
                add(f'<div class="kv"><b>Gap</b>{_e(c["delta"])}</div>')
            if c.get("so_what"):
                add(f'<div class="kv"><b>So what</b>{_e(c["so_what"])}</div>')
            if c.get("evidence_quality"):
                add(f'<div class="kv"><b>Evidence quality</b>{_e(c["evidence_quality"])}</div>')
            add('<div class="kv"><b>Sources</b>'
                + _cite_html(c.get("source_ids"), c.get("sources"), result) + "</div>")
            add("</div>")

    align = comp.get("alignment") or {}
    if any(align.values()):
        add("<h2>Alignment</h2><div class='cols'>")
        for key, title in (("where_deck_matches_market", "Deck matches the market"),
                           ("where_deck_overstates", "Deck overstates"),
                           ("where_deck_understates", "Deck understates"),
                           ("blind_spots", "Blind spots")):
            items = as_list(align.get(key))
            if items:
                add(f'<div class="panel"><h3 style="margin-top:0">{_e(title)}</h3><ul>'
                    + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul></div>")
        add("</div>")

    risks = comp.get("risks") or []
    if risks:
        add("<h2>Risks</h2><div class='tw'><table><tr><th>Risk</th><th>Severity</th>"
            "<th>Likelihood</th><th>Test or mitigation</th></tr>")
        for r in risks:
            sev = (r.get("severity") or "").lower()
            add(f"<tr><td>{_e(r.get('risk'))}</td>"
                f"<td class='sev-{html.escape(sev)}'>{_e(r.get('severity'))}</td>"
                f"<td>{_e(r.get('likelihood'))}</td>"
                f"<td>{_e(r.get('mitigation_or_test'))}</td></tr>")
        add("</table></div>")

    qs = as_list(comp.get("questions"))
    acts = comp.get("actions") or []
    if qs or acts:
        add("<h2>What to do next</h2><div class='cols'>")
        if qs:
            add('<div class="panel"><h3 style="margin-top:0">Questions this raises</h3><ul>'
                + "".join(f"<li>{_e(q)}</li>" for q in qs) + "</ul></div>")
        if acts:
            add('<div class="panel"><h3 style="margin-top:0">Recommended actions</h3><ul>'
                + "".join(f"<li><b>{_e(a.get('priority'))}</b> — {_e(a.get('action'))}"
                          f" <span style='color:var(--muted)'>({_e(a.get('owner'))})</span></li>"
                          for a in acts) + "</ul></div>")
        add("</div>")

    # ---- market annex
    add("<h2>Annex A — What the market evidence shows</h2>")
    sizing = market.get("sizing") or {}
    add('<div class="grid">')
    for k, v in (("Consensus sizing", sizing.get("consensus_view")),
                 ("CAGR range", sizing.get("cagr_range")),
                 ("Sizing confidence", sizing.get("sizing_confidence"))):
        add(f'<div class="stat"><div class="k">{_e(k)}</div>'
            f'<div class="v" style="font-size:15px">{_e(v)}</div></div>')
    add("</div>")
    ests = sizing.get("tam_estimates") or []
    if ests:
        add("<div class='tw'><table><tr><th>Estimate</th><th>Year</th>"
            "<th>Methodology</th><th>Source</th></tr>")
        for e in ests:
            src = _e(e.get("source"))
            if e.get("url"):
                src = _link(e["url"], src)
            add(f"<tr><td><b>{_e(e.get('value'))}</b></td><td>{_e(e.get('year'))}</td>"
                f"<td>{_e(e.get('methodology'))}</td><td>{src}</td></tr>")
        add("</table></div>")

    land = market.get("competitive_landscape") or {}
    for group, title in (("incumbents", "Incumbents"), ("challengers", "Challengers")):
        rows2 = land.get(group) or []
        if rows2:
            add(f"<h3>{title}</h3><div class='tw'><table><tr><th>Company</th><th>Position</th>"
                "<th>Scale</th><th>Threat</th></tr>")
            for c in rows2:
                nm = _e(c.get("name"))
                if c.get("url"):
                    nm = _link(c["url"], nm)
                lvl = (c.get("threat_level") or "").lower()
                add(f"<tr><td><b>{nm}</b></td><td>{_e(c.get('position'))}</td>"
                    f"<td>{_e(c.get('funding_or_scale'))}</td>"
                    f"<td class='sev-{html.escape(lvl)}'>{_e(c.get('threat_level'))}</td></tr>")
            add("</table></div>")

    gaps = as_list(market.get("research_gaps"))
    if gaps:
        add("<h3>What could not be verified</h3><ul>"
            + "".join(f"<li>{_e(g)}</li>" for g in gaps) + "</ul>")

    # ---- deck annex
    add("<h2>Annex B — What the deck claims</h2><div class='tw'><table>")
    mk, tr, ask = (deck.get("market") or {}, deck.get("traction") or {}, deck.get("ask") or {})
    for k, v in (("Problem", (deck.get("problem") or {}).get("statement")),
                 ("Solution", (deck.get("solution") or {}).get("description")),
                 ("TAM claimed", f"{txt(mk.get('tam_claimed'))} ({txt(mk.get('tam_methodology'))})"),
                 ("SAM / SOM", f"{txt(mk.get('sam_claimed'))} / {txt(mk.get('som_claimed'))}"),
                 ("Revenue", tr.get("revenue")), ("Growth", tr.get("growth")),
                 ("Customers", tr.get("customers")), ("Retention", tr.get("retention")),
                 ("Competitors named", txt((deck.get("competition") or {}).get("named_competitors"))),
                 ("Ask", f"{txt(ask.get('amount'))} at {txt(ask.get('valuation'))}")):
        add(f"<tr><th style='width:180px'>{_e(k)}</th><td>{_e(v)}</td></tr>")
    add("</table></div>")

    add(_references_html(result))
    add(_security_html(result))

    add(f"""<footer>Generated by DeckScope
on {_e(h['generated'])} · model {_e(h['model'])} · research {_e(h['research'])}.<br>
AI-generated analysis. Verify every figure before relying on it. Not investment advice.
</footer></div></body></html>""")
    return "\n".join(P)


def _cite_html(source_ids: Any, urls: Any, result) -> str:
    reg = getattr(result, "registry", None)
    parts, seen = [], set()
    for ref in list(as_list(source_ids)) + list(as_list(urls)):
        if not ref:
            continue
        src = reg.find(str(ref)) if reg else None
        if src:
            if src.sid in seen:
                continue
            seen.add(src.sid)
            label = f"{src.sid}"
            title = html.escape((src.title or src.url or "")[:120])
            parts.append(f'<a href="#{src.sid}" title="{title}">[{label}]</a>')
        else:
            parts.append(_link(ref, html.escape(str(ref))[:60]))
    return " ".join(parts) if parts else (
        '<i style="color:var(--muted)">none cited — this assessment rests on no source</i>')


def _references_html(result) -> str:
    reg = getattr(result, "registry", None)
    P = ["<h2>References</h2>"]
    if not reg or not reg.sources:
        backend = _e((result.stats or {}).get("research_backend", "none"))
        return ("<h2>References</h2><div class='panel'>No external sources were retrieved "
                f"(research backend: <code>{backend}</code>). Every statement above rests "
                "on the model's training knowledge and on the deck itself, and is "
                "therefore unverified.</div>")
    st = reg.stats()
    P.append(f"<p style='color:var(--muted)'>{st['total']} sources retrieved and screened: "
             f"<b>{st['cited']}</b> cited, {st['consulted_uncited']} consulted without "
             f"being cited, {st['quarantined']} dropped by the security screen. Every "
             f"source is listed, so absence of evidence is as visible as its presence.</p>")

    def table(sources, title, note=""):
        if not sources:
            return
        P.append(f"<h3>{_e(title)}</h3>")
        if note:
            P.append(f"<p style='color:var(--muted);font-size:14px'>{_e(note)}</p>")
        P.append("<div class='tw'><table><tr><th>ID</th><th>Source</th><th>Published</th>"
                 "<th>Reliability</th><th>Supports</th></tr>")
        for s in sources:
            link = (_link(s.url, _e(s.title or s.domain or s.url))
                    if s.url else _e(s.title))
            P.append(f'<tr id="{html.escape(s.sid)}"><td><b>{_e(s.sid)}</b></td>'
                     f"<td>{link}"
                     + (f"<div style='color:var(--muted);font-size:12.5px'>{_e(s.domain)}</div>"
                        if s.domain else "")
                     + f"</td><td>{_e(s.published)}</td><td>{_e(s.reliability)}</td>"
                     f"<td style='font-size:13px'>{_e('; '.join(s.cited_by[:4]) or '—')}</td></tr>")
        P.append("</table></div>")

    table(reg.cited, "Cited in this analysis")
    table(reg.consulted, "Consulted, not cited",
          "Retrieved by the research queries but did not support any specific conclusion.")
    if reg.quarantined:
        P.append("<h3>Dropped by the security screen</h3><div class='tw'><table>"
                 "<tr><th>ID</th><th>Source</th><th>Reason</th></tr>")
        for s in reg.quarantined:
            P.append(f"<tr><td><b>{_e(s.sid)}</b></td><td>{_e(s.url or s.title)}</td>"
                     f"<td>{_e(s.note or 'flagged as hostile')}</td></tr>")
        P.append("</table></div>")

    queries = ((result.market.get("_meta") or {}).get("queries")) or []
    if queries:
        P.append("<details><summary>Search queries that produced these sources</summary><ul>"
                 + "".join(f"<li><code>{_e(q)}</code></li>" for q in queries) + "</ul></details>")
    return "".join(P)


def _security_html(result) -> str:
    sec = getattr(result, "security", None) or {}
    if not sec:
        return ""
    risk = sec.get("overall_risk", "clean")
    color = {"clean": "var(--good)", "low": "var(--good)", "medium": "var(--warn)",
             "high": "var(--bad)", "critical": "var(--bad)"}.get(risk, "var(--muted)")
    P = ["<h2>Input integrity screen</h2>",
         f"<div class='panel' style='border-left:4px solid {color}'>"
         f"<b style='color:{color}'>Overall risk: {_e(risk.upper())}</b> "
         f"<span style='color:var(--muted)'>· mode <code>{_e(sec.get('mode','balanced'))}</code></span>"]
    if risk == "clean":
        P.append("<p style='margin-bottom:0'>The pitch deck and every web source were "
                 "screened for content written to influence the AI rather than inform a "
                 "human reader — hidden text, invisible characters, fake system messages, "
                 "instructions to change the verdict. Nothing was found.</p></div>")
        return "".join(P)
    P.append("</div>")
    for key, title in (("deck", "Pitch deck"), ("web_sources", "Web sources")):
        block = sec.get(key) or {}
        findings = block.get("findings") or []
        if not findings:
            continue
        P.append(f"<h3>{_e(title)} — {_e(str(block.get('risk','clean')).upper())}</h3>")
        P.append("<div class='tw'><table><tr><th>Severity</th><th>Where</th>"
                 "<th>What was found</th><th>Action</th></tr>")
        for f in findings[:40]:
            sev = str(f.get("severity", "")).lower()
            cls = {"critical": "sev-high", "high": "sev-high",
                   "medium": "sev-medium"}.get(sev, "sev-low")
            P.append(f"<tr><td class='{cls}'>{_e(f.get('severity'))}</td>"
                     f"<td>{_e(f.get('where'))}</td><td>{_e(f.get('detail'))}</td>"
                     f"<td>{_e(f.get('action'))}</td></tr>")
        P.append("</table></div>")
        samples = [f for f in findings if f.get("excerpt")][:5]
        if samples:
            P.append("<details><summary>Defanged excerpts of the flagged content</summary><ul>"
                     + "".join(f"<li><b>{_e(f.get('where'))}</b> — "
                               f"<code>{_e(str(f.get('excerpt'))[:240])}</code></li>"
                               for f in samples) + "</ul></details>")
    P.append("<p style='color:var(--muted);font-size:14px'>Hidden or AI-directed content "
             "in a pitch deck is itself a finding about the company, independent of what "
             "the text says.</p>")
    return "".join(P)


def render(result, out_dir: Path, base: str, theme: str = "slate", **kw: Any) -> List[str]:
    paths = []
    for lens in result.comparisons:
        p = out_dir / f"{base}_{lens}.html"
        p.write_text(build_html(result, lens, theme), encoding="utf-8")
        paths.append(str(p))
    return paths
