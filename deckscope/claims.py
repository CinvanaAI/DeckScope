"""The claim register — what the deck asserts, as objects.

Stage 1 used to emit a summary of the deck and hand it downstream. Everything
after that reasoned about the summary, and by the time anything drew a
conclusion the deck itself was gone. This keeps the assertions as first-class
records instead: each one with its location, whether it can be checked, and
whether the case collapses if it turns out to be false.

Two things that were previously invisible become explicit here.

**Framing is a decision, and it can be uncertain.** "Is this workflow automation
or RPA?" determines every search that follows, and getting it wrong wastes the
entire research budget on the wrong market. It used to be a string chosen
silently. It is now a ranked set of candidates, and when two are close the loop
researches both — the divergence between them is frequently the finding.

**Absence is a claim about the company.** A deck with no team slide, no pricing
and no retention figure has told you three things. They are recorded as findings
with `method: absent` so they carry the same weight, and the same provenance
treatment, as anything the deck did say.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

#: Sections whose absence from a deck is itself informative, and the reason why.
#: Kept as data rather than prose so the omission pass cannot drift from what
#: the report claims it checks.
EXPECTED_SECTIONS = {
    "team": "who is doing this, and whether they have done it before",
    "pricing": "what it costs, which decides whether the unit economics exist",
    "traction": "evidence anybody wants it",
    "retention": "whether the customers it has stay",
    "competition": "who else is in this market",
    "use_of_funds": "what the money buys and what milestone it reaches",
}


@dataclass
class Claim:
    id: str
    text: str
    location: str = ""
    type: str = "other"
    verifiability: str = "partially-verifiable"
    load_bearing: str = "medium"
    #: The market boundary this claim assumes. The `inflated_tam` case is
    #: entirely about this: $88B and $6-8B describe the same industry under two
    #: different framings, and only one of them is the company's market.
    frame: str = ""
    value_text: str = ""

    @property
    def weight(self) -> str:
        return self.load_bearing if self.load_bearing in ("high", "medium", "low") \
            else "medium"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FramingCandidate:
    """One plausible reading of what market this company is in."""

    label: str
    confidence: str = "medium"
    because: str = ""
    #: Codes the dataset backends need. Absent here means those backends will
    #: honestly refuse rather than guess.
    naics: str = ""
    geography_label: str = ""
    state_fips: str = ""
    county_fips: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def params(self) -> Dict[str, Any]:
        return {k: v for k, v in
                {"naics": self.naics, "state_fips": self.state_fips,
                 "county_fips": self.county_fips,
                 "geography_label": self.geography_label}.items() if v}


class ClaimRegister:
    """Owns claim identity for a run."""

    def __init__(self) -> None:
        self.claims: List[Claim] = []
        self.framings: List[FramingCandidate] = []
        #: (section, why it matters) for everything expected and missing.
        self.omissions: List[Dict[str, str]] = []

    # ------------------------------------------------------------- building
    def add(self, text: str, *, location: str = "", type: str = "other",
            verifiability: str = "partially-verifiable",
            load_bearing: str = "medium", frame: str = "",
            value_text: str = "") -> Claim:
        c = Claim(id=f"C{len(self.claims) + 1}", text=(text or "").strip(),
                  location=location, type=type, verifiability=verifiability,
                  load_bearing=load_bearing, frame=frame, value_text=value_text)
        self.claims.append(c)
        return c

    def find(self, cid: str) -> Optional[Claim]:
        for c in self.claims:
            if c.id == cid:
                return c
        return None

    def load_bearing(self) -> List[Claim]:
        return [c for c in self.claims if c.load_bearing == "high"]

    def add_framing(self, label: str, **kw: Any) -> FramingCandidate:
        f = FramingCandidate(label=label.strip(), **kw)
        self.framings.append(f)
        return f

    def primary_framing(self) -> Optional[FramingCandidate]:
        order = {"high": 3, "medium": 2, "low": 1}
        return sorted(self.framings, key=lambda f: -order.get(f.confidence, 2))[0] \
            if self.framings else None

    @property
    def framing_is_contested(self) -> bool:
        """Whether two readings are close enough that both must be researched.

        Silently picking one and spending the whole budget on it is how a run
        researches the wrong market thoroughly and reports it confidently.
        """
        order = {"high": 3, "medium": 2, "low": 1}
        ranked = sorted((order.get(f.confidence, 2) for f in self.framings),
                        reverse=True)
        return len(ranked) >= 2 and (ranked[0] - ranked[1]) <= 0

    # ------------------------------------------------------------ omissions
    def detect_omissions(self, extraction: Dict[str, Any]) -> List[Dict[str, str]]:
        """Which expected sections the deck simply does not contain."""
        present = _present_sections(extraction)
        self.omissions = [
            {"section": name, "why_it_matters": why}
            for name, why in EXPECTED_SECTIONS.items() if name not in present]
        return self.omissions

    # ------------------------------------------------------------ questions
    def seed_questions(self) -> List[Dict[str, Any]]:
        """Opening questions, weighted by what the claims are load-bearing on.

        Seeded from the deck but never owned by it — the loop's whole purpose is
        that a source can add a question the deck would never have prompted.
        """
        rows: List[Dict[str, Any]] = []
        for framing in self.framings[:2]:
            rows.append({
                "text": f"How large is the market for {framing.label}, and how fast "
                        f"is it growing?",
                "beat": "sizing", "weight": "high"})
            rows.append({
                "text": f"How many businesses compete in {framing.label}?",
                "beat": "competitors", "weight": "high"})
            rows.append({
                "text": f"What licences, permits or regulatory requirements apply "
                        f"to {framing.label}?",
                "beat": "regulation", "weight": "high"})
            rows.append({
                "text": f"What fraction of businesses in {framing.label} survive "
                        f"five years, and where do they typically fail?",
                "beat": "failure", "weight": "medium"})
            rows.append({
                "text": f"What does it cost to start and operate in "
                        f"{framing.label}?",
                "beat": "economics", "weight": "high"})

        for claim in self.claims:
            if claim.verifiability == "unfalsifiable":
                continue
            if claim.load_bearing not in ("high", "medium"):
                continue
            rows.append({
                "text": f"Is this supported by independent evidence: {claim.text}",
                "beat": _beat_for(claim.type), "claims": [claim.id],
                "weight": claim.weight})
        return rows

    # ------------------------------------------------------------ reporting
    def to_dict(self) -> Dict[str, Any]:
        return {
            "claims": [c.to_dict() for c in self.claims],
            "framings": [f.to_dict() for f in self.framings],
            "framing_contested": self.framing_is_contested,
            "omissions": list(self.omissions),
            "stats": {"claims": len(self.claims),
                      "load_bearing": len(self.load_bearing()),
                      "omissions": len(self.omissions)},
        }

    @classmethod
    def from_extraction(cls, extraction: Dict[str, Any]) -> "ClaimRegister":
        """Build a register from the deck agent's structured output.

        Deliberately reuses the existing extraction rather than replacing stage
        1 wholesale: the extraction was never the broken part. What was missing
        is that its results were flattened into prose instead of kept as records.
        """
        reg = cls()
        market = extraction.get("market") or {}
        frame = (market.get("category") or "").strip()

        for row in extraction.get("claims") or []:
            if not isinstance(row, dict):
                continue
            slide = row.get("slide")
            reg.add(row.get("claim", ""),
                    location=f"slide {slide}" if slide else "",
                    type=row.get("type", "other"),
                    verifiability=row.get("verifiability", "partially-verifiable"),
                    load_bearing=row.get("load_bearing", "medium"),
                    frame=frame)

        # The framing the deck asserts is always a candidate — it is what the
        # founder believes — but never automatically the only one.
        if frame:
            reg.add_framing(frame, confidence="medium",
                            because="the category the deck names for itself")
        sub = (market.get("sub_category") or "").strip()
        if sub and sub.lower() != frame.lower():
            reg.add_framing(sub, confidence="medium",
                            because="the narrower segment the deck also describes; "
                                    "sizing differs sharply between the two")
        reg.detect_omissions(extraction)
        return reg


def _present_sections(extraction: Dict[str, Any]) -> set:
    present = set()
    team = extraction.get("team") or {}
    if team.get("founders") or team.get("headcount"):
        present.add("team")
    model = extraction.get("business_model") or {}
    if model.get("pricing") or model.get("acv_or_arpu"):
        present.add("pricing")
    traction = extraction.get("traction") or {}
    if traction.get("revenue") or traction.get("customers"):
        present.add("traction")
    if traction.get("retention"):
        present.add("retention")
    competition = extraction.get("competition") or {}
    if competition.get("named_competitors"):
        present.add("competition")
    ask = extraction.get("ask") or {}
    if ask.get("use_of_funds") or ask.get("milestones_promised"):
        present.add("use_of_funds")
    return present


def _beat_for(claim_type: str) -> str:
    return {
        "market-size": "sizing", "growth": "sizing",
        "competition": "competitors", "regulatory": "regulation",
        "traction": "company", "financial": "economics",
        "technology": "company", "team": "company",
    }.get(claim_type, "sizing")
