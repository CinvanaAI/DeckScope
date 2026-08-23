"""Panelists rank each other's finished reports.

The chair's synthesis is still the headline output, but a synthesis is a
committee document: it can smooth away the disagreement that is the most useful
thing a panel produces. Keeping each panelist's own report available, ranked,
gives a reader the coherent single-author version too — and the ranking is itself
evidence, because it shows which analysis the other models found most defensible.

Rules that matter:

  * **Nobody ranks themselves.** A self-vote is not information, and asking a
    model to rank its own work against others reliably produces a first place.
    Each panelist ranks only the others.
  * **Borda count**, not first-past-the-post. With three or four panelists a
    plurality winner can be almost everyone's last choice; Borda uses the whole
    ordering.
  * **Ties are reported as ties.** Manufacturing a winner from a tie is exactly
    the false precision the panel exists to avoid.
  * **A reason is required** with each ranking, so the vote can be audited rather
    than taken on faith.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Ballot:
    """One panelist's ranking of the others' reports."""

    voter: str                       # panelist label
    ranking: List[str]               # other panelists, best first
    reasons: Dict[str, str] = field(default_factory=dict)
    #: What the voter thought was strongest overall, in their own words.
    note: str = ""

    def __post_init__(self) -> None:
        """A ballot never contains its own voter.

        Enforced here rather than in the tally so the invariant holds for anything
        that reads a Ballot — a renderer listing "why each panelist ranked the
        others" should not have to remember to filter, and a self-ranking shown to
        a reader looks like the panel endorsed itself.
        """
        seen = set()
        clean = []
        for label in self.ranking:
            if label == self.voter or label in seen:
                continue
            seen.add(label)
            clean.append(label)
        self.ranking = clean
        self.reasons = {k: v for k, v in self.reasons.items() if k != self.voter}

    def to_dict(self) -> Dict[str, Any]:
        return {"voter": self.voter, "ranking": list(self.ranking),
                "reasons": dict(self.reasons), "note": self.note}


@dataclass
class VoteResult:
    ballots: List[Ballot] = field(default_factory=list)
    #: label -> Borda points
    scores: Dict[str, float] = field(default_factory=dict)
    #: labels in finishing order
    order: List[str] = field(default_factory=list)
    winner: Optional[str] = None
    tied: List[str] = field(default_factory=list)
    #: label -> how many voters put it first
    firsts: Dict[str, int] = field(default_factory=dict)
    note: str = ""
    #: True when the panel's preferences cycle (A beats B beats C beats A), so
    #: no ordering can satisfy them all. Worth naming: it means the panel has a
    #: real three-way disagreement about quality, not a coin-flip.
    cycle: bool = False
    #: label -> label -> how many voters preferred the row over the column
    pairwise: Dict[str, Dict[str, int]] = field(default_factory=dict)

    @property
    def decisive(self) -> bool:
        return self.winner is not None and not self.tied

    def rank_of(self, label: str) -> Optional[int]:
        return self.order.index(label) + 1 if label in self.order else None

    def to_dict(self) -> Dict[str, Any]:
        return {"ballots": [b.to_dict() for b in self.ballots],
                "scores": dict(self.scores), "order": list(self.order),
                "winner": self.winner, "tied": list(self.tied),
                "firsts": dict(self.firsts), "decisive": self.decisive,
                "cycle": self.cycle, "pairwise": self.pairwise,
                "note": self.note}


def tally(ballots: List[Ballot], candidates: List[str]) -> VoteResult:
    """Borda count over ballots that exclude the voter's own report."""
    result = VoteResult(ballots=list(ballots))
    if not candidates:
        result.note = "no reports to rank"
        return result
    if len(candidates) == 1:
        result.order = list(candidates)
        result.winner = candidates[0]
        result.note = ("only one panelist produced a report, so there was nothing to "
                       "rank against it")
        return result

    scores = {c: 0.0 for c in candidates}
    firsts = {c: 0 for c in candidates}
    counted = 0

    for ballot in ballots:
        ranked = [c for c in ballot.ranking if c in scores and c != ballot.voter]
        # Drop duplicates while preserving order — models sometimes repeat a name.
        seen, clean = set(), []
        for c in ranked:
            if c not in seen:
                seen.add(c)
                clean.append(c)
        if not clean:
            continue
        counted += 1
        # Points by position within THIS ballot: first of k gets k, last gets 1.
        #
        # Textbook Borda awards n-1 for first place, which degenerates to zero
        # when a voter can only rank one other report — the two-panelist case,
        # where every ballot would score nothing at all.
        for position, label in enumerate(clean):
            scores[label] += len(clean) - position
        firsts[clean[0]] += 1

    if not counted:
        result.note = "no usable ballots were returned"
        result.order = list(candidates)
        return result

    # Normalize so a panelist is not penalized for having been ranked by fewer
    # voters, which happens when another panelist fails mid-run.
    rated: Dict[str, int] = {c: 0 for c in candidates}
    for ballot in ballots:
        for c in candidates:
            if c != ballot.voter and c in ballot.ranking:
                rated[c] += 1
    normalized = {c: round(scores[c] / rated[c], 3) if rated[c] else 0.0
                  for c in candidates}

    result.scores = normalized
    result.firsts = firsts
    result.order = sorted(candidates,
                          key=lambda c: (-normalized[c], -firsts[c], c))

    # Pairwise preferences, so a cycle can be named rather than reported as a
    # generic tie. "These three disagree about which is best, in a loop" is a
    # different finding from "two were equally good".
    pairwise = {a: {b: 0 for b in candidates if b != a} for a in candidates}
    for ballot in ballots:
        ranked = [c for c in ballot.ranking if c in scores and c != ballot.voter]
        for i, winner_c in enumerate(ranked):
            for loser_c in ranked[i + 1:]:
                pairwise[winner_c][loser_c] += 1
    result.pairwise = pairwise

    def beats(a: str, b: str) -> bool:
        return pairwise.get(a, {}).get(b, 0) > pairwise.get(b, {}).get(a, 0)

    condorcet = [a for a in candidates
                 if all(beats(a, b) for b in candidates if b != a)]
    result.cycle = not condorcet and len(candidates) > 2 and any(
        pairwise[a][b] for a in pairwise for b in pairwise[a])

    best = result.order[0]
    top_score, top_firsts = normalized[best], firsts[best]
    result.tied = [c for c in candidates
                   if normalized[c] == top_score and firsts[c] == top_firsts]
    if len(result.tied) > 1:
        result.winner = None
        if result.cycle:
            loop = " > ".join(result.tied) + f" > {result.tied[0]}"
            result.note = (
                f"The panel's preferences cycle ({loop}), so no ordering satisfies "
                f"all of them and there is no winner to report. That is a real "
                f"finding: these panelists disagree about which analysis is "
                f"strongest, not merely about the company. Read them side by side.")
        else:
            result.note = (
                f"{len(result.tied)} reports tied on both score and first-place "
                f"votes: {', '.join(result.tied)}. Reported as a tie rather than "
                f"broken arbitrarily.")
    else:
        result.winner = best
        result.tied = []
        result.note = (f"{best} was ranked highest by the panel "
                       f"({normalized[best]} points, {firsts[best]} first-place vote(s) "
                       f"from {counted} ballot(s)).")
    return result


