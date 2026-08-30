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

#: A citation written into prose. **Brackets are required**, and that is the whole
#: point of this expression.
#:
#: The previous form was `\bS(\d{1,3})\b`, which matches any S-followed-by-digits
#: token anywhere in a sentence. "Backups are stored in Amazon S3" therefore
#: contained a citation as far as DeckScope was concerned, and the same
#: expression drove harvesting, renumbering, stripping and evaluation scoring. So
#: a legitimate phrase could be attributed to a bibliography entry it has nothing
#: to do with, renumbered during a registry merge into `Amazon S8`, or deleted
#: outright as a dangling citation — leaving "Backups are stored in Amazon ."
#: Silent corruption of the report text, in a product whose entire promise is
#: that the evidence trail is trustworthy.
#:
#: Every prompt already instructs models to cite inline as `[S3]`, so requiring
#: the bracket costs nothing and closes the ambiguity. A group is allowed —
#: `[S1, S3]` — because models write them.
#:
#: The trade is deliberate: a bare `S3` that really was meant as a citation is
#: now ignored rather than acted on. Under-attributing is recoverable; corrupting
#: a sentence is not.
PROSE_CITE_RX = re.compile(r"\[\s*S\d+(?:\s*[,;]\s*S\d+)*\s*\]", re.I)

#: A single S-ID. Used to validate the *contents* of a `source_ids` array, where
#: the whole string is the reference and no bracket is expected.
SID_RX = re.compile(r"^\s*S(\d+)\s*$", re.I)

_SID_IN_GROUP_RX = re.compile(r"S(\d+)", re.I)


def prose_citations(text: str) -> List[str]:
    """Every S-ID cited inside brackets in `text`, in order of appearance."""
    out: List[str] = []
    for group in PROSE_CITE_RX.findall(text or ""):
        out.extend(f"S{n}" for n in _SID_IN_GROUP_RX.findall(group))
    return out


