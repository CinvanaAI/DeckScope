"""Findings and the report they roll up into."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

from .policy import SEVERITY_ORDER


@dataclass
class Finding:
    code: str          # machine-readable, e.g. "invisible_text"
    severity: str      # info | low | medium | high | critical
    where: str         # "slide 4", "source 3 (example.com)", "PDF metadata: Subject"
    detail: str        # what was found, in plain language
    excerpt: str = ""  # a short, defanged sample of the offending content
    action: str = "flagged"  # flagged | redacted | quarantined | stripped

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScanReport:
    target: str = ""                     # "deck" or "web sources"
    findings: List[Finding] = field(default_factory=list)
    scanned_items: int = 0
    scanned_chars: int = 0
    chars_removed: int = 0

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def extend(self, other: "ScanReport") -> None:
        self.findings.extend(other.findings)
        self.scanned_items += other.scanned_items
        self.scanned_chars += other.scanned_chars
        self.chars_removed += other.chars_removed

    @property
    def risk(self) -> str:
        if not self.findings:
            return "clean"
        top = max(SEVERITY_ORDER.get(f.severity, 0) for f in self.findings)
        return {0: "clean", 1: "low", 2: "medium", 3: "high", 4: "critical"}[top]

    @property
    def worst(self) -> str:
        return self.risk

    def by_severity(self, severity: str) -> List[Finding]:
        return [f for f in self.findings if f.severity == severity]

    @property
    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def summary_line(self) -> str:
        if not self.findings:
            return f"{self.target or 'content'}: clean — nothing suspicious found."
        parts = [f"{n} {sev}" for sev, n in sorted(
            self.counts.items(), key=lambda kv: -SEVERITY_ORDER.get(kv[0], 0))]
        redacted = sum(1 for f in self.findings if f.action in ("redacted", "quarantined"))
        tail = f", {redacted} neutralized" if redacted else ""
        return (f"{self.target or 'content'}: {self.risk.upper()} risk — "
                f"{', '.join(parts)}{tail}.")

    def to_dict(self) -> Dict[str, Any]:
        return {"target": self.target, "risk": self.risk,
                "scanned_items": self.scanned_items,
                "scanned_chars": self.scanned_chars,
                "chars_removed": self.chars_removed,
                "counts": self.counts,
                "findings": [f.to_dict() for f in self.findings]}


class SecurityAbort(RuntimeError):
    """Raised in STRICT mode when hostile content is found."""

    def __init__(self, report: ScanReport) -> None:
        crit = [f for f in report.findings if f.severity in ("critical", "high")]
        detail = "\n".join(f"  - [{f.severity}] {f.where}: {f.detail}" for f in crit[:10])
        super().__init__(
            f"Analysis stopped: {report.target} contains content that appears to be "
            f"targeting the AI rather than a human reader.\n{detail}\n\n"
            f"Run again with --security balanced to neutralize and continue, or inspect "
            f"the file yourself first."
        )
        self.report = report
