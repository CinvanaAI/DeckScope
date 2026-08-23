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
            valid_source_ids: Any = ()) -> Dict[str, Any]:
        self.label = f"3/3 Comparison ({lens.value})"
        self.emit("comparing deck claims against market evidence")

        system = COMPARE_SYSTEM.format(lens_block=lens_block(lens))
        user = COMPARE_USER.format(
            schema=schema_block(COMPARISON_SCHEMA, "Comparison"),
            deck_json=json.dumps(_slim(deck), indent=2)[:70_000],
            market_json=json.dumps(_slim(market), indent=2)[:70_000],
        )
        result = self.cached_json(
            self.cache_key(lens=lens.value, deck=_slim(deck), market=_slim(market)),
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
        verdict = (result.get("verdict") or {}).get("call", "—")
        self.emit(f"verdict: {verdict} "
                  f"({result['_meta']['weighted_score']['score']}/100)")
        return result
