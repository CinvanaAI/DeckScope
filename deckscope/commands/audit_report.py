"""`deckscope audit-report <file> --sources <json|dir>` — the citation
audit, unbundled from the pipeline.

DeckScope's most defensible layer is not the analysis; it is the audit
that every citation resolves to a real, unquarantined source and that
figures without sources say so. This command points that layer at a
document DeckScope did not write — an analyst's memo, another AI's
report, a consultant's market section — against a source list the caller
provides.

Deterministic: no model call. The audit can only check what a citation
claims structurally (this [S3] exists, was not quarantined, and the
figure beside it has a source at all) — it cannot check that S3 actually
supports the sentence. The report says so.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

_CITE = re.compile(r"\[(S\d+)\]", re.I)
#: A figure worth sourcing: money, percentages, multiples, scaled counts.
#: Bare years and list numbering are deliberately not figures.
_FIGURE = re.compile(
    r"\$\s?\d[\d,.]*|\b\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?x\b"
    r"|\b\d{1,3}(?:,\d{3})+\b"
    r"|\b\d+(?:\.\d+)?\s?(?:billion|million|trillion|bn|mm|[BMT])\b")
_YEAR_ONLY = re.compile(r"^(?:19|20)\d{2}$")


def load_sources(path: Path) -> List[Dict[str, Any]]:
    """A JSON file, or a directory of them, each holding either a list of
    source dicts or an object with a 'sources' list (a saved DeckScope
    result works as-is)."""
    files = (sorted(path.glob("*.json")) if path.is_dir() else [path])
    if not files:
        raise ValueError(f"No .json files in {path}")
    items: List[Dict[str, Any]] = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("sources") or []
        if not isinstance(data, list):
            raise ValueError(f"{f.name}: expected a list of sources or an "
                             "object with a 'sources' list")
        items.extend(d for d in data if isinstance(d, dict))
    if not items:
        raise ValueError("The source file(s) contained no sources.")
    return items


def build_registry(items: List[Dict[str, Any]]):
    """Sources keep their own S-IDs when they carry them — a report citing
    [S7] must be audited against the caller's S7, not a renumbering."""
    from ..sources import Source, SourceRegistry

    with_sid = [d for d in items if str(d.get("sid", "")).strip()]
    if with_sid and len(with_sid) != len(items):
        raise ValueError("Sources are ambiguous: some carry an 'sid' and "
                         "some do not. All or none.")
    reg = SourceRegistry()
    seen = set()
    for i, d in enumerate(items, 1):
        sid = str(d.get("sid", "")).strip().upper() or f"S{i}"
        if not re.fullmatch(r"S\d+", sid):
            raise ValueError(f"Bad source id {sid!r} — expected S<number>.")
        if sid in seen:
            raise ValueError(f"Duplicate source id {sid}.")
        seen.add(sid)
        src = Source(sid=sid,
                     title=str(d.get("title", "") or ""),
                     url=str(d.get("url", "") or ""),
                     snippet=str(d.get("snippet", "") or ""),
                     published=d.get("published"),
                     backend=str(d.get("backend", "") or "provided"))
        if d.get("status") in ("quarantined", "dropped"):
            src.status = d["status"]
            src.note = str(d.get("note", "") or "")
        if d.get("retrieved_at"):
            src.retrieved_at = str(d["retrieved_at"])
        reg.sources.append(src)
        if src.url:
            reg._by_url[src.url.lower()] = src
    return reg