def ballot_from_json(voter: str, payload: Any, valid: List[str]) -> Optional[Ballot]:
    """Build a Ballot from a model's JSON, tolerating the shapes models produce."""
    if not isinstance(payload, dict):
        return None
    raw = payload.get("ranking") or payload.get("order") or []
    ranking, reasons = [], {}
    for item in raw if isinstance(raw, list) else []:
        reason = ""
        if isinstance(item, str):
            label = item.strip()
        elif isinstance(item, dict):
            label = str(item.get("panelist") or item.get("label") or "").strip()
            reason = str(item.get("reason") or "")
        else:
            continue
        # Models sometimes write "Panelist B (openai/gpt-4o)"; match the prefix.
        match = next((v for v in valid if label == v or label.startswith(v)
                      or v in label), None)
        # Record the reason only for a report this voter is actually eligible to
        # rank. Models often include themselves; that is not a ranking.
        if match and match != voter:
            ranking.append(match)
            if reason:
                reasons[match] = reason
    for k, v in (payload.get("reasons") or {}).items() if isinstance(
            payload.get("reasons"), dict) else []:
        match = next((c for c in valid if k == c or k.startswith(c)), None)
        if match:
            reasons.setdefault(match, str(v))
    if not ranking:
        return None
    return Ballot(voter=voter, ranking=ranking, reasons=reasons,
                  note=str(payload.get("note") or payload.get("summary") or ""))
