"""Self-contained HTML report — one file, no external assets, prints cleanly."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List

from .common import (ASSESSMENT_WORD, SEVERITY_WORD, THEMES, alignment_text,
                     as_list, findings_for, header_block, safe_url,
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


def _cite_chip(sid: str, result) -> str:
    """A citation that goes somewhere.

    An ID printed as plain text asks the reader to scroll to the bibliography and
    find it by eye, which in practice means nobody checks anything. Linking it to
    the entry — and putting the source title in the tooltip — is the difference
    between provenance that exists and provenance that is used.
    """
    registry = getattr(result, "registry", None)
    title = ""
    if registry is not None:
        try:
            src = registry.find(sid)
            title = (src.title or src.url or "") if src else ""
        except Exception:  # noqa: BLE001
            title = ""
    tip = f' title="{html.escape(title)}"' if title else ""
    return f'<a class="cite" href="#{html.escape(sid)}"{tip}>{_e(sid)}</a>'


def _finding_card(f, result) -> str:
    """One finding, drawn according to whether it can be checked.

    The class list is the whole point: `sourced` versus `unsourced` drives a
    solid or dashed edge, so a reader scanning the page sees which claims rest on
    something before reading a word. Severity only colours the edge when there is
    a source behind it — colouring an unsourced disagreement red would lend it
    exactly the authority it has not earned.
    """
    solid = "sourced" if f.source_ids else "unsourced"
    body = [f'<div class="find {solid} sev-{_e(f.severity)}">',
            f'<div class="claim-text">{_e(f.text)}</div>']
    why = (f.delta or f.why or "").strip()
    if why:
        body.append(f'<div class="why">{_e(why)}</div>')
    body.append('<div class="foot">')
    if f.kind == "contested":
        level = f.severity if f.severity in ("high", "medium") else ""
        body.append(f'<span class="badge {level}">'
                    f'{_e(SEVERITY_WORD.get(f.severity, f.severity))}</span>')
    if f.source_ids:
        body.extend(_cite_chip(s, result) for s in f.source_ids)
    elif f.kind == "contested":
        body.append('<span class="badge nosource">no source — a reading, '
                    'not a finding</span>')
    body.append("</div></div>")
    return "".join(body)


def build_html(result, lens: str, theme_name: str = "slate") -> str:
    t = theme(theme_name)
    comp = result.comparisons.get(lens, {})
    deck, market = result.deck, result.market
    h = header_block(result, lens)
    P: List[str] = []
    add = P.append

    dark = THEMES["midnight"]
    # Only the default theme follows the reader's system setting. An explicit
    # --theme is a choice and gets honoured exactly as asked.
    # Built as its own f-string and then substituted, so braces are escaped ONCE
    # here, not twice. A substituted value is inserted verbatim — the outer
    # f-string does not re-process it — and double-escaping leaked literal `{{`
    # into the stylesheet, which silently killed the dark-mode block.
    adaptive = f"""
