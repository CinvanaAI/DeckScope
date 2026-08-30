"""The report as a document, not as terminal output.

The goal the client stated is *"output an S-1 report"*. A filed industry section is a
document people read, print, forward and argue with. Text in a terminal is the
developer's view of it, and shipping only that meant the deliverable did not
exist yet.

Four formats, one source. HTML and Markdown live here; text and JSON are
forwarded to `render`, so `FORMATS` is the single table every caller reads and
the CLI, the web app and the tests cannot disagree about what exists. All four
walk the same `AnswerSet` in the same order, so a fact that appears in one
appears in all of them or in none — a renderer that quietly drops a section is
how a report comes to look more complete than the run behind it.

**Provenance is visible, not available.** Every professional format this was
derived from states its operands and its source next to the number, not in an
appendix. So each figure here carries its sources inline, and three states are
visually distinct at a glance:

- a **sourced** figure, with the dataset named beneath it
- an **unchecked** figure — computed or supplied, no source to go and read
- a **demo** figure, in a warning block that replaces the source line rather
  than sitting beside it, because a made-up number that reaches the eye
  unlabelled has already done its damage — and because listing a "source" for
  a dataset that was never queried is the provenance badge over invented
  numbers all over again

**It prints.** The stylesheet has a `@media print` block that drops the
chrome, sets page margins and prevents sections breaking across pages, so
"save as PDF" from any browser produces the artifact. There is no PDF writer
here on purpose: adding one would mean a second layout to keep in step with
this one, and the browser already does it correctly.
"""
from __future__ import annotations

import datetime as _dt
import html
from typing import Any, Dict, List, Optional

from .panel import Panel
from .panel_render import PANEL_CSS, panel_html, panel_markdown, panel_text
from .questions import STANDING, Answer, AnswerSet
from .render import HEADINGS

__all__ = ["markdown", "as_html", "FORMATS", "render_as", "panel_document",
           "s1_document"]


def _panels(answers: AnswerSet, given: Optional[List[Panel]]) -> List[Panel]:
    """The panels to draw: what the caller passed, else what the run produced.

    An explicit list wins so a caller can render a subset. Falling back to the
    answer set's own is what stops a report whose Q5 was answered by a
    specialist being rendered with no chart in it.
    """
    if given is not None:
        return list(given)
    return list(getattr(answers, "panels", []) or [])


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _today() -> str:
    return _dt.date.today().isoformat()


# ------------------------------------------------------------- markdown

def markdown(answers: AnswerSet, *, generated: Optional[str] = None,
             panels: Optional[List[Panel]] = None) -> str:
    """The report as Markdown.

    Chosen over the terminal format for anything that will be pasted somewhere
    — an email, an issue, a document. It carries the same three provenance
    states as the HTML, in the plainest markers that survive a paste: a bold
    warning for demo, an italic note for unchecked.
    """
    coverage = answers.coverage()
    closure = answers.closure()
    out: List[str] = []

    out.append(f"# Market report — {answers.market}")
    out.append("")
    out.append(f"*Produced {generated or _today()} by DeckScope. "
               f"Every figure below states its own source, or says it has "
               f"none.*")
    out.append("")

    out.append("## How much of this report could be established")
    out.append("")
    if closure["complete"]:
        out.append(f"**Complete.** All {coverage['questions']} standing "
                   f"questions are answered, and every question they raise is "
                   f"answered too.")
    else:
        out.append(f"**Incomplete.** {coverage['answered']} of "
                   f"{coverage['questions']} standing questions answered. "
                   f"{closure['note']}")
    out.append("")
    if coverage.get("answered_from_demo"):
        out.append(f"> **{coverage['answered_from_demo']} of "
                   f"{coverage['answered']} answers come from recorded sample "
                   f"data, not live sources.** They are illustrative. None of "
                   f"them is independently checkable, and none should be "
                   f"quoted as a measurement.")
        out.append("")

    out.append("| | |")
    out.append("|---|---|")
    out.append(f"| Questions answered | {coverage['answered']} of "
               f"{coverage['questions']} |")
    out.append(f"| From live sources | {coverage.get('answered_live', 0)} |")
    out.append(f"| From recorded samples | "
               f"{coverage.get('answered_from_demo', 0)} |")
    out.append(f"| Independently checkable | {coverage['checkable']} |")
    out.append("")

    for question in STANDING:
        answer = answers.get(question.id)
        heading = HEADINGS.get(question.section, question.section.upper())
        out.append(f"## {heading}")
        out.append("")
        out.append(f"*{question.text}*")
        out.append("")

        if answer is None:
            out.append("Not attempted.")
            out.append("")
            continue
        if not answer.answered:
            out.append(f"**Not established.** {answer.unanswered_because}")
            out.append("")
            continue

        out.append(answer.statement)
        out.append("")
        for line in _detail_lines(question.section, answer):
            out.append(f"    {line}")
        if _detail_lines(question.section, answer):
            out.append("")

        if answer.demo:
            out.append("> **Illustrative figure from the offline demo — not a "
                       "measurement.** Run with a Census key for the real "
                       "value.")
        elif answer.source_ids:
            out.append("Sources: "
                       + ", ".join(dict.fromkeys(answer.source_ids)))
            for url in dict.fromkeys(getattr(answer, "source_urls", []) or []):
                out.append(f"  - exact request: <{url}>")
        elif not answer.checkable:
            out.append("*Not independently checkable: there is no source to go "
                       "and read.*")
        out.append("")

    for panel in _panels(answers, panels):
        out.append(panel_markdown(panel))

    return "\n".join(out).rstrip() + "\n"