def _sentences(text: str) -> List[str]:
    out = []
    for block in text.split("\n"):
        line = block.strip()
        if not line or line.startswith(("```", "|--", "---")):
            continue
        out.extend(s.strip() for s in
                   re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", line) if s.strip())
    return out


def audit_text(text: str, registry: Any) -> Dict[str, Any]:
    known = {s.sid.upper(): s for s in registry.sources}
    used, dangling, quarantined = set(), [], []
    for m in _CITE.finditer(text):
        sid = m.group(1).upper()
        used.add(sid)
        src = known.get(sid)
        ctx = text[max(0, m.start() - 60):m.start()].replace("\n", " ").strip()
        if src is None:
            dangling.append((sid, ctx))
        elif src.status == "quarantined":
            quarantined.append((sid, ctx))

    unsourced: List[str] = []
    for s in _sentences(text):
        if _CITE.search(s):
            continue
        figs = [f for f in _FIGURE.findall(s)
                if not _YEAR_ONLY.fullmatch(f.strip())]
        if figs and _FIGURE.search(s):
            unsourced.append(s)

    unused = [s for s in registry.sources
              if s.sid.upper() not in used and s.status != "quarantined"]
    return {"checked": sum(1 for _ in _CITE.finditer(text)),
            "used": sorted(used, key=lambda s: int(s[1:])),
            "dangling": dangling, "quarantined": quarantined,
            "unsourced_figures": unsourced, "unused_sources": unused}


def render_audit(a: Dict[str, Any], report_name: str, n_sources: int,
                 structured_note: str = "") -> str:
    L: List[str] = []
    add = L.append
    clean = not (a["dangling"] or a["quarantined"])
    add(f"# Citation audit — {report_name}")
    add("")
    add(f"**{a['checked']} citation(s) checked against {n_sources} provided "
        f"source(s): {len(a['dangling'])} dangling, "
        f"{len(a['quarantined'])} quarantined, "
        f"{len(a['unsourced_figures'])} figure sentence(s) with no source, "
        f"{len(a['unused_sources'])} source(s) never cited.**")
    add("")
    add("*This audit is structural. It proves each [S#] resolves to a real, "
        "unquarantined source and flags figures asserted with no source in "
        "the sentence — it cannot prove a cited source actually supports "
        "the sentence citing it. That last step is reading.*")
    if structured_note:
        add("")
        add(f"*{structured_note}*")
    add("")

    if a["dangling"]:
        add("## Dangling citations — the source does not exist")
        add("")
        for sid, ctx in a["dangling"]:
            add(f"- **[{sid}]** after: “…{ctx}”")
        add("")
    if a["quarantined"]:
        add("## Citations to quarantined sources")
        add("")
        for sid, ctx in a["quarantined"]:
            add(f"- **[{sid}]** after: “…{ctx}”")
        add("")
    if clean:
        add("## Citations")
        add("")
        add("Every citation resolved to a provided, unquarantined source."
            if a["checked"] else
            "The document contains no [S#] citations at all — every figure "
            "in it is effectively unsourced.")
        add("")

    if a["unsourced_figures"]:
        add("## Figures asserted without a source *(advisory)*")
        add("")
        add("*Leads for review, not verdicts — a figure may be sourced in a "
            "neighboring sentence or be arithmetic on sourced inputs.*")
        add("")
        for s in a["unsourced_figures"][:40]:
            add(f"- {s}")
        if len(a["unsourced_figures"]) > 40:
            add(f"- *…and {len(a['unsourced_figures']) - 40} more.*")
        add("")

    if a["unused_sources"]:
        add("## Provided but never cited")
        add("")
        for s in a["unused_sources"][:20]:
            add(f"- {s.sid}: {s.title or s.url or '(untitled)'}")
        add("")

    add("---")
    add("*Generated by DeckScope's citation-audit layer; deterministic, "
        "no AI call.*")
    return "\n".join(L)


def command(args: Any) -> int:
    import sys

    from ..console import out as _out

    def _err(msg):
        _out(msg, file=sys.stderr)

    report = Path(args.report)
    if not report.is_file():
        _err(f"Report not found: {report}")
        return 2
    try:
        registry = build_registry(load_sources(Path(args.sources)))
    except (ValueError, json.JSONDecodeError, OSError) as e:
        _err(f"Could not load sources: {e}")
        return 2

    text = report.read_text(encoding="utf-8", errors="replace")
    a = audit_text(text, registry)

    structured_note = ""
    if report.suffix.lower() == ".json":
        # Structured reports also carry bracketless source_ids fields; run
        # the pipeline's own recursive auditor over the parsed object.
        from ..sources import audit_fragment

        try:
            node = json.loads(text)
            fa = audit_fragment(node, registry, strip=False,
                                where=report.name)
            for where, sid in fa.dangling:
                a["dangling"].append((str(sid).upper(), where))
            for where, sid in fa.quarantined:
                a["quarantined"].append((str(sid).upper(), where))
            a["checked"] += fa.checked
            structured_note = (f"Structured pass: {fa.checked} additional "
                               "reference(s) in source_ids fields checked "
                               "recursively.")
        except (ValueError, json.JSONDecodeError):
            structured_note = ("The .json file did not parse as JSON; only "
                               "the text scan ran.")

    body = render_audit(a, report.name, len(registry.sources),
                        structured_note)
    out_dir = Path(getattr(args, "out", None) or "deckscope_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{report.stem}_audit.md"
    out.write_text(body, encoding="utf-8")

    bad = len(a["dangling"]) + len(a["quarantined"])
    _out(f"\n{a['checked']} citation(s): {len(a['dangling'])} dangling, "
         f"{len(a['quarantined'])} quarantined; "
         f"{len(a['unsourced_figures'])} unsourced figure sentence(s).")
    _out(f"Audit written: {out}")
    return 1 if bad else 0
