"""One sentence in, a market definition out — or a question back.

This is the seam Von actually described: *"something that can be given a few key
pieces of information (such as a market) and output an S-1 report."* Everything
downstream of here already works on a `MarketDefinition`. What was missing was
the ability to produce one from "landscaping in Phoenix".

**It asks rather than guesses.** An `Interpretation` that is not `ready` carries
the exact question to put to the user and the options to put with it. This is
the same rule the agents follow — refuse rather than degrade — applied one layer
earlier, and it matters more here than anywhere: a request mis-resolved at this
step produces a report that is entirely correct about the wrong market, and
nothing downstream can detect that, because every figure after it is internally
consistent.

**It never invents a geography.** "landscaping" with no place is a national
report, which is a real and correct answer. It is not silently narrowed to
anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .geography import Place, resolve_city, resolve_county, state_fips, state_name
from .naics import Resolution, resolve, too_broad

#: The words that separate an industry from a place in ordinary speech. Kept
#: short and matched as whole words, so "Internet Publishing" does not split on
#: the "in" inside a word.
SPLITTERS = (" in ", " near ", " around ", " within ", " across ")


@dataclass
class Interpretation:
    """What we understood, or what we need to be told."""

    #: Set when the request is fully understood.
    naics: str = ""
    naics_title: str = ""
    state_fips: str = ""
    county_fips: str = ""
    geography_label: str = ""

    #: Set when it is not. `question` is what to ask; `options` is what to
    #: offer. Both empty when `ready`.
    question: str = ""
    options: List[str] = field(default_factory=list)

    #: How we got here, for the report's own provenance line.
    notes: List[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return bool(self.naics) and not self.question

    def definition(self, *, demo: bool = False, customer: str = ""):
        """The `MarketDefinition` the rest of the system runs on."""
        from .report import MarketDefinition

        if not self.ready:
            raise ValueError("this interpretation is not resolved: "
                             + (self.question or "no industry"))
        label = self.naics_title or f"NAICS {self.naics}"
        if self.geography_label:
            label = f"{label} in {self.geography_label}"
        return MarketDefinition(
            label=label, naics=self.naics, state_fips=self.state_fips,
            county_fips=self.county_fips, customer=customer, demo=demo)


def _split(text: str) -> tuple:
    """"landscaping in phoenix" -> ("landscaping", "phoenix").

    Splits on the LAST separator, not the first. "Internet publishing in
    Chicago" has to keep "Internet publishing" whole; splitting on the first
    " in " would hand the resolver "Internet" and the geography "publishing in
    Chicago". Rare, and silently wrong when it happens.
    """
    padded = f" {' '.join((text or '').split())} "
    best = -1
    chosen = ""
    for separator in SPLITTERS:
        position = padded.lower().rfind(separator)
        if position > best:
            best, chosen = position, separator
    if best < 0:
        return text.strip(), ""
    return (padded[:best].strip(), padded[best + len(chosen):].strip())


def _place(text: str) -> Place:
    """A place phrase to a geography, trying the readings in order of certainty.

    "Maricopa County, Arizona" is unambiguous and needs the county table.
    "Phoenix" is a city. "Arizona" is a state. A bare "Maricopa" is a county
    only if we know which state, so it is asked about rather than searched in
    all fifty.
    """
    phrase = " ".join((text or "").split())
    if not phrase:
        return Place()

    if "," in phrase:
        county_part, _, state_part = phrase.rpartition(",")
        code = state_fips(state_part.strip())
        if code:
            county = county_part.strip()
            if not county:
                return Place(state_fips=code, label=state_name(code))
            return resolve_county(county, code)

    # "maricopa county arizona" — try peeling the trailing state off.
    words = phrase.split()
    for take in (2, 1):
        if len(words) > take:
            code = state_fips(" ".join(words[-take:]))
            if code:
                rest = " ".join(words[:-take]).strip()
                if not rest:
                    return Place(state_fips=code, label=state_name(code))
                city = resolve_city(rest)
                if city.resolved and city.state_fips == code:
                    return city
                return resolve_county(rest, code)

    return resolve_city(phrase)


def interpret(text: str, *, place: str = "", offline: bool = False
              ) -> Interpretation:
    """The whole request, from one phrase.

    `place` is the explicit override. When given it wins outright, because a
    caller who passed `--in "Maricopa County, Arizona"` has said what they mean
    and should not have it re-derived from the industry phrase.
    """
    industry_text, embedded_place = _split(text)
    place_text = place.strip() or embedded_place

    found: Resolution = resolve(industry_text, offline=offline)
    result = Interpretation()

    if found.problem:
        return Interpretation(question=found.problem)

    if not found.certain:
        return Interpretation(
            question=(f"'{found.query}' matches {len(found.candidates)} "
                      f"industries in {found.index}. Which one?"),
            options=[str(c) for c in found.candidates])

    broad = too_broad(found.code or "")
    if broad:
        return Interpretation(question=broad)

    result.naics = found.code or ""
    result.naics_title = found.title
    result.notes.append(f"industry resolved from '{industry_text}' against "
                        f"{found.index}")

    if not place_text:
        result.geography_label = "the United States"
        result.notes.append("no place was given, so this is a national report")
        return result

    where = _place(place_text)
    if where.problem:
        return Interpretation(question=where.problem, options=where.candidates)

    result.state_fips = where.state_fips
    result.county_fips = where.county_fips
    result.geography_label = where.label
    result.notes.append(f"geography resolved from '{place_text}'")
    return result
