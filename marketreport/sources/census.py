"""Census backends: establishment counts and revenue per establishment.

These answer the two terms the corpus shows every filing needing, for the
business-to-business archetype:

  COUNT  — County Business Patterns: establishments by NAICS × geography ×
           employee-size band. This is the number Klaviyo paid Analysys Mason
           and Statista for.
  VALUE  — Economic Census: receipts by NAICS, which divided by establishments
           gives average revenue per establishment.

The VALUE one matters most. SCHEMA.md §1a records the constraint that shaped
this module: every filing in the corpus takes its value-per-unit from its own
books, and a standalone market report has no books. Average revenue per
establishment is the honest substitute. It answers a *different* question — "how
big is this industry" rather than "how big is your opportunity" — and saying so
is the point rather than a caveat.

Both refuse rather than degrade. A market count answered from a web search
instead of the census is how you report 193 competitors when there are 71, and
nothing downstream can tell which number it got.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from ..sizing import MEASURED, Term

CBP_BASE = "https://api.census.gov/data/{year}/cbp"
ECN_BASE = "https://api.census.gov/data/{year}/ecnbasic"

#: The Census API began rejecting keyless requests. Every call now needs one.
#: It is free and issued immediately at the URL below, but it IS a setup step
#: and pretending otherwise would make first run fail mysteriously.
KEY_ENV = "CENSUS_API_KEY"
KEY_SIGNUP = "https://api.census.gov/data/key_signup.html"

#: Most recent vintages known to exist. Bumping these is a deliberate act — a
#: silent bump would change every number in every report with no record of why.
CBP_YEAR = 2022
ECN_YEAR = 2022


class Unavailable(RuntimeError):
    """This backend cannot answer, and will not guess.

    Carries what the caller would need to do to fix it, because "unavailable"
    with no remedy trains people to ignore the message.
    """


def _key() -> str:
    """The Census key, from the environment or the saved key file.

    Both, in that order, and the key file matters: the setup wizard writes to
    `%APPDATA%\\DeckScope\\.env` with owner-only permissions, and reading only
    `os.environ` meant a key the user had just been walked through saving was
    not found at run time. An onboarding flow that stores a credential the
    product then cannot see is worse than no onboarding flow.
    """
    key = (os.environ.get(KEY_ENV) or "").strip()
    if not key:
        try:
            from deckscope import settings
            key = (settings.load_env(into_environ=True).get(KEY_ENV) or "").strip()
        except Exception:  # noqa: BLE001 - the store is optional, not required
            key = ""
    if not key:
        raise Unavailable(
            f"{KEY_ENV} is not set. The Census API refuses keyless requests, so "
            f"establishment counts and industry revenue cannot be retrieved. "
            f"A key is free and issued immediately at {KEY_SIGNUP} — "
            f"run `deckscope setup` and it will walk you through it. "
            f"Without it this figure stays unestablished rather than being "
            f"answered from a worse source.")
    return key


def _get(url: str, params: Dict[str, Any], *, timeout: float = 30.0) -> List[List[str]]:
    params = dict(params)
    params["key"] = _key()
    full = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        full, headers={"User-Agent": "marketreport/0.1 (research tool)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise Unavailable(
                f"the Census API has no data for this combination "
                f"(HTTP 404). Most often the industry code does not exist at "
                f"the geography requested — many NAICS codes are published "
                f"nationally but suppressed at county level to protect "
                f"individual businesses.") from exc
        raise Unavailable(f"the Census API returned HTTP {exc.code}") from exc
    except Exception as exc:  # noqa: BLE001
        raise Unavailable(f"the Census API could not be reached: {exc}") from exc

    try:
        rows = json.loads(body)
    except json.JSONDecodeError as exc:
        raise Unavailable("the Census API returned something that is not JSON") \
            from exc
    if not isinstance(rows, list) or len(rows) < 2:
        raise Unavailable(
            "the Census API returned no rows for this query. The industry may "
            "be suppressed at this geography.")
    return rows


def _geography(state_fips: str = "", county_fips: str = "") -> Tuple[str, str]:
    """Census `for`/`in` clauses, and a human label for the ring."""
    if county_fips and state_fips:
        return f"county:{county_fips}", f"state:{state_fips}"
    if state_fips:
        return f"state:{state_fips}", ""
    return "us:1", ""


def establishment_count(naics: str, *, state_fips: str = "",
                        county_fips: str = "", year: int = CBP_YEAR) -> Term:
    """How many businesses operate in this industry, here.

    The count Klaviyo bought. Free, by industry, by geography, by employee-size
    band, and more authoritative than any of the vendors selling it.
    """
    if not naics or not (4 <= len(naics) <= 6) or not naics.isdigit():
        raise Unavailable(
            f"a 4-6 digit NAICS code is required, got {naics!r}. A 2-digit code "
            f"is a whole economic sector and would make this count meaningless "
            f"while looking authoritative.")

    for_clause, in_clause = _geography(state_fips, county_fips)
    params: Dict[str, Any] = {
        "get": "NAME,ESTAB,EMP,PAYANN", "NAICS2017": naics, "for": for_clause}
    if in_clause:
        params["in"] = in_clause

    rows = _get(CBP_BASE.format(year=year), params)
    header, data = rows[0], rows[1:]
    idx = {name: i for i, name in enumerate(header)}
    try:
        total = sum(int(row[idx["ESTAB"]]) for row in data
                    if row[idx["ESTAB"]] not in (None, "", "null"))
    except (KeyError, ValueError) as exc:
        raise Unavailable("the Census response did not contain an "
                          "establishment count") from exc

    label = data[0][idx["NAME"]] if "NAME" in idx else "United States"
    return Term(
        kind="count", value=float(total), unit="establishments",
        as_of=str(year), source=f"Census County Business Patterns {year}",
        source_url=f"{CBP_BASE.format(year=year)}?NAICS2017={naics}",
        method=MEASURED,
        note=f"NAICS {naics}, {label}")


def revenue_per_establishment(naics: str, *, state_fips: str = "",
                              year: int = ECN_YEAR) -> Term:
    """Average annual revenue per establishment in this industry.

    The honest substitute for the proprietary value term. Read the note it
    carries: this makes the resulting figure the *industry's measured revenue*,
    not a company's addressable opportunity. Those are different numbers and
    conflating them is the single most common way a market size gets inflated.
    """
    if not naics or not (4 <= len(naics) <= 6) or not naics.isdigit():
        raise Unavailable(f"a 4-6 digit NAICS code is required, got {naics!r}")

    for_clause, in_clause = _geography(state_fips)
    params: Dict[str, Any] = {
        "get": "NAME,RCPTOT,ESTAB", "NAICS2017": naics, "for": for_clause}
    if in_clause:
        params["in"] = in_clause

    rows = _get(ECN_BASE.format(year=year), params)
    header, data = rows[0], rows[1:]
    idx = {name: i for i, name in enumerate(header)}
    try:
        receipts = sum(float(r[idx["RCPTOT"]]) for r in data if r[idx["RCPTOT"]])
        estabs = sum(float(r[idx["ESTAB"]]) for r in data if r[idx["ESTAB"]])
    except (KeyError, ValueError) as exc:
        raise Unavailable("the Economic Census response did not contain "
                          "receipts and establishments") from exc
    if not estabs:
        raise Unavailable("the Economic Census reports no establishments for "
                          "this industry and geography")

    # Economic Census receipts are published in thousands of dollars.
    per = (receipts * 1_000.0) / estabs
    return Term(
        kind="value", value=per, unit="$ per establishment per year",
        as_of=str(year), source=f"Economic Census {year}",
        source_url=f"{ECN_BASE.format(year=year)}?NAICS2017={naics}",
        method=MEASURED,
        note="industry average revenue per establishment. This makes the "
             "resulting figure the industry's measured revenue, NOT a "
             "company's addressable opportunity — the filings in the corpus "
             "all use their own realized revenue here, which no outside party "
             "can source")


def unavailable_term(kind: str, because: str) -> Term:
    """A term that could not be established, carrying the reason."""
    from ..sizing import UNAVAILABLE
    return Term(kind=kind, value=None, method=UNAVAILABLE, note=because)
