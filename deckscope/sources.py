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
from typing import Any, Dict, Iterable, List, Optional

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
        used = sum(len(l) for l in lines)
        for s in self.sources:
            if s.status == "quarantined":
                continue
            block = (f"[{s.sid}] {s.title or '(untitled)'}\n"
                     f"      url: {s.url or 'n/a'}\n"
                     f"      date: {s.published or 'unknown'}\n"
                     f"      found via query: {s.query or 'n/a'}\n"
                     f"      content: {s.snippet[:2500]}\n")
            if used + len(block) > char_budget:
                lines.append(f"[... {len(self.sources)} sources total; remainder omitted "
                             f"for length ...]")
                break
            lines.append(block)
            used += len(block)
        return "\n".join(lines)

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
                "quarantined": len(self.quarantined)}

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
