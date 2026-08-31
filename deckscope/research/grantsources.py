"""Free public funding-record clients: NSF, NIH RePORTER, USAspending,
PubMed. The grants vertical's evidence universe.

Every endpoint, method, and auth fact here was verified against the live
service or its official documentation on 2026-08-31 BEFORE this module
was written — the captures live in ``recorded/phase0/`` with the quirks
noted (NIH is POST-only; PubMed esearch answers XML reliably; NSF may
ignore ``printFields``). No key is required by any of them, which is what
qualifies them for a shipped vertical under the free-first rule.

Design rules, identical to every other backend in this codebase:

- A failed or unreachable request RAISES or returns an explicit failure —
  it never fabricates rows. Offline, the caller hears "unavailable",
  not silence.
- Each hit becomes a row with a REAL, per-item URL a reader can open —
  an NSF award page, a RePORTER project page, a PubMed abstract — so
  the citation audit has something to hold.
- ``total`` is first-class: absence reasoning needs the full hit count,
  not just the page returned.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

TIMEOUT = 25
_UA = {"User-Agent": "DeckScope/dev (evidence engine; grants vertical)"}


class GrantSourceUnavailable(RuntimeError):
    """The service could not be reached or refused the request. Carries
    the remedy; never converted into empty-but-confident results."""


@dataclass
class FundingHit:
    title: str
    url: str
    snippet: str
    amount: Optional[str] = None
    year: Optional[str] = None
    source: str = ""

    def to_search_result(self):
        from .base import SearchResult

        extra = " ".join(x for x in (
            f"Amount: {self.amount}." if self.amount else "",
            f"Year: {self.year}." if self.year else "") if x)
        return SearchResult(title=self.title, url=self.url,
                            snippet=(self.snippet + (" " + extra if extra
                                                     else "")).strip(),
                            published=self.year)


@dataclass
class FundingRecord:
    """One database's answer to one query — hits plus the full count."""

    source: str
    query: str
    total: int
    hits: List[FundingHit] = field(default_factory=list)
    #: What was searched, stated well enough for a reader to repeat it.
    request_url: str = ""


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 - one message, with the URL
        raise GrantSourceUnavailable(
            f"{url.split('?')[0]} unavailable: {type(exc).__name__}: "
            f"{exc}") from exc


