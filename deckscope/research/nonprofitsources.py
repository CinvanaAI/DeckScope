"""ProPublica Nonprofit Explorer client — the nonprofits vertical's
evidence universe: IRS 990 extract data, free, no key.

Contract recorded live 2026-08-31 (recorded/phase0/): search and
organization-detail endpoints, GET, JSON. The org detail carries a
``filings_with_data`` series keyed by fiscal period — ``tax_prd`` 202306
is the fiscal year ENDING June 2023 (``accounting_period: 6``), which is
why every figure this module returns travels with its fiscal-period
label: a calendar-year claim and a June-fiscal filing are different
bases, and pretending otherwise is the chimera class three audits
punished.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

TIMEOUT = 25
_UA = {"User-Agent": "DeckScope/dev (evidence engine; nonprofits vertical)"}
BASE = "https://projects.propublica.org/nonprofits/api/v2"


class NonprofitSourceUnavailable(RuntimeError):
    """Service unreachable or refusing. Raised, never papered over."""


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        raise NonprofitSourceUnavailable(
            f"{url.split('?')[0]} unavailable: {type(exc).__name__}: "
            f"{exc}") from exc


@dataclass
class OrgCandidate:
    ein: int
    name: str
    city: str = ""
    state: str = ""
    score: float = 0.0


@dataclass
class Filing:
    """One fiscal year's extract figures, basis-labelled."""

    tax_prd_yr: int
    #: The month the fiscal year ENDS (from tax_prd; 6 = June).
    fiscal_end_month: int
    total_revenue: Optional[int] = None
    total_expenses: Optional[int] = None
    total_assets: Optional[int] = None
    net_assets: Optional[int] = None
    officer_comp: Optional[int] = None
    other_salaries: Optional[int] = None
    fundraising_fees: Optional[int] = None
    contributions: Optional[int] = None
    pdf_url: str = ""

    @property
    def basis_label(self) -> str:
        if self.fiscal_end_month == 12:
            return f"calendar year {self.tax_prd_yr}"
        return (f"fiscal year ending {self.fiscal_end_month:02d}/"
                f"{self.tax_prd_yr}")


@dataclass
class OrgRecord:
    ein: int
    name: str
    filings: List[Filing] = field(default_factory=list)
    request_url: str = ""
    #: The response's own stated provenance (the API embeds it).
    data_source: str = ""


def search_orgs(name: str, limit: int = 5) -> List[OrgCandidate]:
    url = f"{BASE}/search.json?" + urllib.parse.urlencode({"q": name})
    data = _get_json(url)
    return [OrgCandidate(ein=o.get("ein", 0), name=o.get("name", ""),
                         city=o.get("city", ""), state=o.get("state", ""),
                         score=float(o.get("score", 0)))
            for o in (data.get("organizations") or [])[:limit]]


def org_record(ein: int) -> OrgRecord:
    url = f"{BASE}/organizations/{int(ein)}.json"
    data = _get_json(url)
    return parse_org(data, request_url=url)


def parse_org(data: Dict[str, Any], request_url: str = "") -> OrgRecord:
    """Pure parsing, so tests can hold it to the recorded capture."""
    org = data.get("organization") or {}
    filings = []
    for f in (data.get("filings_with_data") or []):
        prd = int(f.get("tax_prd") or 0)
        filings.append(Filing(
            tax_prd_yr=int(f.get("tax_prd_yr") or (prd // 100)),
            fiscal_end_month=prd % 100 if prd else 0,
            total_revenue=f.get("totrevenue"),
            total_expenses=f.get("totfuncexpns"),
            total_assets=f.get("totassetsend"),
            net_assets=f.get("totnetassetend"),
            officer_comp=f.get("compnsatncurrofcr"),
            other_salaries=f.get("othrsalwages"),
            fundraising_fees=f.get("profndraising"),
            contributions=f.get("totcntrbgfts"),
            pdf_url=str(f.get("pdf_url") or "")))
    filings.sort(key=lambda x: -x.tax_prd_yr)
    return OrgRecord(ein=int(org.get("ein") or 0),
                     name=str(org.get("name") or ""),
                     filings=filings, request_url=request_url,
                     data_source=str(data.get("data_source") or ""))


def resolve_ein(doc_text: str, org_name: str) -> Optional[int]:
    """An EIN stated in the document wins outright; otherwise the search
    is consulted and only an UNAMBIGUOUS top hit is accepted — attributing
    filings to the wrong organization is worse than refusing to attribute
    at all (the NAICS-resolver rule, applied to charities)."""
    # Hyphenated EINs are unambiguous. A bare 9-digit run is accepted
    # only with EIN/tax-ID wording nearby — otherwise any stray figure
    # could send the lookup at the wrong organization, and misattributing
    # filings is the one failure this resolver exists to prevent.
    m = re.search(r"\b(\d{2})-(\d{7})\b", doc_text or "")
    if not m:
        m = re.search(r"(?:ein|tax\s*id|employer identification)\D{0,12}"
                      r"(\d{2})-?(\d{7})\b", (doc_text or ""), re.I)
    if m:
        return int(m.group(1) + m.group(2))
    if not org_name.strip():
        return None
    candidates = search_orgs(org_name)
    if not candidates:
        return None
    top = candidates[0]
    runner_up = candidates[1].score if len(candidates) > 1 else 0.0
    named = org_name.strip().lower()
    if top.name.strip().lower() == named or top.score >= runner_up + 10:
        return top.ein
    return None
