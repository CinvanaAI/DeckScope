"""The question queue — what the research loop is actually driven by.

DeckScope used to write eight search queries before it had read anything, run
them once, and stop. That is not research; it is a lookup with a plan attached.
An analyst searches, reads, and lets what they found decide the next search, and
the thing that makes that possible is a queue of open questions that any part of
the system can add to.

Three properties matter more than they look:

**Parentage.** Every question records what spawned it. That turns the queue into
an audit trail of curiosity — "we only asked about the licensing exemption
because the experience requirement turned up" — which is exactly the reasoning a
reader needs to trust a conclusion.

**Priority from load-bearing weight.** Budget is finite, so the question attached
to the claim that breaks the case if false gets answered before the one attached
to a nice-to-have.

**A recorded reason for closing.** A question is never closed because a model
felt satisfied. It closes because a stated rule fired, and the rule is kept.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional

#: The specialist beats. Not roles handed to different personas — labels on the
#: kind of question, so a finding in one area can raise a question in another and
#: the report can say which part of the research produced what.
BEATS = ("framing", "sizing", "competitors", "regulation", "demand",
         "economics", "failure", "company")

#: Terminal states. `contested` and `unanswerable` are *results*, not failures:
#: a system that cannot report "two good sources disagree" or "nobody publishes
#: this" will invent an answer instead, which is the failure that matters.
OPEN = "open"
CONFIRMED = "confirmed"
CONTESTED = "contested"
UNANSWERABLE = "unanswerable"
TERMINAL = (CONFIRMED, CONTESTED, UNANSWERABLE)

#: Priority bands, derived from the load-bearing weight of the claim a question
#: descends from.
PRIORITY = {"high": 3.0, "medium": 2.0, "low": 1.0}


def normalize(text: str) -> str:
    """A loose key for de-duplication.

    Two agents will phrase the same question differently — "how many competitors
    are there?" and "How many competitors are there" — and answering it twice
    spends budget to learn nothing. Deliberately crude: it collapses case,
    punctuation and filler, and nothing else. Aggressive normalization would
    merge questions that only look alike.
    """
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\b(the|a|an|of|for|in|on|is|are|do|does|what|how|many|much)\b",
                  " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Attempt:
    """One retrieval try, kept so an unanswerable question can say what was tried."""

    backend: str
    query: str
    results: int = 0
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Question:
    id: str
    text: str
    beat: str = "sizing"
    #: The question whose answer raised this one. None for seed questions.
    parent: Optional[str] = None
    #: Claim IDs this question bears on, so an answer can be routed back.
    claims: List[str] = field(default_factory=list)
    priority: float = 2.0
    status: str = OPEN
    #: The rule that closed it, in words. Never "the model was satisfied".
    closed_because: str = ""
    attempts: List[Attempt] = field(default_factory=list)
    #: Depth in the parentage chain, used to stop runaway rabbit holes.
    depth: int = 0

    @property
    def open(self) -> bool:
        return self.status == OPEN

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["attempts"] = [a.to_dict() if hasattr(a, "to_dict") else a
                         for a in self.attempts]
        return d


class QuestionQueue:
    """Owns question identity for a run, the way SourceRegistry owns S-IDs."""

    #: How deep a chain of "and that raised…" may go. A loop that can spawn
    #: children forever will, and the budget alone is a poor stop because it
    #: spends everything on one thread before touching the others.
    MAX_DEPTH = 3

    def __init__(self, max_depth: Optional[int] = None) -> None:
        self.questions: List[Question] = []
        self._by_key: Dict[str, Question] = {}
        self.max_depth = self.MAX_DEPTH if max_depth is None else max_depth
        #: Questions refused, and why — so a run can explain what it declined to
        #: chase rather than silently dropping it.
        self.refused: List[Dict[str, str]] = []

    # ------------------------------------------------------------- building
    def add(self, text: str, *, beat: str = "sizing", parent: Optional[str] = None,
            claims: Optional[Iterable[str]] = None,
            weight: str = "medium") -> Optional[Question]:
        """Queue a question. Returns None if it was a duplicate or refused.

        Returning None rather than raising is deliberate: a beat posting a
        question another beat already asked is normal and healthy, not an error.
        """
        text = (text or "").strip()
        if not text:
            return None
        key = normalize(text)
        if not key:
            return None
        if key in self._by_key:
            existing = self._by_key[key]
            for cid in claims or []:
                if cid not in existing.claims:
                    existing.claims.append(cid)
            # A duplicate arriving from a more important claim raises priority.
            existing.priority = max(existing.priority, PRIORITY.get(weight, 2.0))
            return None

        depth = 0
        if parent:
            mother = self.find(parent)
            depth = (mother.depth + 1) if mother else 0
            if depth > self.max_depth:
                self.refused.append({
                    "text": text, "parent": parent,
                    "reason": f"deeper than max_depth={self.max_depth}; the chain "
                              f"was followed far enough"})
                return None

        q = Question(
            id=f"Q{len(self.questions) + 1}", text=text, beat=beat, parent=parent,
            claims=list(claims or []), priority=PRIORITY.get(weight, 2.0),
            depth=depth)
        self.questions.append(q)
        self._by_key[key] = q
        return q

    def seed(self, rows: Iterable[Dict[str, Any]]) -> List[Question]:
        """Bulk-add opening questions."""
        out = []
        for row in rows:
            q = self.add(row.get("text", ""), beat=row.get("beat", "sizing"),
                         claims=row.get("claims"), weight=row.get("weight", "medium"))
            if q:
                out.append(q)
        return out

    # -------------------------------------------------------------- reading
    def find(self, qid: str) -> Optional[Question]:
        for q in self.questions:
            if q.id == qid:
                return q
        return None

    def open_questions(self) -> List[Question]:
        return [q for q in self.questions if q.open]

    #: Of every N questions scheduled, at least one must be attached to a claim
    #: the deck actually makes, whenever such a question is still open.
    CLAIM_EVERY = 3

    def next(self) -> Optional[Question]:
        """Highest priority first; ties broken by shallower depth, then by age.

        Preferring shallow questions on a tie keeps the loop broad before it goes
        deep, so a budget that runs out has covered every beat once rather than
        exhausting itself inside one.

        The interleave exists because the first version of this starved the
        thing the product is for. Seeding puts generic market questions in
        first, they carry the same `high` weight as a load-bearing claim, and
        with a tie broken by age the loop worked market sizing — three attempts
        each — until the budget was gone and never checked a single claim in the
        deck. Every claim came back "unverifiable", which reads like a finding
        about the deck and was actually a finding about the scheduler.

        So one slot in every `CLAIM_EVERY` is reserved for a claim-bound
        question. Not a priority bump, which the generic questions would simply
        outrank again, but a slot they cannot take.
        """
        candidates = self.open_questions()
        if not candidates:
            return None

        def rank(q: Question):
            return (-q.priority, q.depth,
                    int(q.id[1:]) if q.id[1:].isdigit() else 0)

        scheduled = sum(1 for q in self.questions if q.attempts)
        if scheduled and scheduled % self.CLAIM_EVERY == 0:
            bound = [q for q in candidates if q.claims]
            if bound:
                return sorted(bound, key=rank)[0]
        return sorted(candidates, key=rank)[0]

    def by_status(self, status: str) -> List[Question]:
        return [q for q in self.questions if q.status == status]

    def chain(self, qid: str) -> List[Question]:
        """A question and every ancestor, oldest first — the trail of curiosity."""
        out: List[Question] = []
        seen = set()
        current = self.find(qid)
        while current and current.id not in seen:
            seen.add(current.id)
            out.append(current)
            current = self.find(current.parent) if current.parent else None
        return list(reversed(out))

    # -------------------------------------------------------------- closing
    def close(self, qid: str, status: str, because: str) -> None:
        if status not in TERMINAL:
            raise ValueError(f"{status!r} is not a terminal status; "
                             f"expected one of {TERMINAL}")
        if not because.strip():
            raise ValueError(
                "a question may not be closed without a stated reason — "
                "'the model was satisfied' is exactly what this prevents")
        q = self.find(qid)
        if q is None:
            return
        q.status = status
        q.closed_because = because.strip()

    def record_attempt(self, qid: str, backend: str, query: str,
                       results: int = 0, note: str = "") -> None:
        q = self.find(qid)
        if q is not None:
            q.attempts.append(Attempt(backend=backend, query=query,
                                      results=results, note=note))

    # ---------------------------------------------------------- reporting
    def stats(self) -> Dict[str, Any]:
        return {
            "total": len(self.questions),
            "open": len(self.open_questions()),
            "confirmed": len(self.by_status(CONFIRMED)),
            "contested": len(self.by_status(CONTESTED)),
            "unanswerable": len(self.by_status(UNANSWERABLE)),
            "refused": len(self.refused),
            "by_beat": {beat: len([q for q in self.questions if q.beat == beat])
                        for beat in BEATS
                        if any(q.beat == beat for q in self.questions)},
        }

    def to_dict(self) -> Dict[str, Any]:
        return {"questions": [q.to_dict() for q in self.questions],
                "refused": list(self.refused),
                "stats": self.stats()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuestionQueue":
        queue = cls()
        for row in (data or {}).get("questions", []):
            q = Question(
                id=row["id"], text=row.get("text", ""), beat=row.get("beat", "sizing"),
                parent=row.get("parent"), claims=list(row.get("claims") or []),
                priority=float(row.get("priority", 2.0)),
                status=row.get("status", OPEN),
                closed_because=row.get("closed_because", ""),
                depth=int(row.get("depth", 0)),
                attempts=[Attempt(**a) for a in (row.get("attempts") or [])])
            queue.questions.append(q)
            queue._by_key[normalize(q.text)] = q
        queue.refused = list((data or {}).get("refused") or [])
        return queue
