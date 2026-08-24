"""When a question is allowed to close, and why.

This is a separate module because it is the part most likely to be quietly
weakened. Every convenient shortcut here — "one good source is enough", "the
model said it had what it needed" — turns the loop back into the one-shot lookup
it replaced, and does so invisibly, because the output still looks like research.

So the rules are code, not prompt text. They are computed over findings, they
always give the same answer for the same evidence, and they cannot be argued
with.

There are exactly four outcomes, and two of them are results rather than
failures:

  CONFIRMED     two independent sources agree within tolerance
  CONTESTED     grounded sources disagree, and nothing settles it
  UNANSWERABLE  budget or backends exhausted — nobody publishes this
  (stay open)   none of the above yet
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence
from urllib.parse import urlparse

from .findings import Finding
from .questions import CONFIRMED, CONTESTED, UNANSWERABLE

#: How far apart two magnitudes may be and still count as agreeing.
AGREEMENT_TOLERANCE = 1.35


@dataclass
class Verdict:
    """A closing decision, with the sentence that justifies it."""

    status: Optional[str]          # None means "leave it open"
    because: str = ""

    @property
    def closes(self) -> bool:
        return self.status is not None


def domain_of(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""
    return host[4:] if host.startswith("www.") else host


def independent_domains(findings: Sequence[Finding], lookup) -> List[str]:
    """Distinct publishers behind a set of findings.

    Counting *sources* rather than publishers is how a system convinces itself
    that four pages from one content farm are corroboration. Counting domains is
    crude — a wire story syndicated to four outlets still looks independent — but
    it removes the failure that actually happens.
    """
    domains = []
    for f in findings:
        for sid in f.source_ids:
            src = lookup(sid)
            if src is None:
                continue
            dom = domain_of(getattr(src, "url", "") or "")
            if dom and dom not in domains:
                domains.append(dom)
    return domains


def _agree(a: Finding, b: Finding) -> bool:
    """Whether two findings say the same thing."""
    if a.value is None or b.value is None:
        # No magnitude to compare: fall back to whether the statements are
        # plainly the same shape. Deliberately conservative — unknown is not
        # agreement.
        return a.statement.strip().lower() == b.statement.strip().lower()
    if a.unit and b.unit and a.unit != b.unit:
        return False
    lo, hi = sorted((abs(a.value), abs(b.value)))
    if lo == 0:
        return hi == 0
    return (hi / lo) <= AGREEMENT_TOLERANCE


def decide(findings: Sequence[Finding], lookup, *,
           attempts: int = 0, max_attempts: int = 3,
           budget_exhausted: bool = False,
           exhausted_reason: str = "") -> Verdict:
    """Should this question close, and on what grounds?

    `lookup(source_id) -> Source|None` comes from the run's registry, so this
    can check publisher independence without importing it.

    `budget_exhausted` means "no further retrieval is possible for this
    question", which covers two different situations: the run is out of money,
    and the loop has no query left to try that it has not already run.
    `exhausted_reason` says which, because a closing note that blames the budget
    when the budget was fine sends the reader to fix the wrong thing.
    """
    grounded = [f for f in findings if f.sourced and f.method != "absent"]
    absent = [f for f in findings if f.method == "absent"]

    # An explicit "no source publishes this" is an answer, and a good one. It has
    # to be checked before the corroboration rules, or the loop keeps spending
    # budget looking for something a researcher has already established is not
    # there.
    if absent and not grounded:
        return Verdict(UNANSWERABLE,
                       "research established that no source addresses this: "
                       + (absent[0].statement or "nothing published"))

    if len(grounded) >= 2:
        disagreeing = [(a, b) for i, a in enumerate(grounded)
                       for b in grounded[i + 1:] if not _agree(a, b)]
        agreeing = [(a, b) for i, a in enumerate(grounded)
                    for b in grounded[i + 1:] if _agree(a, b)]

        if agreeing:
            for a, b in agreeing:
                domains = independent_domains([a, b], lookup)
                if len(domains) >= 2:
                    return Verdict(
                        CONFIRMED,
                        f"{a.id} and {b.id} agree, from independent publishers "
                        f"({', '.join(domains[:3])})")
            # They agree but come from the same publisher. That is one source
            # quoted twice, and treating it as corroboration is exactly the
            # mistake this rule exists to prevent.
            if not disagreeing and attempts >= max_attempts:
                return Verdict(
                    UNANSWERABLE,
                    "every source agreeing on this traces to a single publisher, "
                    "so it could not be independently corroborated")

        if disagreeing:
            # A third opinion may settle it; only give up once the loop has
            # genuinely tried.
            if attempts < max_attempts and not budget_exhausted:
                return Verdict(None)
            a, b = disagreeing[0]
            return Verdict(
                CONTESTED,
                f"{a.id} ({a.value_text or a.statement[:40]}) and "
                f"{b.id} ({b.value_text or b.statement[:40]}) disagree, and "
                f"further research did not settle it")

    if budget_exhausted:
        why = exhausted_reason or "the research budget was spent"
        return Verdict(UNANSWERABLE,
                       f"{why} before this could be established "
                       f"({len(grounded)} grounded finding(s))")

    if attempts >= max_attempts:
        if grounded:
            # "No backend can answer this" was flatly untrue when a backend had
            # just answered it — the first end-to-end run printed exactly that
            # under a sourced $10,000 figure. One source is a real finding that
            # falls short of confirmation, and the difference matters to whoever
            # reads it.
            return Verdict(
                UNANSWERABLE,
                f"{len(grounded)} finding(s) were retrieved but nothing "
                f"independently corroborated them within {attempts} attempt(s), "
                f"so this is reported as evidence rather than as established")
        return Verdict(UNANSWERABLE,
                       f"{attempts} retrieval attempt(s) returned nothing usable; "
                       f"no backend appears to publish this")

    return Verdict(None)
