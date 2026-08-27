"""Drawing a panel — the chart the finding asked for.

`document.py` renders the market report's twelve sections in a fixed order.
This renders one panel in whatever form it chose, which is the difference the
whole exercise was about.

Two decisions worth stating.

**The chart is SVG, written here, with no library.** Chart.js would be less
code and would mean the artifact only renders where a CDN is reachable — and
`document.as_html` is tested for having no network dependency at all, because a
report that phones home stops working offline and leaks who read it and when. A
pie chart is two trigonometric functions; that is a fair price for a file that
works forever.

**Provenance is drawn, not footnoted.** Every wedge carries its state, and a
derived figure shows its arithmetic in the same block as the number. The failure
this prevents is specific and I committed it by hand: my own multiplications sat
in a column beside published figures in identical formatting, and nothing about
the rendering said which was which.
"""
from __future__ import annotations

import html
import math
from typing import Any, Dict, List

from .panel import ABSENT, DERIVED, ESTIMATED, SOURCED, Panel, Series

__all__ = ["panel_html", "panel_text", "panel_markdown", "PALETTE"]

#: One colour per entity, assigned by first appearance and reused across every
#: series in the panel. That reuse is the point: in a share pair the reader is
#: comparing Apple's wedge in one chart against Apple's wedge in the other, and
#: recolouring by rank would make the comparison impossible to see.
PALETTE = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
           "#008300", "#4a3aa7", "#e34948")
MUTED = "#898781"

#: How each provenance state is announced. Kept as one table so the HTML, the
#: Markdown and the terminal cannot drift into describing the same figure
#: differently.
STATE_LABEL = {
    SOURCED: ("sourced", "traceable to a source you can go and read"),
    DERIVED: ("computed", "calculated by us from other figures — the "
                          "arithmetic is shown"),
    ESTIMATED: ("estimated", "inferred rather than measured or computed"),
    ABSENT: ("not established", "asked for and not found"),
}


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _colours(panel: Panel) -> Dict[str, str]:
    """Entity to colour, stable across the panel's series."""
    mapping: Dict[str, str] = {}
    for series in panel.series:
        for wedge in series.slices:
            key = wedge.label.strip().lower()
            if key in mapping:
                continue
            if "else" in key or "other" in key:
                mapping[key] = MUTED
            else:
                mapping[key] = PALETTE[len(
                    [v for v in mapping.values() if v != MUTED]) % len(PALETTE)]
    return mapping


# ------------------------------------------------------------------- SVG

def _donut(series: Series, colours: Dict[str, str], size: int = 220) -> str:
    """A donut, drawn from arcs.

    Donut rather than pie because the hole gives the total somewhere to live,
    and because a reader comparing two of them side by side is judging arc
    length rather than area — which people do far better.

    A series that does not reach 100% gets its remainder drawn in a hatched
    "not broken out" arc rather than being silently scaled to fill the circle.
    Scaling would turn "the publisher only covers the top two" into "these two
    are the whole market", which is a lie the chart tells on its own.
    """
    radius, inner = size / 2 - 4, size / 2 - 4 - 34
    cx = cy = size / 2
    total = max(series.total, 100.0) if series.unit == "%" else series.total
    if total <= 0:
        return ""

    parts: List[str] = []
    angle = -math.pi / 2
    wedges = list(series.slices)
    if series.unit == "%" and series.unaccounted >= 1.0:
        wedges = wedges + [None]

    for wedge in wedges:
        value = series.unaccounted if wedge is None else wedge.value
        if value <= 0:
            continue
        sweep = 2 * math.pi * (value / total)
        end = angle + sweep
        large = 1 if sweep > math.pi else 0
        x1, y1 = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
        x2, y2 = cx + radius * math.cos(end), cy + radius * math.sin(end)
        x3, y3 = cx + inner * math.cos(end), cy + inner * math.sin(end)
        x4, y4 = cx + inner * math.cos(angle), cy + inner * math.sin(angle)
        if wedge is None:
            fill, title = "url(#gap)", (f"Not broken out by this source: "
                                        f"{series.unaccounted:.0f}%")
        else:
            fill = colours.get(wedge.label.strip().lower(), MUTED)
            title = f"{wedge.label}: {wedge.value:g}{series.unit}"
        parts.append(
            f'<path d="M {x1:.2f} {y1:.2f} A {radius:.2f} {radius:.2f} 0 '
            f'{large} 1 {x2:.2f} {y2:.2f} L {x3:.2f} {y3:.2f} A {inner:.2f} '
            f'{inner:.2f} 0 {large} 0 {x4:.2f} {y4:.2f} Z" fill="{fill}" '
            f'stroke="var(--paper)" stroke-width="2">'
            f'<title>{_e(title)}</title></path>')
        angle = end

    lead = max(series.slices, key=lambda s: s.value, default=None)
    centre = ""
    if lead is not None:
        centre = (
            f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" '
            f'class="donut-lead">{_e(lead.label)}</text>'
            f'<text x="{cx}" y="{cy + 16}" text-anchor="middle" '
            f'class="donut-val">{lead.value:g}{_e(series.unit)}</text>')

    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" '
            f'height="{size}" role="img" aria-label="'
            + _e(f"{series.label}: " + ", ".join(
                f"{w.label} {w.value:g}{series.unit}" for w in series.slices))
            + '"><defs><pattern id="gap" width="6" height="6" '
              'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
              '<rect width="6" height="6" fill="var(--surface)"/>'
              '<line x1="0" y1="0" x2="0" y2="6" stroke="var(--line)" '
              'stroke-width="2"/></pattern></defs>'
            + "".join(parts) + centre + "</svg>")


