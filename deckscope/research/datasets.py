"""Structured statistical backends — the sources that actually count things.

Every backend here answers a narrow question from an authoritative publisher and
returns `SearchResult`s, so the rest of the pipeline treats them exactly like web
results: registered, screened, cited. A government table is not automatically
trustworthy, and it gets no special exemption from the evidence ledger.

Two design rules, both learned the hard way:

**A backend that cannot answer says so.** No key, no network, no coverage for
this geography — the answer is `unanswerable`, not "fall back to a web search
and hope". Silently degrading to a worse source is how "193 companies, according
to a directory" ends up in a report with a citation next to it.

**Everything is offline-testable.** Each backend accepts recorded responses, so
the routing and parsing can be exercised in CI without a key and without the
network. A backend that can only be tested live is a backend that is never
tested.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base import SearchResult


class Unavailable(Exception):
    """This backend cannot answer — no key, no network, or no coverage."""


@dataclass
class DatasetAnswer:
    """A structured answer, ready to become a Finding."""

    statement: str
    value_text: str
    unit: str
    as_of: str
    results: List[SearchResult]
    #: `dataset` or `filing` — carried through to the finding's method so a
    #: reader can see that a number came from a census rather than a blog.
    method: str = "dataset"


class DatasetBackend(ABC):
    """Implement `answer()` and the router can send questions here."""

    name: str = "base"
    key_env: str = ""
    #: Short description of exactly what this can answer, shown by
    #: `deckscope backends` so the coverage gap is visible rather than implied.
    covers: str = ""
    homepage: str = ""

    def __init__(self, fixtures: Optional[Dict[str, Any]] = None) -> None:
        #: Recorded responses, keyed by a stable request signature. Present in
        #: tests and in replayed runs; absent live.
        self.fixtures = fixtures or {}

    @property
    def available(self) -> bool:
        """Whether this backend could answer at all right now."""
        if self.fixtures:
            return True
        return not self.key_env or bool(os.getenv(self.key_env))

    def unavailable_reason(self) -> str:
        if self.available:
            return ""
        return (f"{self.name} needs {self.key_env}, which is not set. Set it, or "
                f"this class of question stays unanswerable rather than being "
                f"answered from a worse source.")

    @abstractmethod
    def answer(self, question: str, params: Dict[str, Any]) -> DatasetAnswer:
        """Answer, or raise `Unavailable`. Must never guess."""


# --------------------------------------------------------------------- Census

class CensusBusinessPatterns(DatasetBackend):
    """Establishment counts by industry and county — US Census CBP.

    This is the correct answer to "how many landscaping businesses are there in
    Phoenix". It is free, it requires no key for modest use, and it counts
    establishments rather than counting whoever paid to be on a directory page.
    """

    name = "census_cbp"
    key_env = "CENSUS_API_KEY"          # optional; raises rate limits
    covers = "US establishment counts and employment by NAICS industry and county"
    homepage = "https://www.census.gov/programs-surveys/cbp.html"
    endpoint = "https://api.census.gov/data/2022/cbp"

    def answer(self, question: str, params: Dict[str, Any]) -> DatasetAnswer:
        naics = str(params.get("naics") or "").strip()
        state = str(params.get("state_fips") or "").strip()
        county = str(params.get("county_fips") or "").strip()
        if not (naics and state):
            raise Unavailable(
                "a business count needs an industry code and a geography; the "
                "framing stage did not supply one")

        key = f"{self.name}:{naics}:{state}:{county}"
        rows = self.fixtures.get(key)
        if rows is None:
            rows = self._live(naics, state, county)

        header, *data = rows
        if not data:
            raise Unavailable(
                f"the census reports no establishments for NAICS {naics} in this "
                f"geography — which may be a real zero or a coverage gap, and "
                f"either way is not something to fill in from elsewhere")
        idx = {name: i for i, name in enumerate(header)}
        establishments = int(data[0][idx.get("ESTAB", 1)])
        where = params.get("geography_label") or f"FIPS {state}{county}"
        return DatasetAnswer(
            statement=(f"{establishments:,} establishments in NAICS {naics} "
                       f"in {where}"),
            value_text=str(establishments), unit="establishments",
            as_of=str(params.get("year") or "2022"),
            results=[SearchResult(
                title=f"US Census County Business Patterns — NAICS {naics}, {where}",
                url=f"{self.endpoint}?get=ESTAB&NAICS2017={naics}",
                snippet=(f"County Business Patterns reports {establishments:,} "
                         f"establishments in NAICS {naics} for {where}."),
                published=str(params.get("year") or "2022"),
                source_query=question)])

    def _live(self, naics: str, state: str, county: str) -> Any:
        from ..providers._http import get_json

        geo = f"county:{county}&in=state:{state}" if county else f"state:{state}"
        url = (f"{self.endpoint}?get=ESTAB,NAME&NAICS2017={naics}&for={geo}")
        if os.getenv(self.key_env):
            url += f"&key={os.getenv(self.key_env)}"
        try:
            return get_json(url, timeout=20)
        except Exception as exc:  # noqa: BLE001
            raise Unavailable(f"census request failed: {exc}") from None


# ------------------------------------------------------------------------ BLS

class BLSSurvival(DatasetBackend):
    """Firm survival by age — Business Employment Dynamics.

    "What fraction of businesses in this industry reach five years" is a real
    question with a real published answer, and it is one of the most decision-
    relevant numbers there is. Nobody should be guessing it.
    """

    name = "bls_bed"
    key_env = "BLS_API_KEY"
    covers = "US private-sector firm survival rates by age and industry"
    homepage = "https://www.bls.gov/bdm/"

    def answer(self, question: str, params: Dict[str, Any]) -> DatasetAnswer:
        series = str(params.get("series_id") or "").strip()
        if not series:
            raise Unavailable(
                "survival data needs a BLS series id for the industry; none was "
                "resolved for this framing")
        key = f"{self.name}:{series}"
        payload = self.fixtures.get(key)
        if payload is None:
            raise Unavailable(
                "live BLS lookup is not configured in this build; the series "
                "resolver is the remaining work for this backend")
        rate = payload["rate"]
        years = payload.get("years", 5)
        return DatasetAnswer(
            statement=(f"{rate}% of establishments in this industry survive to "
                       f"{years} years"),
            value_text=f"{rate}%", unit="%", as_of=str(payload.get("as_of", "")),
            results=[SearchResult(
                title=f"BLS Business Employment Dynamics — survival, {series}",
                url=f"https://data.bls.gov/timeseries/{series}",
                snippet=(f"Business Employment Dynamics reports a {rate}% "
                         f"{years}-year survival rate for series {series}."),
                published=str(payload.get("as_of", "")), source_query=question)])


class BLSWages(DatasetBackend):
    """Occupational wages by metro — OES."""

    name = "bls_oes"
    key_env = "BLS_API_KEY"
    covers = "US wages by occupation and metropolitan area"
    homepage = "https://www.bls.gov/oes/"

    def answer(self, question: str, params: Dict[str, Any]) -> DatasetAnswer:
        series = str(params.get("series_id") or "").strip()
        payload = self.fixtures.get(f"{self.name}:{series}") if series else None
        if payload is None:
            raise Unavailable(
                "wage data needs an OES series for the occupation and metro; "
                "none was resolved for this framing")
        return DatasetAnswer(
            statement=f"median hourly wage {payload['median']} in {payload['area']}",
            value_text=str(payload["median"]), unit="USD/hour",
            as_of=str(payload.get("as_of", "")),
            results=[SearchResult(
                title=f"BLS OES — {payload['occupation']}, {payload['area']}",
                url=f"https://data.bls.gov/timeseries/{series}",
                snippet=(f"OES reports a median hourly wage of "
                         f"{payload['median']} for {payload['occupation']} in "
                         f"{payload['area']}."),
                published=str(payload.get("as_of", "")), source_query=question)])


# ---------------------------------------------------------------------- EDGAR

class EdgarFilings(DatasetBackend):
    """Public company filings — SEC EDGAR full-text and company facts.

    A primary filing beats a summary of a filing, and for the opportunity-cost
    comparison this is the difference between a market cap somebody typed into a
    blog and one the company reported.
    """

    name = "edgar"
    key_env = ""                        # no key; requires a User-Agent
    covers = "US public company filings and reported financial facts"
    homepage = "https://www.sec.gov/edgar"

    def answer(self, question: str, params: Dict[str, Any]) -> DatasetAnswer:
        cik = str(params.get("cik") or "").strip()
        if not cik:
            raise Unavailable(
                "an EDGAR lookup needs a CIK; the company was not resolved to a "
                "filer, which usually means it is not publicly traded")
        payload = self.fixtures.get(f"{self.name}:{cik}")
        if payload is None:
            raise Unavailable(
                "live EDGAR lookup is not configured in this build")
        return DatasetAnswer(
            statement=payload["statement"], value_text=str(payload["value"]),
            unit=payload.get("unit", "USD"), as_of=str(payload.get("as_of", "")),
            method="filing",
            results=[SearchResult(
                title=f"SEC EDGAR — {payload.get('company', cik)}",
                url=f"https://www.sec.gov/cgi-bin/browse-edgar?CIK={cik}",
                snippet=payload["statement"],
                published=str(payload.get("as_of", "")), source_query=question)])


# ------------------------------------------------------------------ registry

_BACKENDS = {b.name: b for b in
             (CensusBusinessPatterns, BLSSurvival, BLSWages, EdgarFilings)}


def get_backend(name: str, fixtures: Optional[Dict[str, Any]] = None
                ) -> Optional[DatasetBackend]:
    cls = _BACKENDS.get((name or "").strip().lower())
    return cls(fixtures=fixtures) if cls else None


def list_backends() -> List[Dict[str, str]]:
    """What is available, what it covers, and what it needs — for `deckscope backends`."""
    out = []
    for name, cls in sorted(_BACKENDS.items()):
        b = cls()
        out.append({"name": name, "covers": b.covers, "homepage": b.homepage,
                    "needs": b.key_env or "no key",
                    "available": "yes" if b.available else "no"})
    return out


def load_fixtures(path: str) -> Dict[str, Any]:
    """Recorded dataset responses, so routing and parsing are testable offline."""
    from pathlib import Path

    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
