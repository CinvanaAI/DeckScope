"""Turning "landscaping" into 561730.

The report currently asks for a NAICS code. That is the industry classification
the US statistical system runs on, it is the right internal identifier, and it
is a question almost nobody can answer off the top of their head. Requiring it
means the product only works for people who already do this work — which is the
opposite of the point.

**The index is fetched, not typed.** There are 1,012 six-digit NAICS codes and
their official titles carry legal precision ("Landscaping Services" includes
lawn care and excludes landscape architecture, which is 541320). A table I wrote
from memory would be wrong in places nobody would check, and the wrongness would
be invisible: every number downstream of a mis-resolved code is internally
consistent and about the wrong industry. So the index comes from the Census API
— the same key the report already requires — and is cached on disk.

**A small starter set ships** so `--demo` and the tests can run offline. It is
labelled as a subset everywhere it is used, and `resolve()` says which index it
searched. It is not a fallback that silently substitutes for the real one.

**Ambiguity is reported, never broken.** "consulting" matches sixteen codes and
they are different industries with different economics. Returning the
best-scoring one would be a guess wearing a decision's clothes. `resolve()`
returns candidates and marks itself uncertain; the caller asks.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

#: Words that carry no discriminating power in an industry title. Dropped from
#: both sides of the match so "landscaping services" and "landscaping" score the
#: same — otherwise the generic half of every title dominates the score and
#: everything matches "services".
STOPWORDS = frozenset("""
and or the of for in a an to n e c nec nsk other all not elsewhere classified
services service industry industries business businesses establishments
""".split())

#: Enough to run offline and to demonstrate the resolver, drawn from the codes
#: this repository already exercises. **A subset, and labelled one.** The full
#: index has 1,012 entries and arrives from the Census API on first use.
#:
#: Every title here is the official NAICS title verbatim. Where I was not
#: certain of the official wording, the code is absent rather than approximated
#: — an approximate title resolves the wrong query to a real code, which is a
#: worse failure than not resolving it at all.
STARTER: Dict[str, str] = {
    "561730": "Landscaping Services",
    "541320": "Landscape Architectural Services",
    "541310": "Architectural Services",
    "541330": "Engineering Services",
    "541511": "Custom Computer Programming Services",
    "541512": "Computer Systems Design Services",
    "541611": "Administrative Management and General Management Consulting "
              "Services",
    "541618": "Other Management Consulting Services",
    "541110": "Offices of Lawyers",
    "541211": "Offices of Certified Public Accountants",
    "621111": "Offices of Physicians (except Mental Health Specialists)",
    "621210": "Offices of Dentists",
    "722511": "Full-Service Restaurants",
    "722513": "Limited-Service Restaurants",
    "722515": "Snack and Nonalcoholic Beverage Bars",
    "811111": "General Automotive Repair",
    "812112": "Beauty Salons",
    "812113": "Nail Salons",
    "238220": "Plumbing, Heating, and Air-Conditioning Contractors",
    "238210": "Electrical Contractors and Other Wiring Installation "
              "Contractors",
    "236115": "New Single-Family Housing Construction (except For-Sale "
              "Builders)",
    "531210": "Offices of Real Estate Agents and Brokers",
    "541921": "Photography Studios, Portrait",
    "561720": "Janitorial Services",
    "561740": "Carpet and Upholstery Cleaning Services",
    "713940": "Fitness and Recreational Sports Centers",
    "624410": "Child Day Care Services",
    "492210": "Local Messengers and Local Delivery",
    "484110": "General Freight Trucking, Local",
    "445110": "Supermarkets and Other Grocery Retailers (except Convenience "
              "Retailers)",
    "459510": "Used Merchandise Retailers",
    "455110": "Department Stores",
}

STARTER_NOTE = ("the built-in starter index of "
                f"{len(STARTER)} industries, not the full NAICS list of 1,012")

#: Words people actually use that are not in any official title. Kept small and
#: explicit: each entry is a synonym, not a reinterpretation, and it widens what
#: matches rather than changing what a code means.
SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "landscaping": ("lawn", "lawncare", "yard", "gardening", "landscaper"),
    "restaurants": ("restaurant", "diner", "eatery", "cafe"),
    "programming": ("software", "developer", "development", "coding"),
    "physicians": ("doctor", "doctors", "medical", "clinic"),
    "dentists": ("dentist", "dental"),
    "lawyers": ("lawyer", "attorney", "attorneys", "legal", "law"),
    "accountants": ("accountant", "accounting", "cpa", "bookkeeping"),
    "salons": ("salon", "hairdresser", "barber", "hair"),
    "plumbing": ("plumber", "plumbers", "hvac"),
    "electrical": ("electrician", "electricians"),
    "janitorial": ("cleaning", "cleaner", "cleaners", "custodial"),
    "trucking": ("freight", "haulage", "hauling"),
    "grocery": ("groceries", "supermarket", "supermarkets"),
    "fitness": ("gym", "gyms", "health club"),
    "consulting": ("consultancy", "consultant", "consultants"),
    "day": ("daycare", "childcare", "nursery", "preschool"),
}

_EXPAND: Dict[str, str] = {}
for _canonical, _aliases in SYNONYMS.items():
    for _alias in _aliases:
        _EXPAND[_alias] = _canonical


@dataclass
class Candidate:
    code: str
    title: str
    score: float

    def __str__(self) -> str:
        return f"{self.code}  {self.title}"


@dataclass
class Resolution:
    """What a phrase resolved to, and how sure that is.

    `certain` is deliberately conservative. It means one candidate scored well
    AND the runner-up did not — not merely that something came first. A ranked
    list with a close second is an ambiguous query, and reporting it as resolved
    is how a report about management consulting gets filed as one about IT
    consulting with no visible seam.
    """

    query: str = ""
    candidates: List[Candidate] = field(default_factory=list)
    certain: bool = False
    index: str = ""
    problem: str = ""

    @property
    def code(self) -> Optional[str]:
        """The resolved code, or None. None whenever `certain` is False."""
        if self.certain and self.candidates:
            return self.candidates[0].code
        return None

    @property
    def title(self) -> str:
        return self.candidates[0].title if self.candidates else ""


def _words(text: str) -> List[str]:
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    out = []
    for word in raw:
        word = _EXPAND.get(word, word)
        if word in STOPWORDS or len(word) < 2:
            continue
        out.append(word)
    return out


def _score(query_words: List[str], title: str) -> float:
    """Overlap, weighted toward rarer words and toward covering the query.

    Two properties matter. Matching more of what the user said is better than
    matching more of the title, because a long official title should not be
    penalised for its length. And an exact word beats a prefix, so "law" does
    not outrank "lawyers" for the query "lawyers".
    """
    title_words = _words(title)
    if not query_words or not title_words:
        return 0.0

    hits = 0.0
    for word in query_words:
        if word in title_words:
            hits += 1.0
        elif any(t.startswith(word) or word.startswith(t) for t in title_words):
            hits += 0.5

    coverage = hits / len(query_words)
    # A small tie-break toward titles that are mostly about the query, so
    # "Landscaping Services" beats a long title that merely mentions it.
    density = hits / len(title_words)
    return coverage + 0.25 * density


# ------------------------------------------------------------- the index

def _cache_path() -> str:
    # The documented app dir, not a second undocumented ~/.deckscope
    # (external audit finding on persistent-data locations).
    from deckscope.settings import app_dir

    return os.path.join(str(app_dir()), "naics-index.json")


def _load_cached() -> Dict[str, str]:
    try:
        with open(_cache_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()
            if str(k).isdigit() and str(v).strip()}


def _save_cached(index: Dict[str, str]) -> None:
    path = _cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = json.dumps(index, indent=1, sort_keys=True)
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            handle.write(body)
        os.replace(temp, path)
    except OSError:
        pass


def download_index() -> Dict[str, str]:
    """The full NAICS index from the Census API, cached on disk.

    The API publishes its own variable metadata, which includes every NAICS
    value it will accept along with the official label. That is exactly the
    right source: it is the list the data actually uses, so a code resolved
    from it cannot be one the data does not have.

    Raises `Unavailable` without a key, like every other backend.
    """
    from .sources.census import CBP_YEAR, Unavailable
    import urllib.error
    import urllib.request

    url = (f"https://api.census.gov/data/{CBP_YEAR}/cbp/variables/"
           f"NAICS2017.json")
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "marketreport/0.1 (research tool)"})
        with urllib.request.urlopen(request, timeout=60.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError) as exc:
        raise Unavailable(
            f"the NAICS index could not be downloaded: {exc}. The built-in "
            f"starter index still works and covers {len(STARTER)} industries."
        ) from exc

    values = ((payload.get("values") or {}).get("item") or {})
    index = {str(code): str(label).strip()
             for code, label in values.items()
             if str(code).isdigit() and str(label).strip()}
    if not index:
        raise Unavailable("the Census API returned a NAICS index with no "
                          "entries")
    _save_cached(index)
    return index


def index(*, offline: bool = False) -> Tuple[Dict[str, str], str]:
    """The best index available, and a plain-English name for which one it is.

    Returned together on purpose. Every caller has to be able to say which list
    it searched, because "not found" means something completely different in a
    32-entry starter set than in the full 1,012.
    """
    cached = _load_cached()
    if cached:
        return cached, f"the downloaded NAICS index ({len(cached)} industries)"
    if offline:
        return dict(STARTER), STARTER_NOTE
    try:
        downloaded = download_index()
        return downloaded, (f"the downloaded NAICS index "
                            f"({len(downloaded)} industries)")
    except Exception:  # noqa: BLE001 - any failure falls back, loudly
        return dict(STARTER), STARTER_NOTE


# --------------------------------------------------------------- resolve

#: The narrowest a code may be and still describe a market rather than a slice
#: of the economy. "56" is Administrative and Support and Waste Management
#: Services — landscaping, security guards, call centres and landfills in one
#: number. Every figure taken against it is real, sourced, and about something
#: other than the market the user asked for, which is the most dangerous shape
#: an answer can have.
NARROWEST = 4


def too_broad(code: str) -> str:
    """Empty if the code is specific enough, otherwise why it is not."""
    digits = "".join(c for c in (code or "") if c.isdigit())
    if len(digits) >= NARROWEST:
        return ""
    return (f"'{digits}' is {len(digits)} digits, which is an economic sector "
            f"rather than a market. A {NARROWEST}-to-6 digit code is needed: "
            f"every number taken against a sector is real and sourced and "
            f"about a different market than the one you asked about, which "
            f"reads as authoritative while being wrong.")


#: How far ahead the winner must be to count as resolved rather than ranked.
MARGIN = 0.30
#: Below this, nothing matched well enough to offer at all.
FLOOR = 0.40


def resolve(text: str, *, offline: bool = False,
            table: Optional[Dict[str, str]] = None) -> Resolution:
    """A phrase to a NAICS code, or to a short list, or to a reason.

    Three outcomes, and the middle one is the useful one:

    - **certain** — one clear winner. `.code` is set.
    - **ranked** — several plausible codes. `.candidates` is set, `.code` is
      None, and the caller asks the user. "consulting" lands here and should.
    - **nothing** — `.problem` says what was searched and how to widen it.
    """
    phrase = (text or "").strip()
    if not phrase:
        return Resolution(problem="no industry was given")

    digits = re.sub(r"\D", "", phrase)
    if digits and digits == phrase.replace("-", "").replace(" ", ""):
        if not 2 <= len(digits) <= 6:
            return Resolution(
                query=phrase,
                problem=f"'{phrase}' looks like a code but NAICS codes are 2 "
                        f"to 6 digits; this one is {len(digits)}")
        # Look offline first. A caller who gave the code already knows the
        # industry; making them wait on a 1,012-entry download to pretty-print
        # a title they did not ask for is a cost with no benefit. The download
        # happens only if the code is genuinely unknown here.
        source, label = (table, "a supplied table") if table else index(
            offline=True)
        title = source.get(digits, "")
        if not title and not table and not offline:
            source, label = index(offline=False)
            title = source.get(digits, "")
        return Resolution(
            query=phrase, index=label, certain=True,
            candidates=[Candidate(digits, title or "(title not in this index)",
                                  1.0)])

    source, label = (table, "a supplied table") if table else index(
        offline=offline)
    words = _words(phrase)
    if not words:
        return Resolution(query=phrase, index=label,
                          problem=f"'{phrase}' has no words to match on")

    scored = [Candidate(code, title, _score(words, title))
              for code, title in source.items()]
    scored = [c for c in scored if c.score >= FLOOR]
    scored.sort(key=lambda c: (-c.score, c.code))

    if not scored:
        return Resolution(
            query=phrase, index=label,
            problem=(f"nothing in {label} matches '{phrase}'. Try a broader "
                     f"word, or give the NAICS code directly."))

    top = scored[:8]
    runner_up = top[1].score if len(top) > 1 else 0.0
    certain = top[0].score - runner_up >= MARGIN
    return Resolution(query=phrase, index=label, candidates=top,
                      certain=certain)