def map_prose_citations(text: str, fn) -> str:
    """Rewrite each bracketed citation group through `fn(sid) -> sid|None`.

    Returning None drops that ID from the group; a group left empty is removed
    along with its brackets. Prose outside brackets is never touched, which is
    the guarantee that keeps "Amazon S3" intact.
    """
    original = text or ""

    def repl(match: "re.Match[str]") -> str:
        kept: List[str] = []
        for n in _SID_IN_GROUP_RX.findall(match.group(0)):
            new = fn(f"S{n}")
            if new:
                kept.append(new)
        return f"[{', '.join(kept)}]" if kept else ""

    out = PROSE_CITE_RX.sub(repl, original)
    if out == original:
        # Nothing was a citation, so nothing may be reformatted. Tidying
        # unconditionally would collapse deliberate spacing in prose that this
        # function has no business touching.
        return original
    # Removing a citation can leave " ." or a doubled space behind.
    out = re.sub(r"\s+([.,;:])", r"\1", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


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
    #: When the snippet was captured, and a hash of exactly what was captured.
    #: A URL is a pointer, not evidence: the page it names moves on (the demo's
    #: IDC page now shows a different quarter than the recorded snippet — the
    #: snippet was independently corroborated, but the link no longer proves
    #: it). The timestamp plus the snippet hash turn "traceable to a URL" into
    #: "traceable to the evidence actually used": a reader can see when it was
    #: read and verify the report quotes what was captured, even after the
    #: live page changes (external audit finding #6).
    retrieved_at: str = ""
    snippet_sha256: str = ""

    def stamp(self) -> None:
        """Fill retrieval provenance from the snippet, once, at capture."""
        import hashlib
        from datetime import datetime, timezone

        if not self.retrieved_at:
            self.retrieved_at = datetime.now(timezone.utc).isoformat(
                timespec="seconds")
        if not self.snippet_sha256 and self.snippet:
            self.snippet_sha256 = hashlib.sha256(
                self.snippet.encode("utf-8")).hexdigest()[:16]

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
            src.stamp()
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
        if re.fullmatch(r"S\d+", ref, re.I):
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
    def reset_attribution(self) -> None:
        """Forget who cited what, keeping quarantine decisions.

        Attribution has to be rebuilt from the *finished* artifact, after invalid
        citations have been stripped. Marking sources cited on the way through and
        never revisiting it meant the bibliography could say "cited" about a source
        whose only reference had since been removed from the report — a claim the
        reader cannot check and that is wrong in the direction that flatters us.
        """
        for src in self.sources:
            if src.status in ("quarantined", "dropped"):
                continue
            src.status = "consulted"
            src.cited_by = []

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
            if self._prompt_built and src.sid not in self._admitted:
                # Never shown to a model, so nothing could have cited it from the
                # evidence. The citation audit already treats this as invalid;
                # attribution has to agree, or the two halves of the ledger
                # disagree about the same source.
                continue
            src.status = "cited"
            if by not in src.cited_by:
                src.cited_by.append(by)
            out.append(src)
        return out

    def harvest_inline(self, text: str, by: str) -> List[Source]:
        """Pick up bracketed [S3]-style citations written inside prose."""
        return self.attribute(dict.fromkeys(prose_citations(text)), by)

    def apply_reliability(self, market: Dict[str, Any]) -> None:
        """Fold the market agent's reliability judgements back onto the registry."""
        for entry in (market.get("sources") or []):
            src = self.find(entry.get("url") or entry.get("title") or "")
            if src and entry.get("reliability"):
                src.reliability = entry["reliability"]
            if src and entry.get("date") and not src.published:
                src.published = entry["date"]

    # ---------------------------------------------------------- rendering
    def prompt_block(self, char_budget: int = 90_000,
                     only: Optional[Iterable[str]] = None) -> str:
        """The numbered bibliography handed to the model, with citation rules.

        `only` restricts the block to specific IDs. That matters for the narrow
        passes — a listing lookup, say — which merge their handful of sources
        into the run's registry and then need a prompt containing *those*, not
        the whole run's bibliography. Rendering everything would both blow the
        budget and mark unrelated sources as admitted, which is the flag the
        citation audit trusts.
        """
        if not self.sources:
            return "(no research material available)"
        wanted = {str(s).strip().upper() for s in only} if only is not None else None
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
            if wanted is not None and s.sid.upper() not in wanted:
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
            # Carry the admission ledger across. Without this the merged
            # registry only learned which sources appeared in later *shared*
            # prompts, so a source a panelist genuinely read in round one looked
            # unadmitted — and the citation audit strips citations to unadmitted
            # sources. The panel would have deleted its own honest evidence.
            if reg is not None and src.sid in reg.admitted_ids:
                merged._admitted.add(existing.sid)
        if reg is not None and reg._prompt_built:
            merged._prompt_built = True
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
    # And the flag itself. Without it, an incoming registry that built a prompt
    # and admitted nothing — because nothing fit the budget — left the target
    # believing no prompt had ever been built, which flips `citable_ids` from
    # "only what a model saw" back to "everything". That is the widened-trust
    # bug this flag exists to prevent, reintroduced through the merge.
    if incoming._prompt_built:
        target._prompt_built = True
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
        # Only inside brackets. Renumbering every S-token in prose is how
        # "Amazon S3" became "Amazon S8" during a panel merge.
        return map_prose_citations(text, lambda sid: local_map.get(sid, sid))

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


#: Every part of a finished result that may carry citations. Attribution, the
#: audit and the evaluation scorer all read this one list, because three
#: traversals with three different ideas of "the whole report" is how a
#: dangling citation in an optional section coexisted with a perfect
#: citation-integrity score.
#: `market_reports` is deliberately NOT here: its reconciliation entries
#: cite each STORED panel's local source ids, a different namespace from the
#: run registry — walking them here would strip valid citations. Their audit
#: happens at the source instead (marketreport.reconcile.scrub_reading,
#: against exactly the ids the bearing model was shown), closing the bypass
#: the fourth external audit demonstrated with a fabricated [S999]. The
#: specialist figures that DO enter the run's prompt are remapped into the
#: run namespace inside `market` and audited with it.
CITATION_SECTIONS = ("market", "comparisons", "opportunity", "discovery_delta",
                     "cold_market")

#: Fields that identify the object a citation sits on, so the bibliography can
#: say "investor: claim C1" rather than a JSON path.
_NAME_KEYS = ("id", "name", "dimension", "company", "value", "claim", "what",
              "market", "risk", "action", "category")


def _label(path: List[str], holder: Optional[Dict[str, Any]]) -> str:
    """A human-readable 'cited by' label for a position in the result tree."""
    parts = [p for p in path if p]
    if parts and parts[0] == "comparisons" and len(parts) > 1:
        head = f"{parts[1]}: " + ".".join(parts[2:]) if len(parts) > 2 else parts[1]
    else:
        head = ".".join(parts)
    if isinstance(holder, dict):
        for key in _NAME_KEYS:
            val = holder.get(key)
            if isinstance(val, str) and val.strip():
                return f"{head} ({val.strip()[:60]})"
    return head or "report"


def walk_citations(result: Any, *, on_ids=None, on_prose=None) -> None:
    """Visit every citation in a finished result, once, in one place.

    `on_ids(sids, label)` sees each `source_ids` array and may return a
    replacement list. `on_prose(text, label)` sees each string and may return
    replacement text. Returning None leaves the value untouched.

    Field-by-field traversals know the fields somebody remembered to list, so a
    schema that grows a new `source_ids` slot escapes them silently. Walking the
    finished object means a new field is covered the day it is added — and
    sharing the walk means the ledger and the audit cannot disagree about what
    they looked at.
    """
    def visit(node: Any, path: List[str], holder: Optional[Dict[str, Any]]) -> None:
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key.startswith("_"):
                    continue          # _meta carries no user-facing citations
                if key == "source_ids" and isinstance(value, list):
                    if on_ids is not None:
                        kept = on_ids([str(v) for v in value],
                                      _label(path, node))
                        if kept is not None:
                            node[key] = kept
                elif isinstance(value, str):
                    if on_prose is not None:
                        new = on_prose(value, _label(path + [key], node))
                        if new is not None:
                            node[key] = new
                else:
                    visit(value, path + [key], node)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                if isinstance(item, str):
                    if on_prose is not None:
                        new = on_prose(item, _label(path, holder))
                        if new is not None:
                            node[i] = new
                else:
                    visit(item, path, holder)

    for section in CITATION_SECTIONS:
        payload = getattr(result, section, None)
        if payload:
            visit(payload, [section], None)


def resolve_citations(result: Any, registry: Optional[SourceRegistry] = None
                      ) -> SourceRegistry:
    """Rebuild the bibliography's `cited` status from the **finished** artifact.

    Ordering is the point of this function, and getting it wrong produced a
    genuinely dishonest report. Attribution used to run *before* the citation
    audit: a source was marked `cited`, the audit then removed its only
    reference from the report as invalid, and nothing revisited the ledger. The
    References section therefore claimed a source supported a conclusion whose
    citation the reader could no longer see — wrong in the direction that
    flatters the product, and impossible for the reader to check.

    So this resets attribution and rebuilds it from what actually survived,
    using the same traversal the audit uses. Run it *after* `audit_citations`.

    `registry` is the live ledger for the run and should always be supplied.
    Rebuilding from `market._meta.registry` reconstructs a snapshot taken when
    the market agent finished — before cold discovery and the opportunity pass
    added their sources. The fallback remains for callers holding only a
    serialized result.
    """
    reg = registry if registry is not None else SourceRegistry.from_dict(
        (result.market.get("_meta") or {}).get("registry", {}))
    reg.apply_reliability(result.market)
    reg.reset_attribution()

    def ids(sids: List[str], where: str):
        reg.attribute(sids, where)
        return None                    # read-only pass; the audit does the editing

    def prose(text: str, where: str):
        reg.harvest_inline(text, where)
        return None

    walk_citations(result, on_ids=ids, on_prose=prose)

    # `claim_audit[].sources` holds full URLs for the same references. It is not
    # a `source_ids` array, so the generic walk sees it as prose and ignores it.
    for lens, comp in (result.comparisons or {}).items():
        for c in comp.get("claim_audit") or []:
            if isinstance(c, dict) and c.get("sources"):
                reg.attribute([str(u) for u in c["sources"]],
                              f"{lens}: claim {c.get('id', '')}")
    return reg


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
    audit, on_ids, on_prose = _make_auditor(registry, strip)
    walk_citations(result, on_ids=on_ids, on_prose=on_prose)
    return audit


def audit_fragment(node: Any, registry: SourceRegistry, *, strip: bool = True,
                   where: str = "fragment") -> CitationAudit:
    """The same check, on a bare dict or list rather than a whole result.

    The panel needs this. Its revisions and its chair's consensus are model
    output like any other, but they live outside an `AnalysisResult`, so the
    recursive audit never reached them — leaving the expensive mode with a
    weaker citation guarantee than the cheap one, which is backwards from what
    anyone paying for a panel would assume. Field-by-field validators covered
    `scorecard` and `claim_audit` and nothing else, so a fabricated citation in
    a revised summary, a blind spot, a risk, or an inline reference survived.
    """
    audit, on_ids, on_prose = _make_auditor(registry, strip)
    shim = type("_Fragment", (), {s: None for s in CITATION_SECTIONS})()
    setattr(shim, CITATION_SECTIONS[0], node)
    walk_citations(shim, on_ids=on_ids, on_prose=on_prose)
    return audit


def _make_auditor(registry: SourceRegistry, strip: bool):
    """The checker itself, shared so every caller enforces the same invariant."""
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

    def on_ids(sids: List[str], where: str):
        kept = [s for s in sids if check(s, where)]
        return kept if strip else None

    def on_prose(text: str, where: str):
        if not PROSE_CITE_RX.search(text or ""):
            return None               # no bracketed citation, so nothing to judge
        bad = {sid for sid in prose_citations(text) if not check(sid, where)}
        if not bad or not strip:
            return None
        # Remove the marker, keep the prose. The sentence may still be a
        # reasonable observation; it simply is not evidenced, and must stop
        # looking as though it were. Only the bracketed reference is touched.
        return map_prose_citations(text, lambda sid: None if sid in bad else sid)

    return audit, on_ids, on_prose
