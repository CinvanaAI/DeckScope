"""Shared helpers and the colour themes every renderer draws from."""
from __future__ import annotations

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
    return {
        "company": result.company,
        "lens": lens_title(lens),
        "verdict": (comp.get("verdict") or {}).get("call", "—"),
        "confidence": (comp.get("verdict") or {}).get("confidence", "—"),
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
