"""The question pack: the founder meeting's agenda, ready to carry in.

The report's most immediately usable output is not its verdict — it is the
list of questions the analysis earned. A partner walks into the meeting
with questions, not with a report; this renders them as that document.
Every question ships with the two things that make it land: WHY it is
being asked (the specific gap that generated it — a question with its
provenance cannot be brushed off as generic diligence theater), and what
a satisfying answer would contain (so whoever runs the meeting can grade
the response in the room rather than back at the desk).

Deterministic: assembled entirely from the finished comparison and the
findings layer. No model call, no new tokens — the report already paid
for everything here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

from ..findings import collect


def _grade_hint(question: str, comp: dict) -> str:
    """What a good answer looks like, derived from the question's own gap.

    Heuristic and honest about being one: where the question names figures,
    a good answer reconciles them; where it names an omission, a good
    answer is a direct account; otherwise the generic-but-true standard —
    specifics with numbers, not reassurance.
    """
    low = question.lower()
    if "%" in question or "$" in question:
        return ("A good answer reconciles the specific figures named above "
                "— with the arithmetic, not around it.")
    if any(w in low for w in ("omit", "not mention", "never mention",
                              "doesn't mention", "why is", "why does")):
        return ("A good answer engages the omission directly — 'we haven't "
                "seen them in deals' is an answer; changing the subject is "
                "also an answer, and a worse one.")
    if any(w in low for w in ("retention", "churn", "renew", "nrr")):
        return ("A good answer is a number with a cohort behind it. "
                "'Strong' is not a number.")
    if any(w in low for w in ("burn", "runway", "cash")):
        return "A good answer states the denominator: monthly burn and cash."
    return ("A good answer is specific: names, numbers, dates. Confidence "
            "without specifics is information too — about the answer.")


def build_question_pack(result: Any, lens: str) -> str:
    comp = result.comparisons.get(lens) or {}
    found = collect(comp, getattr(result, "registry", None))
    company = getattr(result, "company", "") or "the company"

    L: List[str] = []
    add = L.append
    add(f"# Question pack — {company}")
    add("")
    add(f"*Generated from the {lens} analysis. Each question names the gap "
        f"that produced it — none of these is generic diligence theater, "
        f"and each carries the standard its answer should meet.*")
    add("")

    n = 0
    for question in (comp.get("questions") or []):
        text = str(question or "").strip()
        if not text:
            continue
        n += 1
        add(f"## {n}. {text}")
        add("")
        add(f"*{_grade_hint(text, comp)}*")
        add("")

    # Unverified claims are questions by another name: each one is
    # something the founder can settle in the room that the research
    # could not settle from outside.
    unverified = [f for f in found.unverified]
    if unverified:
        add("## Claims only the founder can settle")
        add("")
        add("*Research found nothing either way on these — which makes them "
            "questions for the room, not marks against the company.*")
        add("")
        for f in unverified:
            n += 1
            add(f"**{n}.** Can you walk me through: {f.text.strip().rstrip('.')}?")
            add("")

    if n == 0:
        add("*(This analysis generated no open questions — which is itself "
            "unusual enough to be worth a question.)*")
        add("")

    add("---")
    add(f"*{n} question(s). Produced by DeckScope from the run's own audit; "
        f"no additional AI call was made to write this document.*")
    return "\n".join(L)


def render(result, out_dir: Path, base: str, **kw: Any) -> List[str]:
    paths = []
    for lens in result.comparisons:
        p = out_dir / f"{base}_{lens}_questions.md"
        p.write_text(build_question_pack(result, lens), encoding="utf-8")
        paths.append(str(p))
    return paths