def _bars(series: Series, colours: Dict[str, str]) -> str:
    """Horizontal bars, for a ranking. Widths are proportional to the largest."""
    top = max((s.value for s in series.slices), default=0) or 1
    rows = []
    for wedge in sorted(series.slices, key=lambda s: -s.value):
        width = max(1.0, 100.0 * wedge.value / top)
        colour = colours.get(wedge.label.strip().lower(), MUTED)
        rows.append(
            f'<div class="bar-row"><span class="bar-label">'
            f'{_e(wedge.label)}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:'
            f'{width:.1f}%;background:{colour}"></span></span>'
            f'<span class="bar-value">{wedge.value:g}{_e(series.unit)}</span>'
            f'</div>')
    return f'<div class="bars">{"".join(rows)}</div>'


def _legend(series: Series, colours: Dict[str, str]) -> str:
    items = []
    for wedge in series.slices:
        colour = colours.get(wedge.label.strip().lower(), MUTED)
        mark = "" if wedge.state == SOURCED else (
            f' <span class="est">{_e(STATE_LABEL[wedge.state][0])}</span>')
        items.append(
            f'<span class="key"><i style="background:{colour}"></i>'
            f'{_e(wedge.label)} {wedge.value:g}{_e(series.unit)}{mark}</span>')
    if series.unit == "%" and series.unaccounted >= 1.0:
        items.append(
            f'<span class="key"><i class="hatch"></i>Not broken out '
            f'{series.unaccounted:.0f}%</span>')
    return f'<div class="legend">{"".join(items)}</div>'


def _chart(panel: Panel, series: Series, colours: Dict[str, str]) -> str:
    if panel.form == "ranking":
        body = _bars(series, colours)
    elif panel.form in ("share", "share_pair"):
        body = f'<div class="donut-wrap">{_donut(series, colours)}</div>'
    else:
        body = _bars(series, colours)
    return (f'<div class="chart"><p class="chart-title">{_e(series.label)}</p>'
            f'<p class="chart-sub">{_e(series.measure)}'
            + (f' · {_e(series.as_of)}' if series.as_of else "")
            + (f' · {_e(series.basis)}' if series.basis else "")
            + f'</p>{_legend(series, colours)}{body}</div>')


# ------------------------------------------------------------------ HTML