def _detail_lines(section: str, answer: Answer) -> List[str]:
    """The section-specific detail, as flat lines.

    Deliberately shares its shape with `render._detail` rather than its code:
    that one emits terminal indentation, this one emits content. Sharing the
    function would mean one of the two formats getting the other's whitespace.
    """
    detail = answer.detail or {}
    out: List[str] = []

    if section == "size_bottom_up":
        out.extend(detail.get("arithmetic") or [])
        out.extend(f"! {p}" for p in (detail.get("problems") or []))
    elif section == "convergence":
        out.extend(detail.get("detail_lines") or [])
    elif section == "structure":
        conc = detail.get("concentration") or {}
        if conc.get("hhi") is not None:
            out.append(f"HHI {conc['hhi']:,.0f} · CR4 "
                       f"{(conc.get('cr4') or 0) * 100:.0f}% · "
                       f"{conc.get('firms', 0):,} establishments · "
                       f"{conc.get('basis', '')}")
        form = detail.get("shape") or {}
        if form.get("average_size") is not None:
            out.append(f"{form['average_size']:.1f} employees per "
                       f"establishment · largest tenth hold "
                       f"{(form.get('top_decile_share') or 0) * 100:.0f}% of "
                       f"employment")
    elif section == "barriers":
        out.extend(f"· {r}" for r in (detail.get("reasons") or []))
    elif section == "gaps":
        for hole in detail.get("unanswered") or []:
            out.append(f"[{hole['question']}] {hole['section']}: "
                       f"{hole['because']}")
        for item in detail.get("open_follow_ups") or []:
            out.append(f"? raised by {item['raised_by']} and unanswered: "
                       f"{item['question']}")
    return out


# ------------------------------------------------------------------ HTML

