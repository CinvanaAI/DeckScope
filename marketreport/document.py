"""The report as a document, not as terminal output.

The goal Von stated is *"output an S-1 report"*. A filed industry section is a
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
from typing import Any, List, Optional

from .questions import STANDING, Answer, AnswerSet
from .render import HEADINGS

__all__ = ["markdown", "as_html", "FORMATS", "render_as"]


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _today() -> str:
    return _dt.date.today().isoformat()


# ------------------------------------------------------------- markdown

def markdown(answers: AnswerSet, *, generated: Optional[str] = None) -> str:
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
        elif not answer.checkable:
            out.append("*Not independently checkable: there is no source to go "
                       "and read.*")
        out.append("")

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


def as_html(answers: AnswerSet, *, generated: Optional[str] = None) -> str:
    """A self-contained HTML document. No network, no scripts, prints to PDF."""
    coverage = answers.coverage()
    closure = answers.closure()
    out: List[str] = []

    out.append("<!doctype html><html lang=\"en\"><head>")
    out.append("<meta charset=\"utf-8\">")
    out.append("<meta name=\"viewport\" content=\"width=device-width,"
               "initial-scale=1\">")
    out.append(f"<title>Market report — {_e(answers.market)}</title>")
    out.append(f"<style>{_CSS}</style></head><body><div class=\"sheet\">")

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

    out.append("</div></body></html>")
    return "\n".join(out)


# --------------------------------------------------------------- dispatch

def _text(answers: AnswerSet, *, generated: Optional[str] = None) -> str:
    from .render import text

    return text(answers)


def _json(answers: AnswerSet, *, generated: Optional[str] = None) -> str:
    import json as _j

    from .render import summary

    return _j.dumps(summary(answers), indent=2, default=str)


#: Every format the report can be written as, by file extension. One table so
#: the CLI, the web app and the tests cannot disagree about what exists.
FORMATS = {
    "html": as_html,
    "md": markdown,
    "txt": _text,
    "json": _json,
}


def render_as(fmt: str, answers: AnswerSet, *,
              generated: Optional[str] = None) -> str:
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
    return writer(answers, generated=generated)


def infer_format(path: str, default: str = "txt") -> str:
    """The format implied by a filename, so `--save report.html` just works."""
    tail = (path or "").rsplit(".", 1)
    if len(tail) == 2 and tail[1].lower() in FORMATS:
        return tail[1].lower()
    return default
