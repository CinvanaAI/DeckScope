"""A panel: one question, answered, carrying the form it should be drawn in.

See PANELS.md for why this exists. The short version: I produced a market-share
answer by hand that this repository could not produce, and the difference was
not the data — it was that the finding chose its own shape. Nothing in the code
could express "the shape of this answer is two pies", so the shape could never
depend on the answer.

`form` is the load-bearing field here. Everything else is bookkeeping that
already existed in one form or another.

The other thing this file carries is the provenance state of every figure, and
`DERIVED` is new. The old system only ever did arithmetic it performed itself
over data it fetched itself, so it never mixed computed and retrieved numbers in
one view. A panel mixes them constantly. When I built the cell-phone answer by
hand I put my own multiplications in a column beside published figures with no
visual distinction between them — the exact failure the provenance rendering
exists to prevent, committed an hour after I fixed it elsewhere. So the state is
explicit, it is required, and the renderers are tested for showing it.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "SOURCED", "DERIVED", "ESTIMATED", "ABSENT", "STATES",
    "Figure", "Slice", "Series", "Panel",
    "FORMS", "form_spec", "register_form", "UnknownForm",
]

# ------------------------------------------------------- provenance states

#: A source ID to go and read. The only state that is independently checkable.
SOURCED = "sourced"
#: Computed by us from other figures. Inspectable — `operands` names what went
#: in — but not something a reader can look up, because nobody published it.
DERIVED = "derived"
#: Inferred rather than computed or retrieved: a figure we reasoned to, with the
#: reasoning stated. Weaker than DERIVED and deliberately harder to read past.
ESTIMATED = "estimated"
#: Asked for and not established. Present in the panel on purpose — a figure
#: that vanishes reads as an oversight, one that says why reads as a finding.
ABSENT = "absent"

STATES = (SOURCED, DERIVED, ESTIMATED, ABSENT)


@dataclass
class Figure:
    """One number in a panel, and how we came to have it."""

    label: str
    value: Optional[float] = None
    #: The figure as the source wrote it. Kept alongside `value` because
    #: "$6-8B" carries information a midpoint does not.
    value_text: str = ""
    unit: str = ""
    state: str = SOURCED
    #: The date the fact is true *of*, not the date it was retrieved.
    as_of: str = ""
    source_ids: List[str] = field(default_factory=list)
    #: For DERIVED: the labels of the figures this was computed from, and the
    #: arithmetic in words. A derived number whose operands are not shown is an
    #: assertion wearing a calculation's clothes.
    operands: List[str] = field(default_factory=list)
    how: str = ""
    #: For ABSENT: what stopped us.
    because: str = ""
    #: The finding this came from, so a panel can be traced back to the run.
    finding_id: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(
                f"'{self.state}' is not a provenance state; one of {STATES}. "
                f"Defaulting would let an unknown state render as sourced, "
                f"which is the one direction that must never happen silently.")
        if self.state == SOURCED and not self.source_ids:
            raise ValueError(
                f"figure {self.label!r} claims to be sourced and names no "
                f"source. A source list that can be empty is a provenance "
                f"badge available to anything that asks for one.")
        if self.state == DERIVED and not self.operands:
            raise ValueError(
                f"figure {self.label!r} is derived and names no operands. "
                f"Showing the arithmetic is the whole difference between a "
                f"derived figure and an asserted one.")
        if self.state == ABSENT and not self.because:
            raise ValueError(
                f"figure {self.label!r} is absent and does not say why. "
                f"'No data' is not a finding; 'the tracker publishes revenue "
                f"share only for the top two' is.")

    @property
    def checkable(self) -> bool:
        """Whether a reader could go and verify this themselves."""
        return self.state == SOURCED and bool(self.source_ids)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label, "value": self.value,
            "value_text": self.value_text, "unit": self.unit,
            "state": self.state, "as_of": self.as_of,
            "source_ids": list(self.source_ids), "operands": list(self.operands),
            "how": self.how, "because": self.because,
            "finding_id": self.finding_id, "note": self.note,
            "checkable": self.checkable,
        }


@dataclass
class Slice:
    """One wedge, bar or point — a named quantity inside a series."""

    label: str
    value: float
    #: What the source actually said, when it differs from the plotted number.
    value_text: str = ""
    state: str = SOURCED
    source_ids: List[str] = field(default_factory=list)
    finding_id: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(f"'{self.state}' is not a provenance state")

    def to_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "value": self.value,
                "value_text": self.value_text, "state": self.state,
                "source_ids": list(self.source_ids),
                "finding_id": self.finding_id, "note": self.note}


@dataclass
class Series:
    """A set of slices that belong on one chart, and what they measure.

    `measure` and `unit` are required and not decorative. The whole cell-phone
    finding was that two series over the same population measure different
    things — units and dollars — and a chart pair that does not say which is
    which reproduces the confusion it exists to resolve.
    """

    label: str
    measure: str
    unit: str = "%"
    slices: List[Slice] = field(default_factory=list)
    as_of: str = ""
    #: The tracker or dataset this series came from. Named per-series because
    #: two series in one panel legitimately come from different publishers, and
    #: a single panel-level source line would hide that.
    basis: str = ""

    @property
    def total(self) -> float:
        return sum(s.value for s in self.slices)

    def sums_to(self, target: float = 100.0, tolerance: float = 1.5) -> bool:
        return abs(self.total - target) <= tolerance

    @property
    def overfull(self) -> bool:
        """Whether the parts add up to more than the whole.

        The asymmetry matters. A share series summing to 72% is *correct* when
        the publisher only breaks out the top five — it is a disclosure, not a
        defect, and the missing 28% gets said out loud. A series summing to 115%
        is arithmetically impossible and means two slices are double-counting
        the same firms, which no amount of disclosure fixes.
        """
        return self.unit == "%" and self.total > 100.0 + 1.5

    @property
    def unaccounted(self) -> float:
        """How much of the population these slices do not cover."""
        if self.unit != "%":
            return 0.0
        return max(0.0, round(100.0 - self.total, 1))

    def to_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "measure": self.measure,
                "unit": self.unit, "as_of": self.as_of, "basis": self.basis,
                "total": round(self.total, 3),
                "slices": [s.to_dict() for s in self.slices]}


# ------------------------------------------------------------------- forms

class UnknownForm(Exception):
    """A panel named a form nothing can draw.

    Raised rather than falling back to a table. A caller who asked for a
    comparison and silently received a list has been handed something that looks
    like it worked — the same rule `document.render_as` follows for formats.
    """


@dataclass
class FormSpec:
    """What a form is for, and what a panel must supply to use it.

    `job` is written out because the form registry doubles as the menu the
    shaper chooses from. A form with a vague job gets chosen for vague reasons.
    """

    name: str
    job: str
    min_series: int = 1
    max_series: int = 1
    min_slices: int = 2

    def check(self, panel: "Panel") -> List[str]:
        """Everything wrong with using this form for this panel."""
        problems: List[str] = []
        count = len(panel.series)
        if count < self.min_series:
            problems.append(f"{self.name} needs at least {self.min_series} "
                            f"series and the panel has {count}")
        if count > self.max_series:
            problems.append(f"{self.name} takes at most {self.max_series} "
                            f"series and the panel has {count}")
        for series in panel.series:
            if len(series.slices) < self.min_slices:
                problems.append(f"series {series.label!r} has "
                                f"{len(series.slices)} points; {self.name} "
                                f"needs {self.min_slices}")
        return problems


#: The starting set. The test for adding one is that a real question needed it —
#: `share_pair` is here because the cell-phone answer could not be carried by a
#: single pie, and inventing forms ahead of a question that wants them is how a
#: menu grows options nobody picks for good reasons.
FORMS: Dict[str, FormSpec] = {}


def register_form(spec: FormSpec) -> FormSpec:
    FORMS[spec.name] = spec
    return spec


register_form(FormSpec(
    "share", "one population split into parts — who has how much",
    min_series=1, max_series=1, min_slices=2))
register_form(FormSpec(
    "share_pair",
    "the same population split two ways, where the difference IS the finding",
    min_series=2, max_series=2, min_slices=2))
register_form(FormSpec(
    "ranking", "ordered magnitudes — who is biggest, by how much",
    min_series=1, max_series=1, min_slices=2))
register_form(FormSpec(
    "trend", "one measure over time",
    min_series=1, max_series=4, min_slices=2))
register_form(FormSpec(
    "stat", "a single number that is itself the answer",
    min_series=0, max_series=1, min_slices=0))
register_form(FormSpec(
    "table", "more classes than a chart can carry without lying",
    min_series=1, max_series=4, min_slices=1))


def form_spec(name: str) -> FormSpec:
    spec = FORMS.get((name or "").strip().lower())
    if spec is None:
        raise UnknownForm(
            f"there is no '{name}' form; available: "
            + ", ".join(sorted(FORMS)))
    return spec


# ------------------------------------------------------------------- panel

@dataclass
class Panel:
    """One question, answered, with the shape of its answer.

    Deliberately a *record* rather than a rendering. It holds the findings, the
    source IDs, the series and the form, so re-rendering re-runs nothing and two
    people looking at the same panel see the same panel. That is what replaces
    determinism once a model is in the loop: not that the run cannot vary, but
    that its output is a fixed artifact that can be kept, diffed and argued with.
    """

    question: str
    headline: str = ""
    form: str = "table"
    figures: List[Figure] = field(default_factory=list)
    series: List[Series] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    #: Source IDs, resolvable against the run's SourceRegistry.
    source_ids: List[str] = field(default_factory=list)
    #: Human-readable publishers, for a rendering that has no registry to hand.
    source_labels: List[str] = field(default_factory=list)
    #: Which specialist produced this.
    agent: str = ""
    #: Set when the question could not be answered at all. A panel that failed
    #: is still a panel — it says what was tried and what stopped it.
    problem: str = ""
    generated: str = field(
        default_factory=lambda: _dt.datetime.now().replace(
            microsecond=0).isoformat())
    #: What the run read and spent, for the audit trail.
    provenance: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------- checking
    @property
    def answered(self) -> bool:
        return bool(self.headline) and not self.problem

    @property
    def checkable_figures(self) -> List[Figure]:
        return [f for f in self.figures if f.checkable]

    def coverage(self) -> Dict[str, Any]:
        """How much of this panel a reader could verify.

        Counted rather than asserted, and split by state, because "12 figures
        with sources" and "3 sourced, 9 of my own arithmetic" are different
        panels that look identical from a distance.
        """
        by_state = {state: 0 for state in STATES}
        for figure in self.figures:
            by_state[figure.state] = by_state.get(figure.state, 0) + 1
        total = len(self.figures)
        return {
            "figures": total,
            "sourced": by_state[SOURCED],
            "derived": by_state[DERIVED],
            "estimated": by_state[ESTIMATED],
            "absent": by_state[ABSENT],
            "checkable": len(self.checkable_figures),
            "fraction_checkable": (round(len(self.checkable_figures) / total, 3)
                                   if total else 0.0),
        }

    def problems(self) -> List[str]:
        """Everything structurally wrong with this panel.

        Separate from raising, because a panel with a problem should still be
        renderable — the problems get shown. A panel that refuses to exist
        because one series is short teaches the reader nothing.
        """
        found: List[str] = []
        if not self.question.strip():
            found.append("the panel does not say what question it answers")
        if self.answered and not self.figures and not self.series:
            found.append("the panel has a headline and no figures behind it")

        try:
            spec = form_spec(self.form)
        except UnknownForm as exc:
            found.append(str(exc))
            return found

        found.extend(spec.check(self))

        for series in self.series:
            if series.slices and series.overfull:
                found.append(
                    f"series {series.label!r} sums to {series.total:.1f}% — "
                    f"more than the whole market. Two slices are counting the "
                    f"same firms, and unlike an incomplete series this cannot "
                    f"be fixed by disclosing it")

        # One entity, one wedge. Two sources reporting different numbers for
        # the same company is a real and interesting disagreement — but it is a
        # finding to report, not two slices to draw. Left alone the chart shows
        # Samsung twice, the shares sum past 100, and the duplicate reads as a
        # second company nobody has heard of.
        for series in self.series:
            seen: Dict[str, int] = {}
            for wedge in series.slices:
                key = wedge.label.strip().lower()
                seen[key] = seen.get(key, 0) + 1
            for label, count in seen.items():
                if count > 1:
                    found.append(
                        f"{label!r} appears {count} times in series "
                        f"{series.label!r}. Sources disagreeing about one "
                        f"company is a finding to report, not two wedges to "
                        f"draw.")

        # Every slice must trace to something. A wedge with no provenance is a
        # number that arrived from nowhere and reads as measured.
        for series in self.series:
            for wedge in series.slices:
                if wedge.state == SOURCED and not (wedge.source_ids
                                                   or wedge.finding_id):
                    found.append(f"slice {wedge.label!r} in {series.label!r} "
                                 f"claims a source and names none")
        return found

    def valid(self) -> bool:
        return not self.problems()

    # -------------------------------------------------------------- output
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "headline": self.headline,
            "form": self.form,
            "agent": self.agent,
            "answered": self.answered,
            "problem": self.problem,
            "generated": self.generated,
            "figures": [f.to_dict() for f in self.figures],
            "series": [s.to_dict() for s in self.series],
            "caveats": list(self.caveats),
            "source_ids": list(self.source_ids),
            "source_labels": list(self.source_labels),
            "coverage": self.coverage(),
            "problems": self.problems(),
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Panel":
        """Rebuild a panel from its record.

        The round trip is what makes a panel a saved artifact rather than a
        transient view: the gallery reads these back without re-running
        anything, and a stored panel outlives the process that made it.
        """
        panel = cls(
            question=data.get("question", ""),
            headline=data.get("headline", ""),
            form=data.get("form", "table"),
            agent=data.get("agent", ""),
            problem=data.get("problem", ""),
            caveats=list(data.get("caveats") or []),
            source_ids=list(data.get("source_ids") or []),
            source_labels=list(data.get("source_labels") or []),
            provenance=dict(data.get("provenance") or {}),
        )
        if data.get("generated"):
            panel.generated = data["generated"]
        for raw in data.get("figures") or []:
            panel.figures.append(Figure(
                label=raw.get("label", ""), value=raw.get("value"),
                value_text=raw.get("value_text", ""), unit=raw.get("unit", ""),
                state=raw.get("state", SOURCED), as_of=raw.get("as_of", ""),
                source_ids=list(raw.get("source_ids") or []),
                operands=list(raw.get("operands") or []),
                how=raw.get("how", ""), because=raw.get("because", ""),
                finding_id=raw.get("finding_id", ""), note=raw.get("note", "")))
        for raw in data.get("series") or []:
            panel.series.append(Series(
                label=raw.get("label", ""), measure=raw.get("measure", ""),
                unit=raw.get("unit", "%"), as_of=raw.get("as_of", ""),
                basis=raw.get("basis", ""),
                slices=[Slice(
                    label=s.get("label", ""), value=float(s.get("value") or 0),
                    value_text=s.get("value_text", ""),
                    state=s.get("state", SOURCED),
                    source_ids=list(s.get("source_ids") or []),
                    finding_id=s.get("finding_id", ""), note=s.get("note", ""))
                    for s in raw.get("slices") or []]))
        return panel


def unanswered(question: str, because: str, *, agent: str = "") -> Panel:
    """A panel for a question that could not be answered.

    Still a panel, and still rendered. The alternative — returning nothing — is
    how a report comes to look more complete than the run behind it.
    """
    return Panel(question=question, problem=because, agent=agent, form="stat")
