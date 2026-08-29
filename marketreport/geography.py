"""Turning a place someone typed into the FIPS codes the Census API wants.

Today the product asks for `--state 04 --county 013`. That is a question only
someone who already does this work can answer, which makes the tool useless to
the person it was built for. The client's original question was "landscaping in
Phoenix", and nothing in the product could take it.

Three tiers, in descending order of how much I trust myself:

**State codes are typed here.** There are 56 of them, they are ANSI standard,
they have not changed since 1970, and the set has a checkable shape — five
numbers in the range are deliberately unassigned, which is a real invariant a
typo would break. A test asserts it.

**County codes are fetched, never typed.** There are 3,143 and I would get some
of them wrong. They come from the Census API — the same key the report already
needs — and are cached on disk after the first call. A county the user names
that the API does not return is reported as not found, with the near misses,
rather than resolved to something close.

**City-to-county is a short, explicit list.** A city is not a Census geography;
it sits inside one or more counties, and the mapping is genuinely ambiguous for
places that straddle county lines. Rather than pretend, this ships the largest
US cities where the containing county is unambiguous, each one written out, and
says plainly that it is a list rather than a lookup. Anything not on it is a
question back to the user, not a guess.

The through-line is the one from BUILD.md: refuse rather than degrade. A
geography resolved to the wrong county produces a report that is wrong in a way
nothing downstream can detect, because every number after it will be internally
consistent.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------- states

#: ANSI/FIPS state codes. Note the gaps at 03, 07, 14, 43 and 52 — those codes
#: were assigned to Canal Zone and other jurisdictions and were never reused.
#: `test_geography` asserts they stay empty, which catches a fat-fingered digit
#: that would otherwise silently point at the wrong state.
STATES: Dict[str, Tuple[str, str]] = {
    "01": ("Alabama", "AL"),        "02": ("Alaska", "AK"),
    "04": ("Arizona", "AZ"),        "05": ("Arkansas", "AR"),
    "06": ("California", "CA"),     "08": ("Colorado", "CO"),
    "09": ("Connecticut", "CT"),    "10": ("Delaware", "DE"),
    "11": ("District of Columbia", "DC"),
    "12": ("Florida", "FL"),        "13": ("Georgia", "GA"),
    "15": ("Hawaii", "HI"),         "16": ("Idaho", "ID"),
    "17": ("Illinois", "IL"),       "18": ("Indiana", "IN"),
    "19": ("Iowa", "IA"),           "20": ("Kansas", "KS"),
    "21": ("Kentucky", "KY"),       "22": ("Louisiana", "LA"),
    "23": ("Maine", "ME"),          "24": ("Maryland", "MD"),
    "25": ("Massachusetts", "MA"),  "26": ("Michigan", "MI"),
    "27": ("Minnesota", "MN"),      "28": ("Mississippi", "MS"),
    "29": ("Missouri", "MO"),       "30": ("Montana", "MT"),
    "31": ("Nebraska", "NE"),       "32": ("Nevada", "NV"),
    "33": ("New Hampshire", "NH"),  "34": ("New Jersey", "NJ"),
    "35": ("New Mexico", "NM"),     "36": ("New York", "NY"),
    "37": ("North Carolina", "NC"), "38": ("North Dakota", "ND"),
    "39": ("Ohio", "OH"),           "40": ("Oklahoma", "OK"),
    "41": ("Oregon", "OR"),         "42": ("Pennsylvania", "PA"),
    "44": ("Rhode Island", "RI"),   "45": ("South Carolina", "SC"),
    "46": ("South Dakota", "SD"),   "47": ("Tennessee", "TN"),
    "48": ("Texas", "TX"),          "49": ("Utah", "UT"),
    "50": ("Vermont", "VT"),        "51": ("Virginia", "VA"),
    "53": ("Washington", "WA"),     "54": ("West Virginia", "WV"),
    "55": ("Wisconsin", "WI"),      "56": ("Wyoming", "WY"),
    "72": ("Puerto Rico", "PR"),
}

#: The codes inside the 01-56 range that are deliberately never assigned.
UNASSIGNED = ("03", "07", "14", "43", "52")

_BY_NAME: Dict[str, str] = {}
for _fips, (_name, _abbr) in STATES.items():
    _BY_NAME[_name.lower()] = _fips
    _BY_NAME[_abbr.lower()] = _fips


def state_fips(text: str) -> Optional[str]:
    """"AZ", "Arizona", "arizona", "04" -> "04". Anything else -> None."""
    key = (text or "").strip().lower()
    if not key:
        return None
    if key in STATES:
        return key
    if key.isdigit() and key.zfill(2) in STATES:
        return key.zfill(2)
    return _BY_NAME.get(key)


def state_name(fips: str) -> str:
    entry = STATES.get((fips or "").zfill(2))
    return entry[0] if entry else ""


# ----------------------------------------------------------------- cities

#: City -> (state FIPS, county FIPS, county name). Written out rather than
#: derived, because the derivation is the part that goes wrong.
#:
#: Only cities whose containing county is unambiguous are here. New York City
#: spans five counties and is therefore absent by design — resolving it to any
#: one of them would be a factual error dressed as a convenience. The same goes
#: for Kansas City (Missouri, four counties) and Houston (three).
#:
#: This is a convenience list, not a gazetteer. `resolve_city` says so when it
#: misses, and the report never resolves a place it was not asked about.
CITIES: Dict[str, Tuple[str, str, str]] = {
    "phoenix": ("04", "013", "Maricopa County"),
    "tucson": ("04", "019", "Pima County"),
    "mesa": ("04", "013", "Maricopa County"),
    "scottsdale": ("04", "013", "Maricopa County"),
    "tempe": ("04", "013", "Maricopa County"),
    "chandler": ("04", "013", "Maricopa County"),
    "glendale az": ("04", "013", "Maricopa County"),
    "los angeles": ("06", "037", "Los Angeles County"),
    "san diego": ("06", "073", "San Diego County"),
    "san jose": ("06", "085", "Santa Clara County"),
    "san francisco": ("06", "075", "San Francisco County"),
    "fresno": ("06", "019", "Fresno County"),
    "sacramento": ("06", "067", "Sacramento County"),
    "oakland": ("06", "001", "Alameda County"),
    "denver": ("08", "031", "Denver County"),
    "miami": ("12", "086", "Miami-Dade County"),
    "orlando": ("12", "095", "Orange County"),
    "tampa": ("12", "057", "Hillsborough County"),
    "jacksonville": ("12", "031", "Duval County"),
    "atlanta": ("13", "121", "Fulton County"),
    "chicago": ("17", "031", "Cook County"),
    "indianapolis": ("18", "097", "Marion County"),
    "new orleans": ("22", "071", "Orleans Parish"),
    "baltimore": ("24", "510", "Baltimore city"),
    "boston": ("25", "025", "Suffolk County"),
    "detroit": ("26", "163", "Wayne County"),
    "minneapolis": ("27", "053", "Hennepin County"),
    "st louis": ("29", "510", "St. Louis city"),
    "las vegas": ("32", "003", "Clark County"),
    "albuquerque": ("35", "001", "Bernalillo County"),
    "charlotte": ("37", "119", "Mecklenburg County"),
    "raleigh": ("37", "183", "Wake County"),
    "cleveland": ("39", "035", "Cuyahoga County"),
    "columbus": ("39", "049", "Franklin County"),
    "cincinnati": ("39", "061", "Hamilton County"),
    "portland": ("41", "051", "Multnomah County"),
    "philadelphia": ("42", "101", "Philadelphia County"),
    "pittsburgh": ("42", "003", "Allegheny County"),
    "memphis": ("47", "157", "Shelby County"),
    "nashville": ("47", "037", "Davidson County"),
    "austin": ("48", "453", "Travis County"),
    "dallas": ("48", "113", "Dallas County"),
    "san antonio": ("48", "029", "Bexar County"),
    "el paso": ("48", "141", "El Paso County"),
    "fort worth": ("48", "439", "Tarrant County"),
    "salt lake city": ("49", "035", "Salt Lake County"),
    "seattle": ("53", "033", "King County"),
    "milwaukee": ("55", "079", "Milwaukee County"),
}

#: Places deliberately excluded, with the reason. Named rather than silently
#: missing, so `resolve_city` can explain instead of shrugging — and so nobody
#: later "fixes" the gap by picking one county at random.
SPANS_COUNTIES: Dict[str, str] = {
    "new york": "New York City spans five counties (Bronx, Kings, New York, "
                "Queens, Richmond). Name the borough or use the state.",
    "new york city": "New York City spans five counties (Bronx, Kings, New "
                     "York, Queens, Richmond). Name the borough or use the "
                     "state.",
    "nyc": "New York City spans five counties. Name the borough instead.",
    "houston": "Houston spans Harris, Fort Bend and Montgomery counties. "
               "Harris County holds most of it — name it explicitly if that "
               "is what you want.",
    "kansas city": "Kansas City spans four Missouri counties, and there is a "
                   "separate Kansas City in Kansas. Name the county.",
    "washington": "Washington could be the District of Columbia or the state "
                  "of Washington. Say which.",
}


@dataclass
class Place:
    """A resolved geography, or an explanation of why it is not resolved."""

    state_fips: str = ""
    county_fips: str = ""
    label: str = ""
    #: Empty when the place resolved. Otherwise what the caller should do.
    problem: str = ""
    #: Other readings we considered, so an ambiguous place can be re-asked.
    candidates: List[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return bool(self.state_fips) and not self.problem


def resolve_city(text: str) -> Place:
    """A city name to a state and county, or a reason it could not be done."""
    key = " ".join((text or "").lower().replace(".", "").split())
    if not key:
        return Place(problem="no place was given")

    if key in SPANS_COUNTIES:
        return Place(problem=SPANS_COUNTIES[key])

    hit = CITIES.get(key)
    if hit:
        state, county, county_name = hit
        return Place(state_fips=state, county_fips=county,
                     label=f"{text.title()} ({county_name}, "
                           f"{state_name(state)})")

    as_state = state_fips(key)
    if as_state:
        return Place(state_fips=as_state, label=state_name(as_state))

    near = sorted(name for name in CITIES if key in name or name in key)
    return Place(
        problem=(f"'{text}' is not in the built-in city list, which covers the "
                 f"largest US cities only. Give the county directly with "
                 f"--state and --county, or name the state to size it "
                 f"state-wide."),
        candidates=[n.title() for n in near[:5]])


# ------------------------------------------------- counties, fetched live

def _cache_path() -> str:
    # The documented app dir, not a second undocumented ~/.deckscope
    # (external audit finding on persistent-data locations).
    from deckscope.settings import app_dir

    return os.path.join(str(app_dir()), "county-fips.json")


def _load_cache() -> Dict[str, Dict[str, str]]:
    try:
        with open(_cache_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(cache: Dict[str, Dict[str, str]]) -> None:
    path = _cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Serialize first, then replace. A crash mid-write must not leave a
        # truncated cache that parses as valid JSON with half the counties —
        # that failure has already cost this repository one debugging session.
        body = json.dumps(cache, indent=1, sort_keys=True)
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            handle.write(body)
        os.replace(temp, path)
    except OSError:
        pass        # a cache that cannot be written is slow, not wrong


def counties(state: str, *, refresh: bool = False) -> Dict[str, str]:
    """`{county name: 3-digit FIPS}` for one state, from the Census API.

    Fetched rather than shipped. There are 3,143 counties, their names carry
    real distinctions ("St. Louis city" is not "St. Louis County", and the
    difference is a different set of businesses), and a table I typed would be
    wrong somewhere I would never look.

    Raises `Unavailable` without a key, like every other backend here.
    """
    from .sources.census import CBP_BASE, CBP_YEAR, Unavailable, _get

    state = (state or "").zfill(2)
    if state not in STATES:
        raise Unavailable(f"'{state}' is not a state FIPS code")

    cache = _load_cache()
    if not refresh and state in cache and cache[state]:
        return dict(cache[state])

    rows = _get(CBP_BASE.format(year=CBP_YEAR),
                {"get": "NAME", "for": "county:*", "in": f"state:{state}"})
    found: Dict[str, str] = {}
    for row in rows[1:]:
        # Rows come back as [NAME, state, county]; NAME is "Maricopa County, Arizona"
        name = str(row[0]).split(",")[0].strip()
        found[name] = str(row[-1]).zfill(3)
    if not found:
        raise Unavailable(f"the Census API returned no counties for state "
                          f"{state}")

    cache[state] = found
    _save_cache(cache)
    return found


def resolve_county(name: str, state: str) -> Place:
    """A county name within a state, matched against what the Census publishes.

    Exact match first, then a case-insensitive match, then a prefix match — and
    if more than one county matches the prefix, it reports the tie rather than
    taking the first. "Washington County" exists in 30 states and picking one
    silently is how a report ends up describing the wrong place with perfect
    internal consistency.
    """
    from .sources.census import Unavailable

    code = state_fips(state)
    if not code:
        return Place(problem=f"'{state}' is not a state I recognise")

    want = " ".join((name or "").lower().split())
    if not want:
        return Place(state_fips=code, label=state_name(code))

    # The city list already carries a county name and FIPS for every entry, so
    # it doubles as a small offline county index — for free, and without a key.
    # Without this, naming the county explicitly ("Maricopa County, Arizona")
    # was HARDER than naming the city inside it, which is backwards: the more
    # precise request should never be the one that fails.
    for city_state, city_county, county_name in CITIES.values():
        if city_state == code and county_name.lower() in (want,
                                                          f"{want} county"):
            return Place(state_fips=code, county_fips=city_county,
                         label=f"{county_name}, {state_name(code)}")

    try:
        table = counties(code)
    except Unavailable as exc:
        return Place(state_fips=code, problem=str(exc))

    for county, fips in table.items():
        if county.lower() == want:
            return Place(state_fips=code, county_fips=fips,
                         label=f"{county}, {state_name(code)}")

    matches = [(c, f) for c, f in table.items() if c.lower().startswith(want)]
    if len(matches) == 1:
        county, fips = matches[0]
        return Place(state_fips=code, county_fips=fips,
                     label=f"{county}, {state_name(code)}")
    if len(matches) > 1:
        return Place(state_fips=code,
                     problem=f"'{name}' matches {len(matches)} counties in "
                             f"{state_name(code)}; say which",
                     candidates=[c for c, _ in sorted(matches)])

    return Place(state_fips=code,
                 problem=f"{state_name(code)} has no county matching '{name}'",
                 candidates=sorted(table)[:8])
