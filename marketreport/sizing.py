"""Market sizing that shows its arithmetic.

Derived from what filings actually do, not from what a market report ought to
look like. Five S-1s in `market-corpus/` size their market the same way:

    size  =  COUNT of units  ×  RATE that qualify  ×  VALUE per unit per year

Klaviyo multiplies business counts by its own ARR per employee-size band. FIGS
takes 20 million healthcare professionals from BLS, the 85% who buy their own
uniforms, and a per-head spend. agilon takes 17.5 million Medicare beneficiaries
from CMS and $10,000 of revenue per member. Cricut takes an adult population and
a survey incidence rate.

Two things that fall out of reading them, which this module exists to enforce:

**The arithmetic is the product.** "$34 billion" is an assertion. "N businesses
in these size bands × $R average revenue, from these two sources, as of this
date" is a claim somebody can check and disagree with. Every filing that does
this well states its operands. So `Ring.arithmetic()` is not a debugging aid — it
is the thing being sold.

**A missing term is not a zero.** If the value per unit cannot be sourced, the
size is `None` and the report says which term was missing. The tempting failure
is to substitute something plausible and carry on, which produces a confident
number nobody can trace. That is the exact failure this whole project exists to
catch in other people's documents.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

#: How a term was arrived at. `assumed` is legitimate and common — every filing
#: does it — but it has to be visible, and §1a of the derived schema is the
#: reason: the one term nobody publishes is the value per unit.
MEASURED = "measured"      # read from a published dataset
DERIVED = "derived"        # computed from other measured terms
ASSUMED = "assumed"        # stated by a human, must carry a range
UNAVAILABLE = "unavailable"  # nobody publishes it and none was supplied
METHODS = (MEASURED, DERIVED, ASSUMED, UNAVAILABLE)

#: A child ring may exceed its parent by this much before it is treated as an
#: error rather than as rounding between two vintages of the same series.
NESTING_TOLERANCE = 1.02


class SizingError(ValueError):
    """The arithmetic is impossible, not merely unknown."""


@dataclass
class Term:
    """One factor, with where it came from.

    `value` may be None, which means "not established". Callers must never
    coerce that to zero — see the module docstring.
    """

    kind: str                       # count | rate | value
    value: Optional[float]
    unit: str = ""
    as_of: str = ""                 # the date the figure is true OF
    source: str = ""                # "Census CBP" / "CMS" / "assumption"
    source_url: str = ""
    method: str = MEASURED
    #: Assumed terms carry a plausible range. A point estimate presented without
    #: one is how "we believe our international opportunity is at least as large
    #: as our domestic opportunity" doubles a headline unchallenged.
    low: Optional[float] = None
    high: Optional[float] = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.method not in METHODS:
            self.method = MEASURED
        if self.method == ASSUMED and self.low is None and self.high is None:
            # Not fatal, but recorded, because an unranged assumption reads
            # exactly like a measurement once it is in a table.
            self.note = (self.note + " " if self.note else "") + \
                "assumed without a stated range"
        if self.value is not None and self.value < 0:
            raise SizingError(
                f"a {self.kind} term cannot be negative (got {self.value}). "
                f"Negative magnitudes here are almost always a parsing bug — a "
                f"range like '$6-8B' read as a subtraction.")
        if self.kind == "rate" and self.value is not None and self.value > 1.0:
            raise SizingError(
                f"a rate must be a fraction between 0 and 1, got {self.value}. "
                f"Percentages must be divided before they reach this.")

    @property
    def known(self) -> bool:
        return self.value is not None and self.method != UNAVAILABLE

    @property
    def sourced(self) -> bool:
        """Whether a reader could go and check this."""
        return self.known and self.method in (MEASURED, DERIVED) \
            and bool(self.source)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["known"] = self.known
        d["sourced"] = self.sourced
        return d


@dataclass
class Ring:
    """One geography, sized.

    Named for the concentric narrowing agilon health does — $175B nationally,
    $80B in states where it operates, $24B in counties where it operates. That
    is the single most useful thing in the corpus and it is reproducible from
    government data, because the narrowing is purely geographic.
    """

    label: str                      # "United States" | "Arizona" | "Maricopa County"
    count: Term
    value: Term
    rate: Optional[Term] = None
    note: str = ""

    @property
    def terms(self) -> List[Term]:
        return [t for t in (self.count, self.rate, self.value) if t is not None]

    @property
    def missing(self) -> List[str]:
        return [t.kind for t in self.terms if not t.known]

    @property
    def size(self) -> Optional[float]:
        """The market size, or None if any term is unknown.

        None rather than a partial answer. A sizing missing its value term is
        not "the count" — it is not a size at all, and returning the count would
        be a category error that reads as a dollar figure.
        """
        if self.missing:
            return None
        total = self.count.value * self.value.value
        if self.rate is not None:
            total *= self.rate.value
        return total

    @property
    def qualified_count(self) -> Optional[float]:
        """Units after the rate filter — useful even when value is unknown."""
        if not self.count.known:
            return None
        if self.rate is None:
            return self.count.value
        if not self.rate.known:
            return None
        return self.count.value * self.rate.value

    def arithmetic(self) -> str:
        """The calculation, written out. This is the deliverable."""
        parts = [_fmt(self.count.value, self.count.unit or "units")]
        if self.rate is not None:
            parts.append(_pct(self.rate.value))
        parts.append(_fmt(self.value.value, self.value.unit or "per unit"))
        left = "  ×  ".join(parts)
        if self.missing:
            return f"{left}  =  not established ({', '.join(self.missing)} missing)"
        return f"{left}  =  {_money(self.size)}"

    def provenance(self, *, brief: Optional[set] = None) -> List[str]:
        """Where each term came from.

        `brief` holds reasons already stated once elsewhere in the report. One
        missing API key blocks six terms across three rings, and printing the
        same three-hundred-character remedy six times buries the one line the
        reader needs to act on. The reason is stated once; the rings then just
        point at it.
        """
        out = []
        for t in self.terms:
            if not t.known:
                reason = t.note or "no source"
                if brief is not None and reason in brief:
                    out.append(f"{t.kind}: NOT ESTABLISHED — see above")
                else:
                    out.append(f"{t.kind}: NOT ESTABLISHED — {reason}")
            elif t.method == ASSUMED:
                span = (f" (range {_num(t.low)}–{_num(t.high)})"
                        if t.low is not None or t.high is not None else "")
                out.append(f"{t.kind}: ASSUMED{span} — {t.note or 'stated, not measured'}")
            else:
                stamp = f", as of {t.as_of}" if t.as_of else ""
                out.append(f"{t.kind}: {t.source}{stamp}")
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "size": self.size,
            "qualified_count": self.qualified_count,
            "arithmetic": self.arithmetic(),
            "provenance": self.provenance(),
            "missing": self.missing,
            "terms": {t.kind: t.to_dict() for t in self.terms},
            "note": self.note,
        }


class Sizing:
    """A market sized across nested geographies.

    Rings are added widest-first. The nesting is checked rather than trusted:
    a county figure larger than its state means one of the two is wrong, and
    saying so is more useful than reporting both.
    """

    def __init__(self, market: str, *, basis: str = "") -> None:
        self.market = market
        #: Which archetype this is — establishments, population, or programme.
        #: Recorded because the reader should know which kind of number this is.
        self.basis = basis
        self.rings: List[Ring] = []
        self.warnings: List[str] = []

    def add(self, ring: Ring) -> Ring:
        self.rings.append(ring)
        self._check_nesting()
        return ring

    def _check_nesting(self) -> None:
        """Each ring must be no larger than the one before it.

        A computed invariant, not a request in a prompt. Two datasets at
        different vintages, or a NAICS code that means something different at
        county level, will silently produce a county market bigger than the
        national one — and it looks completely normal in a table.
        """
        self.warnings = [w for w in self.warnings if "nesting" not in w]
        prior: Optional[Ring] = None
        for ring in self.rings:
            if prior is not None and ring.size is not None and prior.size:
                if ring.size > prior.size * NESTING_TOLERANCE:
                    self.warnings.append(
                        f"nesting: {ring.label} ({_money(ring.size)}) is larger "
                        f"than {prior.label} ({_money(prior.size)}), which it is "
                        f"contained by. One of the two figures is wrong — most "
                        f"often a mismatched vintage or an industry code that "
                        f"covers different activity at the two levels.")
            if ring.size is not None:
                prior = ring

    @property
    def headline(self) -> Optional[float]:
        return self.rings[0].size if self.rings else None

    def unsourced(self) -> List[str]:
        """Every term a reader could not go and check."""
        out = []
        for ring in self.rings:
            for t in ring.terms:
                if not t.sourced:
                    label = "not established" if not t.known else t.method
                    out.append(f"{ring.label} / {t.kind}: {label}")
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market,
            "basis": self.basis,
            "headline": self.headline,
            "rings": [r.to_dict() for r in self.rings],
            "unsourced": self.unsourced(),
            "warnings": list(self.warnings),
        }

    def blockers(self) -> List[str]:
        """Distinct reasons that stopped a term being established.

        Distinct, because one unset API key blocks every term in the report and
        is one problem with one fix, not six.
        """
        seen: List[str] = []
        for ring in self.rings:
            for t in ring.terms:
                if not t.known:
                    reason = t.note or "no source"
                    if reason not in seen:
                        seen.append(reason)
        return seen

    def render(self) -> str:
        """The sizing as a reader sees it: rings, arithmetic, provenance."""
        lines = [f"MARKET SIZE — {self.market}"]
        if self.basis:
            lines.append(f"Basis: {self.basis}")
        lines.append("")

        blockers = self.blockers()
        if blockers:
            blocked = sum(1 for r in self.rings for t in r.terms if not t.known)
            lines.append(f"  NOTHING COULD BE SIZED — {len(blockers)} problem(s) "
                         f"blocking {blocked} term(s)"
                         if all(r.size is None for r in self.rings) else
                         f"  {len(blockers)} problem(s) blocking {blocked} term(s)")
            for b in blockers:
                lines.append(f"    ! {b}")
            lines.append("")

        already = set(blockers)
        for ring in self.rings:
            lines.append(f"  {ring.label}")
            lines.append(f"    {ring.arithmetic()}")
            for row in ring.provenance(brief=already):
                lines.append(f"      {row}")
            if ring.note:
                lines.append(f"      note: {ring.note}")
            lines.append("")
        if self.warnings:
            lines.append("  PROBLEMS WITH THIS CALCULATION")
            for w in self.warnings:
                lines.append(f"    ! {w}")
            lines.append("")
        gaps = self.unsourced()
        if gaps:
            lines.append("  WHAT YOU CANNOT CHECK")
            for g in gaps:
                lines.append(f"    - {g}")
        return "\n".join(lines)


# ------------------------------------------------------------------ formatting

def _money(v: Optional[float]) -> str:
    if v is None:
        return "not established"
    for cut, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= cut:
            return f"${v / cut:,.1f}{suffix}"
    return f"${v:,.0f}"


def _num(v: Optional[float]) -> str:
    if v is None:
        return "?"
    for cut, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= cut:
            return f"{v / cut:,.1f}{suffix}"
    return f"{v:,.0f}"


def _pct(v: Optional[float]) -> str:
    return "?" if v is None else f"{v * 100:,.1f}%"


def _fmt(v: Optional[float], unit: str) -> str:
    if v is None:
        return f"? {unit}"
    if unit.strip().startswith("$") or unit.lower().startswith("usd"):
        return f"{_money(v)} {unit.lstrip('$ ')}".strip()
    return f"{_num(v)} {unit}".strip()
