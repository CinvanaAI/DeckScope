"""Word output — the format most people actually circulate."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

from .common import ASSESSMENT_WORD, as_list, header_block, txt


def _hex(color: str) -> Any:
    from docx.shared import RGBColor
    return RGBColor.from_string(color.lstrip("#").upper())


def render(result, out_dir: Path, base: str, theme: str = "slate", **kw: Any) -> List[str]:
    try:
        import docx
        from docx.shared import Pt
    except ImportError:
        raise RuntimeError("Word output needs python-docx: pip install python-docx") from None

    from .common import theme as get_theme
    t = get_theme(theme)
    paths = []

    for lens, comp in result.comparisons.items():
        doc = docx.Document()
        h = header_block(result, lens)

        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(10.5)

        # Title block
        p = doc.add_paragraph()
        r = p.add_run(h["lens"].upper())
        r.font.size, r.font.bold, r.font.color.rgb = Pt(8.5), True, _hex(t["muted"])
        doc.add_heading(f"{result.company} — Deck vs. Market Analysis", level=0)
        if h["headline"]:
            p = doc.add_paragraph()
            r = p.add_run(h["headline"])
            r.font.size, r.font.italic, r.font.color.rgb = Pt(12), True, _hex(t["accent"])

        tbl = doc.add_table(rows=0, cols=2)
        tbl.style = "Light Grid Accent 1"
        for k, v in (("Verdict", h["verdict"]), ("Confidence", h["confidence"]),
                     ("Weighted score", f"{h['score']} / 100"),
                     ("Security screen",
                      (result.security or {}).get("overall_risk", "not run").upper()),
                     ("Sources", h["research"]), ("Model", h["model"]),
                     ("Generated", h["generated"])):
            row = tbl.add_row().cells
            row[0].text, row[1].text = str(k), str(v)
            row[0].paragraphs[0].runs[0].font.bold = True

        # Summary
        doc.add_heading("Summary", level=1)
        for para in (comp.get("summary") or "").split("\n"):
            if para.strip():
                doc.add_paragraph(para.strip())
        if comp.get("integrity_note"):
            p = doc.add_paragraph()
            r = p.add_run(f"Integrity note. {comp['integrity_note']}")
            r.font.bold, r.font.color.rgb = True, _hex(t["bad"])

        # Scorecard
        rows = comp.get("scorecard") or []
        if rows:
            doc.add_heading("Scorecard", level=1)
            tb = doc.add_table(rows=1, cols=4)
            tb.style = "Light Grid Accent 1"
            for i, head in enumerate(("Dimension", "Score", "Weight", "Why")):
                cell = tb.rows[0].cells[i]
                cell.text = head
                cell.paragraphs[0].runs[0].font.bold = True
            for r_ in rows:
                c = tb.add_row().cells
                c[0].text = txt(r_.get("dimension"))
                c[1].text = f"{txt(r_.get('score'))}/10"
                c[2].text = txt(r_.get("weight"))
                c[3].text = txt(r_.get("rationale"))

        # Claim audit
        audit = comp.get("claim_audit") or []
        if audit:
            doc.add_heading("Claim-by-claim audit", level=1)
            for c in audit:
                doc.add_heading(f"{txt(c.get('id'))} · {txt(c.get('claim'))}", level=2)
                a = (c.get("assessment") or "").lower()
                p = doc.add_paragraph()
                r = p.add_run(ASSESSMENT_WORD.get(a, a or "—"))
                r.font.bold = True
                r.font.color.rgb = _hex(
                    {"supported": t["good"], "partially-supported": t["warn"],
                     "contradicted": t["bad"]}.get(a, t["muted"]))
                for label, key in (("Market evidence", "market_evidence"),
                                   ("Gap", "delta"), ("So what", "so_what"),
                                   ("Evidence quality", "evidence_quality")):
                    if c.get(key):
                        p = doc.add_paragraph()
                        p.add_run(f"{label}: ").bold = True
                        p.add_run(str(c[key]))
                cites = _cites(c, result)
                p = doc.add_paragraph()
                p.add_run("Sources: ").bold = True
                p.add_run(cites)

        # Alignment
        align = comp.get("alignment") or {}
        if any(align.values()):
            doc.add_heading("Alignment", level=1)
            for key, title in (("where_deck_matches_market", "Deck matches the market"),
                               ("where_deck_overstates", "Deck overstates"),
                               ("where_deck_understates", "Deck understates"),
                               ("blind_spots", "Blind spots")):
                items = as_list(align.get(key))
                if items:
                    doc.add_heading(title, level=2)
                    for i in items:
                        doc.add_paragraph(str(i), style="List Bullet")

        # Risks
        risks = comp.get("risks") or []
        if risks:
            doc.add_heading("Risks", level=1)
            tb = doc.add_table(rows=1, cols=4)
            tb.style = "Light Grid Accent 1"
            for i, head in enumerate(("Risk", "Severity", "Likelihood", "Test")):
                cell = tb.rows[0].cells[i]
                cell.text = head
                cell.paragraphs[0].runs[0].font.bold = True
            for r_ in risks:
                c = tb.add_row().cells
                c[0].text = txt(r_.get("risk"))
                c[1].text = txt(r_.get("severity"))
                c[2].text = txt(r_.get("likelihood"))
                c[3].text = txt(r_.get("mitigation_or_test"))

        # Questions and actions
        qs = as_list(comp.get("questions"))
        if qs:
            doc.add_heading("Questions this raises", level=1)
            for q in qs:
                doc.add_paragraph(str(q), style="List Bullet")
        acts = comp.get("actions") or []
        if acts:
            doc.add_heading("Recommended actions", level=1)
            for a in acts:
                doc.add_paragraph(
                    f"[{txt(a.get('priority'))}] {txt(a.get('action'))} — {txt(a.get('owner'))}",
                    style="List Bullet")

        # References — every source, cited or not
        doc.add_page_break()
        doc.add_heading("References", level=1)
        reg = getattr(result, "registry", None)
        if not reg or not reg.sources:
            doc.add_paragraph(
                "No external sources were retrieved for this analysis. Every statement "
                "above rests on the model's training knowledge and on the deck itself, "
                "and should be treated as unverified.")
        else:
            st = reg.stats()
            doc.add_paragraph(
                f"{st['total']} sources retrieved and screened: {st['cited']} cited, "
                f"{st['consulted_uncited']} consulted without being cited, "
                f"{st['quarantined']} dropped by the security screen. All are listed "
                f"below so that absence of evidence is as visible as its presence.")
            for group, title in ((reg.cited, "Cited in this analysis"),
                                 (reg.consulted, "Consulted, not cited"),
                                 (reg.quarantined, "Dropped by the security screen")):
                if not group:
                    continue
                doc.add_heading(title, level=2)
                for s in group:
                    p = doc.add_paragraph(style="List Number")
                    p.add_run(f"[{s.sid}] ").bold = True
                    p.add_run(s.title or s.url or "(untitled)")
                    if s.url:
                        r = p.add_run(f" — {s.url}")
                        r.font.size, r.font.color.rgb = Pt(8.5), _hex(t["muted"])
                    tail = " · ".join(x for x in (s.published, s.reliability,
                                                  "; ".join(s.cited_by[:3]), s.note) if x)
                    if tail:
                        r = p.add_run(f"\n{tail}")
                        r.font.size, r.font.color.rgb = Pt(8.5), _hex(t["muted"])

        # Security
        sec = result.security or {}
        if sec:
            doc.add_heading("Input integrity screen", level=1)
            p = doc.add_paragraph()
            r = p.add_run(f"Overall risk: {sec.get('overall_risk', 'clean').upper()} "
                          f"(mode: {sec.get('mode', 'balanced')})")
            r.font.bold = True
            if sec.get("overall_risk") == "clean":
                doc.add_paragraph(
                    "The deck and every web source were screened for content written to "
                    "influence the AI rather than inform a human reader. Nothing was found.")
            else:
                for key, title in (("deck", "Pitch deck"), ("web_sources", "Web sources")):
                    findings = (sec.get(key) or {}).get("findings") or []
                    if not findings:
                        continue
                    doc.add_heading(title, level=2)
                    for f in findings[:30]:
                        doc.add_paragraph(
                            f"[{f.get('severity')}] {f.get('where')} — {f.get('detail')} "
                            f"({f.get('action')})", style="List Bullet")

        p = doc.add_paragraph()
        r = p.add_run(f"Generated by DeckScope · "
                      f"{h['model']} · {h['research']}. AI-generated analysis: verify every "
                      f"figure before relying on it. Not investment advice.")
        r.font.size, r.font.italic, r.font.color.rgb = Pt(8), True, _hex(t["muted"])

        path = out_dir / f"{base}_{lens}.docx"
        doc.save(str(path))
        paths.append(str(path))
    return paths


def _cites(claim: Any, result) -> str:
    reg = getattr(result, "registry", None)
    parts, seen = [], set()
    for ref in list(as_list(claim.get("source_ids"))) + list(as_list(claim.get("sources"))):
        if not ref:
            continue
        s = reg.find(str(ref)) if reg else None
        if s and s.sid not in seen:
            seen.add(s.sid)
            parts.append(f"[{s.sid}] {s.url or s.title}")
        elif not s:
            parts.append(str(ref))
    return "; ".join(parts) if parts else "none cited — this assessment rests on no source"
