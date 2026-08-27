"""PDF output.

Prefers a real browser/converter when one is present (best typography, since it
reuses the HTML report), and falls back to a self-contained ReportLab layout that
needs nothing installed beyond reportlab.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, List

from .common import findings_for, ASSESSMENT_WORD, as_list, header_block, theme as get_theme

from ..console import out as _out


def render(result, out_dir: Path, base: str, theme: str = "slate", **kw: Any) -> List[str]:
    paths = []
    for lens in result.comparisons:
        target = out_dir / f"{base}_{lens}.pdf"
        if _via_html(result, lens, target, theme) or _via_reportlab(result, lens, target, theme):
            paths.append(str(target))
        else:
            raise RuntimeError(
                "PDF output needs either reportlab (pip install reportlab), "
                "weasyprint, or a Chrome/Edge install for HTML-to-PDF conversion.")
    return paths


def _via_html(result, lens: str, target: Path, theme: str) -> bool:
    """Render the HTML report through weasyprint or headless Chrome if available."""
    from .html_renderer import build_html

    html = build_html(result, lens, theme)
    try:
        from weasyprint import HTML  # type: ignore

        HTML(string=html).write_pdf(str(target))
        return True
    except Exception:  # noqa: BLE001
        pass

    chrome = _find_chrome()
    if not chrome:
        return False
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "report.html"
        src.write_text(html, encoding="utf-8")
        # Sandboxed first. The browser sandbox is a real mitigation and
        # disabling it by default traded it away for convenience — the HTML we
        # render is our own and escaped, so this is not a demonstrated exploit,
        # but "our input is probably fine" is exactly the reasoning that ages
        # badly. `--no-sandbox` is now a fallback, used only when the sandboxed
        # attempt actually fails, which is the case inside containers and some
        # CI images where the kernel namespaces are unavailable.
        base = [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer"]
        attempts = [base, base + ["--no-sandbox"]]
        for index, argv in enumerate(attempts):
            try:
                subprocess.run(
                    argv + [f"--print-to-pdf={target}", src.as_uri()],
                    capture_output=True, timeout=120, check=True)
                if target.exists():
                    if index:
                        _out("  PDF rendered with the browser sandbox disabled — "
                             "the sandboxed attempt failed, which is normal "
                             "inside a container.")
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False


def _find_chrome() -> str | None:
    for name in ("google-chrome", "chromium", "chromium-browser", "msedge", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if Path(p).exists():
            return p
    return None


def _via_reportlab(result, lens: str, target: Path, theme: str) -> bool:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (KeepTogether, PageBreak, Paragraph,
                                        SimpleDocTemplate, Spacer, Table, TableStyle)
    except ImportError:
        return False

    import html as _h

    t = get_theme(theme)
    comp = result.comparisons.get(lens, {})
    h = header_block(result, lens)
    ink = colors.HexColor(t["ink"])
    muted = colors.HexColor(t["muted"])
    accent = colors.HexColor(t["accent"])
    line = colors.HexColor(t["line"])

    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica",
                          fontSize=9.5, leading=13.5, textColor=ink, alignment=TA_LEFT)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10.5, textColor=muted)
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                        fontSize=17, leading=21, textColor=ink, spaceBefore=16, spaceAfter=7)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                        fontSize=11.5, leading=15, textColor=accent,
                        spaceBefore=11, spaceAfter=4)
    title = ParagraphStyle("title", parent=h1, fontSize=23, leading=27, spaceAfter=3)

    def esc(v: Any) -> str:
        return _h.escape(str(v if v not in (None, "") else "—"))

    story: List[Any] = []
    story.append(Paragraph(esc(h["lens"]).upper(), small))
    story.append(Paragraph(esc(result.company), title))
    story.append(Paragraph("Pitch deck claims measured against market evidence", small))
    story.append(Spacer(1, 12))
    # Same hierarchy as every other format: findings first, verdict demoted, no
    # composite score. This still led with the model's headline, a verdict and
    # "45.7 / 100" — so the product meant something different depending on which
    # export button the reader pressed. See deckscope/findings.py.
    found = findings_for(result, lens)
    story.append(Paragraph(f"<b>{esc(found.headline)}</b>",
                           ParagraphStyle("hl", parent=body, fontSize=11.5,
                                          leading=16, textColor=accent)))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<i>{esc(found.evidence_state)}</i>", small))
    story.append(Spacer(1, 10))

    def table(data, widths, header=True, font=8.5):
        tb = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                 ("FONTSIZE", (0, 0), (-1, -1), font),
                 ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                 ("GRID", (0, 0), (-1, -1), 0.4, line),
                 ("TOPPADDING", (0, 0), (-1, -1), 4),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), accent),
                      ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                      ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        tb.setStyle(TableStyle(style))
        return tb

    story.append(table(
        [["Claims examined", str(found.counts.get("claims_examined", 0))],
         ["Contested", str(found.counts.get("contested", 0))],
         ["Omissions", str(found.counts.get("omissions", 0))],
         ["Could not be checked", str(found.counts.get("unverified", 0))],
         ["Security screen", esc((result.security or {}).get("overall_risk", "n/a")).upper()],
         ["Research", esc(h["research"])], ["Model", esc(h["model"])],
         ["Generated", esc(h["generated"])]],
        [1.6 * inch, 5.0 * inch], header=False))

    def _findings_section(heading: str, items, lede: str, unsourced_note: str = ""):
        if not items:
            return
        story.append(Paragraph(heading, h1))
        story.append(Paragraph(esc(lede), small))
        story.append(Spacer(1, 6))
        for f in items:
            cites = (" ".join(f"[{s}]" for s in f.source_ids) if f.source_ids
                     else unsourced_note)
            detail = esc(f.delta or f.why or "")
            story.append(Paragraph(
                f"<b>{esc(f.text)}</b> {esc(cites)}<br/>{detail}", body))
            story.append(Spacer(1, 5))

    _findings_section(
        "What the evidence contests", found.contested,
        "Claims the deck makes that retrieved evidence pushes back on.",
        "(no source — a reading, not a finding)")
    _findings_section(
        "What the deck leaves out", found.omissions,
        "Present in the market evidence, absent from the deck.",
        "(no source)")
    _findings_section(
        "What could not be checked", found.unverified,
        "Neither confirmed nor refuted. Research tasks, not marks against the "
        "company.")

    if found.next_steps:
        story.append(Paragraph("What to do next", h1))
        for i, step in enumerate(found.next_steps, 1):
            story.append(Paragraph(f"{i}. {esc(step)}", body))
            story.append(Spacer(1, 4))

    story.append(Paragraph("Summary", h1))
    for para in (comp.get("summary") or "").split("\n"):
        if para.strip():
            story.append(Paragraph(esc(para.strip()), body))
            story.append(Spacer(1, 6))
    if comp.get("integrity_note"):
        story.append(Paragraph(f"<b>Integrity note.</b> {esc(comp['integrity_note'])}", body))

    story.append(Paragraph("What this adds up to, for this lens", h1))
    story.append(Paragraph(
        f"<b>{esc(h['verdict'])}</b> · confidence: {esc(h['confidence'])}", body))
    story.append(Paragraph(
        "A verdict is one reader's reading of the findings above, through one "
        "lens. The findings are the durable part; this line is not.", small))
    story.append(Spacer(1, 8))

    rows = comp.get("scorecard") or []
    if rows:
        story.append(Paragraph("Scorecard", h1))
        data = [["Dimension", "Score", "Wt", "Why"]] + [
            [Paragraph(esc(r.get("dimension")), body), esc(r.get("score")),
             esc(r.get("weight")), Paragraph(esc(r.get("rationale")), body)]
            for r in rows]
        story.append(table(data, [1.5 * inch, 0.5 * inch, 0.4 * inch, 4.2 * inch]))

    audit = comp.get("claim_audit") or []
    if audit:
        story.append(Paragraph("Claim-by-claim audit", h1))
        for c in audit:
            a = (c.get("assessment") or "").lower()
            block = [Paragraph(f"{esc(c.get('id'))} · {esc(c.get('claim'))}", h2),
                     Paragraph(f"<b>{esc(ASSESSMENT_WORD.get(a, a))}</b>", body),
                     Paragraph(f"<b>Market evidence:</b> {esc(c.get('market_evidence'))}", body)]
            if c.get("delta"):
                block.append(Paragraph(f"<b>Gap:</b> {esc(c['delta'])}", body))
            if c.get("so_what"):
                block.append(Paragraph(f"<b>So what:</b> {esc(c['so_what'])}", body))
            cites = ", ".join(str(x) for x in as_list(c.get("source_ids")))
            block.append(Paragraph(f"Sources: {esc(cites) if cites else 'none cited'}", small))
            block.append(Spacer(1, 7))
            story.append(KeepTogether(block))

    risks = comp.get("risks") or []
    if risks:
        story.append(Paragraph("Risks", h1))
        data = [["Risk", "Sev", "Lik", "Test or mitigation"]] + [
            [Paragraph(esc(r.get("risk")), body), esc(r.get("severity")),
             esc(r.get("likelihood")),
             Paragraph(esc(r.get("mitigation_or_test")), body)] for r in risks]
        story.append(table(data, [2.4 * inch, 0.6 * inch, 0.6 * inch, 3.0 * inch]))

    # References — the complete bibliography
    story.append(PageBreak())
    story.append(Paragraph("References", h1))
    reg = getattr(result, "registry", None)
    if not reg or not reg.sources:
        story.append(Paragraph(
            "No external sources were retrieved for this analysis. Every statement above "
            "rests on the model's training knowledge and on the deck itself, and should "
            "be treated as unverified.", body))
    else:
        st = reg.stats()
        story.append(Paragraph(
            f"{st['total']} sources retrieved and screened: {st['cited']} cited, "
            f"{st['consulted_uncited']} consulted without being cited, "
            f"{st['quarantined']} dropped by the security screen. All are listed below.",
            small))
        story.append(Spacer(1, 8))
        for group, gt in ((reg.cited, "Cited in this analysis"),
                          (reg.consulted, "Consulted, not cited"),
                          (reg.quarantined, "Dropped by the security screen")):
            if not group:
                continue
            story.append(Paragraph(gt, h2))
            data = [["ID", "Source", "Date", "Reliability"]] + [
                [s.sid,
                 Paragraph(f"{esc(s.title or s.url)}<br/><font size=7 color='#777'>"
                           f"{esc(s.url)}</font>"
                           + (f"<br/><font size=7 color='#777'>{esc(s.note)}</font>"
                              if s.note else ""), body),
                 esc(s.published), esc(s.reliability)] for s in group]
            story.append(table(data, [0.45 * inch, 4.5 * inch, 0.8 * inch, 0.85 * inch]))
            story.append(Spacer(1, 8))

    sec = result.security or {}
    if sec:
        story.append(Paragraph("Input integrity screen", h1))
        story.append(Paragraph(
            f"<b>Overall risk: {esc(sec.get('overall_risk', 'clean')).upper()}</b> "
            f"(mode: {esc(sec.get('mode', 'balanced'))})", body))
        if sec.get("overall_risk") == "clean":
            story.append(Paragraph(
                "The pitch deck and every web source were screened for content written to "
                "influence the AI rather than inform a human reader — hidden text, "
                "invisible characters, fake system messages, instructions to change the "
                "verdict. Nothing was found.", body))
        else:
            for key, gt in (("deck", "Pitch deck"), ("web_sources", "Web sources")):
                findings = (sec.get(key) or {}).get("findings") or []
                if not findings:
                    continue
                story.append(Paragraph(gt, h2))
                data = [["Severity", "Where", "Finding", "Action"]] + [
                    [esc(f.get("severity")), Paragraph(esc(f.get("where")), body),
                     Paragraph(esc(f.get("detail")), body), esc(f.get("action"))]
                    for f in findings[:35]]
                story.append(table(data, [0.7 * inch, 1.1 * inch, 3.9 * inch, 0.9 * inch]))
                story.append(Spacer(1, 8))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        f"Generated by DeckScope · "
        f"{esc(h['model'])} · {esc(h['research'])}. AI-generated analysis: verify every "
        f"figure against the cited source before relying on it. Not investment advice.",
        small))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(0.75 * inch, 0.5 * inch,
                          f"{result.company} — deck vs. market · {lens}")
        canvas.drawRightString(LETTER[0] - 0.75 * inch, 0.5 * inch, f"{doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(target), pagesize=LETTER,
                      leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                      topMargin=0.7 * inch, bottomMargin=0.75 * inch,
                      title=f"{result.company} — deck vs. market ({lens})",
                      author="DeckScope").build(story, onFirstPage=footer,
                                                onLaterPages=footer)
    return target.exists()
