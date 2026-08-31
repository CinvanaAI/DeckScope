"""Shared helpers and the colour themes every renderer draws from."""
from __future__ import annotations

import re
from typing import Any, Dict, List

THEMES: Dict[str, Dict[str, str]] = {
    "slate":   {"accent": "#2E5C8A", "ink": "#1A1D21", "muted": "#5C6570",
                 "bg": "#FFFFFF", "panel": "#F4F6F8", "line": "#DCE1E7",
                 "good": "#2E7D5B", "warn": "#B07A2B", "bad": "#B3402F"},
    "midnight": {"accent": "#7AA2F7", "ink": "#E6EAF2", "muted": "#9AA5B8",
                 "bg": "#12151C", "panel": "#1B202B", "line": "#2A3140",
                 "good": "#6FCF97", "warn": "#E0B25C", "bad": "#E57373"},
    "paper":   {"accent": "#8A5A2E", "ink": "#231F1B", "muted": "#6B6259",
                 "bg": "#FBF8F3", "panel": "#F2ECE2", "line": "#DFD6C7",
                 "good": "#4F7A3A", "warn": "#A8762A", "bad": "#9E3B2C"},
}


def theme(name: str) -> Dict[str, str]:
    return THEMES.get(name, THEMES["slate"])


def score_color(score: Any, t: Dict[str, str]) -> str:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return t["muted"]
    return t["good"] if s >= 7 else t["warn"] if s >= 5 else t["bad"]


ASSESSMENT_ICON = {
    "supported": "✓", "partially-supported": "~", "contradicted": "✗",
    "unverifiable": "?",
}

ASSESSMENT_WORD = {
    "supported": "Supported", "partially-supported": "Partly supported",
    "contradicted": "Contradicted", "unverifiable": "Unverifiable",
}

#: How hard a contested finding lands. Phrased as what the evidence does rather
#: than as a grade, so the reader is pointed at the evidence and not at a label.
SEVERITY_WORD = {
    "high": "contradicted by sourced evidence",
    "medium": "partly contradicted",
    "low": "disputed, but thinly evidenced",
}


#: A figure the summary check cares about: a dollar amount, a percentage, or
#: a multiple. Bare numbers are deliberately not matched — "a 2030 projection"
#: contains a year, not a figure, and flagging years would teach readers to
#: ignore the caveat.
_SUMMARY_FIGURE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:[BMKk]\b|billion|million|thousand)?"
    r"|\b\d[\d,]*(?:\.\d+)?\s*%"
    r"|\b\d+(?:\.\d+)?\s*[x×]\b")

_CITE_MARK = re.compile(r"\[S\d+\]")


def summary_unsourced_figures(summary: str, deck: Any, comp: Any) -> List[str]:
    """Figures in the summary that exist nowhere the reader can follow.

    The three marks (source ID, "no source", "could not be checked") bind
    every findings section — and stopped at the Summary, the most-read prose
    on the page, where a model can still assert "$12B" out of thin air. This
    closes that gap deterministically. A figure is covered if any of:

    - its sentence carries a citation mark ([S3]) — the reader can follow it;
    - it appears anywhere in the deck extraction — it is the deck's own
      number under discussion, attributed by context;
    - it appears in a claim-audit row that cites sources — it is the
      evidence's number.

    Anything else is the model's own assertion, and the caveat names it. The
    check only ever adds a caveat line — it never edits the prose, because a
    checker rewriting the text it checks is grading its own homework.
    """
    import json as _json

    if not summary:
        return []

    def norm(text: str) -> str:
        # "$2 million" and "$2M" are the same figure; a coverage check that
        # treats them as different flags honest prose, and a flagged honest
        # figure teaches readers to ignore the caveat.
        text = text.lower()
        for word, letter in (("billion", "b"), ("million", "m"),
                             ("thousand", "k")):
            text = re.sub(rf"\s*{word}", letter, text)
        return text

    deck_blob = norm(_json.dumps(deck or {}, ensure_ascii=False))
    cited_blob = norm(" ".join(
        f"{row.get('claim', '')} {row.get('market_evidence', '')} "
        f"{row.get('delta', '')}"
        for row in ((comp or {}).get("claim_audit") or [])
        if isinstance(row, dict) and row.get("source_ids")))

    naked: List[str] = []
    sentences = re.split(r"(?<=[.!?])\s+|\n+", summary)
    for sentence in sentences:
        if _CITE_MARK.search(sentence):
            continue
        for m in _SUMMARY_FIGURE.finditer(sentence):
            literal = m.group(0).strip()
            token = norm(literal).replace("$", "").replace(" ", "")
            if token and token not in deck_blob and token not in cited_blob:
                if literal not in naked:
                    naked.append(literal)
    return naked


