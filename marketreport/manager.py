"""The manager: a plain request in, the right specialists dispatched.

    "Show me the market share of cell phone companies in Ireland"
        → what market, what place, which specialists
            → each specialist runs and returns a panel
                → the panels are the answer

The manager decides **scope**. It does not do research and it does not produce
figures — the specialists do that, and keeping the split sharp is what stops the
manager becoming a second place where numbers can be born.

Two things it must get right, and one it must not pretend to.

**What market, and where.** `request.interpret` already does this for anything
Census-shaped: it resolves "landscaping in Phoenix" to a NAICS code and a county
FIPS, refuses to guess between two consulting codes, and names a city that spans
counties rather than picking one. That work is reused wholesale. The difference
is that a NAICS code is no longer *required* — "cell phones in Ireland" has no
NAICS code and no FIPS, and the market-share specialist does not need one. A
resolved code is now a bonus that unlocks the Census route, not the price of
entry.

**Which specialists.** Rules first, model second — the same order `router.py`
uses, for the same reason: a rule table is inspectable, free, deterministic and
testable offline, and a wrong dispatch is a wrong report that looks fine.

**What it must not pretend:** the manager cannot invent a specialist that does
not exist. If a request asks for something nothing here can answer, it says so
and names what it does have, rather than sending the closest specialist and
letting the panel come back about a different question.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .panel import Panel
from .specialists import Specialist, get, registered, run_specialist

__all__ = ["Request", "read_request", "plan", "answer", "DISPATCH"]


@dataclass
class Request:
    """What was asked, resolved as far as it can be."""

    text: str
    market: str = ""
    place: str = ""
    #: Set when the market also resolves to a US industry code, which unlocks
    #: the Census route. Absent is normal, not a failure.
    naics: str = ""
    state_fips: str = ""
    county_fips: str = ""
    #: Specialists to run, in order.
    specialists: List[str] = field(default_factory=list)
    #: Set when the request cannot be acted on as written.
    question: str = ""
    options: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return bool(self.market) and bool(self.specialists) and not self.question

    def framing(self) -> Dict[str, Any]:
        """What the dataset backends need, when we happen to have it."""
        return {"naics": self.naics, "state_fips": self.state_fips,
                "county_fips": self.county_fips,
                "geography_label": self.place}


#: (pattern, specialist, why). First match wins, and a request may match
#: several — each adds its specialist once.
DISPATCH: List[tuple] = [
    (r"\b(market share|share of (the )?market|who (leads|dominates|has)|"
     r"biggest (player|company|vendor|brand)s?|competitors?|"
     r"concentrat|who competes|market leader|share by (vendor|brand)|"
     r"how much of the market)\b",
     "market-share",
     "a question about who holds what is the market-share specialist's job"),
]

#: Words that mean the request is asking for a market at all. Without one of
#: these a request like "what is the weather" would be dispatched to a market
#: specialist and come back with a confidently sourced answer about nothing.
MARKET_WORDS = re.compile(
    r"\b(market|industry|sector|share|competitors?|vendors?|companies|"
    r"brands?|players?|sales|revenue|shipments?|business)\b", re.I)

#: Phrases that carry the request but not the market. Stripped so "show me the
#: market share of cell phone companies in Ireland" resolves the market as
#: "cell phone" rather than as the whole sentence.
_STRIP = re.compile(
    r"\b(show me|give me|tell me|i want|i need|can you|please|what is|"
    r"what'?s|whats|how big is|who (has|holds|leads|dominates)|"
    r"the market share of|market share of|market share for|the share of|"
    r"a (report|breakdown|chart|graph|pie chart) (of|on|for)|"
    r"breakdown of|report on|analysis of|the market for|market for)\b",
    re.I)

#: Leading articles, which survive the strip patterns and end up in the market
#: name — "the smartphone" rather than "smartphone".
_ARTICLE = re.compile(r"^(the|a|an)\s+", re.I)

#: Trailing nouns that describe the players rather than the market. "cell phone
#: companies" is the cell phone market; "companies" is not part of its name.
_TRAILING = re.compile(
    r"\s+(companies|company|vendors?|brands?|manufacturers?|makers?|players?|"
    r"industry|market|sector|business(es)?)\b\s*$", re.I)


def _clean_market(text: str) -> str:
    body = _STRIP.sub(" ", text or "")
    body = " ".join(body.split())
    body = _ARTICLE.sub("", body)
    previous = None
    while previous != body:
        previous = body
        body = _TRAILING.sub("", body).strip()
    return body.strip(" ,;:-")


def read_request(text: str, *, offline: bool = False) -> Request:
    """Turn a sentence into a request, or into a question back.

    The geography and industry resolution is `request.interpret`, reused. What
    changes here is that failing to resolve a NAICS code is no longer fatal:
    "cell phones in Ireland" has no code and no FIPS, and refusing it would
    reproduce the exact limitation that made the old system useless for the
    question Von actually asked.
    """
    from .geography import resolve_city, state_fips, state_name
    from .request import _split

    # Trailing punctuation comes off the WHOLE request before it is split, not
    # off the market half afterwards. Stripping it later left the place as
    # "Seattle?" — which then failed to resolve, and reported a real US city as
    # a foreign geography rather than as a stray question mark.
    asked = " ".join((text or "").split())
    asked = re.sub(r"[?!.]+\s*$", "", asked).strip()
    if not asked:
        return Request(text="", question="Name a market to look at.")

    industry_text, embedded_place = _split(asked)
    request = Request(text=asked,
                      market=_clean_market(industry_text),
                      place=" ".join((embedded_place or "").split()))

    if not request.market:
        return Request(text=asked,
                       question="I could not tell which market you mean.")

    # A NAICS code is a bonus, not a requirement — but it IS evidence that a
    # phrase names a market, which is how "landscaping in Phoenix" gets in.
    #
    # The first version required one of the market words, and rejected Von's
    # original question. A guard whose job is to turn away "what is the weather
    # tomorrow" must not also turn away the question the whole product exists
    # to answer, and a bare industry name carries none of those words.
    from .naics import resolve as resolve_naics

    found = resolve_naics(request.market, offline=True)
    names_an_industry = bool(found.certain and found.code)

    if not names_an_industry and not MARKET_WORDS.search(asked):
        return Request(
            text=asked,
            question=(f"'{asked}' does not look like a question about a "
                      f"market. Say which market you want and I will look at "
                      f"who holds it, how big it is and how it is changing."))

    # When the market happens to be a US industry the code unlocks the Census
    # route for counts and receipts — genuinely better than searching for
    # those. When it does not, we carry on with the words.
    if names_an_industry:
        request.naics = found.code
        request.notes.append(
            f"'{request.market}' also resolves to NAICS {found.code} "
            f"({found.title}), so US statistical sources are available to the "
            f"specialists as well as published research")

    if request.place:
        where = resolve_city(request.place)
        if where.resolved:
            request.state_fips = where.state_fips
            request.county_fips = where.county_fips
            request.notes.append(f"geography resolved to {where.label}")
        else:
            code = state_fips(request.place)
            if code:
                request.state_fips = code
                request.notes.append(f"geography resolved to "
                                     f"{state_name(code)}")
            else:
                # NOT a failure. "Ireland" is a perfectly good geography that
                # no US FIPS table will ever contain, and the specialists take
                # it as words. Refusing here would rebuild the wall this whole
                # exercise was about tearing down.
                request.notes.append(
                    f"'{request.place}' is not a US geography, so the "
                    f"specialists will research it by name rather than by "
                    f"statistical code")

    request.specialists = _choose(asked, names_an_industry)
    if not request.specialists:
        return Request(
            text=asked, market=request.market, place=request.place,
            question=(f"Nothing here answers that yet. What I can do for "
                      f"'{request.market}':"),
            options=[f"{s.name} — {s.job}" for s in registered()])
    return request


def _choose(text: str, names_an_industry: bool = False) -> List[str]:
    """Which specialists this request wants.

    Rules first, and for now rules only. A model classifier would add a call to
    every request and be neither inspectable nor free, and with one specialist
    registered it would have nothing to decide. When the roster grows past what
    a regex table can separate, the model goes here — behind the rules, the way
    `router.classify` consults one only when its table abstains.
    """
    chosen: List[str] = []
    for pattern, name, _why in DISPATCH:
        if re.search(pattern, text, re.I) and name not in chosen:
            if get(name) is not None:
                chosen.append(name)

    # A market question with no clearer signal gets the market-share panel,
    # because "tell me about this market" almost always means "who is in it and
    # how big is it" — and answering the likely question beats asking which of
    # one option the user meant.
    #
    # `names_an_industry` is the second door, and it is the one that lets a
    # bare "landscaping in Phoenix" through. That request carries none of the
    # market words, because a person naming an industry does not also say the
    # word "market" — which is exactly why the first version turned away the
    # question this product was built for.
    if not chosen and get("market-share") and (
            names_an_industry or MARKET_WORDS.search(text)):
        chosen.append("market-share")
    return chosen


def plan(request: Request) -> List[Specialist]:
    return [s for s in (get(n) for n in request.specialists) if s is not None]


def answer(text: str, *, provider: Any, researcher: Any,
           registry: Any = None, policy: Any = None,
           on_event: Optional[Callable[[str], None]] = None,
           on_usage: Optional[Callable] = None,
           shaper: Optional[Callable[..., Dict[str, Any]]] = None,
           offline: bool = False) -> Dict[str, Any]:
    """The whole path: a sentence to a set of panels.

    Returns the request and the panels rather than a rendering, so the caller
    chooses the format and the panels can be stored, re-read and re-arranged
    without re-running anything.

    One `SourceRegistry` is shared across every specialist on purpose. Two
    specialists reading the same page must give it the same citable ID, or the
    assembled document ends up with two source lists that disagree about what
    S3 means.
    """
    from deckscope.sources import SourceRegistry

    emit = on_event or (lambda *_: None)
    request = read_request(text, offline=offline)
    if not request.ready:
        return {"request": request, "panels": [],
                "question": request.question, "options": request.options}

    for note in request.notes:
        emit(f"  {note}")
    emit(f"dispatching: {', '.join(request.specialists)}")

    registry = registry if registry is not None else SourceRegistry()
    panels: List[Panel] = []
    for spec in plan(request):
        emit(f"— {spec.name} —")
        panels.append(run_specialist(
            spec, market=request.market, place=request.place,
            provider=provider, researcher=researcher, registry=registry,
            policy=policy, framing=request.framing(), shaper=shaper,
            on_event=emit, on_usage=on_usage))

    return {"request": request, "panels": panels,
            "question": "", "options": []}