@media(prefers-color-scheme:dark){{:root{{
--accent:{dark['accent']};--ink:{dark['ink']};--muted:{dark['muted']};--bg:{dark['bg']};
--panel:{dark['panel']};--line:{dark['line']};--good:{dark['good']};
--warn:{dark['warn']};--bad:{dark['bad']}}}}}""" if theme_name == "slate" else ""

    add(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(h['company'])} — Deck vs. Market</title><style>
:root{{--accent:{t['accent']};--ink:{t['ink']};--muted:{t['muted']};--bg:{t['bg']};
--panel:{t['panel']};--line:{t['line']};--good:{t['good']};--warn:{t['warn']};--bad:{t['bad']};
--radius:10px}}{adaptive}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
.wrap{{max-width:1180px;margin:0 auto;padding:44px 28px 96px;
display:grid;grid-template-columns:210px minmax(0,1fr);gap:52px;align-items:start}}
.main{{min-width:0}}
header{{grid-column:1/-1;border-bottom:3px solid var(--accent);padding-bottom:22px;margin-bottom:8px}}
.eyebrow{{text-transform:uppercase;letter-spacing:.14em;font-size:11.5px;color:var(--muted);font-weight:700}}
h1{{font-size:37px;line-height:1.12;margin:10px 0 4px;letter-spacing:-.025em;font-weight:700}}
h2{{font-size:21px;margin:46px 0 14px;padding-bottom:9px;border-bottom:1px solid var(--line);
letter-spacing:-.01em;scroll-margin-top:20px}}
h3{{font-size:16.5px;margin:26px 0 8px}}
p{{margin:10px 0}}
.lede{{color:var(--muted);font-size:14.5px}}

/* --- table of contents ------------------------------------------------ */
nav.toc{{position:sticky;top:28px;font-size:13.5px;line-height:1.5}}
nav.toc .t{{text-transform:uppercase;letter-spacing:.1em;font-size:10.5px;
color:var(--muted);font-weight:700;margin-bottom:10px}}
nav.toc a{{display:block;padding:5px 0 5px 12px;color:var(--muted);text-decoration:none;
border-left:2px solid var(--line);transition:color .15s,border-color .15s}}
nav.toc a:hover{{color:var(--accent);border-left-color:var(--accent)}}

/* --- the headline ----------------------------------------------------- */
.headline{{font-size:20.5px;line-height:1.48;background:var(--panel);
border-left:4px solid var(--accent);padding:20px 24px;border-radius:0 var(--radius) var(--radius) 0;
margin:26px 0 10px;font-weight:520;letter-spacing:-.005em}}
.evidence-state{{color:var(--muted);font-size:13.5px;margin:0 0 22px;padding-left:2px}}
.evidence-state.thin{{color:var(--warn);font-weight:600}}

/* --- at a glance ------------------------------------------------------ */
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:10px;margin:20px 0 8px}}
.stat{{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:13px 15px}}
.stat .k{{font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:700}}
.stat .v{{font-size:23px;font-weight:700;margin-top:3px;line-height:1.1;letter-spacing:-.02em}}

/* --- findings: provenance is the visual language ----------------------
   A finding backed by a source you can open looks solid: full-weight border in
   the severity colour. A finding with nothing behind it is drawn provisionally
   — dashed, muted, and labelled — because that is exactly what it is. The
   design carries the epistemics rather than decorating them. */
.find{{border:1px solid var(--line);border-left:4px solid var(--muted);
border-radius:0 var(--radius) var(--radius) 0;padding:15px 18px;margin:11px 0;
background:var(--panel);transition:border-color .15s}}
.find.sourced.sev-high{{border-left-color:var(--bad)}}
.find.sourced.sev-medium{{border-left-color:var(--warn)}}
.find.sourced.sev-low{{border-left-color:var(--muted)}}
.find.unsourced{{border-style:dashed;border-left-style:dashed;
border-left-color:var(--line);background:transparent}}
.find .claim-text{{font-weight:650;font-size:15.5px;letter-spacing:-.005em}}
.find .why{{color:var(--muted);font-size:14px;margin-top:5px}}
.find .foot{{margin-top:9px;display:flex;flex-wrap:wrap;gap:7px;align-items:center}}
.badge{{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.05em;
text-transform:uppercase;padding:3px 9px;border-radius:20px;
border:1px solid var(--line);color:var(--muted)}}
.badge.high{{color:var(--bad);border-color:var(--bad)}}
.badge.medium{{color:var(--warn);border-color:var(--warn)}}
.badge.nosource{{color:var(--muted);border-style:dashed}}
a.cite{{display:inline-block;font-size:11.5px;font-weight:700;padding:3px 9px;
border-radius:20px;background:var(--accent);color:var(--bg);text-decoration:none;
letter-spacing:.02em;transition:opacity .15s}}
a.cite:hover{{opacity:.78}}

/* --- next steps ------------------------------------------------------- */
ol.steps{{counter-reset:s;list-style:none;padding:0;margin:14px 0}}
ol.steps li{{counter-increment:s;position:relative;padding:9px 0 9px 42px;
border-bottom:1px solid var(--line)}}
ol.steps li:last-child{{border-bottom:0}}
ol.steps li::before{{content:counter(s);position:absolute;left:0;top:9px;
width:25px;height:25px;border-radius:50%;background:var(--accent);color:var(--bg);
font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center}}

table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:14.5px}}
th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:700}}
tbody tr:hover{{background:var(--panel)}}
.tw{{overflow-x:auto}}
.bar{{height:6px;background:var(--line);border-radius:4px;overflow:hidden;min-width:80px;margin-top:6px}}
.bar span{{display:block;height:100%;border-radius:4px}}
.claim{{border:1px solid var(--line);border-radius:var(--radius);padding:17px 19px;
margin:13px 0;background:var(--panel)}}
.claim h4{{margin:0 0 10px;font-size:15.5px}}
.tag{{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.05em;
text-transform:uppercase;padding:3px 9px;border-radius:20px;color:#fff}}
.t-supported{{background:var(--good)}}.t-partially-supported{{background:var(--warn)}}
.t-contradicted{{background:var(--bad)}}.t-unverifiable{{background:var(--muted)}}
.kv{{margin:8px 0}}.kv b{{color:var(--muted);font-weight:700;font-size:12px;
text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:2px}}
ul{{padding-left:20px}}li{{margin:5px 0}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 20px}}
.sev-high{{color:var(--bad);font-weight:650}}.sev-medium{{color:var(--warn);font-weight:650}}
.sev-low{{color:var(--good);font-weight:650}}
/* A clicked citation lands on its source row and says so — otherwise the
   reader arrives at a table and has to hunt for the line they asked for. */
tr[id]{{scroll-margin-top:70px}}
tr:target{{background:var(--panel);outline:2px solid var(--accent);outline-offset:-2px}}
tr:target td:first-child{{font-weight:800}}
footer{{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);
font-size:12.5px;color:var(--muted)}}
details{{margin:14px 0}}summary{{cursor:pointer;color:var(--accent);font-weight:600}}
a{{color:var(--accent)}}
@media(max-width:940px){{
.wrap{{grid-template-columns:1fr;gap:0;padding:32px 20px 72px}}
nav.toc{{display:none}}h1{{font-size:30px}}.headline{{font-size:18px;padding:16px 18px}}
.cols{{grid-template-columns:1fr}}}}
@media print{{
.wrap{{max-width:none;padding:0;display:block}}nav.toc{{display:none}}
h2{{page-break-after:avoid}}.claim,.find{{page-break-inside:avoid}}
a.cite{{background:none;color:var(--ink);border:1px solid var(--line)}}
.find.unsourced{{border-style:solid}}}}
</style></head><body><div class="wrap">""")

    add(f"""<header>
<div class="eyebrow">{_e(h['lens'])}</div>
<h1>{_e(h['company'])}</h1>
<div class="lede">Pitch deck claims measured against market evidence</div>
</header>""")

    # Same hierarchy as the markdown report: findings first, verdict demoted, no
    # composite score above the fold. See deckscope/findings.py.
    found = findings_for(result, lens)

    # The table of contents is built from what this report actually contains, so
    # it never advertises a section that is not there.
    toc = [("contests", "What the evidence contests", bool(found.contested)),
           ("omits", "What the deck leaves out", bool(found.omissions)),
           ("unchecked", "What could not be checked", bool(found.unverified)),
           ("next", "What to do next", bool(found.next_steps)),
           ("summary", "Summary", True),
           ("verdict", "This lens's read", True),
           ("scorecard", "Scorecard", bool(comp.get("scorecard"))),
           ("audit", "Claim-by-claim", bool(comp.get("claim_audit"))),
           ("risks", "Risks", bool(comp.get("risks"))),
           ("market", "Market evidence", True),
           ("refs", "References", True)]
    add('<nav class="toc"><div class="t">On this page</div>')
    for anchor, label, present in toc:
        if present:
            add(f'<a href="#{anchor}">{_e(label)}</a>')
    add("</nav>")
    add('<div class="main">')

    add(f'<div class="headline">{_e(found.headline)}</div>')
    thin = " thin" if found.evidence_too_thin else ""
    add(f'<p class="evidence-state{thin}">{_e(found.evidence_state)}</p>')

    if comp.get("integrity_note"):
        add(f'<div class="headline" style="border-left-color:var(--bad)">'
            f'<b>Integrity note.</b> {_e(comp["integrity_note"])}</div>')

    add('<div class="grid">')
    for k, v in (("Claims examined", str(found.counts.get("claims_examined", 0))),
                 ("Contested", str(found.counts.get("contested", 0))),
                 ("Omissions", str(found.counts.get("omissions", 0))),
                 ("Unresolved", str(found.counts.get("unverified", 0))),
                 ("Sources", str(result.stats.get("sources_found", 0)))):
        add(f'<div class="stat"><div class="k">{_e(k)}</div>'
            f'<div class="v">{_e(v)}</div></div>')
    add("</div>")

    if found.contested:
        add('<h2 id="contests">What the evidence contests</h2>')
        add('<p class="lede">Claims the deck makes that retrieved evidence pushes '
            'back on. A solid left edge means a source you can open; a dashed one '
            'means the analysis disagrees but cannot show you why.</p>')
        for f in found.contested:
            add(_finding_card(f, result))

    if found.omissions:
        add('<h2 id="omits">What the deck leaves out</h2>')
        add('<p class="lede">Present in the market evidence, absent from the deck.</p>')
        for f in found.omissions:
            add(_finding_card(f, result))

    if found.unverified:
        add('<h2 id="unchecked">What could not be checked</h2>')
        add('<p class="lede">Neither confirmed nor refuted by the evidence '
            'retrieved. These are research tasks, <b>not</b> marks against the '
            'company — an analysis must not turn its own gaps into a verdict.</p>')
        for f in found.unverified:
            add(_finding_card(f, result))

    if found.next_steps:
        add('<h2 id="next">What to do next</h2><ol class="steps">')
        for step in found.next_steps:
            add(f"<li>{_e(step)}</li>")
        add("</ol>")

    add('<h2 id="summary">Summary</h2>')
    for para in (comp.get("summary") or "").split("\n"):
        if para.strip():
            add(f"<p>{_e(para.strip())}</p>")

    add('<h2 id="verdict">What this adds up to, for this lens</h2>')
    add(f'<p><b>{_e(h["verdict"])}</b> · confidence: {_e(h["confidence"])}</p>')
    rationale = (comp.get("verdict") or {}).get("confidence_rationale")
    if rationale:
        add(f'<p style="color:var(--muted);font-size:14px">'
            f'<b>Confidence basis:</b> {_e(rationale)}</p>')
    add("<p style='color:var(--muted);font-size:14px'>A verdict is one reader's "
        "reading of the findings above, through one lens. The findings are the "
        "durable part; this line is not.</p>")

    rows = comp.get("scorecard") or []
    if rows:
        add('<h2 id="scorecard">Scorecard</h2>')
        add("<p style='color:var(--muted);font-size:14px'>Per-dimension, each "
            "with its reasoning. There is deliberately no headline total: a "
            "weighted average of seven subjective scores is the one figure here "
            "that cannot be traced to a source.</p>")
        add("<div class='tw'><table><tr><th>Dimension</th>"
            "<th style='width:120px'>Score</th><th>Weight</th><th>Why</th></tr>")
        for r in rows:
            add(f"<tr><td><b>{_e(r.get('dimension'))}</b></td>"
                f"<td><b>{_e(r.get('score'))}</b>/10{_bar(r.get('score'), r.get('weight'), t)}</td>"
                f"<td>{_e(r.get('weight'))}</td><td>{_e(r.get('rationale'))}</td></tr>")
        add("</table></div>")

    audit = comp.get("claim_audit") or []
    if audit:
        add('<h2 id="audit">Claim-by-claim audit</h2>')
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
                    + "".join(f"<li>{_e(alignment_text(i))}</li>" for i in items)
                    + "</ul></div>")
        add("</div>")

    risks = comp.get("risks") or []
    if risks:
        add('<h2 id="risks">Risks</h2>')
        add("<div class='tw'><table><tr><th>Risk</th><th>Severity</th>"
            "<th>Likelihood</th><th>Test or mitigation</th></tr>")
        for r in risks:
            sev = (r.get("severity") or "").lower()
            add(f"<tr><td>{_e(r.get('risk'))}</td>"
                f"<td class='sev-{html.escape(sev)}'>{_e(r.get('severity'))}</td>"
                f"<td>{_e(r.get('likelihood'))}</td>"
                f"<td>{_e(r.get('mitigation_or_test'))}</td></tr>")
        add("</table></div>")

    # Questions and actions already appear, consolidated and ranked, under
    # "What to do next" at the top. Repeating them here produced a second
    # heading with the same name and left the reader to reconcile two lists.
    # Only the owner/priority detail unique to the actions table survives.
    acts = comp.get("actions") or []
    if acts:
        add("<h2>Who does what</h2><div class='tw'><table>"
            "<tr><th style='width:80px'>Priority</th><th>Action</th>"
            "<th style='width:160px'>Owner</th></tr>")
        for a in sorted(acts, key=lambda x: str(x.get("priority", "P9"))):
            add(f"<tr><td><b>{_e(a.get('priority'))}</b></td>"
                f"<td>{_e(a.get('action'))}</td><td>{_e(a.get('owner'))}</td></tr>")
        add("</table></div>")

    # ---- market annex
    add('<h2 id="market">Annex A — What the market evidence shows</h2>')
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

    add(_discovery_html(result))
    add(_market_structure_html(market))
    add(_opportunity_html(result))
    add(_references_html(result))
    add(_security_html(result))

    add(f"""<footer>Generated by DeckScope
on {_e(h['generated'])} · model {_e(h['model'])} · research {_e(h['research'])}.<br>
AI-generated analysis. Verify every figure before relying on it. Not investment advice.
</footer></div></div></body></html>""")
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