def summary_caveat(summary: str, deck: Any, comp: Any) -> str:
    """The one-line caveat under the Summary heading, or ""."""
    naked = summary_unsourced_figures(summary, deck, comp)
    if not naked:
        return ""
    shown = ", ".join(naked[:6]) + ("…" if len(naked) > 6 else "")
    return (f"{len(naked)} figure(s) in this summary — {shown} — appear in "
            f"neither the deck nor any cited evidence. They are the model's "
            f"own assertions; treat them accordingly.")


def alignment_text(item: Any) -> str:
    """One alignment entry as a readable line, whatever shape it arrived in.

    `blind_spots` became objects so an omission can carry the evidence that
    established it. Every renderer iterating these lists would otherwise print a
    raw dict at the reader.
    """
    if isinstance(item, dict):
        text = str(item.get("what") or item.get("text") or "").strip()
        why = str(item.get("why_it_matters") or "").strip()
        cites = " ".join(f"[{s}]" for s in (item.get("source_ids") or []))
        return " — ".join(p for p in (text, why) if p) + (f" {cites}" if cites else "")
    return str(item)


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def txt(value: Any, dash: str = "—") -> str:
    if value is None or value == "" or value == []:
        return dash
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def safe_cell(v: Any) -> Any:
    """Spreadsheet formula-injection defense, shared by every xlsx/csv
    writer (seventh external audit: the batch table was fixed, the main
    workbook renderer still wrote raw cells). Deck names, company names,
    verdicts and error strings are attacker-reachable; a cell starting
    with = + - @ (or tab/CR) executes as a formula in Excel and in most
    CSV importers. A leading apostrophe renders it inert; non-strings
    pass through untouched."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


SAFE_URL_SCHEMES = ("http://", "https://", "mailto:")


def safe_url(value: Any) -> str:
    """Return a URL only if it is safe to put in an href, else "".

    HTML-escaping a `javascript:` URL does not make it safe — the escape protects
    the surrounding markup, not the navigation. Sources carrying such URLs are
    quarantined upstream, but renderers also read model-supplied URLs, so this is
    the second line: anything that is not plain http(s)/mailto is dropped and the
    link is rendered as inert text.
    """
    if not value:
        return ""
    url = str(value).strip().replace("\x00", "")
    if any(ch in url for ch in "\r\n\t"):
        return ""
    if url.lower().startswith(SAFE_URL_SCHEMES):
        return url
    return ""


def lens_title(lens: str) -> str:
    return {"investor": "Investor / diligence view",
            "founder": "Founder / self-critique view",
            "neutral": "Neutral analyst view"}.get(lens, lens.title())


def header_block(result, lens: str) -> Dict[str, str]:
    stats = result.stats or {}
    comp = result.comparisons.get(lens, {})
    meta = comp.get("_meta") or {}

    # A verdict needs something outside the deck underneath it. A run that
    # cited no external source still printed "LEAN NO · confidence: low" —
    # which is the deck being graded by a model's priors about decks, dressed
    # as a conclusion. Gated here, in the block every renderer builds from,
    # so no format can drift into printing one. Keyed on *cited*, not
    # *retrieved*: evidence the report never used cannot be what its verdict
    # rests on.
    verdict = (comp.get("verdict") or {}).get("call", "—")
    confidence = (comp.get("verdict") or {}).get("confidence", "—")
    verdict_note = ""
    cited = 0
    reg = getattr(result, "registry", None)
    if reg is not None:
        try:
            cited = int((reg.stats() or {}).get("cited", 0))
        except Exception:  # noqa: BLE001 - a broken registry reads as no evidence
            cited = 0
    if cited == 0 and verdict not in ("", "—"):
        verdict_note = (
            "No external source is cited anywhere in this run, so the reading "
            "the model formed is withheld: a verdict from the deck alone would "
            "be the deck grading itself. The findings above are what stands.")
        verdict, confidence = "No verdict", "withheld"

    return {
        "company": result.company,
        "lens": lens_title(lens),
        "verdict": verdict,
        "confidence": confidence,
        "verdict_note": verdict_note,
        # Still computed, because the panel ranks reports by it. It is no longer
        # printed at the top of a report: a weighted average of seven subjective
        # 1-10 scores, shown to three significant figures, is the one number here
        # that cannot be traced back to a source — and putting it above the fold
        # invited exactly the use this tool should not support, which is
        # thresholding decks by it.
        "score": str((meta.get("weighted_score") or {}).get("score", "—")),
        "headline": comp.get("headline") or "",
        "generated": stats.get("generated_at", ""),
        "model": f"{stats.get('provider', '?')} / {stats.get('model', '?')}",
        "research": f"{stats.get('research_backend', '?')} "
                    f"({stats.get('sources_found', 0)} sources)",
    }


def findings_for(result, lens: str):
    """The consolidated findings for a lens, shared by every renderer.

    Computed once here rather than per renderer, so markdown, HTML and DOCX
    cannot drift into telling the reader different things.
    """
    from ..findings import collect

    return collect(result.comparisons.get(lens, {}),
                   getattr(result, "registry", None))
