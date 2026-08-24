"""The finding registry — what the research actually established.

The report was the primary artifact for the whole of DeckScope's life, and that
was the ceiling on everything. A fixed report schema can only hold what somebody
anticipated: `claim_audit`, `blind_spots`, `risks`. A licensing exemption that
decides whether the business is legal to start has nowhere to go, so even when
the research finds it, the product cannot say it.

Turn it around. The primary artifact is a **set of findings**, each one an object
with a value, a unit, a method and its sources. The written report becomes one
*view* over that set, alongside a saturation panel, a survival chart, and a list
of the things nobody could establish. Anything renderable is derived; nothing is
trapped in prose.

This is deliberately the same shape as `SourceRegistry`, one level up. Sources
got stable IDs, provenance and status years before findings did, and the
asymmetry is most of the gap between what DeckScope was asked for and what it
became.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: How a finding was established. `absent` is the interesting one: "the deck has
#: no team slide" and "no public source sizes this market" are findings, and
#: recording them as such is what stops them being quietly dropped.
METHODS = ("search", "dataset", "filing", "fetch", "computed", "absent", "deck")

#: Confidence is about the *evidence*, not the model's feelings. High means
#: independent corroboration; low means one source or a weak one.
CONFIDENCE = ("high", "medium", "low")

#: A magnitude. The leading minus is allowed only when nothing numeric precedes
#: it, because in "$6-8B" the hyphen is a range separator, not a sign. The
#: obvious `-?\d...` parsed that as [6, -8], took the midpoint, and returned
#: *negative one billion* for a perfectly ordinary market-size range — which
#: then flowed into every agreement and contradiction check without ever looking
#: wrong on screen, since only `value_text` is displayed.
_NUM = re.compile(r"(?<![\d.])-?\d[\d,]*\.?\d*")


def parse_number(text: Any) -> Optional[float]:
    """Pull a single magnitude out of a value like '$6-8B' or '14-18%'.

    Returns the midpoint of a range, because a range is a legitimate answer and
    refusing to compare it would silently drop the most honest sources. Returns
    None when there is no number, which callers must treat as "not comparable"
    rather than as zero.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().lower().replace(",", "")
    if not s:
        return None
    mult = 1.0
    if re.search(r"\btrillion\b|\dt\b", s):
        mult = 1e12
    elif re.search(r"\bbillion\b|\db\b", s):
        mult = 1e9
    elif re.search(r"\bmillion\b|\dm\b", s):
        mult = 1e6
    elif re.search(r"\bthousand\b|\dk\b", s):
        mult = 1e3
    nums = [float(n.replace(",", "")) for n in _NUM.findall(s)]
    if not nums:
        return None
    value = sum(nums[:2]) / 2 if len(nums) >= 2 and "-" in s else nums[0]
    return value * mult


@dataclass
class Finding:
    id: str
    statement: str
    question_id: Optional[str] = None
    beat: str = "sizing"
    #: The magnitude, when there is one. Kept alongside `value_text` rather than
    #: replacing it, because "$6-8B" carries information a midpoint does not.
    value: Optional[float] = None
    value_text: str = ""
    unit: str = ""
    #: The date the fact is true *of* — not the date it was retrieved. A 2019
    #: market size found today is a 2019 market size.
    as_of: str = ""
    method: str = "search"
    confidence: str = "medium"
    source_ids: List[str] = field(default_factory=list)
    #: Finding IDs this one disagrees with, filled in by the contradiction pass.
    contradicts: List[str] = field(default_factory=list)
    #: Claim IDs from the deck that this finding speaks to.
    claims: List[str] = field(default_factory=list)
    note: str = ""

    @property
    def sourced(self) -> bool:
        """Whether anything backs this.

        The distinction that makes disagreement usable: two findings that
        conflict and are *both* sourced are a real result worth chasing. One that
        conflicts and cites nothing is a hallucination to strip.
        """
        return bool(self.source_ids) or self.method in ("absent", "computed", "deck")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["sourced"] = self.sourced
        return d