def _discovery_html(result) -> str:
    """What a cold reading of the market found that the directed pass missed."""
    delta = getattr(result, "discovery_delta", None) or {}
    if not delta or not delta.get("ran"):
        return ""

    P = ["<h2>What the deck steered the research away from</h2>",
         "<p style='color:var(--muted)'>The market analysis was given the deck's "
         "claims — it has to be, it is checking them — so its searches were shaped by "
         "what the deck raises. That finds errors well and finds omissions badly. The "
         "category was therefore <b>also researched cold</b>, by a pass that saw only "
         "the category name and never a single claim.</p>"]

    if not delta.get("anything_found"):
        P.append("<div class='panel'>Nothing. Researching the category from scratch "
                 "surfaced no competitor, headwind or absorber the claim-directed pass "
                 "had missed — which suggests the deck's framing did not steer the "
                 "research away from anything material.</div>")
        return "".join(P)

    P.append(f"<p style='color:var(--muted)'>Overlap between the two routes: "
             f"<b>{float(delta.get('agreement') or 0):.0%}</b> of the competitors "
             f"named.</p>")

    only_cold = delta.get("competitors_only_cold") or []
    if only_cold:
        P.append("<h3>Competitors found only when the deck was out of the room</h3>"
                 "<div class='tw'><table><tr><th>Competitor</th><th>Position</th>"
                 "<th>Threat</th></tr>")
        for c in only_cold:
            lvl = str(c.get("threat_level") or "").lower()
            cls = {"high": "sev-high", "medium": "sev-medium"}.get(lvl, "sev-low")
            P.append(f"<tr><td><b>{_e(c.get('name'))}</b></td>"
                     f"<td>{_e(c.get('position'))}</td>"
                     f"<td class='{cls}'>{_e(c.get('threat_level'))}</td></tr>")
        P.append("</table></div>")

    for key, label in (("absorbers_only_cold", "Potential absorbers not raised"),
                       ("adjacent_only_cold", "Adjacent markets missed")):
        items = delta.get(key) or []
        if items:
            P.append(f"<p><b>{label}:</b> "
                     f"{_e(', '.join(str(x) for x in items))}</p>")

    headwinds = delta.get("headwinds_only_cold") or []
    if headwinds:
        P.append("<h3>Headwinds surfaced only by the cold pass</h3><ul>"
                 + "".join(f"<li>{_e(h)}</li>" for h in headwinds) + "</ul>")

    sizing = delta.get("sizing") or {}
    if sizing.get("cold_consensus") and \
            sizing.get("cold_consensus") != sizing.get("directed_consensus"):
        P.append("<h3>The two routes sized it differently</h3><div class='tw'><table>"
                 f"<tr><th>Route</th><th>Consensus</th><th>Confidence</th></tr>"
                 f"<tr><td>Claim-directed</td><td>{_e(sizing.get('directed_consensus'))}"
                 f"</td><td>{_e(sizing.get('directed_confidence'))}</td></tr>"
                 f"<tr><td>Cold</td><td>{_e(sizing.get('cold_consensus'))}</td>"
                 f"<td>{_e(sizing.get('cold_confidence'))}</td></tr></table></div>")

    P.append("<p style='color:var(--muted);font-size:14px'>These are not necessarily "
             "errors above — the cold pass may be wrong, and it cannot know which of "
             "these matters to this company. What it establishes is that the deck's "
             "framing narrowed the search, and by how much.</p>")
    return "".join(P)


