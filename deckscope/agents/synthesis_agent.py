"""Agent 3 — the comparison itself, written through the chosen lens."""
from __future__ import annotations

import json
from typing import Any, Dict

from ..config import Lens
from ..prompts.lenses import lens_block
from ..prompts.templates import COMPARE_SYSTEM, COMPARE_USER
from ..schemas import COMPARISON_SCHEMA, coerce, schema_block, scorecard_total
from ..validate import validate_comparison
from .base import Agent


def _slim(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Drop bulky internals before handing an artifact to the next agent."""
    out = {k: v for k, v in obj.items() if k != "_meta"}
    meta = obj.get("_meta") or {}
    keep = {k: meta[k] for k in ("queries", "backend", "n_results", "source",
                                 "slides", "loader_warnings") if k in meta}
    if keep:
        out["_context"] = keep
    return out


class ComparisonSynthesist(Agent):
    name = "compare"
    label = "3/3 Comparison"

    def run(self, deck: Dict[str, Any], market: Dict[str, Any], *,
            lens: Lens = Lens.INVESTOR,
            valid_source_ids: Any = (),
            sources_block: str = "") -> Dict[str, Any]:
        self.label = f"3/3 Comparison ({lens.value})"
        self.emit("comparing deck claims against market evidence")

        system = COMPARE_SYSTEM.format(lens_block=lens_block(lens))
        user = COMPARE_USER.format(
            schema=schema_block(COMPARISON_SCHEMA, "Comparison"),
            deck_json=json.dumps(_slim(deck), indent=2)[:70_000],
            market_json=json.dumps(_slim(market), indent=2)[:70_000],
            sources=sources_block or "(no sources were retrieved for this run)",
        )
        result = self.cached_json(
            # The bibliography is part of the input, so it belongs in the cache
            # key. Without it, a run against different evidence would replay a
            # cached answer computed from the old sources.
            self.cache_key(lens=lens.value, deck=_slim(deck), market=_slim(market),
                           sources=sources_block),
            lambda: self.complete_json(system, user, temperature=0.3),
        )
        result = coerce(result, COMPARISON_SCHEMA)
        # Validate BEFORE scoring: a score of 47 or a citation to a source that
        # was never supplied must not reach the weighted total or the report.
        validation = validate_comparison(result, valid_source_ids=valid_source_ids)
        if not validation.ok:
            self.emit(f"validation: {validation.summary()}")
        result["_meta"] = {
            "lens": lens.value,
            "weighted_score": scorecard_total(result.get("scorecard") or []),
            "validation": validation.to_dict(),
        }
        # Report what was found, not the composite score. The score is still
        # computed above for the panel's ranking, but announcing it here — after
        # it was removed from every report for being untraceable — would put the
        # number back in front of the only person who reads the terminal.
        audit = result.get("claim_audit") or []
        contested = sum(1 for row in audit if isinstance(row, dict)
                        and str(row.get("assessment", "")).lower()
                        in ("contradicted", "partially-supported"))
        cited = sum(1 for row in audit if isinstance(row, dict)
                    and (row.get("source_ids") or []))
        self.emit(f"{len(audit)} claim(s) examined, {contested} contested, "
                  f"{cited} citing a source")
        return result
