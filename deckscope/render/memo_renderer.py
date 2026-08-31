"""The IC memo: one page, the way deal memos actually circulate.

Investors do not forward forty-section reports; they forward a memo — the
verdict, the three claims that decide it, what the deck never says, the
read, and the questions. Everything here is lifted from the finished,
audited comparison: the memo is the report's front page, not a second
opinion, and it inherits every honesty rule the report earned — a
zero-evidence run withholds its verdict here exactly as it does there,
demo figures stay labelled, and unverifiable stays unverifiable.

Deterministic. No model call writes this document.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

from .common import ASSESSMENT_WORD, header_block
from ..findings import collect

#: Materiality sort: what kills the thesis outranks what dents it.
_MATERIALITY_RANK = {"fatal": 0, "damaging": 1, "cosmetic": 2}


def _decisive_claims(comp: dict, limit: int = 3) -> List[dict]:
    """The rows that decide the memo: contested first, worst materiality
    first, cited before uncited — the ordering a partner applies by hand."""
    rows = [r for r in (comp.get("claim_audit") or []) if isinstance(r, dict)]

    def key(r):
        contested = 0 if str(r.get("assessment", "")).lower() in (
            "contradicted", "partially-supported") else 1
        mat = _MATERIALITY_RANK.get(str(r.get("materiality", "")).lower(), 3)
        cited = 0 if r.get("source_ids") else 1
        return (contested, mat, cited)

    return sorted(rows, key=key)[:limit]


def build_memo(result: Any, lens: str) -> str:
    comp = result.comparisons.get(lens) or {}
    found = collect(comp, getattr(result, "registry", None))
    h = header_block(result, lens)
    company = getattr(result, "company", "") or "the company"

    L: List[str] = []
    add = L.append
    add(f"# Deal memo — {company}")
    add("")
    add(f"**Call:** {h.get('verdict') or '—'}"
        + (f" · {h.get('confidence')}" if h.get("confidence") else ""))
    if h.get("verdict_note"):
        add("")
        add(f"*{h['verdict_note']}*")
    add("")
    add(f"> {found.headline}")
    add("")
    add(f"*{found.evidence_state}*")
    add("")

    decisive = _decisive_claims(comp)
    if decisive:
        add("## The claims that decide it")
        add("")
        for r in decisive:
            word = ASSESSMENT_WORD.get(r.get("assessment", ""),
                                       r.get("assessment", ""))
            line = f"- **{r.get('claim', '')}** — {word}"
            if r.get("delta"):
                line += f". {r['delta']}"
            ids = " ".join(f"[{s}]" for s in (r.get("source_ids") or []))
            if ids:
                line += f" {ids}"
            elif str(r.get("assessment", "")).lower() in (
                    "contradicted", "partially-supported"):
                line += " *(no source — a reading, not a finding)*"
            add(line)
            for rep in (r.get("checked_by_reports") or [])[:1]:
                rep_ids = " ".join(f"[{s}]"
                                   for s in (rep.get("source_ids") or []))
                add(f"  - independently checked by the "
                    f"{rep.get('specialist')} report: "
                    f"{rep.get('finding')} {rep_ids}".rstrip())
        add("")

    blind = [b for b in ((comp.get("alignment") or {}).get("blind_spots")
                         or []) if isinstance(b, dict)][:2]
    if blind:
        add("## What the deck never says")
        add("")
        for b in blind:
            note = ("" if b.get("source_ids") else
                    " *(no source — the analysis asserts this)*")
            add(f"- {b.get('what', '')} — {b.get('why_it_matters', '')}{note}")
        add("")

    if (comp.get("advisor_read") or "").strip():
        add("## The advisor's read *(judgment, not evidence)*")
        add("")
        # First paragraph only: the memo is one page; the full read lives
        # in the report.
        first = comp["advisor_read"].strip().split("\n\n")[0]
        add(first)
        add("")

    questions = [str(q).strip() for q in (comp.get("questions") or [])
                 if str(q).strip()][:5]
    if questions:
        add("## Ask before the next meeting")
        add("")
        for i, q in enumerate(questions, 1):
            add(f"{i}. {q}")
        add("")

    add("---")
    add("*One-page memo generated from the audited report — the full "
        "claim-by-claim audit, sources, and reconciliation are in the "
        "report itself. AI-generated analysis, not investment advice.*")
    return "\n".join(L)


def render(result, out_dir: Path, base: str, **kw: Any) -> List[str]:
    paths = []
    for lens in result.comparisons:
        p = out_dir / f"{base}_{lens}_memo.md"
        p.write_text(build_memo(result, lens), encoding="utf-8")
        paths.append(str(p))
    return paths
