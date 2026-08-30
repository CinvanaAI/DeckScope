"""The research loop — the engine that was missing.

The old pipeline wrote eight search queries having read nothing, ran them once,
and produced a report. Everything downstream inherited whatever that single
guess happened to retrieve, and no finding could ever change what got looked up
next. That is a lookup with a plan attached, not research.

This is the loop:

    while budget remains and open questions exist:
        q       = highest-priority open question
        route   = classify(q)               # search | dataset | filing | fetch
        results = retrieve(q, route)        # screened + registered on the way in
        read    -> findings, contradictions, and NEW questions
        post new questions, to any beat
        close q when a stated rule fires

Three things make it more than a for-loop.

**Any beat can question any other.** The demand researcher finding something odd
can put a question on the competitor researcher's queue. That cross-posting is
the mechanism that surfaces the disagreement neither would have reached alone.

**Budget is enforced here, not requested in a prompt.** A loop that can spawn its
own work will spend everything on the first interesting thread unless something
in the scheduler stops it.

**Nothing reaches a model unscreened.** Every retrieval goes through the same
`gather()` the rest of DeckScope uses: registered before screening, quarantined
if hostile, given a citable ID. The fifth audit found a research path that
skipped this, and the lesson was that the exception is always the one that gets
exploited.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Callable, Dict, List, Optional

from ..security.policy import SecurityPolicy
from ..sources import SourceRegistry, merge_into
from . import router
from .closing import decide
from .datasets import Unavailable, get_backend
from .findings import FindingRegistry
from .metrics import answers, classify
from .questions import (CONFIRMED, CONTESTED, UNANSWERABLE, QuestionQueue)


#: The thoroughness dial: how long the loop keeps hunting before the
#: budget, rather than the evidence, ends a question. `quick` is a sighting
#: pass; `exhaustive` is for when the reader has decided the answer is worth
#: real spend. Selected by DECKSCOPE_THOROUGHNESS (the CLI --thoroughness
#: flag sets it), read at Budget construction so it reaches every loop in
#: the process without threading a parameter through six call sites — the
#: same environment-as-configuration layer DECKSCOPE_PROVIDER already uses.
THOROUGHNESS = {
    "quick": 0.5,
    "standard": 1.0,
    "exhaustive": 2.5,
}


def _scale() -> float:
    import os

    name = (os.getenv("DECKSCOPE_THOROUGHNESS") or "standard").strip().lower()
    return THOROUGHNESS.get(name, 1.0)


@dataclass
class Budget:
    """What the loop is allowed to spend. Checked before every iteration.

    The defaults scale with the thoroughness dial; an explicitly passed
    value is used as given — the dial adjusts defaults, it does not
    override decisions.
    """

    max_iterations: int = field(default_factory=lambda: int(24 * _scale()))
    max_retrievals: int = field(default_factory=lambda: int(40 * _scale()))
    max_seconds: float = field(default_factory=lambda: 600.0 * _scale())
    #: Retrieval attempts on one question before it is declared unanswerable.
    max_attempts_per_question: int = field(
        default_factory=lambda: max(2, int(3 * _scale())))

    iterations: int = 0
    retrievals: int = 0
    started: float = field(default_factory=time.time)

    @property
    def spent(self) -> bool:
        return (self.iterations >= self.max_iterations
                or self.retrievals >= self.max_retrievals
                or (time.time() - self.started) >= self.max_seconds)

    def why_spent(self) -> str:
        if self.iterations >= self.max_iterations:
            return f"iteration cap reached ({self.max_iterations})"
        if self.retrievals >= self.max_retrievals:
            return f"retrieval cap reached ({self.max_retrievals})"
        return f"time cap reached ({self.max_seconds:.0f}s)"

    def to_dict(self) -> Dict[str, Any]:
        return {"iterations": self.iterations, "retrievals": self.retrievals,
                "seconds": round(time.time() - self.started, 1),
                "caps": {"iterations": self.max_iterations,
                         "retrievals": self.max_retrievals,
                         "seconds": self.max_seconds},
                "exhausted": self.spent,
                "stopped_because": self.why_spent() if self.spent else ""}


class ResearchLoop:
    """Question-driven market research with a budget and an audit trail.

    `reader` is the only model-facing part: given a question and a block of
    screened evidence, it returns findings and follow-up questions. Keeping it
    behind a callable means the loop itself is deterministic and testable with a
    fake reader — the mechanics can be verified without a model in the way.
    """

    def __init__(self, *, researcher: Any, registry: SourceRegistry,
                 queue: QuestionQueue, findings: FindingRegistry,
                 reader: Callable[..., Dict[str, Any]],
                 policy: Optional[SecurityPolicy] = None,
                 budget: Optional[Budget] = None,
                 dataset_fixtures: Optional[Dict[str, Any]] = None,
                 framing: Optional[Dict[str, Any]] = None,
                 on_event: Optional[Callable[[str], None]] = None) -> None:
        self.researcher = researcher
        self.registry = registry
        self.queue = queue
        self.findings = findings
        self.reader = reader
        self.policy = policy or SecurityPolicy()
        self.budget = budget or Budget()
        self.dataset_fixtures = dataset_fixtures or {}
        #: Industry codes, geography, series ids — whatever the framing stage
        #: resolved. Dataset backends need these and will refuse without them.
        self.framing = framing or {}
        self.on_event = on_event or (lambda *_: None)
        #: Every screening report produced along the way, so the run's security
        #: section describes the whole loop rather than the first retrieval.
        self.security_reports: List[Any] = []
        self.log: List[Dict[str, Any]] = []
        self._last_ids: List[str] = []
        self._repeated = False
        #: Findings dropped for not answering the question they were retrieved
        #: for. Reported rather than discarded silently — a reader that keeps
        #: returning off-topic figures is a fault worth seeing.
        self.off_topic: List[Dict[str, Any]] = []
        #: Queries whose backend failed. Kept apart from questions that were
        #: asked and genuinely had no answer, because only one of those is a
        #: statement about the subject.
        self.retrieval_failures: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ run
    def run(self) -> Dict[str, Any]:
        while not self.budget.spent:
            question = self.queue.next()
            if question is None:
                break
            self.budget.iterations += 1
            self._work(question)

        # Anything still open when the money runs out is reported as
        # unanswerable with the reason, never left dangling or quietly dropped.
        if self.budget.spent:
            reason = self.budget.why_spent()
            for q in self.queue.open_questions():
                self.queue.close(q.id, UNANSWERABLE,
                                 f"still open when the budget ran out: {reason}")

        self.findings.detect_contradictions()
        stripped = self.findings.strip_unsourced()
        if stripped:
            self._emit(f"removed {len(stripped)} finding(s) with no source behind them")

        return self.report()

    # ------------------------------------------------------------- one step
    def _work(self, question) -> None:
        #: Set by the retrieval helpers when there was nothing new to fetch.
        self._repeated = False
        route = router.classify(question.text, params=self.framing)
        self._emit(f"[{question.beat}] {question.text}  →  {route.kind}")

        try:
            if route.kind in (router.DATASET, router.FILING):
                results = self._from_dataset(question, route)
            else:
                results = self._from_search(question, route)
        except Unavailable as exc:
            # An honest dead end. Recorded, not papered over with a web search:
            # answering a census question from a directory is precisely the
            # failure this routing exists to prevent.
            self.queue.record_attempt(question.id, route.backend or route.kind,
                                      question.text, 0, str(exc))
            self.queue.close(question.id, UNANSWERABLE,
                             f"no backend could answer this: {exc}")
            self.log.append({"question": question.id, "route": route.kind,
                             "outcome": "unavailable", "detail": str(exc)})
            return

        attempts = len(question.attempts)
        if results:
            self._read(question, route)

        # A question the loop cannot retrieve anything *new* for must decide on
        # what it has. Leaving it open re-selects it next iteration, which is
        # how the first run spent three iterations re-reading identical pages
        # and then closed on a timer rather than on evidence.
        exhausted = self.budget.spent or self._repeated
        verdict = decide(self.findings.for_question(question.id),
                         self.registry.find,
                         attempts=attempts,
                         max_attempts=self.budget.max_attempts_per_question,
                         budget_exhausted=exhausted,
                         exhausted_reason=(
                             "the research budget was spent" if self.budget.spent
                             else "every query the loop could form for this had "
                                  "already been run"))
        if verdict.closes:
            self.queue.close(question.id, verdict.status, verdict.because)
            self._emit(f"    {verdict.status}: {verdict.because}")
        self.log.append({"question": question.id, "route": route.kind,
                         "backend": route.backend, "results": len(results),
                         "status": question.status,
                         "because": question.closed_because})

    # ------------------------------------------------------------ retrieval
    def _from_search(self, question, route) -> List[Any]:
        """Web search or a full-page fetch, both through the screen."""
        from ..corpus import gather

        # Re-running the identical query returns the identical pages and costs a
        # retrieval and a model call to learn nothing. The first end-to-end run
        # did exactly this three times per question and produced three copies of
        # the same finding. If a question needs another attempt it needs a
        # different query, and until the loop can rephrase, a repeat is waste.
        if any(a.query == question.text and a.backend == route.kind
               for a in question.attempts):
            self.queue.record_attempt(
                question.id, route.kind, question.text, 0,
                "skipped: this exact query was already run and would return the "
                "same pages")
            self._last_ids = []
            self._repeated = True
            return []

        self.budget.retrievals += 1
        corpus = gather(self.researcher, [question.text], self.policy,
                        max_results=5)
        if corpus.security is not None:
            self.security_reports.append(corpus.security)
        added = list(corpus.registry.sources)
        if added:
            remap = merge_into(self.registry, corpus.registry,
                               note=f"retrieved for {question.id}")
            question_ids = [remap.get(s.sid, s.sid) for s in added]
            self._last_ids = question_ids
        else:
            self._last_ids = []

        # A retrieval that failed is reported as a failure. Without this the
        # attempt records "0 sources", the question closes as unanswerable, and
        # the section says the fact could not be established — describing the
        # search backend as though it were the market.
        if corpus.failures and not added:
            why = corpus.failures[0].get("error") or "the search did not run"
            self.retrieval_failures.append(
                {"question_id": question.id, "query": question.text,
                 "error": why})
            self.queue.record_attempt(
                question.id, route.kind, question.text, 0,
                f"the search backend failed, so nothing was retrieved: {why}")
            return added

        self.queue.record_attempt(question.id, route.kind, question.text,
                                  len(added))
        return added

    def _from_dataset(self, question, route) -> List[Any]:
        """A structured source. Refuses rather than degrading to search."""
        backend = get_backend(route.backend or "", self.dataset_fixtures)
        if backend is None:
            raise Unavailable(f"no backend named {route.backend!r} is registered")
        if not backend.available:
            raise Unavailable(backend.unavailable_reason())

        self.budget.retrievals += 1
        answer = backend.answer(question.text, dict(self.framing))

        # Dataset rows go through the same screen as web pages. A government
        # table is not automatically safe, and giving it an exemption would
        # create exactly the unscreened path the fifth audit found.
        from ..corpus import EvidenceCorpus
        from ..security.screening import screen_sources

        staging = SourceRegistry()
        staging.add_results(answer.results, backend=backend.name)
        kept, report = screen_sources(answer.results, self.policy)
        self.security_reports.append(report)
        kept_keys = {(getattr(r, "url", "") or getattr(r, "title", "")).lower()
                     for r in kept}
        for src in staging.sources:
            if (src.url or src.title).lower() not in kept_keys:
                src.status = "quarantined"
                src.note = "Dropped by the security screen."

        remap = merge_into(self.registry, staging,
                           note=f"{backend.name} lookup for {question.id}")
        # ONLY the sources that survived screening may back the finding.
        #
        # This used to map every staged source, quarantined ones included, so a
        # structured result the screen had rejected for carrying an injection
        # still appeared as provenance on a high-confidence finding and still
        # counted toward independent-publisher corroboration. `Finding.sourced`
        # only checks that the list is non-empty, so nothing downstream could
        # tell. Rejected evidence must not ground anything.
        ids = [remap.get(s.sid, s.sid) for s in staging.sources
               if s.status != "quarantined"]
        dropped = len(staging.sources) - len(ids)
        self._last_ids = ids
        self.queue.record_attempt(question.id, backend.name, question.text,
                                  len(answer.results))

        if not ids:
            # Everything the backend returned was rejected. That is a real
            # outcome and it is not "no data" — it is hostile data, and the
            # question should say so rather than silently finding nothing.
            self._emit(f"    all {dropped} {backend.name} result(s) were "
                       f"quarantined by the security screen")
            self.queue.close(
                question.id, UNANSWERABLE,
                f"every result {backend.name} returned was rejected by the "
                f"security screen, so nothing here can ground a finding")
            return []

        # A structured answer needs no model to interpret it, so it becomes a
        # finding directly. That is the point of routing here: the number is the
        # answer, not raw material for one.
        self.findings.add(
            answer.statement, question_id=question.id, beat=question.beat,
            value_text=answer.value_text, unit=answer.unit, as_of=answer.as_of,
            method=answer.method, confidence="high", source_ids=ids,
            claims=question.claims,
            note=f"routed to {backend.name}: {route.because}")
        _ = EvidenceCorpus  # imported for symmetry with the search path
        return list(answer.results)

    # ---------------------------------------------------------------- read
    def _read(self, question, route) -> None:
        """Hand the screened evidence to the reader and record what came back."""
        ids = getattr(self, "_last_ids", [])
        if not ids:
            return
        block = self.registry.prompt_block(char_budget=24_000, only=ids)
        citable = {s.upper() for s in self.registry.citable_ids}

        try:
            payload = self.reader(question=question, evidence=block,
                                  citable_ids=sorted(citable))
        except Exception as exc:  # noqa: BLE001 - one bad read must not end the run
            self.queue.record_attempt(question.id, route.kind, question.text,
                                      0, f"read failed: {exc}")
            return

        for row in (payload or {}).get("findings", []) or []:
            if not isinstance(row, dict):
                continue
            sources = [str(s).strip().upper()
                       for s in (row.get("source_ids") or [])]
            # Citations to sources this question never retrieved are dropped
            # here rather than at the end, so an invented ID cannot influence a
            # closing decision on its way to being stripped.
            sources = [s for s in sources if s in citable]

            # A finding has to answer the question it was retrieved for.
            #
            # `_clean()` in the reader checks that citations resolve, which is a
            # structural check, not a relevance one. A reader that returns the
            # first figure on the page produces a perfectly well-formed, properly
            # sourced finding about something else entirely — and that finding
            # then reaches the closing rules and changes the outcome. An audit
            # watched a $6-8B market size get compared against a $10,000 startup
            # cost and reported as a contradiction.
            statement = row.get("statement", "")
            metric = classify(statement, unit=row.get("unit", ""),
                              value_text=str(row.get("value", "") or ""),
                              as_of=row.get("as_of", ""))
            if not row.get("absent") and not answers(question.text, metric):
                self.off_topic.append({
                    "question": question.id, "statement": statement,
                    "why": "measures something other than what the question "
                           "was retrieved for"})
                continue

            self.findings.add(
                row.get("statement", ""), question_id=question.id,
                beat=question.beat, value_text=row.get("value", ""),
                unit=row.get("unit", ""), as_of=row.get("as_of", ""),
                method=("absent" if row.get("absent") else route.kind
                        if route.kind in ("search", "fetch") else "search"),
                confidence=row.get("confidence", "medium"),
                source_ids=sources, claims=question.claims,
                note=row.get("note", ""))

        for row in (payload or {}).get("new_questions", []) or []:
            if not isinstance(row, dict):
                continue
            posted = self.queue.add(
                row.get("text", ""), beat=row.get("beat", question.beat),
                parent=question.id, claims=question.claims,
                weight=row.get("weight", "medium"))
            if posted and posted.beat != question.beat:
                self._emit(f"    → {posted.beat}: {posted.text}")

    # -------------------------------------------------------------- output
    def _emit(self, message: str) -> None:
        self.on_event(message)

    def report(self) -> Dict[str, Any]:
        return {
            # Every screen the loop ran, so the run's security section describes
            # the whole loop rather than the first retrieval. They were collected
            # from the start and then never handed out, which meant a hostile
            # page found on iteration nine was quarantined correctly and reported
            # nowhere.
            #
            # Serialized HERE, not by the caller. `report()` is the boundary
            # between live objects and data, and returning a live ScanReport from
            # a method named `report` made `--save` crash mid-write and leave a
            # truncated JSON file on disk. Anything this returns must survive
            # json.dumps().
            "security_reports": [_as_data(r) for r in self.security_reports],
            "off_topic_dropped": list(self.off_topic),
            "retrieval_failures": list(self.retrieval_failures),
            "questions": self.queue.to_dict(),
            "findings": self.findings.to_dict(),
            "budget": self.budget.to_dict(),
            "routing": router.routing_report(self.queue.questions),
            "log": self.log,
            "unanswered": [
                {"question": q.text, "beat": q.beat, "because": q.closed_because,
                 "tried": [a.to_dict() for a in q.attempts]}
                for q in self.queue.by_status(UNANSWERABLE)],
            "contested": [
                {"a": a.to_dict(), "b": b.to_dict(),
                 "question": (self.queue.find(a.question_id).text
                              if a.question_id and self.queue.find(a.question_id)
                              else "")}
                for a, b in self.findings.contested()],
            "confirmed": len(self.queue.by_status(CONFIRMED)),
            "contested_count": len(self.queue.by_status(CONTESTED)),
        }


def _as_data(node: Any) -> Any:
    """Anything, as something json.dumps() will accept.

    Deliberately recursive and defensive. A report that crashes while being
    written is worse than one that never starts: the destination has already
    been opened and truncated, so the user is left with a half-written file that
    looks like output. Better to degrade one unexpected object to its repr than
    to lose the whole run.
    """
    if node is None or isinstance(node, (str, int, float, bool)):
        return node
    if hasattr(node, "to_dict"):
        try:
            return _as_data(node.to_dict())
        except Exception:  # noqa: BLE001
            return repr(node)
    if isinstance(node, dict):
        return {str(k): _as_data(v) for k, v in node.items()}
    if isinstance(node, (list, tuple, set)):
        return [_as_data(v) for v in node]
    if is_dataclass(node) and not isinstance(node, type):
        return _as_data(asdict(node))
    return repr(node)
