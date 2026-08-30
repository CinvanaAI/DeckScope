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


_CITE = __import__("re").compile(r"\[(S\d{1,4}|A\d{1,4})\]",
                                 __import__("re").IGNORECASE)


def scrub_reading(text: str, allowed: set) -> str:
    """Remove citations the reading invented — the fourth audit's bypass.

    bearing() is model output produced AFTER the run's citation audit and
    outside its traversal, so a fabricated [S999] used to ride into the
    reconciliation document unchecked — the one class of text the product
    promises cannot exist. The valid namespace here is the panel's own ids,
    exactly the ones shown in the prompt; anything else is removed and the
    removal is announced, matching the run-level audit's strip semantics.
    """
    removed = []

    def swap(match):
        sid = match.group(1).upper()
        if sid in allowed:
            return f"[{sid}]"
        removed.append(sid)
        return "[citation removed: not in this report's evidence]"

    out = _CITE.sub(swap, text or "")
    if removed:
        out += ("\n(The reading cited "
                + ", ".join(sorted(set(removed)))
                + ", which are not in this report's evidence — removed by "
                  "the reconciliation audit.)")
    return out


def bearing(claim: str, panel: Any, provider: Any,
            on_usage: Any = None) -> str:
    """One model reading of report-vs-claim, or an honest absence.

    The audit that matters here: `LLMProvider.complete` takes a LIST of
    Message objects, not a bare string. The first version passed a string,
    every real provider raised, the except swallowed it — and every bearing
    would have been the fallback text, forever, on every real run. The
    fakes in the tests had the same wrong signature, which is why the tests
    were green: an author's fake tests the author's assumption. The fakes
    now enforce the real contract.
    """
    from deckscope.providers.base import Message

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
        out = provider.complete(_BEARING_SYSTEM,
                                [Message("user", "\n".join(lines))],
                                temperature=0.2)
        if on_usage is not None:
            # These calls spend real tokens; a receipt that omits them is
            # the honesty artifact undercounting (found by self-audit).
            on_usage(out)
        text = (getattr(out, "text", None) or str(out)).strip()
        return text[:1200] if text else _fallback()
    except Exception:  # noqa: BLE001 - the document must stand without the reading
        return _fallback()


def _fallback() -> str:
    return ("(No reading was produced — the model call failed. The claim and "
            "the report's finding are printed above; read them against each "
            "other directly.)")


def entry_for(brief: Any, panel: Any, stored_id: str, provider: Any,
              on_usage: Any = None) -> Entry:
    figures = []
    for fig in list(getattr(panel, "figures", []))[:5]:
        ids = " ".join(f"[{s}]" for s in (getattr(fig, "source_ids", None) or []))
        figures.append(f"{fig.label}: {fig.value_text} {ids}".rstrip())
    claim = brief.because or f"(the scoper recorded no specific claim; the report covers {brief.market})"
    allowed = {str(s).upper()
               for fig in list(getattr(panel, "figures", []))
               for s in (getattr(fig, "source_ids", None) or [])}
    return Entry(
        claim=claim,
        specialist=brief.specialist,
        measure_label=getattr(panel, "measure_label", "") or getattr(panel, "measure", ""),
        headline=(panel.headline if getattr(panel, "answered", False)
                  else f"Could not be established: {getattr(panel, 'problem', '') or 'no reason recorded'}"),
        answered=bool(getattr(panel, "answered", False)),
        figures=figures,
        stored_id=stored_id,
        reading=scrub_reading(
            bearing(claim, panel, provider, on_usage=on_usage), allowed),
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


def document_html(entries: Sequence[Entry], *, market: str,
                  definition: str = "", company: str = "") -> str:
    """The reconciliation as a self-contained page.

    The app hands this file to a guest with one click, and a guest clicking
    a deliverable should land on a document, not on raw markdown in whatever
    their machine opens `.md` with. Styled to sit beside the deck report:
    same font stack, same light/dark behavior, no external assets.
    """
    import html as _h

    def e(s: Any) -> str:
        return _h.escape(str(s if s is not None else ""))

    title = f"What the market reports say about {company or 'this deck'}'s claims"
    body: List[str] = []
    add = body.append
    for i, entry in enumerate(entries, 1):
        add(f'<section><h2>{i}. The deck\'s claim</h2>'
            f'<blockquote>{e(entry.claim)}</blockquote>'
            f'<p class="meta">Checked by the <b>{e(entry.specialist)}</b> report'
            + (f' ({e(entry.measure_label)})' if entry.measure_label else '')
            + f' · stored as <code>{e(entry.stored_id)}</code></p>'
            f'<p><b>What it established:</b> {e(entry.headline)}</p>')
        if entry.figures:
            add("<ul>" + "".join(f"<li>{e(f)}</li>" for f in entry.figures)
                + "</ul>")
        add(f'<p><b>Bearing on the claim:</b> {e(entry.reading)}</p></section>')

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>
:root{{--ink:#1A1D21;--muted:#5C6570;--bg:#F7F9FB;--panel:#fff;--line:#DCE1E7;--accent:#2E5C8A}}
@media(prefers-color-scheme:dark){{:root{{--ink:#E6EAF2;--muted:#9AA5B8;--bg:#12151C;
--panel:#1B202B;--line:#2A3140;--accent:#7AA2F7}}}}
body{{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}}
.wrap{{max-width:820px;margin:0 auto;padding:44px 26px 90px}}
h1{{font-size:28px;letter-spacing:-.02em;border-bottom:3px solid var(--accent);
padding-bottom:14px}}
h2{{font-size:18px;margin:34px 0 8px}}
blockquote{{margin:8px 0;padding:12px 18px;background:var(--panel);
border-left:4px solid var(--accent);border-radius:0 8px 8px 0;font-size:16.5px}}
.meta{{color:var(--muted);font-size:13.5px}}
code{{background:var(--panel);border:1px solid var(--line);border-radius:5px;
padding:1px 6px;font-size:13px}}
ul{{margin:6px 0}}
footer{{margin-top:40px;color:var(--muted);font-size:13.5px;
border-top:1px solid var(--line);padding-top:14px;font-style:italic}}
</style></head><body><div class="wrap">
<h1>{e(title)}</h1>
<p>Market as scoped: <b>{e(market)}</b>{(" — " + e(definition)) if definition else ""}</p>
<p class="meta">Each report below was dispatched to check one specific claim the
deck makes. The finding is the report's own, with its source IDs; the full
report, chart and bibliography included, is stored under the ID shown — open it
with <code>deckscope panels</code> or from the app's &ldquo;Reports you have
made&rdquo;.</p>
{"".join(body)}
<footer>Source IDs refer to each stored report's own bibliography. An
unestablished finding is a result, not a failure: it means the deck's number
rests on something no independent reader can check.</footer>
</div></body></html>"""