class FindingRegistry:
    """Owns finding identity for a run."""

    def __init__(self) -> None:
        self.findings: List[Finding] = []

    # ------------------------------------------------------------- building
    def add(self, statement: str, *, question_id: Optional[str] = None,
            beat: str = "sizing", value_text: str = "", unit: str = "",
            as_of: str = "", method: str = "search", confidence: str = "medium",
            source_ids: Optional[Iterable[str]] = None,
            claims: Optional[Iterable[str]] = None, note: str = "") -> Finding:
        if method not in METHODS:
            method = "search"
        if confidence not in CONFIDENCE:
            confidence = "medium"

        # The same statement from the same sources is one finding, no matter how
        # many times it is read. Two separate questions arriving at the same
        # sourced fact is the normal case — the first end-to-end run produced
        # three identical market-size findings — and letting them accumulate
        # would inflate the evidence table and, worse, let a single source
        # masquerade as corroboration by appearing more than once.
        existing = self._duplicate(statement, source_ids or [], value_text)
        if existing is not None:
            for cid in claims or []:
                if cid not in existing.claims:
                    existing.claims.append(cid)
            return existing

        f = Finding(
            id=f"F{len(self.findings) + 1}",
            statement=(statement or "").strip(),
            question_id=question_id, beat=beat,
            value=parse_number(value_text), value_text=str(value_text or ""),
            unit=unit, as_of=as_of, method=method, confidence=confidence,
            source_ids=[str(s).strip().upper() for s in (source_ids or [])],
            claims=list(claims or []), note=note)
        self.findings.append(f)
        return f

    def find(self, fid: str) -> Optional[Finding]:
        for f in self.findings:
            if f.id == fid:
                return f
        return None

    def _duplicate(self, statement: str, source_ids: Iterable[str],
                   value_text: str) -> Optional[Finding]:
        """An existing finding saying the same thing from the same sources.

        Matched on the normalized statement, the source set and the figure.
        Same words from a *different* source is not a duplicate — it is
        corroboration, and collapsing it would destroy the independence check
        that the closing rules depend on.
        """
        key = _norm(statement)
        if not key:
            return None
        ids = {str(s).strip().upper() for s in source_ids}
        for f in self.findings:
            if (_norm(f.statement) == key and set(f.source_ids) == ids
                    and str(f.value_text or "") == str(value_text or "")):
                return f
        return None

    # -------------------------------------------------------------- reading
    def for_question(self, qid: str) -> List[Finding]:
        return [f for f in self.findings if f.question_id == qid]

    def for_claim(self, cid: str) -> List[Finding]:
        return [f for f in self.findings if cid in f.claims]

    def for_beat(self, beat: str) -> List[Finding]:
        return [f for f in self.findings if f.beat == beat]

    def contested(self) -> List[Tuple[Finding, Finding]]:
        """Pairs that disagree, both of which are backed by something."""
        out = []
        seen = set()
        for f in self.findings:
            for other_id in f.contradicts:
                pair = tuple(sorted((f.id, other_id)))
                if pair in seen:
                    continue
                other = self.find(other_id)
                if other is None:
                    continue
                seen.add(pair)
                if f.sourced and other.sourced:
                    out.append((f, other))
        return out

    def unsourced(self) -> List[Finding]:
        """Findings nothing backs. These are stripped before the report is built."""
        return [f for f in self.findings if not f.sourced]

    def strip_unsourced(self) -> List[Finding]:
        """Remove findings with no evidence behind them, and return what went.

        The same invariant the citation audit enforces for report text, applied
        to the dataset the report is built from. A finding with no source is a
        model's recollection, and the whole product exists to keep those out.
        """
        removed = self.unsourced()
        keep = {f.id for f in self.findings} - {f.id for f in removed}
        self.findings = [f for f in self.findings if f.id in keep]
        for f in self.findings:
            f.contradicts = [c for c in f.contradicts if c in keep]
        return removed

    # -------------------------------------------------------- contradiction
    #: Two magnitudes are "the same answer" within this ratio. Deliberately
    #: generous: market estimates that differ by a fifth agree for our purposes,
    #: and flagging that as contested would bury the real disagreements.
    TOLERANCE = 1.35

    def detect_contradictions(self) -> int:
        """Link findings that answer the same question with different magnitudes.

        Computed rather than asked of a model, so it cannot be talked out of a
        disagreement — and so the same two numbers always produce the same
        result.
        """
        found = 0
        by_question: Dict[str, List[Finding]] = {}
        for f in self.findings:
            if f.question_id and f.value is not None:
                by_question.setdefault(f.question_id, []).append(f)
        for group in by_question.values():
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if a.unit and b.unit and a.unit != b.unit:
                        continue          # different units are not a disagreement
                    lo, hi = sorted((abs(a.value), abs(b.value)))
                    if lo == 0:
                        differs = hi != 0
                    else:
                        differs = (hi / lo) > self.TOLERANCE
                    if differs:
                        if b.id not in a.contradicts:
                            a.contradicts.append(b.id)
                        if a.id not in b.contradicts:
                            b.contradicts.append(a.id)
                        found += 1
        return found

    # ------------------------------------------------------------ reporting
    def stats(self) -> Dict[str, Any]:
        return {
            "total": len(self.findings),
            "sourced": len([f for f in self.findings if f.sourced]),
            "contested_pairs": len(self.contested()),
            "by_method": {m: len([f for f in self.findings if f.method == m])
                          for m in METHODS
                          if any(f.method == m for f in self.findings)},
            "by_beat": {b: len(self.for_beat(b))
                        for b in {f.beat for f in self.findings}},
        }

    def to_dict(self) -> Dict[str, Any]:
        return {"findings": [f.to_dict() for f in self.findings],
                "stats": self.stats()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FindingRegistry":
        reg = cls()
        for row in (data or {}).get("findings", []):
            f = Finding(
                id=row["id"], statement=row.get("statement", ""),
                question_id=row.get("question_id"), beat=row.get("beat", "sizing"),
                value=row.get("value"), value_text=row.get("value_text", ""),
                unit=row.get("unit", ""), as_of=row.get("as_of", ""),
                method=row.get("method", "search"),
                confidence=row.get("confidence", "medium"),
                source_ids=list(row.get("source_ids") or []),
                contradicts=list(row.get("contradicts") or []),
                claims=list(row.get("claims") or []), note=row.get("note", ""))
            reg.findings.append(f)
        return reg


def _norm(text: str) -> str:
    """A loose key for spotting the same statement said twice."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (text or "").lower())).strip()
