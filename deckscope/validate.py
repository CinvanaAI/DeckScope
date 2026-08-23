"""Validation for model output, beyond "the top-level keys exist".

`coerce()` filled in missing top-level keys so renderers would not raise. That is
not validation: a model could return a score of 47, an assessment of "probably",
a scorecard row that is a string, or a citation to a source that was never
supplied, and all of it flowed into the report looking authoritative.

This module checks the things that actually matter for a report a person might
act on — enums, numeric ranges, row shapes, and citation existence — and repairs
what it safely can, recording every repair so the run is auditable rather than
quietly corrected.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

ASSESSMENTS = {"supported", "partially-supported", "contradicted", "unverifiable"}
EVIDENCE_QUALITY = {"strong", "moderate", "weak", "none"}
CONFIDENCE = {"high", "medium", "low"}
SEVERITY = {"high", "medium", "low"}
PRIORITY = {"P0", "P1", "P2"}
AGREEMENT = {"unanimous", "majority", "split", "irreconcilable"}
SIZING_CONFIDENCE = {"high", "medium", "low"}
RELIABILITY = {"primary", "secondary", "vendor-marketing", "unknown"}


@dataclass
class Repair:
    path: str
    problem: str
    action: str


@dataclass
class ValidationReport:
    repairs: List[Repair] = field(default_factory=list)
    dropped: int = 0

    def note(self, path: str, problem: str, action: str) -> None:
        self.repairs.append(Repair(path, problem, action))

    @property
    def ok(self) -> bool:
        return not self.repairs

    def to_dict(self) -> Dict[str, Any]:
        return {"repairs": [r.__dict__ for r in self.repairs],
                "dropped_rows": self.dropped,
                "clean": self.ok}

    def summary(self) -> str:
        if self.ok:
            return "model output validated cleanly"
        return (f"{len(self.repairs)} field(s) repaired, {self.dropped} malformed "
                f"row(s) dropped")


def _clamp_int(value: Any, lo: int, hi: int) -> Optional[int]:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, n))


def _enum(value: Any, allowed: Set[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in allowed:
        return v
    # Models drift toward near-misses: "partially supported", "partly-supported".
    normal = re.sub(r"[\s_]+", "-", v)
    if normal in allowed:
        return normal
    for a in allowed:
        if normal.startswith(a[:6]) or a.startswith(normal[:6]):
            return a
    return None


def _rows(obj: Any) -> List[Any]:
    return obj if isinstance(obj, list) else []


def validate_comparison(data: Dict[str, Any], *, valid_source_ids: Iterable[str] = (),
                        report: Optional[ValidationReport] = None) -> ValidationReport:
    """Check and repair a comparison in place. Returns what was changed."""
    rep = report or ValidationReport()
    valid = {str(s).upper() for s in valid_source_ids}

    # ---- scorecard: rows must be dicts with a 1-10 score and a 1-5 weight
    clean_rows = []
    for i, row in enumerate(_rows(data.get("scorecard"))):
        path = f"scorecard[{i}]"
        if not isinstance(row, dict):
            rep.note(path, "not an object", "row dropped")
            rep.dropped += 1
            continue
        score = _clamp_int(row.get("score"), 1, 10)
        if score is None:
            rep.note(f"{path}.score", f"{row.get('score')!r} is not a number",
                     "row dropped")
            rep.dropped += 1
            continue
        if score != row.get("score"):
            rep.note(f"{path}.score", f"{row.get('score')!r} out of range 1-10",
                     f"clamped to {score}")
        row["score"] = score
        weight = _clamp_int(row.get("weight"), 1, 5)
        if weight is None:
            rep.note(f"{path}.weight", f"{row.get('weight')!r} is not a number",
                     "defaulted to 3")
            weight = 3
        elif weight != row.get("weight"):
            rep.note(f"{path}.weight", f"{row.get('weight')!r} out of range 1-5",
                     f"clamped to {weight}")
        row["weight"] = weight
        _check_ids(row, "source_ids", valid, path, rep)
        clean_rows.append(row)
    if "scorecard" in data:
        data["scorecard"] = clean_rows

    # ---- claim audit: assessment and evidence_quality must be known values
    clean_claims = []
    for i, row in enumerate(_rows(data.get("claim_audit"))):
        path = f"claim_audit[{i}]"
        if not isinstance(row, dict):
            rep.note(path, "not an object", "row dropped")
            rep.dropped += 1
            continue
        a = _enum(row.get("assessment"), ASSESSMENTS)
        if a is None:
            rep.note(f"{path}.assessment", f"{row.get('assessment')!r} is not a "
                     f"recognized assessment", "set to 'unverifiable'")
            a = "unverifiable"
        elif a != row.get("assessment"):
            rep.note(f"{path}.assessment", f"{row.get('assessment')!r}",
                     f"normalized to '{a}'")
        row["assessment"] = a

        if row.get("evidence_quality") is not None:
            q = _enum(row.get("evidence_quality"), EVIDENCE_QUALITY)
            if q is None:
                rep.note(f"{path}.evidence_quality",
                         f"{row.get('evidence_quality')!r} unrecognized", "set to 'weak'")
                q = "weak"
            row["evidence_quality"] = q

        _check_ids(row, "source_ids", valid, path, rep)
        # A claim asserting strong evidence with no citation is the exact failure
        # the bibliography exists to prevent.
        if row.get("evidence_quality") == "strong" and not row.get("source_ids"):
            rep.note(f"{path}.evidence_quality",
                     "claims 'strong' evidence but cites no source",
                     "downgraded to 'weak'")
            row["evidence_quality"] = "weak"
        clean_claims.append(row)
    if "claim_audit" in data:
        data["claim_audit"] = clean_claims

    # ---- risks
    for i, row in enumerate(_rows(data.get("risks"))):
        if not isinstance(row, dict):
            continue
        for field_name, allowed in (("severity", SEVERITY), ("likelihood", SEVERITY)):
            v = _enum(row.get(field_name), allowed)
            if row.get(field_name) is not None and v is None:
                rep.note(f"risks[{i}].{field_name}", f"{row.get(field_name)!r}",
                         "set to 'medium'")
                v = "medium"
            if v:
                row[field_name] = v

    # ---- actions
    for i, row in enumerate(_rows(data.get("actions"))):
        if not isinstance(row, dict):
            continue
        p = str(row.get("priority") or "").strip().upper()
        if p not in PRIORITY:
            rep.note(f"actions[{i}].priority", f"{row.get('priority')!r}",
                     "set to 'P1'")
            row["priority"] = "P1"
        else:
            row["priority"] = p

    # ---- verdict confidence
    verdict = data.get("verdict")
    if isinstance(verdict, dict):
        c = _enum(verdict.get("confidence"), CONFIDENCE)
        if verdict.get("confidence") is not None and c is None:
            rep.note("verdict.confidence", f"{verdict.get('confidence')!r}",
                     "set to 'low'")
            c = "low"
        if c:
            verdict["confidence"] = c

    return rep


def validate_market(data: Dict[str, Any], *, valid_source_ids: Iterable[str] = (),
                    report: Optional[ValidationReport] = None) -> ValidationReport:
    """Check and repair a market analysis in place."""
    rep = report or ValidationReport()
    valid = {str(s).upper() for s in valid_source_ids}

    sizing = data.get("sizing")
    if isinstance(sizing, dict):
        c = _enum(sizing.get("sizing_confidence"), SIZING_CONFIDENCE)
        if sizing.get("sizing_confidence") is not None and c is None:
            rep.note("sizing.sizing_confidence", f"{sizing.get('sizing_confidence')!r}",
                     "set to 'low'")
            c = "low"
        if c:
            sizing["sizing_confidence"] = c
        for i, est in enumerate(_rows(sizing.get("tam_estimates"))):
            if isinstance(est, dict):
                _check_ids(est, "source_ids", valid, f"sizing.tam_estimates[{i}]", rep)

    land = data.get("competitive_landscape")
    if isinstance(land, dict):
        for group in ("incumbents", "challengers"):
            for i, c in enumerate(_rows(land.get(group))):
                if not isinstance(c, dict):
                    continue
                lvl = _enum(c.get("threat_level"), SEVERITY)
                if c.get("threat_level") is not None and lvl is None:
                    rep.note(f"{group}[{i}].threat_level", f"{c.get('threat_level')!r}",
                             "set to 'medium'")
                    lvl = "medium"
                if lvl:
                    c["threat_level"] = lvl
                _check_ids(c, "source_ids", valid, f"{group}[{i}]", rep)

    for i, s in enumerate(_rows(data.get("sources"))):
        if not isinstance(s, dict):
            continue
        r = _enum(s.get("reliability"), RELIABILITY)
        if s.get("reliability") is not None and r is None:
            rep.note(f"sources[{i}].reliability", f"{s.get('reliability')!r}",
                     "set to 'unknown'")
            r = "unknown"
        if r:
            s["reliability"] = r
    return rep


def _check_ids(row: Dict[str, Any], key: str, valid: Set[str], path: str,
               rep: ValidationReport) -> None:
    """Drop citations to sources that were never supplied.

    A model inventing S9 when only S1-S4 exist is the failure the whole citation
    registry exists to catch. Dropping it is right: an assessment resting on
    nothing should say so rather than borrow authority from a plausible number.
    """
    ids = row.get(key)
    if not isinstance(ids, list) or not valid:
        return
    kept, bad = [], []
    for raw in ids:
        sid = str(raw).strip().upper()
        (kept if sid in valid else bad).append(sid)
    if bad:
        rep.note(f"{path}.{key}", f"cites {', '.join(bad)}, which were never supplied",
                 "citation(s) removed")
        row[key] = kept