PANEL_CSS = """
.panel{border:1px solid var(--line);border-radius:6px;padding:24px 26px;
  margin:0 0 26px;background:var(--paper);break-inside:avoid;
  page-break-inside:avoid}
.panel h3{font-size:20px;margin:0 0 4px;line-height:1.3;font-weight:600}
.panel .asked{color:var(--muted);font-size:13px;margin:0 0 18px;font-style:italic}
.charts{display:flex;flex-wrap:wrap;gap:26px;margin:0 0 18px}
.chart{flex:1 1 260px;min-width:240px}
.chart-title{font-size:15px;font-weight:600;margin:0 0 2px}
.chart-sub{font-size:12px;color:var(--muted);margin:0 0 10px}
.donut-wrap{display:flex;justify-content:center}
.donut-lead{font-size:13px;fill:var(--muted)}
.donut-val{font-size:19px;font-weight:600;fill:var(--ink)}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin:0 0 12px;font-size:12px;
  color:var(--muted)}
.key{display:inline-flex;align-items:center;gap:5px}
.key i{width:10px;height:10px;border-radius:2px;display:inline-block}
.key i.hatch{background:repeating-linear-gradient(45deg,var(--line),
  var(--line) 2px,transparent 2px,transparent 5px);border:1px solid var(--line)}
.est{color:var(--warn);font-style:italic}
.bars{display:flex;flex-direction:column;gap:7px}
.bar-row{display:flex;align-items:center;gap:10px;font-size:13px}
.bar-label{flex:0 0 34%;text-align:right;color:var(--muted)}
.bar-track{flex:1;height:14px;background:var(--surface);border-radius:3px}
.bar-fill{display:block;height:100%;border-radius:3px}
.bar-value{flex:0 0 62px;font-variant-numeric:tabular-nums;font-weight:600}
.figs{border-top:1px solid var(--line);margin:18px 0 0;padding:16px 0 0;
  display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}
.fig{font-size:13px}
.fig .n{font-size:19px;font-weight:600;display:block;margin:0 0 2px}
.fig .l{color:var(--muted);display:block}
.fig .tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:3px;
  margin-top:5px}
.tag-sourced{background:var(--ok-bg);color:var(--ok)}
.tag-derived{background:var(--surface);color:var(--muted);
  border:1px solid var(--line)}
.tag-estimated{background:var(--warn-bg);color:var(--warn)}
.tag-absent{background:var(--warn-bg);color:var(--warn)}
.fig .how{display:block;color:var(--muted);font-size:11.5px;margin-top:4px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.caveats{border-top:1px solid var(--line);margin:18px 0 0;padding:14px 0 0}
.caveats p{font-size:13px;color:var(--muted);margin:0 0 7px;padding-left:16px;
  position:relative}
.caveats p:before{content:"—";position:absolute;left:0}
.panel .srcs{font-size:12px;color:var(--muted);margin:12px 0 0}
.panel .fail{background:var(--warn-bg);border-left:3px solid var(--warn);
  padding:12px 16px;color:var(--warn);font-size:14px}
"""


def panel_html(panel: Panel) -> str:
    """One panel, as a self-contained block. No scripts, no network."""
    colours = _colours(panel)
    out: List[str] = ['<div class="panel">']
    out.append(f"<h3>{_e(panel.headline or panel.question)}</h3>")
    out.append(f'<p class="asked">{_e(panel.question)}'
               + (f' · answered by the {_e(panel.agent)} agent'
                  if panel.agent else "") + "</p>")

    if panel.problem:
        out.append(f'<p class="fail"><b>Not established.</b> '
                   f'{_e(panel.problem)}</p></div>')
        return "\n".join(out)

    if panel.series:
        out.append('<div class="charts">')
        for series in panel.series:
            out.append(_chart(panel, series, colours))
        out.append("</div>")

    shown = [f for f in panel.figures if f.state != ABSENT]
    if shown:
        out.append('<div class="figs">')
        for figure in shown:
            label, _ = STATE_LABEL[figure.state]
            out.append('<div class="fig">')
            out.append(f'<span class="n">{_e(figure.value_text or "—")}</span>')
            out.append(f'<span class="l">{_e(figure.label)}</span>')
            out.append(f'<span class="tag tag-{figure.state}">{_e(label)}'
                       f'</span>')
            # The arithmetic sits with the number, not in an appendix. This is
            # the line whose absence let my own multiplications read as
            # published figures.
            if figure.state == DERIVED and figure.how:
                out.append(f'<span class="how">{_e(figure.how)}</span>')
            if figure.source_ids:
                out.append(f'<span class="how">'
                           f'{_e(", ".join(figure.source_ids))}</span>')
            out.append("</div>")
        out.append("</div>")

    missing = [f for f in panel.figures if f.state == ABSENT]
    if missing or panel.caveats:
        out.append('<div class="caveats">')
        for caveat in panel.caveats:
            out.append(f"<p>{_e(caveat)}</p>")
        for figure in missing:
            out.append(f'<p><b>Not established:</b> {_e(figure.label)} — '
                       f'{_e(figure.because)}</p>')
        out.append("</div>")

    if panel.source_labels:
        out.append(f'<p class="srcs"><b>Sources:</b> '
                   f'{_e(" · ".join(panel.source_labels))}</p>')
    out.append("</div>")
    return "\n".join(out)


# ---------------------------------------------------------------- text

