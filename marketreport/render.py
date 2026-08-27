"""The report, as a reader meets it.

A view over the answer set — nothing here computes anything, and nothing here
narrates. If a sentence in the output is not traceable to an `Answer`, it is a
bug in this file rather than a stylistic choice.

The order is deliberate and matches how the professional formats order theirs:
what this market is, then how big, then how it is shaped, then how hard it is to
get into. The one addition is at the end, and it is the section neither format
writes — what could not be established. It goes last because a reader should
finish knowing the limits of what they just read, and it goes in the document
rather than a footnote because somebody deciding something needs to know which
part of the answer is thin.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .questions import STANDING, Answer, AnswerSet

#: Section headings, in reading order. Keyed by section name so a renamed
#: question cannot silently lose its heading.
HEADINGS: Dict[str, str] = {
    "definition": "WHAT THIS MARKET IS",
    "size_top_down": "HOW BIG IT IS — FROM PUBLISHED AGGREGATES",
    "size_bottom_up": "HOW BIG IT IS — COUNTED FROM THE GROUND UP",
    "growth": "HOW FAST IT IS GROWING",
    "structure": "HOW CONCENTRATED IT IS",
    "competitors": "WHO COMPETES",
    "economics": "WHAT IT COSTS TO OPERATE",
    "regulation": "WHAT RULES APPLY",
    "barriers": "HOW HARD IT IS TO ENTER",
    "lifecycle": "WHERE IT IS IN ITS LIFE CYCLE",
    "gaps": "WHAT COULD NOT BE ESTABLISHED",
}

RULE = "=" * 74
THIN = "-" * 74


def text(answers: AnswerSet) -> str:
    """The whole report as plain text."""
    out: List[str] = []
    coverage = answers.coverage()
    closure = answers.closure()

    out.append(RULE)
    out.append(f"MARKET REPORT — {answers.market}")
    out.append(RULE)
    out.append("")

    # The completeness statement goes at the TOP, not buried at the end.
    # A reader deciding whether to rely on this needs it before they read it,
    # not after.
    if closure["complete"]:
        out.append(f"  All {coverage['questions']} standing questions answered.")
    else:
        out.append(f"  INCOMPLETE — {coverage['answered']} of "
                   f"{coverage['questions']} questions answered.")
        out.append(f"  {closure['note']}")
    out.append("")

    for question in STANDING:
        answer = answers.get(question.id)
        heading = HEADINGS.get(question.section, question.section.upper())
        out.append(THIN)
        out.append(f"{heading}   [{question.id}]")
        out.append(THIN)
        out.append(f"  Question: {question.text}")
        out.append("")

        if answer is None:
            out.append("  Not attempted.")
            out.append("")
            continue

        if not answer.answered:
            out.append(f"  NOT ESTABLISHED — {answer.unanswered_because}")
            out.append("")
            continue

        for line in _wrap(answer.statement):
            out.append(f"  {line}")
        out.extend(_detail(question.section, answer))

        if answer.source_ids:
            out.append("")
            out.append(f"  Sources: {', '.join(dict.fromkeys(answer.source_ids))}")
        if not answer.checkable:
            out.append("  NOTE: this answer is not independently checkable.")
        out.append("")

    return "\n".join(out)


def _detail(section: str, answer: Answer) -> List[str]:
    """Section-specific detail, rendered from the answer's own record."""
    out: List[str] = []
    detail = answer.detail or {}

    if section == "size_bottom_up":
        for line in detail.get("arithmetic") or []:
            out.append(f"    {line}")
        for problem in detail.get("problems") or []:
            out.append(f"    ! {problem}")

    elif section == "structure":
        conc = detail.get("concentration") or {}
        if conc.get("hhi") is not None:
            out.append(f"    HHI {conc['hhi']:,.0f}  ·  "
                       f"CR4 {(conc.get('cr4') or 0) * 100:.0f}%  ·  "
                       f"{conc.get('firms', 0):,} establishments  ·  "
                       f"{conc.get('basis', '')}")
        bands = detail.get("size_bands") or {}
        if bands:
            out.append("    By employee-size band:")
            for label, count in bands.items():
                out.append(f"      {label:>8}  {count:>8,}")

    elif section == "barriers":
        for reason in detail.get("reasons") or []:
            for line in _wrap(reason, width=68):
                out.append(f"    · {line}")

    elif section == "gaps":
        for hole in detail.get("unanswered") or []:
            out.append(f"    [{hole['question']}] {hole['section']}")
            for line in _wrap(hole["because"], width=66):
                out.append(f"        {line}")
        for item in detail.get("open_follow_ups") or []:
            out.append(f"    ? raised by {item['raised_by']} and unanswered: "
                       f"{item['question']}")

    return out


def _wrap(body: str, width: int = 72) -> List[str]:
    import textwrap
    return textwrap.wrap(body or "", width) or [""]


def summary(answers: AnswerSet) -> Dict[str, Any]:
    """A compact machine-readable view, for a UI or another program."""
    rows = []
    for question in STANDING:
        answer = answers.get(question.id)
        rows.append({
            "id": question.id,
            "section": question.section,
            "heading": HEADINGS.get(question.section, question.section),
            "question": question.text,
            "answered": bool(answer and answer.answered),
            "checkable": bool(answer and answer.checkable),
            "statement": (answer.statement if answer and answer.answered
                          else ""),
            "because": (answer.unanswered_because
                        if answer and not answer.answered else ""),
            "value_text": answer.value_text if answer else "",
        })
    return {
        "market": answers.market,
        "coverage": answers.coverage(),
        "closure": answers.closure(),
        "sections": rows,
    }
