"""What the cold pass found that the claim-directed pass never looked for.

Two market analyses arrive by different routes. One was given the deck's claims
and searched for evidence about them; the other was given a category and searched
it cold. Comparing them is not about deciding which is right — it is about
isolating the things only the unprompted process could surface.

That difference is the strongest blind-spot signal DeckScope can produce. When the
claim-directed research misses a dominant incumbent, it usually misses it because
the deck never named it, and the research agenda came from the deck. The cold pass
has no such gap, because it never saw the deck.

The comparison is computed here rather than asked of a model, so it is stable and
inspectable: set arithmetic over normalized names, not a judgement call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


def _norm(name: Any) -> str:
    """Company names, comparably. 'Microsoft Corp.' and 'microsoft' are one thing."""
    text = re.sub(r"[^a-z0-9 ]+", " ", str(name or "").lower())
    text = re.sub(
        r"\b(inc|corp|corporation|ltd|limited|llc|plc|gmbh|sa|ag|co|company|"
        r"technologies|technology|software|labs|group|holdings)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _competitors(market: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    land = (market or {}).get("competitive_landscape") or {}
    for group in ("incumbents", "challengers"):
        for row in land.get(group) or []:
            if not isinstance(row, dict):
                continue
            key = _norm(row.get("name"))
            if key:
                out.setdefault(key, {**row, "_group": group})
    return out


def _phrases(items: Any) -> Dict[str, str]:
    """Short free-text findings, keyed by a normalized form for set comparison."""
    out: Dict[str, str] = {}
    for item in (items or []):
        text = item if isinstance(item, str) else str((item or {}).get("point") or "")
        key = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
        key = re.sub(r"\s+", " ", key).strip()
        if len(key) > 12:
            out[key] = text
    return out


@dataclass
class DiscoveryDelta:
    """What each route saw that the other did not."""

    ran: bool = True
    #: Competitors the cold pass found and the claim-directed pass missed. The
    #: headline output: nothing prompted the deck-blind analyst to look for these.
    competitors_only_cold: List[Dict[str, Any]] = field(default_factory=list)
    competitors_only_directed: List[Dict[str, Any]] = field(default_factory=list)
    competitors_in_both: List[str] = field(default_factory=list)
    headwinds_only_cold: List[str] = field(default_factory=list)
    absorbers_only_cold: List[str] = field(default_factory=list)
    adjacent_only_cold: List[str] = field(default_factory=list)
    sizing: Dict[str, Any] = field(default_factory=dict)
    concentration: Dict[str, Any] = field(default_factory=dict)
    #: How much the two routes overlapped at all, 0-1.
    agreement: float = 0.0
    note: str = ""
    reason_skipped: Optional[str] = None

    @property
    def anything_found(self) -> bool:
        return bool(self.competitors_only_cold or self.headwinds_only_cold
                    or self.absorbers_only_cold or self.adjacent_only_cold)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["anything_found"] = self.anything_found
        return d


def compare(directed: Dict[str, Any], cold: Dict[str, Any]) -> DiscoveryDelta:
    """Diff the claim-directed market view against the cold one."""
    delta = DiscoveryDelta()
    if not cold or (cold.get("_meta") or {}).get("skipped"):
        delta.ran = False
        delta.reason_skipped = (cold.get("_meta") or {}).get("skipped",
                                                            "cold pass did not run")
        return delta

    d_comp, c_comp = _competitors(directed), _competitors(cold)
    only_cold = sorted(set(c_comp) - set(d_comp))
    only_directed = sorted(set(d_comp) - set(c_comp))
    both = sorted(set(d_comp) & set(c_comp))

    delta.competitors_only_cold = [
        {"name": c_comp[k].get("name"), "position": c_comp[k].get("position"),
         "threat_level": c_comp[k].get("threat_level"),
         "group": c_comp[k].get("_group"),
         "source_ids": c_comp[k].get("source_ids") or []}
        for k in only_cold]
    delta.competitors_only_directed = [
        {"name": d_comp[k].get("name"), "position": d_comp[k].get("position")}
        for k in only_directed]
    delta.competitors_in_both = [d_comp[k].get("name") for k in both]

    universe = len(set(d_comp) | set(c_comp))
    delta.agreement = round(len(both) / universe, 2) if universe else 0.0

    d_head = _phrases((directed.get("demand_signals") or {}).get("headwinds"))
    c_head = _phrases((cold.get("demand_signals") or {}).get("headwinds"))
    delta.headwinds_only_cold = [c_head[k] for k in sorted(set(c_head) - set(d_head))]

    d_abs = {_norm(a.get("name")) for a in
             ((directed.get("absorption_risk") or {}).get("likely_absorbers") or [])
             if isinstance(a, dict)}
    for a in ((cold.get("absorption_risk") or {}).get("likely_absorbers") or []):
        if isinstance(a, dict) and _norm(a.get("name")) not in d_abs:
            delta.absorbers_only_cold.append(str(a.get("name")))

    d_adj = {_norm(m.get("market")) for m in (directed.get("adjacent_markets") or [])
             if isinstance(m, dict)}
    for m in (cold.get("adjacent_markets") or []):
        if isinstance(m, dict) and _norm(m.get("market")) not in d_adj:
            delta.adjacent_only_cold.append(str(m.get("market")))

    d_size = (directed.get("sizing") or {})
    c_size = (cold.get("sizing") or {})
    delta.sizing = {
        "directed_consensus": d_size.get("consensus_view"),
        "cold_consensus": c_size.get("consensus_view"),
        "directed_confidence": d_size.get("sizing_confidence"),
        "cold_confidence": c_size.get("sizing_confidence"),
    }
    d_land = (directed.get("competitive_landscape") or {})
    c_land = (cold.get("competitive_landscape") or {})
    delta.concentration = {
        "directed": d_land.get("concentration"),
        "cold": c_land.get("concentration"),
        "agree": d_land.get("concentration") == c_land.get("concentration"),
    }

    delta.note = _narrate(delta)
    return delta


def _narrate(delta: DiscoveryDelta) -> str:
    if not delta.anything_found:
        return ("Researching the category cold surfaced nothing the claim-directed "
                "pass had missed. That is a meaningful result: it suggests the deck's "
                "framing did not steer the research away from anything material.")

    parts = []
    if delta.competitors_only_cold:
        names = ", ".join(str(c["name"]) for c in delta.competitors_only_cold[:4])
        parts.append(
            f"{len(delta.competitors_only_cold)} competitor(s) appeared only when the "
            f"market was researched cold: {names}. Nothing in the deck prompted a "
            f"search for them, which is exactly how a dominant incumbent goes "
            f"unexamined")
    if delta.absorbers_only_cold:
        parts.append(f"potential absorbers not raised by the directed pass: "
                     f"{', '.join(delta.absorbers_only_cold[:3])}")
    if delta.headwinds_only_cold:
        parts.append(f"{len(delta.headwinds_only_cold)} headwind(s) surfaced only cold")
    if delta.adjacent_only_cold:
        parts.append(f"adjacent markets missed: "
                     f"{', '.join(delta.adjacent_only_cold[:3])}")
    return ("Two routes to the same market disagreed about what is in it. "
            + "; ".join(parts) + ".")