def panel_text(panel: Panel, width: int = 74) -> str:
    """The terminal view. Same content, same order, no chart."""
    import textwrap

    out: List[str] = ["=" * width]
    out.append(panel.headline or panel.question)
    out.append("=" * width)
    out.append(f"  Asked: {panel.question}")
    if panel.agent:
        out.append(f"  Answered by: {panel.agent}")
    out.append("")

    if panel.problem:
        out.extend(f"  NOT ESTABLISHED — {line}"
                   for line in textwrap.wrap(panel.problem, width - 22))
        return "\n".join(out)

    for series in panel.series:
        head = f"  {series.label} — {series.measure}"
        if series.as_of:
            head += f", {series.as_of}"
        if series.basis:
            head += f"  [{series.basis}]"
        out.append(head)
        top = max((s.value for s in series.slices), default=0) or 1
        for wedge in sorted(series.slices, key=lambda s: -s.value):
            bar = "#" * max(1, int(28 * wedge.value / top))
            mark = "" if wedge.state == SOURCED else f" ({wedge.state})"
            out.append(f"    {wedge.label[:18]:<18} {wedge.value:>6g}"
                       f"{series.unit:<2} {bar}{mark}")
        if series.unit == "%" and series.unaccounted >= 1.0:
            out.append(f"    {'not broken out':<18} "
                       f"{series.unaccounted:>6.0f}%")
        out.append("")

    shown = [f for f in panel.figures if f.state != ABSENT]
    if shown:
        out.append("  " + "-" * (width - 4))
        for figure in shown:
            out.append(f"  {figure.label[:44]:<44} "
                       f"{figure.value_text or '—':>14}  [{figure.state}]")
            if figure.state == DERIVED and figure.how:
                out.append(f"      = {figure.how}")
            if figure.source_ids:
                out.append(f"      sources: {', '.join(figure.source_ids)}")
        out.append("")

    missing = [f for f in panel.figures if f.state == ABSENT]
    if panel.caveats or missing:
        out.append("  WHAT TO KNOW READING THIS")
        for caveat in panel.caveats:
            for i, line in enumerate(textwrap.wrap(caveat, width - 8)):
                out.append(("    - " if i == 0 else "      ") + line)
        for figure in missing:
            out.append(f"    - not established: {figure.label[:52]}")
            for line in textwrap.wrap(figure.because, width - 10):
                out.append(f"      {line}")
        out.append("")

    coverage = panel.coverage()
    out.append(f"  {coverage['checkable']} of {coverage['figures']} figures "
               f"are independently checkable "
               f"({coverage['derived']} computed here, "
               f"{coverage['absent']} not established).")
    return "\n".join(out)


def panel_markdown(panel: Panel) -> str:
    """For pasting into an email or an issue."""
    out: List[str] = [f"## {panel.headline or panel.question}", "",
                      f"*{panel.question}*", ""]
    if panel.problem:
        out.append(f"**Not established.** {panel.problem}")
        return "\n".join(out) + "\n"

    for series in panel.series:
        out.append(f"**{series.label}** — {series.measure}"
                   + (f", {series.as_of}" if series.as_of else "")
                   + (f" ({series.basis})" if series.basis else ""))
        out.append("")
        out.append("| | |")
        out.append("|---|---|")
        for wedge in sorted(series.slices, key=lambda s: -s.value):
            mark = "" if wedge.state == SOURCED else f" *({wedge.state})*"
            out.append(f"| {wedge.label} | {wedge.value:g}{series.unit}"
                       f"{mark} |")
        if series.unit == "%" and series.unaccounted >= 1.0:
            out.append(f"| *not broken out* | {series.unaccounted:.0f}% |")
        out.append("")

    shown = [f for f in panel.figures if f.state != ABSENT]
    if shown:
        out.append("| Figure | Value | How we have it |")
        out.append("|---|---|---|")
        for figure in shown:
            how = figure.how or ", ".join(figure.source_ids) or "—"
            out.append(f"| {figure.label} | {figure.value_text or '—'} | "
                       f"{STATE_LABEL[figure.state][0]}: {how} |")
        out.append("")

    missing = [f for f in panel.figures if f.state == ABSENT]
    if panel.caveats or missing:
        out.append("**What to know reading this**")
        out.append("")
        for caveat in panel.caveats:
            out.append(f"- {caveat}")
        for figure in missing:
            out.append(f"- Not established: {figure.label} — {figure.because}")
        out.append("")
    if panel.source_labels:
        out.append("Sources: " + " · ".join(panel.source_labels))
    return "\n".join(out).rstrip() + "\n"
