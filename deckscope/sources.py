"""The bibliography: every source retrieved, indexed, traceable, and printed.

A report that cites four URLs out of forty consulted is not auditable. DeckScope
assigns a stable ID (S1, S2, …) to every result the researcher returns, hands those
IDs to the agents, resolves whatever the agents cite back to the registry, and prints
the *entire* registry in the References section — marking which entries actually
supported a conclusion, which were consulted but unused, and which were dropped by
the security screen and why.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

CITE_RX = re.compile(r"\bS(\d{1,3})\b")


@dataclass
class Source:
    sid: str                      # "S1"
    title: str = ""
    url: str = ""
    snippet: str = ""
    published: Optional[str] = None
    query: Optional[str] = None   # which search produced it
    backend: str = ""             # which research backend
    reliability: str = "unknown"  # primary | secondary | vendor-marketing | unknown
    status: str = "consulted"     # consulted | cited | quarantined | dropped
    note: str = ""                # why it was dropped, if it was
    cited_by: List[str] = field(default_factory=list)  # e.g. ["C1", "scorecard:Market size"]

    @property
    def domain(self) -> str:
        import urllib.parse
        try:
            return (urllib.parse.urlparse(self.url).hostname or "").lower()
        except Exception:  # noqa: BLE001
            return ""

    @property
    def label(self) -> str:
        return self.title or self.url or f"Source {self.sid}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["domain"] = self.domain
        return d


class SourceRegistry:
    """Owns the S-IDs. One per run."""

    def __init__(self) -> None:
        self.sources: List[Source] = []
        #: IDs that have actually been rendered into a prompt block.
        #: Empty means no prompt has been built yet, not that none qualify.
        self._admitted: Set[str] = set()
        self._by_url: Dict[str, Source] = {}

    # ------------------------------------------------------------ building
    def add_results(self, results: Iterable[Any], backend: str = "") -> List[Source]:
        added = []
        for r in results:
            url = (getattr(r, "url", "") or "").strip()
            key = url.lower() or f"__title__{(getattr(r, 'title', '') or '').lower()}"
            if key in self._by_url:
                continue
            src = Source(
                sid=f"S{len(self.sources) + 1}",
                title=(getattr(r, "title", "") or "").strip(),
                url=url,
                snippet=(getattr(r, "snippet", "") or "").strip(),
                published=getattr(r, "published", None),
                query=getattr(r, "source_query", None),
                backend=backend,
            )
            self.sources.append(src)
            self._by_url[key] = src
            added.append(src)
        return added

    def mark_dropped(self, url_or_title: str, note: str) -> None:
        src = self.find(url_or_title)
        if src:
            src.status = "quarantined"
            src.note = note

    # ------------------------------------------------------------- lookup
    def find(self, ref: str) -> Optional[Source]:
        """Resolve an S-ID, a URL, or a title fragment to a Source."""
        if not ref:
            return None
        ref = str(ref).strip()
        if re.fullmatch(r"S\d{1,3}", ref, re.I):
            idx = int(ref[1:]) - 1
            return self.sources[idx] if 0 <= idx < len(self.sources) else None
        key = ref.lower()
        if key in self._by_url:
            return self._by_url[key]
        for s in self.sources:
            if s.url and (s.url.lower() == key or key in s.url.lower()):
                return s
        for s in self.sources:
            if s.title and key[:60] in s.title.lower():
                return s
        return None

    # -------------------------------------------------------- attribution
    def attribute(self, refs: Iterable[str], by: str) -> List[Source]:
        """Mark sources as cited by a specific finding. Returns the resolved ones."""
        out = []
        for ref in refs or []:
            src = self.find(str(ref))
            if not src:
                continue
            if src.status == "quarantined":
                # A source the security screen removed is never allowed to become
                # evidence, even if the model cites it from memory of an earlier pass.
                continue
            src.status = "cited"
            if by not in src.cited_by:
                src.cited_by.append(by)
            out.append(src)
        return out

    def harvest_inline(self, text: str, by: str) -> List[Source]:
        """Pick up bare [S3]-style citations written inside prose."""
        return self.attribute({f"S{m}" for m in CITE_RX.findall(text or "")}, by)

    def apply_reliability(self, market: Dict[str, Any]) -> None:
        """Fold the market agent's reliability judgements back onto the registry."""
        for entry in (market.get("sources") or []):
            src = self.find(entry.get("url") or entry.get("title") or "")
            if src and entry.get("reliability"):
                src.reliability = entry["reliability"]
            if src and entry.get("date") and not src.published:
                src.published = entry["date"]

    # ---------------------------------------------------------- rendering
    def prompt_block(self, char_budget: int = 90_000) -> str:
        """The numbered bibliography handed to the model, with citation rules."""
        if not self.sources:
            return "(no research material available)"
        lines = [
            "Each source below has a citation ID. Cite them by ID — for example S3 — in "
            "every field that has a `source_ids` slot, and inline in prose where a figure "
            "comes from a specific source. Never cite an ID that is not listed here.",
            "",
        ]
        used = sum(len(line) for line in lines)
        omitted = 0
        for s in self.sources:
            if s.status == "quarantined":
                continue
            block = (f"[{s.sid}] {s.title or '(untitled)'}\n"
                     f"      url: {s.url or 'n/a'}\n"
                     f"      date: {s.published or 'unknown'}\n"
                     f"      found via query: {s.query or 'n/a'}\n"
                     f"      content: {s.snippet[:2500]}\n")
            if used + len(block) > char_budget:
                omitted += 1
                continue
            lines.append(block)
            used += len(block)
            # Record what was actually put in front of a model. Validation asks
            # this set — not the registry — whether a citation could be genuine.
            self._admitted.add(s.sid)
        if omitted:
            lines.append(f"[... {omitted} further source(s) omitted for length. They "
                         f"are not listed above, so do not cite them ...]")
        return "\n".join(lines)

    @property
    def admitted_ids(self) -> Set[str]:
        """Every source ID that has appeared in some prompt block.

        A union across calls rather than the last call's set, because a source
        shown to the market agent was genuinely available to cite even if a later,
        differently budgeted block left it out.
        """
        return set(self._admitted)

    @property
    def citable(self) -> List[Source]:
        """Sources the model actually saw, and could therefore honestly cite.

        Two things remove a source from this set. Quarantined sources are in the
        registry so the report can say they were dropped and why, but they were
        never rendered into a prompt. Sources past the prompt's character budget
        were also never rendered — and this is the case that used to slip through:
        `citable` returned everything unquarantined, so a citation to source 200
        of 200 validated cleanly even though the block stopped at source 40 and no
        model ever laid eyes on it. Truncation is silent by nature, which is
        exactly why it needed to be tracked rather than assumed away.

        Before any prompt has been built there is nothing to be wrong about, so
        the unquarantined set stands in.
        """
        alive = [s for s in self.sources if s.status != "quarantined"]
        if not self._admitted:
            return alive
        return [s for s in alive if s.sid in self._admitted]

    @property
    def citable_ids(self) -> List[str]:
        return [s.sid for s in self.citable]

    @property
    def omitted_for_length(self) -> List[Source]:
        """Unquarantined sources that never fitted into a prompt.

        Reported rather than hidden: if research found evidence the model was
        never shown, the reader should know the analysis did not consider it.
        """
        if not self._admitted:
            return []
        return [s for s in self.sources
                if s.status != "quarantined" and s.sid not in self._admitted]

    @property
    def cited(self) -> List[Source]:
        return [s for s in self.sources if s.status == "cited"]

    @property
    def consulted(self) -> List[Source]:
        return [s for s in self.sources if s.status == "consulted"]

    @property
    def quarantined(self) -> List[Source]:
        return [s for s in self.sources if s.status == "quarantined"]

    def stats(self) -> Dict[str, int]:
        return {"total": len(self.sources), "cited": len(self.cited),
                "consulted_uncited": len(self.consulted),
                "quarantined": len(self.quarantined),
                # Reported rather than hidden: evidence that never reached a
                # prompt was not considered, and a reader deserves to know the
                # analysis was working from a subset.
                "omitted_for_length": len(self.omitted_for_length)}

    def to_dict(self) -> Dict[str, Any]:
        return {"stats": self.stats(),
                "sources": [s.to_dict() for s in self.sources]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceRegistry":
        reg = cls()
        for d in (data or {}).get("sources", []):
            d = {k: v for k, v in d.items() if k in Source.__dataclass_fields__}
            src = Source(**d)
            reg.sources.append(src)
            reg._by_url[(src.url or f"__title__{src.title}").lower()] = src
        return reg


def merge_registries(registries: Dict[str, "SourceRegistry"]
                     ) -> Tuple["SourceRegistry", Dict[str, Dict[str, str]]]:
    """Fold per-panelist registries into one namespace.

    Each panelist researches independently and numbers its own sources from S1.
    Panelist A's S1 and Panelist B's S1 are therefore different documents. If the
    panel then keeps only one registry — as an earlier version did — a citation
    written by B resolves against A's bibliography and silently attributes a
    figure to a source that never contained it.

    This assigns every distinct source one global ID, de-duplicating by URL so a
    document several panelists found keeps a single entry that records all of
    them. It returns the merged registry and, per panelist, a map from their
    local ID to the global one, so their reports can be rewritten.
    """
    merged = SourceRegistry()
    remap: Dict[str, Dict[str, str]] = {}

    for label, reg in registries.items():
        local_map: Dict[str, str] = {}
        for src in (reg.sources if reg else []):
            key = (src.url or f"__title__{src.title}").strip().lower()
            existing = merged._by_url.get(key)
            if existing is None:
                new = Source(
                    sid=f"S{len(merged.sources) + 1}",
                    title=src.title, url=src.url, snippet=src.snippet,
                    published=src.published, query=src.query, backend=src.backend,
                    reliability=src.reliability, status=src.status, note=src.note,
                    cited_by=[f"{label}: {c}" for c in src.cited_by])
                merged.sources.append(new)
                merged._by_url[key] = new
                existing = new
            else:
                # Same document, found by more than one panelist. Keep the richer
                # metadata and record every panelist that used it.
                if not existing.published and src.published:
                    existing.published = src.published
                if existing.reliability == "unknown" and src.reliability != "unknown":
                    existing.reliability = src.reliability
                if src.status == "quarantined":
                    existing.status = "quarantined"
                    existing.note = existing.note or src.note
                for c in src.cited_by:
                    tag = f"{label}: {c}"
                    if tag not in existing.cited_by:
                        existing.cited_by.append(tag)
            local_map[src.sid] = existing.sid
        remap[label] = local_map
    return merged, remap


def rewrite_citations(obj: Any, local_map: Dict[str, str]) -> Any:
    """Rewrite a panelist's local S-IDs to global ones, in place, recursively.

    Applies to `source_ids` arrays and to inline [S3] references in prose, so a
    merged report's citations resolve to the document the panelist actually read.
    """
    if not local_map:
        return obj

    def swap_token(tok: str) -> str:
        return local_map.get(tok.strip(), tok.strip())

    def swap_prose(text: str) -> str:
        return CITE_RX.sub(lambda m: local_map.get(f"S{m.group(1)}", m.group(0)), text)

    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "source_ids" and isinstance(v, list):
                obj[k] = [swap_token(str(x)) for x in v]
            elif isinstance(v, str):
                obj[k] = swap_prose(v)
            else:
                rewrite_citations(v, local_map)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = swap_prose(v)
            else:
                rewrite_citations(v, local_map)
    return obj


def resolve_citations(result: Any) -> SourceRegistry:
    """Walk a finished AnalysisResult and attribute every citation it contains."""
    reg = SourceRegistry.from_dict((result.market.get("_meta") or {}).get("registry", {}))
    reg.apply_reliability(result.market)

    market = result.market
    for est in (market.get("sizing") or {}).get("tam_estimates", []) or []:
        reg.attribute(est.get("source_ids") or ([est["url"]] if est.get("url") else []),
                      f"TAM estimate {est.get('value', '')}")
    land = market.get("competitive_landscape") or {}
    for group in ("incumbents", "challengers"):
        for c in land.get(group) or []:
            reg.attribute(c.get("source_ids") or ([c["url"]] if c.get("url") else []),
                          f"competitor: {c.get('name', '')}")
    for r in (market.get("funding_environment") or {}).get("recent_rounds", []) or []:
        reg.attribute(r.get("source_ids") or ([r["url"]] if r.get("url") else []),
                      f"round: {r.get('company', '')}")
    reg.harvest_inline((market.get("sizing") or {}).get("consensus_view", ""),
                       "market: consensus view")

    for lens, comp in (result.comparisons or {}).items():
        for c in comp.get("claim_audit") or []:
            refs = list(c.get("source_ids") or []) + list(c.get("sources") or [])
            reg.attribute(refs, f"{lens}: claim {c.get('id', '')}")
            reg.harvest_inline(c.get("market_evidence", ""),
                               f"{lens}: claim {c.get('id', '')}")
        for row in comp.get("scorecard") or []:
            reg.attribute(row.get("source_ids") or [],
                          f"{lens}: scorecard {row.get('dimension', '')}")
            for ev in row.get("evidence") or []:
                reg.harvest_inline(str(ev), f"{lens}: scorecard {row.get('dimension', '')}")
        reg.harvest_inline(comp.get("summary", ""), f"{lens}: summary")
        reg.harvest_inline(comp.get("headline", ""), f"{lens}: headline")

    return reg