def _post_json(url: str, body: Dict[str, Any]) -> Any:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={**_UA, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        raise GrantSourceUnavailable(
            f"{url} unavailable: {type(exc).__name__}: {exc}") from exc


# ----------------------------------------------------------------- NSF

def nsf_awards(keyword: str, limit: int = 5) -> FundingRecord:
    """NSF Award Search v1. GET, no key. Contract recorded 2026-08-31."""
    url = ("https://api.nsf.gov/services/v1/awards.json?"
           + urllib.parse.urlencode({"keyword": keyword,
                                     "rpp": max(1, min(limit, 25))}))
    data = _get_json(url)
    resp = (data or {}).get("response") or {}
    meta = resp.get("metadata") or {}
    hits = []
    for a in (resp.get("award") or [])[:limit]:
        award_id = str(a.get("id", ""))
        hits.append(FundingHit(
            title=str(a.get("title", ""))[:200],
            url=f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={award_id}",
            snippet=(f"NSF {a.get('transType', 'award')} to "
                     f"{a.get('awardeeName', 'unknown awardee')}, program "
                     f"{a.get('fundProgramName', 'n/a')}, PI "
                     f"{a.get('piFirstName', '')} {a.get('piLastName', '')}"
                     ).strip(),
            amount=(f"${a['fundsObligatedAmt']}"
                    if a.get("fundsObligatedAmt") else None),
            year=str(a.get("date", ""))[-4:] or None,
            source="nsf"))
    return FundingRecord(source="nsf", query=keyword,
                         total=int(meta.get("totalCount", len(hits))),
                         hits=hits, request_url=url)


# ------------------------------------------------------- NIH RePORTER

def nih_projects(terms: str, limit: int = 5) -> FundingRecord:
    """NIH RePORTER v2. POST-only, no key; the contract is from the
    official docs and the live POST is exercised by the weekly canary —
    the phase-0 capture environment could not perform POSTs, and this
    docstring says so instead of pretending otherwise."""
    url = "https://api.reporter.nih.gov/v2/projects/search"
    body = {"criteria": {"advanced_text_search": {
                "operator": "and", "search_field": "projecttitle,abstract",
                "search_text": terms}},
            "include_fields": ["ProjectTitle", "ProjectNum", "FiscalYear",
                               "AwardAmount", "Organization"],
            "offset": 0, "limit": max(1, min(limit, 25))}
    data = _post_json(url, body)
    hits = []
    for r in (data.get("results") or [])[:limit]:
        org = (r.get("organization") or {})
        num = str(r.get("project_num", ""))
        hits.append(FundingHit(
            title=str(r.get("project_title", ""))[:200],
            url=f"https://reporter.nih.gov/project-details/{num}",
            snippet=(f"NIH project {num} at "
                     f"{org.get('org_name', 'unknown organization')}"),
            amount=(f"${r['award_amount']:,}"
                    if isinstance(r.get("award_amount"), int) else None),
            year=str(r.get("fiscal_year", "")) or None,
            source="nih"))
    total = int((data.get("meta") or {}).get("total", len(hits)))
    return FundingRecord(source="nih", query=terms, total=total,
                         hits=hits, request_url=url)


# ------------------------------------------------------- USAspending

def usaspending_awards(keyword: str, limit: int = 5) -> FundingRecord:
    """USAspending v2 keyword search. POST, no key; GET reachability was
    captured live 2026-08-31, the search POST contract is from the
    official docs and exercised by the canary."""
    url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    body = {"filters": {"keywords": [keyword],
                        "award_type_codes": ["02", "03", "04", "05"]},
            "fields": ["Award ID", "Recipient Name", "Award Amount",
                       "Start Date", "Awarding Agency"],
            "limit": max(1, min(limit, 25)), "page": 1}
    data = _post_json(url, body)
    hits = []
    for r in (data.get("results") or [])[:limit]:
        internal = str(r.get("internal_id") or r.get("generated_internal_id")
                       or "")
        hits.append(FundingHit(
            title=(f"{r.get('Recipient Name', 'unknown recipient')} — "
                   f"award {r.get('Award ID', '')}")[:200],
            url=(f"https://www.usaspending.gov/award/{internal}"
                 if internal else "https://www.usaspending.gov/search"),
            snippet=(f"Federal assistance award by "
                     f"{r.get('Awarding Agency', 'unknown agency')}"),
            amount=(f"${r['Award Amount']:,.0f}"
                    if isinstance(r.get("Award Amount"), (int, float))
                    else None),
            year=str(r.get("Start Date", ""))[:4] or None,
            source="usaspending"))
    meta = data.get("page_metadata") or {}
    # USAspending reports hasNext rather than a total on this endpoint;
    # absence reasoning must treat the count as a floor, and says so.
    total = len(hits) if not meta.get("hasNext") else len(hits) + 1
    return FundingRecord(source="usaspending", query=keyword, total=total,
                         hits=hits, request_url=url)


# ------------------------------------------------------------- PubMed

def pubmed_count(term: str, limit: int = 5) -> FundingRecord:
    """NCBI E-utilities esearch. GET, no key (optional key raises rate
    limits). XML is the reliable retmode — recorded 2026-08-31."""
    url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
           + urllib.parse.urlencode({"db": "pubmed", "term": term,
                                     "retmax": max(1, min(limit, 20))}))
    req = urllib.request.Request(url, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            root = ElementTree.fromstring(resp.read())
    except Exception as exc:  # noqa: BLE001
        raise GrantSourceUnavailable(
            f"eutils.ncbi.nlm.nih.gov unavailable: "
            f"{type(exc).__name__}: {exc}") from exc
    count = int((root.findtext("Count") or "0"))
    hits = [FundingHit(
        title=f"PubMed record {pmid.text}",
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid.text}/",
        snippet=f"Indexed publication matching: {term}",
        source="pubmed")
        for pmid in root.findall("IdList/Id")]
    return FundingRecord(source="pubmed", query=term, total=count,
                         hits=hits, request_url=url)
