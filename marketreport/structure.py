"""Concentration, saturation and life cycle — computed, never asked.

Everything a market-research professional works out with a formula, this works
out with a formula. `RESEARCH_NOTES.md` §4 records why: a model asked to
"consider the concentration of this market" returns a plausible adjective, and
`sum(share ** 2)` returns a number with a published threshold attached to it.

The measures here are the standard ones, and the thresholds are the ones the US
antitrust agencies publish, so a reader who disagrees with our reading can
disagree with the number rather than with our taste.

One boundary runs through this module, drawn by the fourth external audit's
arithmetic. County Business Patterns counts **establishments** — physical
locations — and an establishment may belong to a multi-establishment company.
One hundred locations in the 1-4 employee band is compatible with one hundred
independent businesses (firm HHI ~100) and with a single company owning every
location (firm HHI 10,000). Firm concentration is therefore NOT IDENTIFIABLE
from CBP size bands — not noisy, not estimated: undetermined by the data. An
earlier version computed a pseudo-HHI over establishments anyway, labelled it
an estimate, and let "unconcentrated" flow into barriers and life-cycle;
the label did not stop the wrong entity's number from acquiring the real
one's authority. HHI and CR4 are now computed ONLY from actual firm-level
shares (`from_shares`). What CBP does support — establishment-size
dispersion, density, scale — lives in `shape()`, named as what it is.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: US DOJ/FTC 2023 Merger Guidelines (§2.4): below 1,000 unconcentrated,
#: 1,000-1,800 moderately concentrated, above 1,800 highly concentrated.
#: The vintage is stated because an earlier version quoted the withdrawn
#: 2010 thresholds (1,500/2,500) while calling them current.
HHI_UNCONCENTRATED = 1_000
HHI_MODERATE = 1_800

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
                f"HHI {score:,.0f} is below {HHI_UNCONCENTRATED:,}, the 2023 "
                f"US merger-guideline threshold for an unconcentrated market")
    if score < HHI_MODERATE:
        return ("moderately concentrated",
                f"HHI {score:,.0f} falls between {HHI_UNCONCENTRATED:,} and "
                f"{HHI_MODERATE:,}")
    return ("highly concentrated",
            f"HHI {score:,.0f} is above {HHI_MODERATE:,}, the threshold for a "
            f"highly concentrated market")


def from_size_bands(bands: Dict[str, int]) -> Concentration:
    """Firm concentration from CBP size bands: NOT identifiable — and said so.

    An earlier version treated every establishment as an independent firm and
    computed an "estimated" HHI. The fourth external audit did the arithmetic
    that kills it: 100 establishments in the 1-4 band yields the same CBP row
    whether they are 100 independent businesses (firm HHI ~100) or one
    company's 100 locations (firm HHI 10,000). No caveat rescues a number
    about the wrong entity, so none is produced. The dispersion measures in
    `shape()` carry what the data DOES support.
    """
    total = sum(int(v) for v in (bands or {}).values()
                if v and str(v).strip())
    if not total:
        return Concentration(
            basis="not-identifiable", reading="",
            because="no usable size-band data",
            caveat="County Business Patterns suppresses size-band detail for "
                   "small geographies to protect individual businesses")
    return Concentration(
        hhi=None, cr4=None, firms=None, basis="not-identifiable",
        reading="not identifiable from establishment data",
        because=(f"County Business Patterns counts {total:,} establishments "
                 f"— physical locations — and an establishment may belong to "
                 f"a multi-establishment company. The same counts are "
                 f"compatible with {total:,} independent businesses and with "
                 f"one company owning every location, so firm concentration "
                 f"(HHI, CR4) is undetermined by this data"),
        caveat="Use the establishment-size dispersion measures instead: they "
               "describe locations, which is what this data counts.")


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


def cagr(start: float, end: float, years: float) -> Optional[float]:
    """Compound annual rate taking `start` to `end` over `years`.

    Extracted from the growth agent so it can be checked against filings that
    publish both their endpoints and their answer. Inline arithmetic inside an
    agent is arithmetic nothing outside the repository ever grades, which is how
    an inverted CAGR survives a green test suite.

    Returns None rather than raising on the degenerate inputs, because a growth
    section that cannot be computed must say so, not blow up the report.
    """
    if years <= 0 or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def penetration(served: float, base: float) -> Optional[float]:
    """Share of the addressable base that is served.

    The direction matters and is easy to get backwards: Cricut's filing reports
    3.7M users against an 85M SAM as "more than 4%". Inverted it reads 2,297%,
    which is absurd enough to catch by eye and exactly the kind of thing that
    passes silently when nothing checks it against a published answer.
    """
    if base <= 0:
        return None
    return served / base


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


# --------------------------------------------------------------------------
# Measures for markets HHI cannot describe.
#
# HHI is built for firm-level revenue shares in markets with few players. Most
# markets somebody asks this tool about are fragmented local trades, where it
# lands far below the 1,500 threshold and reports "unconcentrated" — true, and
# carrying almost no information beyond the establishment count the reader
# already has.
#
# Worse, it measures share EQUALITY and says nothing about scale: 1,422 sole
# traders and 1,422 large firms produce an identical HHI and an identical
# reading, while being completely different markets to enter.
#
# These are the measures that discriminate where HHI does not.
# --------------------------------------------------------------------------

@dataclass
class Shape:
    """What a fragmented market actually looks like."""

    establishments: Optional[int] = None
    #: Establishments per 100,000 people — is this geography over-served?
    per_capita: Optional[float] = None
    #: The national rate, for comparison. The number alone means nothing.
    national_per_capita: Optional[float] = None
    #: Employment share held by the largest decile of establishments.
    top_decile_share: Optional[float] = None
    #: Mean employees per establishment. Separates a trade of sole operators
    #: from one of substantial firms — the distinction HHI is blind to.
    average_size: Optional[float] = None
    reading: str = ""
    because: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


#: How far above the national rate a geography must be before it is described
#: as crowded. Conventional, and stated so it can be argued with.
CROWDED_RATIO = 1.25
SPARSE_RATIO = 0.80


def shape(bands: Dict[str, int], *, population: Optional[int] = None,
          national_bands: Optional[Dict[str, int]] = None,
          national_population: Optional[int] = None) -> Shape:
    """Describe a market HHI would call 'unconcentrated' and leave at that."""
    total = sum(int(v) for v in (bands or {}).values() if v)
    if not total:
        return Shape(because="no establishment counts were available")

    employment = sum(SIZE_BAND_MIDPOINTS.get(str(k).strip(), 0.0) * int(v)
                     for k, v in bands.items() if v)
    average = employment / total if total else None

    # Largest decile by employment. Walk the bands from the top until a tenth
    # of establishments is accounted for.
    ordered = sorted(
        ((SIZE_BAND_MIDPOINTS.get(str(k).strip(), 0.0), int(v))
         for k, v in bands.items() if v and str(k).strip() in SIZE_BAND_MIDPOINTS),
        reverse=True)
    want = max(1, int(round(total * 0.10)))
    taken = 0
    taken_employment = 0.0
    for size, count in ordered:
        use = min(count, want - taken)
        if use <= 0:
            break
        taken += use
        taken_employment += size * use
    top_decile = (taken_employment / employment) if employment else None

    per_capita = (total / population * 100_000) if population else None
    national_rate = None
    if national_bands and national_population:
        national_total = sum(int(v) for v in national_bands.values() if v)
        if national_total:
            national_rate = national_total / national_population * 100_000

    reading, because = _read_shape(per_capita, national_rate, average,
                                   top_decile, total)
    return Shape(establishments=total, per_capita=per_capita,
                 national_per_capita=national_rate,
                 top_decile_share=top_decile, average_size=average,
                 reading=reading, because=because)


def _read_shape(per_capita: Optional[float], national: Optional[float],
                average: Optional[float], top_decile: Optional[float],
                total: int) -> Tuple[str, str]:
    parts: List[str] = []
    # Two independent readings, both reported. Density says whether the
    # geography is over-served; scale says what kind of firm operates here.
    # Reporting only the first made a market of sole traders and a market of
    # large firms read identically, which is the same blindness HHI has.
    density = ""
    scale = ""

    if per_capita is not None and national:
        ratio = per_capita / national
        if ratio >= CROWDED_RATIO:
            density = "more crowded than the country as a whole"
        elif ratio <= SPARSE_RATIO:
            density = "less served than the country as a whole"
        else:
            density = "served at about the national rate"
        parts.append(f"{per_capita:.1f} establishments per 100,000 people "
                     f"against a national {national:.1f} ({ratio:.2f}x)")
    elif per_capita is not None:
        parts.append(f"{per_capita:.1f} establishments per 100,000 people, "
                     f"with no national rate to compare against")

    if average is not None:
        parts.append(f"averaging {average:.1f} employees each")
        scale = ("almost entirely sole operators and micro-businesses"
                 if average < 5 else
                 "a trade of very small operators" if average < 10 else
                 "a mix of small and mid-sized firms" if average < 50 else
                 "a market of substantial firms")

    if top_decile is not None:
        parts.append(f"the largest tenth hold {top_decile * 100:.0f}% of "
                     f"employment")
        if top_decile >= 0.50:
            parts.append("so employment is concentrated in a few larger "
                         "operators even though the firm count is not")

    reading = " — ".join(x for x in (scale, density) if x)
    return reading, (f"{total:,} establishments, " + "; ".join(parts)
                     if parts else f"{total:,} establishments")