_CSS = """
:root{--ink:#111827;--muted:#6b7280;--line:#e5e7eb;--paper:#fff;
  --warn:#b45309;--warnbg:#fffbeb;--ok:#047857;--accent:#1d4ed8}
*{box-sizing:border-box}
body{margin:0;background:#f6f7f9;color:var(--ink);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,
  Arial,sans-serif}
.sheet{max-width:820px;margin:32px auto;background:var(--paper);padding:56px;
  border:1px solid var(--line);border-radius:6px}
h1{font-size:27px;margin:0 0 4px;line-height:1.25}
h2{font-size:13px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--muted);margin:0 0 14px;font-weight:700}
.stamp{color:var(--muted);font-size:13px;margin:0 0 28px}
section{border-top:1px solid var(--line);padding:26px 0;
  break-inside:avoid;page-break-inside:avoid}
.q{color:var(--muted);font-size:14px;font-style:italic;margin:0 0 12px}
.statement{margin:0 0 10px}
.figure{font-size:22px;font-weight:600;margin:0 0 6px}
.detail{background:#f9fafb;border:1px solid var(--line);border-radius:4px;
  padding:12px 14px;margin:12px 0;font:13px/1.7 ui-monospace,SFMono-Regular,
  Menlo,Consolas,monospace;white-space:pre-wrap;overflow-x:auto}
.src{font-size:13px;color:var(--muted);margin:8px 0 0}
.src b{color:var(--ok);font-weight:600}
.unchecked{font-size:13px;color:var(--muted);font-style:italic;margin:8px 0 0}
.demo{background:var(--warnbg);border-left:3px solid var(--warn);
  padding:10px 14px;margin:12px 0 0;font-size:13px;color:var(--warn)}
.missing{color:var(--warn)}
.banner{border:1px solid var(--line);border-left:3px solid var(--accent);
  padding:14px 18px;margin:0 0 22px;font-size:14px}
.banner.warn{border-left-color:var(--warn);background:var(--warnbg);
  color:var(--warn)}
table.cover{width:100%;border-collapse:collapse;margin:0 0 30px;font-size:14px}
table.cover td{padding:7px 0;border-bottom:1px solid var(--line)}
table.cover td:last-child{text-align:right;font-variant-numeric:tabular-nums;
  font-weight:600}
@media (prefers-color-scheme:dark){
  :root{--ink:#e5e7eb;--muted:#9ca3af;--line:#374151;--paper:#111827;
    --warnbg:#1f1a0e}
  body{background:#0b0f19}
  .detail{background:#0f1623}
}
@media print{
  body{background:#fff}
  .sheet{margin:0;padding:0;border:0;max-width:none}
  @page{margin:18mm}
}
"""


def panel_document(panels: List[Panel], *, title: str = "Market report",
                   generated: Optional[str] = None) -> str:
    """A set of panels as one document.

    This is what a request produces: the manager dispatches specialists, each
    returns a panel, and the panels are arranged. The market report's twelve
    sections are one arrangement of panels rather than a different kind of
    thing — which is the whole point of the client's question, that a market report
    which cannot produce the market-share report is not a market report.
    """
    answered = [p for p in panels if p.answered]
    out: List[str] = []
    out.append("<!doctype html><html lang=\"en\"><head>")
    out.append("<meta charset=\"utf-8\">")
    out.append("<meta name=\"viewport\" content=\"width=device-width,"
               "initial-scale=1\">")
    out.append(f"<title>{_e(title)}</title>")
    out.append(f"<style>{_CSS}{PANEL_CSS}</style></head><body>"
               f"<div class=\"sheet\">")
    out.append(f"<h1>{_e(title)}</h1>")
    out.append(f"<p class=\"stamp\">Produced {_e(generated or _today())} · "
               f"{len(answered)} of {len(panels)} questions answered · every "
               f"figure states its own source, or says it has none</p>")

    unanswered = [p for p in panels if not p.answered]
    if unanswered:
        out.append(f"<div class=\"banner warn\"><b>{len(unanswered)} of "
                   f"{len(panels)} questions could not be answered.</b> They "
                   f"are shown below with what stopped them, rather than "
                   f"omitted — a question that vanishes reads as one nobody "
                   f"asked.</div>")

    for panel in panels:
        out.append(panel_html(panel))

    out.append("</div></body></html>")
    return "\n".join(out)


