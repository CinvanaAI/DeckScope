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
        self._admitted: Set[str] = set()
        #: Whether a prompt block has ever been built. An empty `_admitted` means
        #: two opposite things without this: "nothing has been asked of a model
        #: yet, so every source is still a candidate" versus "a prompt was built
        #: and not one source fit in it, so nothing is citable". Conflating them
        #: made the second silently behave like the first.
        self._prompt_built: bool = False
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
        self._prompt_built = True
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
        if not self._prompt_built:
            # Nothing has been put in front of a model yet, so nothing has been
            # ruled out. Every surviving source is still a candidate.
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
        if not self._prompt_built:
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
        # `admitted` is part of the ledger, not a runtime detail. Dropping it on
        # serialization silently *widened* what counted as citable: a registry
        # round-tripped through JSON forgot that some of its sources never fitted
        # into a prompt, and validation then accepted citations to material no
        # model had seen. `prompt_built` distinguishes the two states an empty
        # set would otherwise conflate — no prompt yet, versus a prompt in which
        # nothing fit — which are opposite trust positions.
        return {"stats": self.stats(),
                "admitted": sorted(self._admitted),
                "prompt_built": self._prompt_built,
                "sources": [s.to_dict() for s in self.sources]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceRegistry":
        reg = cls()
        for d in (data or {}).get("sources", []):
            d = {k: v for k, v in d.items() if k in Source.__dataclass_fields__}
            src = Source(**d)
            reg.sources.append(src)
            reg._by_url[(src.url or f"__title__{src.title}").lower()] = src
        # Restore the ledger, not just the shelf. Without this a round-trip
        # forgot which sources a model had actually been shown.
        reg._admitted = {str(s) for s in ((data or {}).get("admitted") or [])}
        reg._prompt_built = bool((data or {}).get("prompt_built", False))
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


def merge_into(target: "SourceRegistry", incoming: "SourceRegistry",
               note: str = "") -> Dict[str, str]:
    """Fold `incoming`'s sources into `target` and return the ID remapping.

    **The return value is not optional.** Any caller that merges registries must
    apply this map to whatever model output cited the incoming IDs, because those
    IDs are about to mean something else.

    This exists because an earlier version of the cold-discovery merge renumbered
    sources in place and never rewrote the analysis that cited them. The result
    was silent and severe: a finding about one company displayed a real,
    openable citation to an unrelated document. Returning the map — rather than
    mutating and hoping — makes the obligation impossible to miss, and matching
    on URL means a source both passes found is merged rather than duplicated.
    """
    remap: Dict[str, str] = {}
    for src in incoming.sources:
        key = (src.url or f"__title__{src.title}").lower()
        existing = target._by_url.get(key)
        if existing is not None:
            remap[src.sid] = existing.sid
            continue
        old = src.sid
        src.sid = f"S{len(target.sources) + 1}"
        remap[old] = src.sid
        if note and not src.note:
            src.note = note
        target.sources.append(src)
        target._by_url[key] = src
        # A source only counts as admitted if it reached a prompt. The incoming
        # registry knows which of its own did; carry that across under the new
        # ID rather than losing or inventing it.
        if old in incoming.admitted_ids:
            target._admitted.add(src.sid)
    return remap


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


def resolve_citations(result: Any, registry: Optional[SourceRegistry] = None
                      ) -> SourceRegistry:
    """Walk a finished AnalysisResult and attribute every citation it contains.

    `registry` is the live ledger for the run and should always be supplied.
    Rebuilding from `market._meta.registry` reconstructs a *snapshot* taken when
    the market agent finished — before cold discovery and the opportunity pass
    added their sources. Anything those passes found was therefore missing from
    the final bibliography, and their citations resolved to nothing or, worse, to
    whatever source happened to occupy that index.

    The fallback remains for callers holding only a serialized result.
    """
    reg = registry if registry is not None else SourceRegistry.from_dict(
        (result.market.get("_meta") or {}).get("registry", {}))
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

    # Everything above names the fields it knows about, which means a new
    # source-bearing field is invisible to it until somebody remembers to add a
    # line here. Nobody ever remembers. This sweeps whatever is left — including
    # the optional passes, which no hand-written branch covered.
    for section in ("opportunity", "discovery_delta", "cold_market"):
        payload = getattr(result, section, None)
        if payload:
            _attribute_recursively(reg, payload, section)

    return reg


def _attribute_recursively(reg: SourceRegistry, node: Any, where: str) -> None:
    """Attribute every `source_ids` list and inline [S#] anywhere beneath `node`."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "source_ids" and isinstance(value, list):
                reg.attribute([str(v) for v in value], where)
            elif isinstance(value, str):
                reg.harvest_inline(value, where)
            else:
                _attribute_recursively(reg, value, where)
    elif isinstance(node, list):
        for item in node:
            _attribute_recursively(reg, item, where)


@dataclass
class CitationAudit:
    """Every citation in a finished result, checked against the one ledger."""

    #: (where, id) for IDs that name no source at all.
    dangling: List[Tuple[str, str]] = field(default_factory=list)
    #: (where, id) for IDs naming a source the security screen removed.
    quarantined: List[Tuple[str, str]] = field(default_factory=list)
    #: (where, id) for IDs naming a source no model was ever shown.
    unadmitted: List[Tuple[str, str]] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not (self.dangling or self.quarantined or self.unadmitted)

    def summary(self) -> str:
        if self.ok:
            return f"all {self.checked} citation(s) resolve to admitted sources"
        parts = []
        if self.dangling:
            parts.append(f"{len(self.dangling)} to sources that do not exist")
        if self.quarantined:
            parts.append(f"{len(self.quarantined)} to quarantined sources")
        if self.unadmitted:
            parts.append(f"{len(self.unadmitted)} to sources no model was shown")
        return f"of {self.checked} citation(s): " + ", ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "checked": self.checked,
                "summary": self.summary(),
                "dangling": [{"where": w, "id": i} for w, i in self.dangling],
                "quarantined": [{"where": w, "id": i} for w, i in self.quarantined],
                "unadmitted": [{"where": w, "id": i} for w, i in self.unadmitted]}


def audit_citations(result: Any, registry: SourceRegistry,
                    strip: bool = True) -> CitationAudit:
    """Check — and optionally strip — every citation in a finished result.

    One pass over the complete artifact, whatever agent or optional feature
    produced it, enforcing the invariant the product's whole promise rests on:

        every displayed source reference exists, was not quarantined, and was
        actually shown to the model that cited it.

    Field-by-field validators cannot enforce that. They know the fields somebody
    remembered to list, so a schema that grows a new `source_ids` slot silently
    escapes checking — which is exactly what happened to absorbers, absorption
    precedents, open-source projects and adjacent markets. Walking the finished
    object instead means a new field is covered the day it is added.

    With `strip`, a citation that fails is removed rather than displayed. A
    badge pointing at the wrong source is worse than no badge: it converts an
    unsupported statement into an apparently evidenced one.
    """
    audit = CitationAudit()
    known = {s.sid.upper(): s for s in registry.sources}
    admitted = registry.admitted_ids
    prompt_built = registry._prompt_built

    def check(sid: str, where: str) -> bool:
        audit.checked += 1
        src = known.get(str(sid).strip().upper())
        if src is None:
            audit.dangling.append((where, str(sid)))
            return False
        if src.status == "quarantined":
            audit.quarantined.append((where, str(sid)))
            return False
        if prompt_built and src.sid not in admitted:
            audit.unadmitted.append((where, str(sid)))
            return False
        return True

    def walk(node: Any, where: str) -> Any:
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key == "source_ids" and isinstance(value, list):
                    kept = [v for v in value if check(v, f"{where}.{key}")]
                    if strip:
                        node[key] = kept
                elif isinstance(value, str):
                    bad = [f"S{m}" for m in CITE_RX.findall(value)
                           if not check(f"S{m}", f"{where}.{key}")]
                    if strip and bad:
                        # Remove the marker, keep the prose. The sentence may
                        # still be a reasonable observation; it simply is not
                        # evidenced, and must stop looking as though it were.
                        for token in set(bad):
                            node[key] = re.sub(rf"\[?\b{token}\b\]?", "", node[key])
                        node[key] = re.sub(r"\s{2,}", " ", node[key]).strip()
                else:
                    walk(value, f"{where}.{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, where)
        return node

    for section in ("market", "comparisons", "opportunity", "discovery_delta",
                    "cold_market"):
        payload = getattr(result, section, None)
        if payload:
            walk(payload, section)
    return audit
