"""`deckscope diff old.pdf new.pdf` — what changed between two versions of
the same deck, told claim by claim.

The use case is the second meeting: the founder sends a revised deck, and
the question is not "is this deck good" (run the pipeline for that) but
"what moved since last time" — which figures changed, which claims quietly
disappeared, what is newly asserted. Funds do this today by eyeballing two
PDFs side by side.

The model is used for exactly one thing per deck: claim extraction, via
the same DeckAnalyst the pipeline uses, under the same security screen and
NDA gate. The diff itself is deterministic — pairing, figure comparison,
and rendering are code, so the same two decks always produce the same
diff. A model that extracts a claim differently across versions can still
produce a spurious add/drop pair; the diff says so in its header rather
than pretending extraction is deterministic.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..research.findings import parse_number

#: Pairing threshold: below this token overlap two claims are different
#: claims, not two versions of one. Chosen loose — a rewritten sentence
#: keeps its nouns and figures even when every verb changes.
PAIR_THRESHOLD = 0.30

_STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "and", "or", "is",
         "are", "was", "were", "our", "we", "for", "with", "by", "per",
         "from", "that", "this", "its", "it"}


def _tokens(text: str) -> set:
    words = re.findall(r"[a-z0-9$%.]+", str(text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOP} | \
           {w for w in words if any(ch.isdigit() for ch in w)}


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _figure(claim: Dict[str, Any]) -> Optional[float]:
    return parse_number(claim.get("value_text") or "") \
        if claim.get("value_text") else parse_number(claim.get("text") or "")


def pair_claims(old: List[Dict[str, Any]], new: List[Dict[str, Any]]
                ) -> Tuple[List[Tuple[dict, dict, float]], List[dict], List[dict]]:
    """Greedy best-overlap pairing within claim type.

    Same-type first because a $47B market-size claim should never pair with
    a $47K pricing claim on shared digits; cross-type pairing is attempted
    only for leftovers, at a stricter threshold, to catch retyped claims.
    """
    old_left = list(old)
    new_left = list(new)
    pairs: List[Tuple[dict, dict, float]] = []

    def best_pairs(candidates_old, candidates_new, floor):
        scored = []
        for o in candidates_old:
            to = _tokens(o.get("text", ""))
            for n in candidates_new:
                if o.get("type") != n.get("type") and floor <= PAIR_THRESHOLD:
                    continue
                s = _overlap(to, _tokens(n.get("text", "")))
                if s >= floor:
                    scored.append((s, o, n))
        scored.sort(key=lambda t: -t[0])
        for s, o, n in scored:
            if o in old_left and n in new_left:
                pairs.append((o, n, s))
                old_left.remove(o)
                new_left.remove(n)

    best_pairs(old_left, new_left, PAIR_THRESHOLD)          # same type
    best_pairs(old_left, new_left, PAIR_THRESHOLD + 0.20)   # retyped, stricter
    return pairs, old_left, new_left


def diff_claims(old: List[Dict[str, Any]], new: List[Dict[str, Any]]
                ) -> Dict[str, Any]:
    """The deterministic core: pure data in, pure data out."""
    pairs, dropped, added = pair_claims(
        [c for c in old if isinstance(c, dict)],
        [c for c in new if isinstance(c, dict)])

    changed, unchanged, moved = [], [], []
    for o, n, score in pairs:
        fo, fn = _figure(o), _figure(n)
        row = {"old": o, "new": n, "overlap": round(score, 2)}
        if fo is not None and fn is not None and fo != fn:
            row["old_figure"] = fo
            row["new_figure"] = fn
            row["ratio"] = round(fn / fo, 2) if fo else None
            changed.append(row)
        elif (o.get("text", "").strip() != n.get("text", "").strip()):
            row["reworded"] = True
            changed.append(row)
        else:
            unchanged.append(row)
        loc_o = (o.get("location") or "").strip()
        loc_n = (n.get("location") or "").strip()
        if loc_o and loc_n and loc_o.lower() != loc_n.lower():
            moved.append({"claim": n.get("text", ""),
                          "from": loc_o, "to": loc_n})

    return {"changed": changed, "dropped": dropped, "added": added,
            "unchanged": len(unchanged), "moved": moved,
            "counts": {"old": len(old), "new": len(new)}}


def _fmt_fig(v: Optional[float]) -> str:
    if v is None:
        return "?"
    if v == int(v) and abs(v) < 1e15:
        return f"{int(v):,}"
    return f"{v:,.2f}"


def render_diff(d: Dict[str, Any], old_name: str, new_name: str,
                company: str = "") -> str:
    L: List[str] = []
    add = L.append
    add(f"# Deck diff — {company or 'two versions'}")
    add("")
    add(f"**Old:** {old_name} ({d['counts']['old']} claims) → "
        f"**New:** {new_name} ({d['counts']['new']} claims)")
    add("")
    add("*Claims were extracted by the model; the comparison below is "
        "deterministic. An extraction that phrases the same claim "
        "differently across versions can appear as a drop plus an add — "
        "treat those sections as leads, not verdicts.*")
    add("")

    if d["changed"]:
        add("## Figures and wording that changed")
        add("")
        for row in d["changed"]:
            if "new_figure" in row:
                ratio = row.get("ratio")
                direction = ("" if ratio is None else
                             f" ({ratio}x)" if ratio >= 1 else
                             f" ({ratio}x — reduced)")
                add(f"- **{_fmt_fig(row['old_figure'])} → "
                    f"{_fmt_fig(row['new_figure'])}**{direction}")
                add(f"  - was: {row['old'].get('text', '')}")
                add(f"  - now: {row['new'].get('text', '')}")
            else:
                add("- **Reworded** (figures unchanged):")
                add(f"  - was: {row['old'].get('text', '')}")
                add(f"  - now: {row['new'].get('text', '')}")
        add("")

    if d["dropped"]:
        add("## Claims that disappeared")
        add("")
        add("*A dropped claim is often the interesting one — ask why it "
            "left the deck.*")
        add("")
        for c in d["dropped"]:
            loc = f" *({c['location']})*" if c.get("location") else ""
            add(f"- {c.get('text', '')}{loc}")
        add("")

    if d["added"]:
        add("## New claims")
        add("")
        for c in d["added"]:
            loc = f" *({c['location']})*" if c.get("location") else ""
            add(f"- {c.get('text', '')}{loc}")
        add("")

    if d["moved"]:
        add("## Claims that moved")
        add("")
        for m in d["moved"]:
            add(f"- \"{m['claim']}\" — {m['from']} → {m['to']}")
        add("")

    if not (d["changed"] or d["dropped"] or d["added"] or d["moved"]):
        add("*No claim-level differences found — "
            f"{d['unchanged']} claim(s) matched unchanged.*")
        add("")
    else:
        add(f"*{d['unchanged']} claim(s) unchanged. The diff is a change "
            f"log, not an audit — run each version through "
            f"`deckscope run` to judge the claims themselves.*")
        add("")
    return "\n".join(L)


def command(args: Any) -> int:
    """CLI entry: extract both decks, diff, write markdown."""
    import sys

    from ..console import out as _out

    def _err(msg):
        _out(msg, file=sys.stderr)
    from ..config import load_config
    from ..ingest.loader import load_deck
    from ..providers.registry import get_provider
    from ..security.screening import screen_deck
    from ..tiering import NDAGuard, is_local

    cfg = load_config(getattr(args, "config", None))
    if getattr(args, "provider", None):
        cfg.provider.name = args.provider
    provider_cfg = cfg.extract_provider or cfg.provider

    nda = bool(getattr(args, "nda", False))
    if nda and not is_local(provider_cfg):
        _err("--nda refused: the configured extraction model "
             f"('{provider_cfg.name}') is not local, and a diff sends both "
             "decks to it. Use a local model or drop --nda.")
        return 4

    old_path, new_path = args.old_deck, args.new_deck
    for p in (old_path, new_path):
        if not Path(p).exists():
            _err(f"Deck not found: {p}")
            return 2

    provider = get_provider(provider_cfg)
    guard = NDAGuard(enabled=nda)

    from ..agents.deck_agent import DeckAnalyst
    agent = DeckAnalyst(provider, cache_dir=cfg.cache_dir,
                        verbose=cfg.verbose)

    extractions = []
    for p in (old_path, new_path):
        doc = load_deck(p)
        doc, _scan = screen_deck(doc, cfg.security, deck_path=p)
        guard.protect(doc.text)
        extractions.append(agent.run(doc))

    d = diff_claims(extractions[0].get("claims") or [],
                    extractions[1].get("claims") or [])
    company = ((extractions[1].get("company") or {}).get("name")
               or (extractions[0].get("company") or {}).get("name") or "")

    body = render_diff(d, Path(old_path).name, Path(new_path).name, company)
    out_dir = Path(getattr(args, "out", None) or "deckscope_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{Path(new_path).stem}_diff.md"
    out.write_text(body, encoding="utf-8")

    _out(f"\n{len(d['changed'])} changed, {len(d['dropped'])} dropped, "
         f"{len(d['added'])} new, {d['unchanged']} unchanged.")
    _out(f"Diff written: {out}")
    return 0