def s1_document(report: Dict[str, Any], *,
                generated: Optional[str] = None) -> str:
    """The industry section as a document.

    Three things go on the page that a filing does not put there, and each is
    the reason to read this instead of one:

    **The coverage, at the top.** A filing does not tell you how much of itself
    it could establish. This one leads with it.

    **The stretches, named.** The constructions that expand a market without
    measuring the expansion. Filings write them and disclose them; this
    computes them and puts them where they cannot be skimmed past.

    **The upgrade slots**, only on sections that are actually thin — an offer
    where the public sources ran out, not an advert on a section that came back
    complete.
    """
    stats = report.get("coverage") or {}
    panels = report.get("panels") or []
    title = f"{report.get('market', 'Market')}"
    if report.get("place") and report["place"] != "not specified":
        title += f" in {report['place']}"

    out: List[str] = []
    out.append("<!doctype html><html lang=\"en\"><head>")
    out.append("<meta charset=\"utf-8\">")
    out.append("<meta name=\"viewport\" content=\"width=device-width,"
               "initial-scale=1\">")
    out.append(f"<title>{_e(title)} — industry report</title>")
    out.append(f"<style>{_CSS}{PANEL_CSS}</style></head><body>"
               f"<div class=\"sheet\">")
    out.append(f"<h1>{_e(title)}</h1>")
    out.append(f"<p class=\"stamp\">Industry section · produced "
               f"{_e(generated or _today())} · structured after the industry "
               f"sections of five filed S-1s</p>")

    out.append("<table class=\"cover\">")
    for label, value in (
            ("Sections established",
             f"{stats.get('answered', 0)} of {stats.get('sections', 0)}"),
            ("Figures that trace to a source",
             f"{stats.get('checkable', 0)} of {stats.get('figures', 0)}"),
            ("Definitional stretches found",
             len(report.get("stretches") or []))):
        out.append(f"<tr><td>{_e(label)}</td><td>{_e(value)}</td></tr>")
    out.append("</table>")

    if report.get("disclaimer"):
        out.append(f"<div class=\"banner\"><b>Industry and market data.</b> "
                   f"{_e(report['disclaimer'])}</div>")

    stretch = report.get("stretches") or []
    if stretch:
        out.append("<div class=\"banner warn\">")
        out.append(f"<b>{len(stretch)} definitional stretch(es).</b> These are "
                   f"the constructions that make a market bigger without "
                   f"measuring the expansion. A filing discloses them and "
                   f"lets the headline stand; they are listed here instead.")
        out.append("<ul>")
        for item in stretch:
            out.append(f"<li><b>{_e(item['section'])}</b> — "
                       f"&ldquo;{_e(item['phrase'])}&rdquo;: "
                       f"{_e(item['why'])}</li>")
        out.append("</ul></div>")

    for panel in panels:
        out.append(panel_html(panel))

    offers = [o for o in (report.get("upgrades") or [])
              if o.get("would_help") == "yes"]
    if offers:
        out.append("<div class=\"banner\">")
        out.append("<b>Where a paid source would sharpen this.</b> Everything "
                   "above is built from public sources and stands on its own. "
                   "These sections ran thin, and the firms named collect data "
                   "themselves — channel panels, retail point-of-sale, "
                   "commissioned surveys — rather than assembling public "
                   "figures the way this report does. If you have a "
                   "subscription, connecting it improves these specifically:")
        out.append("<ul>")
        for offer in offers:
            out.append(f"<li><b>{_e(offer['title'])}</b> — {_e(offer['what'])} "
                       f"<i>({_e(offer['sources'])})</i></li>")
        out.append("</ul></div>")

    out.append("</div></body></html>")
    return "\n".join(out)


