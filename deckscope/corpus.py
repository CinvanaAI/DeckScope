"""A frozen body of evidence, so two analyses can be compared fairly.

DeckScope's central claim is that separating extraction, research and comparison
beats asking one model to do all three. `--mode both` was meant to test that, and
could not: each mode ran its own searches, so the two analyses read different
sources. Any difference between their outputs was confounded by the evidence, and
"the pipeline found more risks" might only mean "the pipeline happened to retrieve
a page about risks".

An `EvidenceCorpus` fixes the confound by construction. Research runs once, the
results are frozen, and both modes read the identical bytes. What remains between
them is the thing under test: how the evidence was processed.

It also makes a run reproducible. A corpus can be saved and replayed, so a change
to a prompt can be evaluated against the same evidence a week later rather than
against whatever the web says that day — which is the difference between an
experiment and an anecdote.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .research.base import SearchResult
from .security.policy import SecurityPolicy
from .security.report import ScanReport
from .security.screening import screen_sources
from .sources import SourceRegistry


@dataclass
class EvidenceCorpus:
    """Screened, frozen research results plus the provenance to reproduce them."""

    registry: SourceRegistry = field(default_factory=SourceRegistry)
    queries: List[str] = field(default_factory=list)
    backend: str = "none"
    security: Optional[ScanReport] = None
    gathered_at: str = ""
    #: How many results the backend returned before screening dropped any.
    retrieved: int = 0
    #: Set when this corpus was replayed from disk rather than freshly gathered.
    replayed_from: Optional[str] = None
    #: Queries that did not execute, as {query, error}. Deliberately NOT
    #: sources: an outage says nothing about the subject, and a corpus that
    #: reports "0 sources" after a backend failure is describing the network,
    #: not the market. Whatever consumes this corpus must be able to tell those
    #: two apart, so the failures are carried beside the evidence, not inside it.
    failures: List[Dict[str, str]] = field(default_factory=list)

    @property
    def kept(self) -> int:
        return len(self.registry.citable)

    @property
    def empty(self) -> bool:
        return not self.registry.sources

    def fingerprint(self) -> str:
        """Stable hash of the evidence itself.

        Two runs sharing a fingerprint read exactly the same sources, which is
        what makes a comparison between them meaningful. It covers content, not
        ordering metadata, so it survives a reserialization.
        """
        # Serialize each source first, then sort the STRINGS — dicts are not
        # orderable, and sorting on the serialized form also makes the hash
        # independent of the order the backend happened to return them in.
        rows = sorted(
            json.dumps({"url": s.url, "title": s.title, "snippet": s.snippet,
                        "published": s.published or "", "status": s.status},
                       sort_keys=True, ensure_ascii=False)
            for s in self.registry.sources)
        return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16]

    def prompt_block(self, char_budget: int = 90_000) -> str:
        return self.registry.prompt_block(char_budget=char_budget)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint": self.fingerprint(),
            "queries": list(self.queries),
            "backend": self.backend,
            "gathered_at": self.gathered_at,
            "retrieved": self.retrieved,
            "kept": self.kept,
            "replayed_from": self.replayed_from,
            "registry": self.registry.to_dict(),
            "security": self.security.to_dict() if self.security else None,
        }

    def save(self, path: str) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, default=str),
                     encoding="utf-8")
        return str(p)

    @classmethod
    def load(cls, path: str) -> "EvidenceCorpus":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        corpus = cls(
            registry=SourceRegistry.from_dict(data.get("registry") or {}),
            queries=list(data.get("queries") or []),
            backend=str(data.get("backend") or "none"),
            gathered_at=str(data.get("gathered_at") or ""),
            retrieved=int(data.get("retrieved") or 0),
            replayed_from=str(path),
        )
        return corpus


def gather(researcher: Any, queries: List[str], policy: SecurityPolicy, *,
           max_results: int = 8,
           on_event: Optional[Any] = None) -> EvidenceCorpus:
    """Run the searches once and freeze what comes back.

    Registration happens BEFORE screening so a source dropped as hostile still
    appears in the corpus with the reason — the corpus records what was
    retrieved, not merely what survived.
    """
    def log(message: str) -> None:
        if on_event:
            on_event(message, {})

    corpus = EvidenceCorpus(
        queries=list(queries),
        backend=getattr(researcher, "name", "none"),
        gathered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    if researcher is None or corpus.backend == "none" or not queries:
        corpus.security = ScanReport(target="web sources")
        return corpus

    try:
        results: List[SearchResult] = researcher.search_many(
            queries, max_results=max_results)
    except Exception as exc:  # noqa: BLE001 - an empty corpus is a valid outcome
        log(f"research failed: {exc}")
        corpus.security = ScanReport(target="web sources")
        return corpus

    # A failed query is separated before anything can register or cite it. The
    # gate is here as well as at the origin because `gather` accepts results
    # from any Researcher, including third-party ones, and this is the last
    # point where a non-source can still be stopped from becoming a source.
    failures = [r for r in results if getattr(r, "failed", False)]
    results = [r for r in results if not getattr(r, "failed", False)]
    for bad in failures:
        corpus.failures.append({"query": bad.source_query or "",
                                "error": bad.error or "the search did not run"})
        log(f"search failed for {bad.source_query!r}: {bad.error}")

    corpus.retrieved = len(results)
    corpus.registry.add_results(results, backend=corpus.backend)

    kept, report = screen_sources(results, policy)
    corpus.security = report
    kept_keys = {(getattr(r, "url", "") or getattr(r, "title", "")).lower()
                 for r in kept}
    for src in corpus.registry.sources:
        if (src.url or src.title).lower() not in kept_keys:
            src.status = "quarantined"
            src.note = src.note or ("Dropped by the security screen: the page "
                                    "addressed the AI rather than reporting facts.")
    log(f"corpus {corpus.fingerprint()}: {corpus.kept} usable of "
        f"{corpus.retrieved} retrieved")
    return corpus