def _market_structure_html(market) -> str:
    """Saturation, absorption risk, the open-source signal and adjacent markets."""
    land = market.get("competitive_landscape") or {}
    sat = land.get("saturation") or {}
    ab = market.get("absorption_risk") or {}
    oss = market.get("open_source_landscape") or {}
    assessment = market.get("bundling_assessment") or {}
    adjacent = market.get("adjacent_markets") or []
    if not any([any(sat.values()), any(ab.values()), oss, adjacent]):
        return ""

    P = ["<h2>Market structure</h2>"]

    if any(sat.values()):
        P.append("<h3>Saturation</h3><div class='grid'>")
        for label, key in (("Funded competitors", "funded_competitors_known"),
                           ("New entrants", "new_entrants_trend"),
                           ("Pricing", "pricing_direction"),
                           ("Lifecycle stage", "lifecycle_stage"),
                           ("Room to enter", "room_for_a_new_entrant")):
            P.append(f"<div class='stat'><div class='k'>{_e(label)}</div>"
                     f"<div class='v' style='font-size:15px'>{_e(sat.get(key))}</div>"
                     f"</div>")
        P.append("</div>")
        if sat.get("consolidation_activity"):
            P.append(f"<p><b>Consolidation:</b> {_e(sat['consolidation_activity'])}</p>")
        if sat.get("why"):
            P.append(f"<p style='color:var(--muted)'>{_e(sat['why'])}</p>")

    if any(ab.values()):
        verdict = str(ab.get("verdict") or "").lower()
        colour = {"feature": "var(--bad)", "contested": "var(--warn)",
                  "product": "var(--good)"}.get(verdict, "var(--muted)")
        P.append(f"<h3>Is this a product or a feature?</h3>"
                 f"<div class='panel' style='border-left:4px solid {colour}'>"
                 f"<b style='color:{colour}'>{_e(str(ab.get('verdict')).upper())}</b> "
                 f"· horizon {_e(ab.get('horizon'))} · confidence "
                 f"{_e(ab.get('confidence'))}"
                 f"<p style='margin-bottom:0'>Categories are regularly built out by "
                 f"startups, proven useful, and then bundled into a platform that "
                 f"already owns the customer. When that happens the market stops "
                 f"existing separately.</p></div>")
        absorbers = ab.get("likely_absorbers") or []
        if absorbers:
            P.append("<div class='tw'><table><tr><th>Could absorb it</th>"
                     "<th>Mechanism</th><th>Already visible</th></tr>")
            for a in absorbers:
                signals = as_list(a.get("signals_already_visible"))
                P.append(f"<tr><td><b>{_e(a.get('name'))}</b><br>"
                         f"<span style='color:var(--muted);font-size:13px'>"
                         f"{_e(a.get('why_them'))}</span></td>"
                         f"<td>{_e(a.get('mechanism'))}</td>"
                         f"<td>{_e('; '.join(str(x) for x in signals))}</td></tr>")
            P.append("</table></div>")
        precedents = ab.get("precedents") or []
        if precedents:
            P.append("<h4>Precedents</h4><div class='tw'><table><tr><th>Category</th>"
                     "<th>Absorbed by</th><th>How long</th><th>Why comparable</th></tr>")
            for pr in precedents:
                P.append(f"<tr><td>{_e(pr.get('category'))}</td>"
                         f"<td>{_e(pr.get('absorbed_by'))}</td>"
                         f"<td>{_e(pr.get('how_long_it_took'))}</td>"
                         f"<td>{_e(pr.get('why_it_is_comparable'))}</td></tr>")
            P.append("</table></div>")
        prevent = as_list(ab.get("what_would_prevent_it"))
        if prevent:
            P.append("<p><b>What would keep this a standalone market</b></p><ul>"
                     + "".join(f"<li>{_e(x)}</li>" for x in prevent) + "</ul>")

    if oss and assessment.get("applicable") is not False:
        level = str(assessment.get("level") or "unknown").lower()
        colour = {"severe": "var(--bad)", "high": "var(--bad)",
                  "elevated": "var(--warn)", "moderate": "var(--warn)",
                  "low": "var(--good)"}.get(level, "var(--muted)")
        P.append(f"<h3>Open source, and what it predicts</h3>"
                 f"<div class='panel' style='border-left:4px solid {colour}'>"
                 f"<b style='color:{colour}'>Bundling risk from commoditization: "
                 f"{_e(level.upper())}</b>"
                 + (f"<p style='margin-bottom:0'>{_e(assessment.get('reasoning'))}</p>"
                    if assessment.get("reasoning") else "") + "</div>")
        projects = oss.get("projects") or []
        if projects:
            P.append("<div class='tw'><table><tr><th>Project</th><th>Maturity</th>"
                     "<th>Governance</th><th>Adoption</th></tr>")
            for pr in projects:
                name = _link(pr.get("url"), _e(pr.get("name")))
                P.append(f"<tr><td><b>{name}</b></td><td>{_e(pr.get('maturity'))}</td>"
                         f"<td>{_e(pr.get('governance'))}</td>"
                         f"<td>{_e(pr.get('adoption_signal'))}</td></tr>")
            P.append("</table></div>")
        provides = oss.get("what_commercial_still_provides") or []
        if provides:
            P.append("<h4>What commercial products still provide once open source "
                     "arrives</h4><p style='color:var(--muted);font-size:14px'>This is "
                     "what decides the outcome. Parity only matters to the extent that "
                     "what is left can be cheaply reproduced by a platform vendor that "
                     "already owns the customer.</p>"
                     "<div class='tw'><table><tr><th>Capability</th><th>Kind</th>"
                     "<th>Hard to replicate?</th></tr>")
            for item in provides:
                durable = str(item.get("durable")).lower() in ("true", "yes")
                P.append(f"<tr><td>{_e(item.get('capability'))}</td>"
                         f"<td>{_e(item.get('type'))}</td>"
                         f"<td class='{'sev-low' if durable else 'sev-high'}'>"
                         f"{'yes' if durable else 'no'}</td></tr>")
            P.append("</table></div>")
        for c in assessment.get("caveats") or []:
            P.append(f"<div class='panel' style='border-left:4px solid var(--warn)'>"
                     f"{_e(c)}</div>")

    if adjacent:
        P.append("<h3>Adjacent markets</h3><div class='tw'><table><tr><th>Market</th>"
                 "<th>Relationship</th><th>Why it matters</th></tr>")
        for m in adjacent:
            P.append(f"<tr><td><b>{_e(m.get('market'))}</b></td>"
                     f"<td>{_e(m.get('relationship'))}</td>"
                     f"<td>{_e(m.get('why_it_matters'))}</td></tr>")
        P.append("</table></div>")
    return "".join(P)


