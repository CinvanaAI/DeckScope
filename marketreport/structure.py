"""Concentration, saturation and life cycle — computed, never asked.

Everything a market-research professional works out with a formula, this works
out with a formula. `RESEARCH_NOTES.md` §4 records why: a model asked to
"consider the concentration of this market" returns a plausible adjective, and
`sum(share ** 2)` returns a number with a published threshold attached to it.

The measures here are the standard ones, and the thresholds are the ones the US
antitrust agencies publish, so a reader who disagrees with our reading can
disagree with the number rather than with our taste.

One honest approximation runs through this module and is labelled everywhere it
appears. Firm-level revenue is not free — but County Business Patterns publishes
**establishment counts by employee-size band**, free, by industry and geography.
Employment is a defensible proxy for share, and a size-band distribution gives a
concentration estimate that is good enough to distinguish a fragmented trade
from a duopoly. It is not good enough to quote as a measured HHI, and the code
says so rather than letting the approximation acquire the authority of the real
thing.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: US DOJ/FTC Horizontal Merger Guidelines thresholds. Quoted rather than
#: invented so a reader can check the reading against the source.
HHI_UNCONCENTRATED = 1_500
HHI_MODERATE = 2_500

#: The conventional reading of a four-firm concentration ratio.
CR4_COMPETITIVE = 0.40
CR4_CONCENTRATED = 0.60

#: Midpoints for the CBP employee-size bands, used to turn a count of
#: establishments per band into an employment estimate. Approximate by
#: construction — the top band is open-ended and any midpoint for it is a guess,
#: so it is deliberately conservative.
SIZE_BAND_MIDPOINTS: Dict[str, float] = {
    "1-4": 2.5, "5-9": 7.0, "10-19": 14.5, "20-49": 34.5,
    "50-99": 74.5, "100-249": 174.5, "250-499": 374.5,
    "500-999": 749.5, "1000+": 1500.0,
}


@dataclass
class Concentration:
    """How concentrated a market is, and how confident that reading is."""

    hhi: Optional[float] = None
    cr4: Optional[float] = None
    firms: Optional[int] = None
    #: "measured" when built from real shares, "estimated" from size bands.
    basis: str = "estimated"
    reading: str = ""
    because: str = ""
    caveat: str = ""
    shares: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def hhi(shares: Sequence[float]) -> Optional[float]:
    """Herfindahl-Hirschman Index over fractional market shares.

    Shares are fractions of one. Returns the conventional 0–10,000 scale.
    Squaring is the point: it weights large firms heavily, so it separates
    "ten firms with 10% each" from "one firm with 91% and nine with 1%",
    which a simple count of firms cannot.
    """
    usable = [s for s in shares if s is not None and s > 0]
    if not usable:
        return None
    total = sum(usable)
    if total <= 0:
        return None
    # Normalize, because a partial list of shares is the normal case — we rarely
    # know every firm — and an un-normalized HHI over a partial list understates
    # concentration without saying so.
    return round(sum((s / total) ** 2 for s in usable) * 10_000, 1)


def cr(shares: Sequence[float], n: int = 4) -> Optional[float]:
    """Concentration ratio: the combined share of the largest `n` firms."""
    usable = sorted((s for s in shares if s is not None and s > 0), reverse=True)
    if not usable:
        return None
    total = sum(usable)
    if total <= 0:
        return None
    return round(sum(usable[:n]) / total, 4)


def read_hhi(score: Optional[float]) -> Tuple[str, str]:
    """The published reading of an HHI, with the threshold that produced it."""
    if score is None:
        return "", ""
    if score < HHI_UNCONCENTRATED:
        return ("unconcentrated",
                f"HHI {score:,.0f} is below {HHI_UNCONCENTRATED:,}, the US "
                f"merger-guideline threshold for an unconcentrated market")
    if score < HHI_MODERATE:
        return ("moderately concentrated",
                f"HHI {score:,.0f} falls between {HHI_UNCONCENTRATED:,} and "
                f"{HHI_MODERATE:,}")
    return ("highly concentrated",
            f"HHI {score:,.0f} is above {HHI_MODERATE:,}, the threshold for a "
            f"highly concentrated market")


def from_size_bands(bands: Dict[str, int]) -> Concentration:
    """Estimate concentration from establishment counts per employee-size band.

    `bands` maps a CBP size label to how many establishments fall in it.

    This is the free route, and it is an estimate. Employment stands in for
    revenue, every establishment within a band is treated as identical, and the
    open-ended top band gets a conservative midpoint. It will not give a
    publishable HHI. It will reliably tell you whether you are looking at
    twenty thousand small operators or four large ones, which is the question
    a reader actually has.
    """
    weights: List[float] = []
    firms = 0
    for label, count in (bands or {}).items():
        midpoint = SIZE_BAND_MIDPOINTS.get(str(label).strip())
        if midpoint is None or not count:
            continue
        firms += int(count)
        weights.extend([midpoint] * int(count))

    if not weights:
        return Concentration(
            basis="estimated", reading="",
            because="no usable size-band data",
            caveat="County Business Patterns suppresses size-band detail for "
                   "small geographies to protect individual businesses")

    total = sum(weights)
    shares = sorted((w / total for w in weights), reverse=True)
    score = hhi(shares)
    reading, because = read_hhi(score)
    return Concentration(
        hhi=score, cr4=cr(shares, 4), firms=firms, basis="estimated",
        reading=reading, because=because,
        shares=[round(s, 6) for s in shares[:10]],
        caveat="Estimated from establishment counts by employee-size band, not "
               "from firm revenue. Employment stands in for share and every "
               "establishment in a band is treated as identical, so this "
               "separates a fragmented trade from a concentrated one but is not "
               "a measured HHI.")


def from_shares(shares: Sequence[float], *, firms: Optional[int] = None) -> Concentration:
    """Concentration from real market shares, when they are actually known."""
    score = hhi(shares)
    reading, because = read_hhi(score)
    return Concentration(
        hhi=score, cr4=cr(shares, 4),
        firms=firms if firms is not None else len(list(shares)),
        basis="measured", reading=reading, because=because,
        shares=[round(s, 6) for s in sorted(shares, reverse=True)[:10]])


@dataclass
class Saturation:
    """How full a market is, from penetration and growth together.

    Neither number means much alone. High penetration in a fast-growing market
    is a different situation from high penetration in a flat one, and reporting
    only the first would flatter the wrong markets.
    """

    penetration: Optional[float] = None
    growth: Optional[float] = None
    reading: str = ""
    because: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


#: Above this share of the addressable base, a market is treated as well
#: penetrated. Conventional rather than derived, and stated so it can be argued
#: with instead of being buried in a comparison.
PENETRATION_HIGH = 0.60
PENETRATION_LOW = 0.20
#: Real annual growth above this is treated as a growing market.
GROWTH_HEALTHY = 0.05


def saturation(penetration: Optional[float],
               growth: Optional[float]) -> Saturation:
    """Read penetration and growth together."""
    if penetration is None and growth is None:
        return Saturation(
            because="neither penetration nor growth could be established")

    if penetration is None:
        if growth is None:
            return Saturation(penetration=penetration, growth=growth)
        fast = growth >= GROWTH_HEALTHY
        return Saturation(
            growth=growth,
            reading="growing" if fast else "flat or declining",
            because=(f"growth of {growth * 100:.1f}% a year, with no penetration "
                     f"figure — so how much room remains is unknown"))

    if growth is None:
        return Saturation(
            penetration=penetration,
            reading=("well penetrated" if penetration >= PENETRATION_HIGH
                     else "lightly penetrated" if penetration <= PENETRATION_LOW
                     else "partly penetrated"),
            because=(f"{penetration * 100:.1f}% of the addressable base is "
                     f"served, with no growth figure — so whether that is "
                     f"filling up or standing still is unknown"))

    high = penetration >= PENETRATION_HIGH
    fast = growth >= GROWTH_HEALTHY
    if high and not fast:
        reading = "saturated"
        why = "most of the addressable base is served and the market is not growing"
    elif high and fast:
        reading = "penetrated but expanding"
        why = ("most of the current base is served, but the base itself is "
               "growing — share must come from expansion rather than switching")
    elif not high and fast:
        reading = "open and growing"
        why = "much of the base is unserved and the market is growing"
    else:
        reading = "open but static"
        why = ("much of the base is unserved and yet the market is not growing, "
               "which usually means the unserved part does not want the product "
               "rather than that it has not been reached")
    return Saturation(penetration=penetration, growth=growth,
                      reading=reading,
                      because=f"{penetration * 100:.1f}% penetrated, "
                              f"{growth * 100:.1f}% annual growth — {why}")


#: IBISWorld carries a life-cycle stage in every report and no S-1 does, because
#: a filer would rather not say its market is mature. It is derived from growth
#: and concentration together.
LIFECYCLE = ("emerging", "growth", "mature", "declining")


def lifecycle(growth: Optional[float],
              conc: Optional[Concentration]) -> Tuple[str, str]:
    """Life-cycle stage, from growth and concentration.

    The usual shape: young markets grow fast and are fragmented; mature ones
    grow slowly and have consolidated; declining ones shrink. Concentration
    separates "emerging" from "growth" — both grow, but an emerging market has
    not sorted itself out yet.
    """
    if growth is None:
        return "", ("growth could not be established, and life-cycle stage is "
                    "not readable without it")

    score = conc.hhi if conc else None
    if growth < 0:
        return "declining", (f"the market is contracting at "
                             f"{abs(growth) * 100:.1f}% a year")
    if growth >= 0.15:
        if score is not None and score < HHI_UNCONCENTRATED:
            return "emerging", (f"growing {growth * 100:.1f}% a year and still "
                                f"fragmented (HHI {score:,.0f}) — no structure "
                                f"has settled yet")
        return "growth", (f"growing {growth * 100:.1f}% a year with "
                          + (f"HHI {score:,.0f}" if score else
                             "concentration unknown"))
    if growth >= GROWTH_HEALTHY:
        return "growth", f"growing {growth * 100:.1f}% a year"
    return "mature", (f"growing {growth * 100:.1f}% a year, at or below general "
                      f"economic growth")


#: Barriers to entry, graded AND trended — copied from IBISWorld, which reports
#: high/medium/low alongside increasing/decreasing/steady. A level with a
#: direction is far more useful than either alone, and far more useful than a
#: paragraph.
BARRIER_LEVELS = ("low", "medium", "high")
BARRIER_TRENDS = ("decreasing", "steady", "increasing")


@dataclass
class Barriers:
    level: str = ""
    trend: str = "steady"
    reasons: List[str] = field(default_factory=list)
    because: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def barriers(*, conc: Optional[Concentration] = None,
             startup_cost: Optional[float] = None,
             licences: Optional[int] = None,
             licence_note: str = "") -> Barriers:
    """Grade barriers to entry from concentration, capital and regulation.

    Derived from other ANSWERS, never from raw evidence — which is the point of
    the denial in AGENTS.md. Three signals, each of which independently raises
    the barrier, and the reasons are listed so a reader can disagree with one
    without discarding the grade.
    """
    reasons: List[str] = []
    score = 0

    if conc is not None and conc.hhi is not None:
        if conc.hhi >= HHI_MODERATE:
            score += 2
            reasons.append(
                f"the market is highly concentrated (HHI {conc.hhi:,.0f}), so a "
                f"new entrant competes against established scale")
        elif conc.hhi >= HHI_UNCONCENTRATED:
            score += 1
            reasons.append(
                f"the market is moderately concentrated (HHI {conc.hhi:,.0f})")
        else:
            reasons.append(
                f"the market is fragmented (HHI {conc.hhi:,.0f}), which lowers "
                f"the bar for a new entrant")

    if startup_cost is not None:
        if startup_cost >= 1_000_000:
            score += 2
            reasons.append(
                f"starting requires roughly ${startup_cost:,.0f} of capital")
        elif startup_cost >= 100_000:
            score += 1
            reasons.append(
                f"starting requires roughly ${startup_cost:,.0f} of capital")
        else:
            reasons.append(
                f"capital requirements are modest, around ${startup_cost:,.0f}")

    if licences:
        score += 1
        reasons.append(licence_note or
                       f"{licences} licence or permit requirement(s) apply")

    if not reasons:
        return Barriers(because="none of concentration, capital requirement or "
                                "licensing could be established, so barriers "
                                "cannot be graded")

    level = "high" if score >= 3 else "medium" if score >= 1 else "low"
    return Barriers(
        level=level, trend="steady", reasons=reasons,
        because=f"graded {level} from {len(reasons)} signal(s); the trend is "
                f"reported as steady because establishing a direction needs two "
                f"vintages of the same series and only one was read")
