"""Run a case: its pages in, a real report out, scored.

The report is produced by the same code path a user gets — the specialist, the
loop, the reader, the shaper. Nothing is stubbed except the search backend,
which serves the case's recorded pages instead of the live web. That is the
only substitution, and it is the point: the corpus is fixed so the *system* is
what varies between runs.

**It grades the rendered report, not the internal objects.** A panel whose
figures are all correct and whose rendering drops them is a failed report, and
checking the data structure would call it a pass. What the reader sees is what
is scored.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .schema import Case, Result, registered, score

__all__ = ["CaseResearcher", "run_case", "run_all"]


class CaseResearcher:
    """Serves one case's recorded pages for every query.

    Deliberately does not match pages to queries. Matching would make the
    harness look cleverer than the system: the loop's job is to read what it
    gets and the reader's job is to answer from it, and a researcher that hands
    over the perfect page per question quietly does both and hides whether
    either works.
    """

    name = "case"
    needs_key = False

    def __init__(self, case: Case, config: Any = None) -> None:
        self.case = case
        self.config = config

    def search(self, query: str, max_results: int = 8) -> List[Any]:
        from deckscope.research.base import SearchResult

        return [SearchResult(title=p["title"], url=p["url"],
                             snippet=p["snippet"],
                             published=p.get("published"), source_query=query)
                for p in self.case.pages[:max_results]]

    def search_many(self, queries: Sequence[str],
                    max_results: int = 8) -> List[Any]:
        from deckscope.research.base import Researcher

        return Researcher.search_many(self, list(queries),
                                      max_results=max_results)

    def health_check(self) -> Dict[str, Any]:
        return {"ok": True, "backend": self.name,
                "results": len(self.case.pages)}


def run_case(case: Case, *, provider: Any,
             on_event: Optional[Any] = None) -> Result:
    """Produce the report this case describes, then score it."""
    from deckscope.security.policy import SecurityPolicy
    from ..panel_render import panel_text
    from ..specialists import get as get_specialist, run_specialist

    emit = on_event or (lambda *_: None)
    spec = get_specialist(case.report)
    if spec is None:
        return Result(case_id=case.id,
                      error=f"no specialist named {case.report!r}")

    try:
        panel = run_specialist(
            spec, market=case.market, place="",
            measure=case.measure or None,
            provider=provider, researcher=CaseResearcher(case),
            policy=SecurityPolicy(), on_event=emit)
    except Exception as exc:  # noqa: BLE001 - a crash is a case result
        return Result(case_id=case.id,
                      error=f"{type(exc).__name__}: {exc}")

    rendered = panel_text(panel)
    # Traps convict assertions, and the "Asked:" line is not one — it is the
    # question, phrased by the specialist registry, not by the model under
    # test. The growth specialist's own job description says "on whose
    # forecast", which the forecast trap read as a projection: the same
    # false-conviction class the direction-aware negation fixed for denials,
    # in interrogative form. Only the question preamble is excluded; the
    # headline and every finding stay inside the trap's jurisdiction, because
    # those are claim zones.
    rendered = "\n".join(
        line for line in rendered.splitlines()
        if not line.strip().startswith(("Asked:", "Answered by:")))
    # `must_cite` is checked against the parts of the report that carry source
    # attribution, so a figure quoted in a headline with no citation behind it
    # does not satisfy it.
    cited = "\n".join(
        [f"{f.label} {f.value_text} {' '.join(f.source_ids)}"
         for f in panel.figures if f.source_ids]
        + [f"{s.label} {' '.join(w.label for w in s.slices)} {s.basis}"
           for s in panel.series]
        + list(panel.source_labels))
    return score(case, rendered, cited=cited)


def run_all(*, provider: Any, only: str = "",
            on_event: Optional[Any] = None) -> List[Result]:
    cases = [c for c in registered()
             if not only or only.lower() in (c.id + " " + c.report).lower()]
    return [run_case(c, provider=provider, on_event=on_event) for c in cases]


#: Providers whose answers are canned, so a score against them measures the
#: fixture rather than the system.
STUB_PROVIDERS = ("mock",)


def caveat(provider: Any) -> str:
    """Said before any score, when the score cannot mean what it looks like.

    The harness grades a report, and a report is produced by a specialist AND
    a model. Run it against the offline mock — whose answers are canned
    smartphone market-share text regardless of the question — and every case
    fails, which reads as "the specialists are broken" when it means "the stub
    cannot answer". Publishing that number without this sentence would be the
    same class of thing this whole harness exists to catch.
    """
    name = getattr(provider, "name", "") or ""
    if name not in STUB_PROVIDERS:
        return ""
    return (
        "  These scores are against the offline mock, whose replies are fixed "
        "text and do not depend on the question.\n"
        "  They measure the fixture, not the specialists. Use them as a "
        "regression baseline — a change in\n"
        "  them means the code changed — and never as evidence that a report "
        "type does or does not work.\n"
        "  For that, run this with a real model.\n")


def report(results: Sequence[Result], provider: Any = None) -> str:
    """The summary, written so a red line explains itself."""
    lines: List[str] = []
    note = caveat(provider) if provider is not None else ""
    if note:
        lines.append(note)
    clean = sum(1 for r in results if r.clean and not r.error)
    passed = sum(1 for r in results if r.passed)

    for result in results:
        lines.append("  " + result.summary())
        for pattern, why in result.fabricated:
            lines.append(f"      FABRICATED  /{pattern}/")
            lines.append(f"                  {why}")
        for pattern, why in result.absences_omitted:
            lines.append(f"      not stated  {why}")
        for pattern, why in result.missed[:3]:
            lines.append(f"      missed      {why}")
        for pattern, why in result.uncited:
            lines.append(f"      uncited     {why}")

    lines.append("")
    lines.append(f"  {passed} of {len(results)} cases pass; "
                 f"{clean} of {len(results)} invented nothing.")
    if clean < len(results):
        lines.append("  A fabrication is not offset by recall. A report that "
                     "finds half the facts and invents nothing can be trusted "
                     "with a caveat; one that finds all of them and invents "
                     "one cannot be trusted at all, because the reader cannot "
                     "tell which sentence was invented.")
    return "\n".join(lines)