def _opportunity_html(result) -> str:
    """What buying the listed alternative would require instead."""
    opp = getattr(result, "opportunity", None) or {}
    if not opp or opp.get("error"):
        return ""

    P = ["<h2>Compared to what?</h2>"]
    if opp.get("headline"):
        P.append(f'<div class="headline">{_e(opp["headline"])}</div>')
    P.append("<p>An investment is a choice against alternatives, and when a named "
             "competitor is publicly traded the alternative is concrete: you could "
             "simply buy it. What follows is <b>not a forecast</b>. It is the outcome "
             "this company would have to reach to match each benchmark, under stated "
             "assumptions you can change.</p>")

    comps = opp.get("comparables") or []
    if comps:
        P.append("<h3>The named competitors, and whether you could buy them instead</h3>"
                 "<div class='tw'><table><tr><th>Competitor</th><th>Listed</th>"
                 "<th>Market cap</th><th>Revenue</th><th>5-year return</th>"
                 "<th>Source</th></tr>")
        for c in comps:
            listed = (f"<b>{_e(c.get('ticker'))}</b>" if c.get("ticker") else "private")
            ret = f"{c['total_return_5y']}x" if c.get("total_return_5y") else "—"
            P.append(f"<tr><td>{_e(c.get('name'))}</td><td>{listed}</td>"
                     f"<td>{_e(c.get('market_cap_display'))}</td>"
                     f"<td>{_e(c.get('revenue_display'))}</td><td>{_e(ret)}</td>"
                     f"<td>{_e(', '.join(c.get('source_ids') or []) or '—')}</td></tr>")
        P.append("</table></div>")

    reqs = opp.get("requirements") or {}
    if reqs:
        P.append("<h3>What this company would have to reach</h3><div class='tw'>"
                 "<table><tr><th>To match</th><th>Exit value needed</th>"
                 "<th>Implied revenue</th><th>Multiple of today</th></tr>")
        for label, r in reqs.items():
            P.append(f"<tr><td>{_e(label)}</td>"
                     f"<td>{_e(r.get('exit_value_required_display'))}</td>"
                     f"<td>{_e(r.get('implied_arr_required_display'))}</td>"
                     f"<td>{_e(r.get('growth_multiple_required'))}x</td></tr>")
        P.append("</table></div>")
        note = next((r.get("note") for r in reqs.values() if r.get("note")), "")
        if note:
            P.append(f"<div class='panel' style='border-left:4px solid var(--warn)'>"
                     f"{_e(note)}</div>")

    a = opp.get("assumptions") or {}
    if a:
        P.append("<details><summary>The assumptions every number above rests on"
                 "</summary><ul>"
                 f"<li>Future dilution: <b>{float(a.get('future_dilution') or 0):.0%}"
                 f"</b> before exit</li>"
                 f"<li>Exit revenue multiple: <b>{_e(a.get('exit_revenue_multiple'))}x"
                 f"</b></li>"
                 f"<li>Horizon: <b>{_e(a.get('horizon_years'))} years</b></li>"
                 f"<li>Liquidation preference ahead of this round: "
                 f"<b>{_e(a.get('preference_stack'))}x</b></li></ul>"
                 "<p>Change any of these and every figure changes. They are "
                 "conventional defaults, not authoritative ones.</p></details>")

    rates = opp.get("base_rates") or []
    if rates:
        P.append("<h3>Base rates</h3><p style='color:var(--muted)'>How companies in "
                 "this position have historically done. Every rate is sourced; rates "
                 "that could not be traced were dropped.</p><div class='tw'><table>"
                 "<tr><th>Rate</th><th>Figure</th><th>Population</th><th>Source</th>"
                 "<th>Caveat</th></tr>")
        for r in rates:
            P.append(f"<tr><td>{_e(r.get('statement'))}</td><td><b>{_e(r.get('value'))}"
                     f"</b></td><td>{_e(r.get('population'))}</td>"
                     f"<td>{_e(', '.join(r.get('source_ids') or []) or r.get('source'))}"
                     f"</td><td>{_e(r.get('caveat'))}</td></tr>")
        P.append("</table></div>")
    else:
        P.append("<p style='color:var(--muted)'><i>No base rates could be sourced for "
                 "this stage and category, so there is no denominator to read the "
                 "requirement against.</i></p>")

    for u in opp.get("unavailable") or []:
        P.append(f"<p style='color:var(--muted)'><i>{_e(u)}</i></p>")
    P.append(f"<div class='panel' style='border-left:4px solid var(--muted)'>"
             f"{_e(opp.get('disclaimer'))}</div>")
    return "".join(P)


def _references_html(result) -> str:
    reg = getattr(result, "registry", None)
    P = ['<h2 id="refs">References</h2>']
    if not reg or not reg.sources:
        backend = _e((result.stats or {}).get("research_backend", "none"))
        return ('<h2 id="refs">References</h2>' "<div class='panel'>No external sources were retrieved "
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
