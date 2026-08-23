"""Open-source parity as a leading indicator of platform bundling.

The pattern this encodes, stated plainly:

    While an open-source alternative is meaningfully behind, commercial products
    are differentiated on capability, customers pay for something they cannot get
    free, and the market is healthy.

    Once open source reaches rough parity, capability stops being the
    differentiator. What remains is packaging, operations, support and
    distribution — and a platform vendor already owns all four. It only has to be
    good enough and free, and the mid-market has nowhere to stand.

That is why open-source maturity predicts absorption better than market size,
growth or funding do.

But parity alone does not decide it, and conflating the two gets the answer wrong
in both directions:

  * Kubernetes reached parity and Docker Inc. could not monetize, because the
    residual differentiation was distribution — the thing platforms have most of.
  * Credible open-source data warehouses existed throughout Snowflake's rise,
    because the residual differentiation was operational burden at scale, which is
    expensive to give away for free even if you are Amazon.

So the assessment takes both inputs: how close open source is, and what kind of
thing the commercial offering still provides once it arrives. This module combines
them deterministically, so the reasoning is inspectable and consistent across runs
rather than re-derived by a model each time.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

#: How close the closest open-source project is, worst-to-best for the incumbent.
GAP_ORDER = ["far behind", "meaningfully behind", "approaching parity",
             "at parity", "ahead of commercial"]

#: Whether a platform vendor can cheaply replicate this kind of differentiation.
#:
#: Distribution and packaging are what platforms ARE, so a company whose remaining
#: advantage is either of those is defending the hill the giant already occupies.
#: Compliance depth, data network effects and workflow entrenchment are slow and
#: expensive to reproduce, which is why they are where survivors end up.
REPLICABILITY = {
    "distribution": 1.0,     # the platform's core asset
    "packaging": 0.95,
    "operational": 0.7,      # real work, but a hyperscaler can fund it
    "support": 0.6,
    "integrations": 0.5,
    "workflow-depth": 0.3,
    "data-network": 0.2,
    "compliance": 0.2,
    "none-left": 1.0,        # nothing to defend at all
}

LEVELS = ["low", "moderate", "elevated", "high", "severe"]


@dataclass
class BundlingAssessment:
    """A derived read on how exposed this category is to being bundled away."""

    level: str = "unknown"
    score: float = 0.0                       # 0-1, for ordering only
    gap: Optional[str] = None
    gap_trend: Optional[str] = None
    closest_project: Optional[str] = None
    #: Differentiation a platform vendor could cheaply reproduce.
    replicable: List[str] = field(default_factory=list)
    #: Differentiation that is genuinely hard to reproduce.
    durable: List[str] = field(default_factory=list)
    reasoning: str = ""
    caveats: List[str] = field(default_factory=list)
    applicable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def assess(oss: Optional[Dict[str, Any]],
           absorption: Optional[Dict[str, Any]] = None) -> BundlingAssessment:
    """Combine open-source parity with the shape of what commercial still offers."""
    out = BundlingAssessment()
    oss = oss or {}

    applicable = oss.get("applicable")
    if applicable is False or (applicable is None and not oss.get("projects")):
        out.applicable = False
        out.level = "not applicable"
        out.reasoning = ("This category has no meaningful open-source dimension, so "
                         "open-source parity says nothing about it either way. Read "
                         "the absorption section on its own.")
        return out

    gap = (oss.get("capability_gap") or "").strip().lower()
    out.gap = gap or None
    out.gap_trend = oss.get("gap_trend")
    out.closest_project = oss.get("closest_project")

    if gap not in GAP_ORDER:
        out.level = "unknown"
        out.reasoning = ("The open-source capability gap could not be established, so "
                         "this signal is unavailable. That is not the same as low risk.")
        return out

    # How much of the differentiation has already collapsed onto packaging?
    gap_pressure = GAP_ORDER.index(gap) / (len(GAP_ORDER) - 1)   # 0.0 .. 1.0

    provides = [p for p in (oss.get("what_commercial_still_provides") or [])
                if isinstance(p, dict)]
    if provides:
        weights = []
        for item in provides:
            kind = str(item.get("type") or "").strip().lower()
            weight = REPLICABILITY.get(kind, 0.6)
            # An explicit "not durable" overrides a category that usually is.
            if str(item.get("durable")).lower() in ("false", "no"):
                weight = max(weight, 0.85)
            weights.append(weight)
            label = f"{item.get('capability') or kind} ({kind})"
            (out.replicable if weight >= 0.6 else out.durable).append(label)
        # The company survives on its BEST defence, not its average one.
        residual_replicability = min(weights)
    else:
        residual_replicability = 0.8
        out.caveats.append(
            "No specific remaining commercial differentiation was identified, which is "
            "itself a finding — if nothing was named, there may be nothing to name.")

    # Parity only matters to the extent that what is left is easy to copy. A
    # company at parity whose moat is compliance depth is in a different position
    # from one whose moat is a nicer installer.
    out.score = round(gap_pressure * residual_replicability, 3)

    if gap_pressure >= 0.5 and residual_replicability >= 0.85:
        out.level = "severe"
    elif out.score >= 0.55:
        out.level = "high"
    elif out.score >= 0.35:
        out.level = "elevated"
    elif out.score >= 0.15:
        out.level = "moderate"
    else:
        out.level = "low"

    # A narrowing gap raises the reading; a widening one lowers it.
    trend = (out.gap_trend or "").strip().lower()
    if trend in ("narrowing", "closed") and out.level in LEVELS:
        idx = LEVELS.index(out.level)
        if idx < len(LEVELS) - 1:
            out.level = LEVELS[idx + 1]
            out.caveats.append("Raised one level because the capability gap is "
                               "narrowing rather than holding.")
    elif trend == "widening" and out.level in LEVELS and LEVELS.index(out.level) > 0:
        out.level = LEVELS[LEVELS.index(out.level) - 1]
        out.caveats.append("Lowered one level because commercial offerings are "
                           "pulling further ahead of open source.")

    out.reasoning = _explain(out, gap, residual_replicability)

    # Cross-check against what the market agent concluded separately.
    verdict = str((absorption or {}).get("verdict") or "").lower()
    if verdict == "product" and out.level in ("high", "severe"):
        out.caveats.append(
            f"The market analysis called this a standalone product, but the "
            f"open-source signal reads {out.level}. Those disagree, and the "
            f"disagreement is worth resolving before relying on either.")
    if verdict == "feature" and out.level in ("low", "moderate"):
        out.caveats.append(
            f"The market analysis called this a feature, but open source is "
            f"{gap} and the residual differentiation looks defensible. Absorption "
            f"may be driven by something other than commoditization here.")

    pressure = str(oss.get("pricing_pressure") or "").lower()
    if pressure in ("significant", "severe"):
        out.caveats.append(
            f"Pricing pressure from the free alternative is already {pressure}, which "
            f"usually precedes bundling rather than following it.")
    return out


def _explain(a: BundlingAssessment, gap: str, replicability: float) -> str:
    project = a.closest_project or "the closest open-source project"
    if gap in ("far behind", "meaningfully behind"):
        base = (f"{project} is {gap}, so commercial products here are still "
                f"differentiated on capability — customers are paying for something "
                f"they cannot get free. That is the healthy configuration, and it is "
                f"the main thing holding platform bundling off.")
    elif gap == "approaching parity":
        base = (f"{project} is approaching parity. Capability is ceasing to be the "
                f"differentiator, which is the point at which the ground starts moving.")
    else:
        base = (f"{project} is {gap}. Capability is no longer the differentiator, so "
                f"whatever the commercial offering still provides is the whole business.")

    if replicability >= 0.85:
        tail = (" And what remains is packaging and distribution — precisely what a "
                "platform vendor already owns. It does not need to build a better "
                "product, only a good-enough one it can give away, and the mid-market "
                "has nowhere to stand.")
    elif replicability >= 0.6:
        tail = (" What remains is operational and support work. A hyperscaler can fund "
                "that, so it buys time rather than safety.")
    else:
        tail = (" What remains — compliance depth, data effects, workflow entrenchment "
                "— is slow and expensive to reproduce, which is where companies in "
                "commoditizing categories actually survive.")
    return base + tail
