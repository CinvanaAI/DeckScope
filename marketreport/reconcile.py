"""Reading the finished reports back against the claims that dispatched them.

The half of the handoff that was missing. The scoper decides which deck
claims need checking and dispatches a report per claim; until this module,
that was where the thread ended — the reports landed in the library and the
person holding the deck was left to do the comparison themselves, which is
the analysis they came for. "Someone brings me a pitch deck and I get a
market share report? Not so useful." This is the step that makes it useful:
claim, then what the report established, then the bearing of one on the
other, in one document.

The structure is deterministic — the claim is the scoper's own `because`,
the finding is the panel's headline and figures with their source IDs, the
storage id is printed so the full report is one command away. Only the
`bearing` sentence asks a model to read the two against each other, and when
that call fails the document still stands with the claim and the finding
side by side and says the reading is missing — an absent judgment stated
beats a fabricated one, as everywhere else in this codebase.

An unanswered report reconciles too, and the wording matters: "nobody
publishes this basis" bears on a deck claim differently than silence would —
it means the deck's number rests on something no reader can check, and the
report saying so IS the finding.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

__all__ = ["Entry", "entry_for", "bearing", "document"]


class Entry:
    """One dispatched report, read back against its claim."""

    def __init__(self, claim: str, specialist: str, measure_label: str,
                 headline: str, answered: bool, figures: List[str],
                 stored_id: str, reading: str) -> None:
        self.claim = claim
        self.specialist = specialist
        self.measure_label = measure_label
        self.headline = headline
        self.answered = answered
        self.figures = figures
        self.stored_id = stored_id
        self.reading = reading

    def to_dict(self) -> Dict[str, Any]:
        return dict(claim=self.claim, specialist=self.specialist,
                    measure_label=self.measure_label, headline=self.headline,
                    answered=self.answered, figures=list(self.figures),
                    stored_id=self.stored_id, reading=self.reading)


_BEARING_SYSTEM = """You are reading one independent market report against one claim from a pitch deck.

You get the claim the report was dispatched to check, and what the report
established — its headline finding and its key figures, each figure tagged with
the source ID it rests on.

Write 2-4 sentences on the bearing of the finding on the claim: does it support
it, contradict it, or leave it untestable? Quote the report's figures with their
source IDs (like [S2]) when they carry the point. If the report established that
nobody publishes the figure, say what that means for the claim: it rests on a
number no reader can check, which is itself information.

Rules: only the figures given here — nothing from memory. No verdict on the
company, only on this one claim. If the finding and the claim talk past each
other (different basis, different geography), say so plainly instead of forcing
a comparison.
"""


def bearing(claim: str, panel: Any, provider: Any) -> str:
    """One model reading of report-vs-claim, or an honest absence."""
    lines = [f"THE DECK CLAIM THIS REPORT WAS DISPATCHED TO CHECK:\n{claim}",
             "", "WHAT THE REPORT ESTABLISHED:"]
    if getattr(panel, "answered", False):
        lines.append(f"Headline: {panel.headline}")
    else:
        lines.append(f"Not established: {getattr(panel, 'problem', '') or 'no reason recorded'}")
    for fig in list(getattr(panel, "figures", []))[:8]:
        ids = " ".join(f"[{s}]" for s in (getattr(fig, "source_ids", None) or []))
        lines.append(f"- {fig.label}: {fig.value_text} {ids}".rstrip())
    try:
        text = provider.complete(_BEARING_SYSTEM, "\n".join(lines),
                                 temperature=0.2)
        text = (getattr(text, "text", None) or str(text)).strip()
        return text[:1200] if text else _fallback()
    except Exception:  # noqa: BLE001 - the document must stand without the reading
        return _fallback()


def _fallback() -> str:
    return ("(No reading was produced — the model call failed. The claim and "
            "the report's finding are printed above; read them against each "
            "other directly.)")


def entry_for(brief: Any, panel: Any, stored_id: str, provider: Any) -> Entry:
    figures = []
    for fig in list(getattr(panel, "figures", []))[:5]:
        ids = " ".join(f"[{s}]" for s in (getattr(fig, "source_ids", None) or []))
        figures.append(f"{fig.label}: {fig.value_text} {ids}".rstrip())
    claim = brief.because or f"(the scoper recorded no specific claim; the report covers {brief.market})"
    return Entry(
        claim=claim,
        specialist=brief.specialist,
        measure_label=getattr(panel, "measure_label", "") or getattr(panel, "measure", ""),
        headline=(panel.headline if getattr(panel, "answered", False)
                  else f"Could not be established: {getattr(panel, 'problem', '') or 'no reason recorded'}"),
        answered=bool(getattr(panel, "answered", False)),
        figures=figures,
        stored_id=stored_id,
        reading=bearing(claim, panel, provider),
    )


def document(entries: Sequence[Entry], *, market: str,
             definition: str = "", company: str = "") -> str:
    """The reconciliation as one markdown document."""
    L: List[str] = []
    add = L.append
    title = f"What the market reports say about {company or 'this deck'}'s claims"
    add(f"# {title}")
    add("")
    add(f"Market as scoped: **{market}**"
        + (f" — {definition}" if definition else ""))
    add("")
    add("Each report below was dispatched to check one specific claim the deck "
        "makes. The finding is the report's own, with its source IDs; the full "
        "report, chart and bibliography included, is stored under the ID shown "
        "— open it with `deckscope panels`.")
    add("")
    for i, e in enumerate(entries, 1):
        add(f"## {i}. The deck's claim")
        add("")
        add(f"> {e.claim}")
        add("")
        add(f"**Checked by:** {e.specialist} report"
            + (f" ({e.measure_label})" if e.measure_label else "")
            + f" · stored as `{e.stored_id}`")
        add("")
        add(f"**What it established:** {e.headline}")
        add("")
        for fig in e.figures:
            add(f"- {fig}")
        if e.figures:
            add("")
        add(f"**Bearing on the claim:** {e.reading}")
        add("")
    add("---")
    add("")
    add("_Source IDs refer to each stored report's own bibliography. An "
        "unestablished finding is a result, not a failure: it means the "
        "deck's number rests on something no independent reader can check._")
    add("")
    return "\n".join(L)