def as_html(answers: AnswerSet, *, generated: Optional[str] = None,
            panels: Optional[List[Panel]] = None) -> str:
    """A self-contained HTML document. No network, no scripts, prints to PDF."""
    coverage = answers.coverage()
    closure = answers.closure()
    out: List[str] = []

    out.append("<!doctype html><html lang=\"en\"><head>")
    out.append("<meta charset=\"utf-8\">")
    out.append("<meta name=\"viewport\" content=\"width=device-width,"
               "initial-scale=1\">")
    out.append(f"<title>Market report — {_e(answers.market)}</title>")
    out.append(f"<style>{_CSS}{PANEL_CSS}</style></head><body>"
               f"<div class=\"sheet\">")

    out.append(f"<h1>{_e(answers.market)}</h1>")
    out.append(f"<p class=\"stamp\">Market report · produced "
               f"{_e(generated or _today())} · every figure below states its "
               f"own source, or says it has none</p>")

    if closure["complete"]:
        out.append(f"<div class=\"banner\">All {coverage['questions']} "
                   f"standing questions are answered, and every question they "
                   f"raise is answered too.</div>")
    else:
        out.append(f"<div class=\"banner warn\">"
                   f"<b>Incomplete.</b> {coverage['answered']} of "
                   f"{coverage['questions']} standing questions answered. "
                   f"{_e(closure['note'])}</div>")

    if coverage.get("answered_from_demo"):
        out.append(f"<div class=\"banner warn\"><b>"
                   f"{coverage['answered_from_demo']} of "
                   f"{coverage['answered']} answers come from recorded sample "
                   f"data, not live sources.</b> They are illustrative, none "
                   f"is independently checkable, and none should be quoted as "
                   f"a measurement.</div>")

    out.append("<table class=\"cover\">")
    for label, value in (
            ("Questions answered",
             f"{coverage['answered']} of {coverage['questions']}"),
            ("From live sources", coverage.get("answered_live", 0)),
            ("From recorded samples", coverage.get("answered_from_demo", 0)),
            ("Independently checkable", coverage["checkable"])):
        out.append(f"<tr><td>{_e(label)}</td><td>{_e(value)}</td></tr>")
    out.append("</table>")

    for question in STANDING:
        answer = answers.get(question.id)
        heading = HEADINGS.get(question.section, question.section.upper())
        out.append("<section>")
        out.append(f"<h2>{_e(heading)}</h2>")
        out.append(f"<p class=\"q\">{_e(question.text)}</p>")

        if answer is None:
            out.append("<p class=\"missing\">Not attempted.</p></section>")
            continue
        if not answer.answered:
            out.append(f"<p class=\"missing\"><b>Not established.</b> "
                       f"{_e(answer.unanswered_because)}</p></section>")
            continue

        if answer.value_text:
            out.append(f"<p class=\"figure\">{_e(answer.value_text)}</p>")
        out.append(f"<p class=\"statement\">{_e(answer.statement)}</p>")

        lines = _detail_lines(question.section, answer)
        if lines:
            out.append("<div class=\"detail\">"
                       + _e("\n".join(lines)) + "</div>")

        if answer.demo:
            out.append("<p class=\"demo\"><b>Illustrative figure from the "
                       "offline demo — not a measurement.</b> Run with a "
                       "Census key for the real value.</p>")
        elif answer.source_ids:
            named = ", ".join(dict.fromkeys(answer.source_ids))
            out.append(f"<p class=\"src\"><b>Sources:</b> {_e(named)}</p>")
        elif not answer.checkable:
            out.append("<p class=\"unchecked\">Not independently checkable: "
                       "there is no source to go and read.</p>")
        out.append("</section>")

    # Panels go after the standing sections. A section answered by a
    # specialist is a richer answer to a question the report already asks, so
    # it belongs in the same document rather than in a separate artifact.
    #
    # Defaulting to the answer set's own panels means a caller who ran with
    # `ask=` gets the charts without having to hand them over a second time —
    # and cannot accidentally render a report whose Q5 says "see the panel"
    # with no panel in the file.
    for panel in _panels(answers, panels):
        out.append(panel_html(panel))

    out.append("</div></body></html>")
    return "\n".join(out)


# --------------------------------------------------------------- dispatch

def _text(answers: AnswerSet, *, generated: Optional[str] = None,
          panels: Optional[List[Panel]] = None) -> str:
    from .render import text

    body = text(answers)
    for panel in _panels(answers, panels):
        body += "\n\n" + panel_text(panel)
    return body


def _json(answers: AnswerSet, *, generated: Optional[str] = None,
          panels: Optional[List[Panel]] = None) -> str:
    import json as _j

    from .render import summary

    payload = summary(answers)
    payload["panels"] = [p.to_dict() for p in _panels(answers, panels)]
    return _j.dumps(payload, indent=2, default=str)


#: Every format the report can be written as, by file extension. One table so
#: the CLI, the web app and the tests cannot disagree about what exists.
FORMATS = {
    "html": as_html,
    "md": markdown,
    "txt": _text,
    "json": _json,
}


def render_as(fmt: str, answers: AnswerSet, *,
              generated: Optional[str] = None,
              panels: Optional[List[Panel]] = None) -> str:
    """One report, in the named format. Raises `ValueError` on an unknown one.

    Raises rather than falling back to text: a caller who asked for `--format
    pdf` and silently received plain text has been given something that looks
    like it worked.
    """
    key = (fmt or "").strip().lower().lstrip(".")
    writer = FORMATS.get(key)
    if writer is None:
        raise ValueError(f"there is no '{fmt}' format; available: "
                         + ", ".join(sorted(FORMATS)))
    return writer(answers, generated=generated, panels=panels)


def infer_format(path: str, default: str = "txt") -> str:
    """The format implied by a filename, so `--save report.html` just works."""
    tail = (path or "").rsplit(".", 1)
    if len(tail) == 2 and tail[1].lower() in FORMATS:
        return tail[1].lower()
    return default
