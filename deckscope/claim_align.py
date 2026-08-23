"""Match claims across panelists by what they say, not by their position.

Each panelist extracts claims independently and numbers them from C1. Nothing
guarantees that A's C1 and B's C1 are the same proposition — one may have
numbered the TAM first and the other traction. Grouping the agreement matrix by
raw ID therefore compares unrelated statements and reports the result as
"agreement", which is worse than reporting nothing.

This module aligns claims on their content:

  * the salient numbers in the claim (47, 23%, $340k) — the strongest signal,
    because two analysts describing the same figure almost always quote it
  * the significant word overlap, ignoring filler
  * the claim type, when both recorded one

Claims that match nothing are kept and reported as single-panelist observations
rather than silently dropped. "Only one of three analysts noticed this" is a
finding in its own right.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Words carrying no discriminating power in a claim about a startup.
STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is",
    "are", "was", "were", "be", "been", "with", "by", "from", "that", "this",
    "it", "its", "we", "our", "their", "has", "have", "had", "will", "would",
    "than", "as", "per", "over", "about", "into", "claims", "claim", "deck",
}

NUM_RX = re.compile(r"""
    (?P<num>\d[\d,]*(?:\.\d+)?)      # 47   340   1.2
    \s*
    (?P<unit>%|percent|bn|b\b|billion|m\b|million|k\b|thousand|x\b|cagr)?
""", re.I | re.X)

#: Above this token overlap alone, two claims are the same proposition.
STRONG_OVERLAP = 0.55
#: One shared salient number plus some wording overlap.
NUMBER_OVERLAP = 0.18
#: Two or more shared salient numbers is decisive on its own. Analysts describing
#: the same figure quote the same digits even when their prose differs entirely —
#: "$47B TAM growing 23% CAGR" and "total addressable market of $47B at 23% CAGR"
#: share almost no significant words but are plainly one claim.
DECISIVE_NUMBER_MATCHES = 2


def canonical(text: str) -> str:
    """Whitespace- and case-normalized claim text, for exact-match comparison."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


@dataclass
class ClaimCluster:
    """One proposition, as seen by however many panelists raised it."""

    key: str                                        # representative text
    claim_type: Optional[str] = None
    #: panelist label -> their assessment of it
    assessments: Dict[str, str] = field(default_factory=dict)
    #: panelist label -> the ID they gave it, so a reader can trace back
    local_ids: Dict[str, str] = field(default_factory=dict)
    texts: List[str] = field(default_factory=list)
    tokens: set = field(default_factory=set)
    numbers: set = field(default_factory=set)
    #: Canonical forms seen in this cluster, so identical wording always matches
    #: even when the claim is too short to yield tokens or numbers.
    canon: set = field(default_factory=set)

    @property
    def raised_by(self) -> int:
        return len(self.assessments)

    def to_dict(self, total_panelists: int) -> Dict[str, Any]:
        distinct = {a for a in self.assessments.values()}
        return {
            "claim": self.key,
            "type": self.claim_type,
            "assessments": dict(self.assessments),
            "local_ids": dict(self.local_ids),
            "raised_by": self.raised_by,
            "of_panelists": total_panelists,
            "unanimous": len(distinct) == 1 and self.raised_by == total_panelists,
            "distinct_positions": len(distinct),
            "contested": len(distinct) > 1,
            "single_panelist": self.raised_by == 1 and total_panelists > 1,
        }


def normalize(text: str) -> Tuple[set, set]:
    """Return (significant tokens, salient numbers) for a claim."""
    lowered = (text or "").lower()
    numbers = set()
    for m in NUM_RX.finditer(lowered):
        raw = m.group("num").replace(",", "")
        unit = (m.group("unit") or "").strip().lower()
        unit = {"percent": "%", "b": "bn", "billion": "bn", "m": "m",
                "million": "m", "k": "k", "thousand": "k"}.get(unit, unit)
        try:
            val = float(raw)
        except ValueError:
            continue
        numbers.add(f"{val:g}{unit}")
    tokens = {w for w in re.findall(r"[a-z][a-z0-9'-]{2,}", lowered)
              if w not in STOPWORDS}
    return tokens, numbers


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _matches(cluster: ClaimCluster, tokens: set, numbers: set,
             claim_type: Optional[str], canon: str = "") -> bool:
    # A conflicting declared type is a hard no: a market-size claim and a
    # traction claim are not the same proposition however similar the wording.
    if cluster.claim_type and claim_type and cluster.claim_type != claim_type:
        return False
    # Identical wording is always the same claim. This also covers claims too
    # short to produce any tokens or numbers, which would otherwise never match
    # even themselves.
    if canon and canon in cluster.canon:
        return True
    shared_numbers = cluster.numbers & numbers
    if len(shared_numbers) >= DECISIVE_NUMBER_MATCHES:
        return True
    overlap = _jaccard(cluster.tokens, tokens)
    if overlap >= STRONG_OVERLAP:
        return True
    if shared_numbers and overlap >= NUMBER_OVERLAP:
        return True
    return False


def align_claims(per_panelist: Dict[str, List[Dict[str, Any]]]
                 ) -> List[ClaimCluster]:
    """Cluster claims across panelists by content.

    `per_panelist` maps a panelist label to its claim_audit rows.
    """
    clusters: List[ClaimCluster] = []
    for label, rows in per_panelist.items():
        for row in rows or []:
            text = str(row.get("claim") or "").strip()
            if not text:
                continue
            ctype = row.get("type") or None
            tokens, numbers = normalize(text)
            canon = canonical(text)
            target = None
            best = 0.0
            for c in clusters:
                # A panelist cannot appear twice in one cluster; if it already
                # has an entry, this is a different claim of theirs.
                if label in c.assessments:
                    continue
                if _matches(c, tokens, numbers, ctype, canon):
                    # An exact-wording match always wins over a fuzzy one.
                    score = 1.1 if canon in c.canon else _jaccard(c.tokens, tokens)
                    if score >= best:
                        best, target = score, c
            if target is None:
                target = ClaimCluster(key=text, claim_type=ctype)
                clusters.append(target)
            target.assessments[label] = str(row.get("assessment") or "—")
            target.local_ids[label] = str(row.get("id") or "")
            target.texts.append(text)
            target.tokens |= tokens
            target.numbers |= numbers
            target.canon.add(canon)
            # Prefer the longest phrasing as the representative: it usually
            # carries the most context for a reader.
            if len(text) > len(target.key):
                target.key = text
    # Most-discussed first, then contested ones, so the useful rows lead.
    clusters.sort(key=lambda c: (-c.raised_by, -len(set(c.assessments.values()))))
    return clusters
