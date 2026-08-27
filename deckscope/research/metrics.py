"""What a number is *about*, so two numbers are only compared when comparable.

An audit put two findings in front of the closing rules:

    "The market is $7 billion."              [alpha.example.com]
    "A competitor raised $7.2 billion."      [beta.example.org]

and got back CONFIRMED — two independent publishers agreeing within tolerance.
They agreed on nothing. They are both dollars, and that was the entire test.

The mistake is treating a magnitude as if it were a claim. `$7B` is not a claim;
`the annual revenue of this industry in the United States in 2024 is $7B` is.
Agreement is a property of claims, so before comparing magnitudes there has to
be something that says the two numbers measure the same thing.

That is what a `MetricID` is. It is deliberately coarse — subject, measure,
basis, period — because a fine-grained ontology would be wrong in a hundred
quiet ways and this only has to be right about one question: *may these two
numbers be compared at all?* When it cannot tell, it says so, and the closing
rules treat "cannot tell" as "do not compare", which costs a confirmation and
never manufactures one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

#: What kind of quantity this is. Two findings with different measures are never
#: comparable, whatever their units say.
SIZE = "market-size"        # the whole industry or segment
REVENUE = "revenue"         # one company's turnover
FUNDING = "funding"         # capital raised, not earned
COUNT = "count"             # units, firms, people
PRICE = "price"             # what one unit costs a buyer
RATE = "rate"               # growth, retention, margin, share
COST = "cost"               # what it costs to operate or start
UNKNOWN = "unknown"

MEASURES = (SIZE, REVENUE, FUNDING, COUNT, PRICE, RATE, COST, UNKNOWN)

#: Per what. A monthly price and an annual price are the same measure on
#: different bases and must be normalized before they are compared.
PER_YEAR = "year"
PER_MONTH = "month"
PER_ONE = "one"
NO_BASIS = ""

#: Multipliers to bring a basis onto an annual footing.
_TO_ANNUAL = {PER_MONTH: 12.0, PER_YEAR: 1.0, PER_ONE: 1.0, NO_BASIS: 1.0}

_MEASURE_PATTERNS = (
    # Order matters — the first match wins, and the more specific phrasings
    # come first. "raised $7.2B" must not be read as a market size just
    # because the sentence also contains the word market.
    (FUNDING, r"\b(raised|funding round|series [a-f]\b|seed round|venture|"
              r"投資|valuation|valued at|pre-money|post-money)\b"),
    (COST, r"\b(startup cost|start-up cost|capital required|costs? to (start|open|"
           r"launch)|upfront|equipment cost|operating cost)\b"),
    (PRICE, r"\b(price|pricing|per seat|per user|per month|subscription|"
            r"list price|charges?|fees?|contract value|\bacv\b|\bcac\b)\b"),
    # "share of revenue" is a RATE, not a REVENUE. It has to be caught here,
    # above the REVENUE rule, because the first match wins.
    #
    # This cost the entire revenue half of a market-share panel. The question
    # "what share of smartphone revenue does each company hold" classified as
    # REVENUE (one company's turnover) while the finding "Apple held 49% of
    # smartphone revenue" classified as RATE — so the relevance guard saw a
    # measure mismatch and dropped every finding it had just retrieved. The
    # panel then reported the question as unanswerable, which reads as an
    # absence in the world rather than a regex precedence bug.
    #
    # `share price` stays a PRICE because the PRICE rule is above this one.
    (RATE, r"\b(cagr|growth rate|retention|churn|margin|market share|penetration|"
           r"survival|conversion)\b|%|"
           r"\bshare of\b|\b(revenue|unit|shipment|volume|value|installed base)"
           r" share\b|\bpercentage of\b|\bshares? (of the )?market\b"),
    (SIZE, r"\b(market size|market is|addressable market|\btam\b|\bsam\b|\bsom\b|"
           r"industry (is|was|totall?ed)|category is|segment is|market for|"
           # Interrogative forms. The patterns were written against statements,
           # so "How large is the workflow automation market?" classified as
           # UNKNOWN and the relevance guard fell through to permissive.
           r"how (large|big) is|size of the market|market\??$|"
           r"segment (is|was)|addressable segment|category boundary)\b"),
    (REVENUE, r"\b(revenue|arr|mrr|turnover|sales of|billings|earned)\b"),
    (COUNT, r"\b(number of|how many|establishments|businesses|firms|companies|"
            r"customers?|users?|employees?|beneficiaries|professionals?|"
            r"practitioners?|households?|operators?)\b"),
)

_BASIS_PATTERNS = (
    (PER_MONTH, r"\bper month\b|\bmonthly\b|/\s*mo\b|\bmo\b|\bpcm\b|\bmrr\b"),
    (PER_YEAR, r"\bper year\b|\bannual(?:ly)?\b|\bper annum\b|/\s*yr\b|\barr\b|"
               r"\ba year\b"),
    (PER_ONE, r"\bper (customer|user|seat|member|head|establishment|business|"
              r"firm|employee|professional|beneficiary|patient|unit)\b|\beach\b"),
)

_YEAR = re.compile(r"\b(19|20)\d{2}\b")

#: Words too generic to identify a subject. Without this, every finding shares
#: the subject "market" and the check does nothing.
_STOP = {
    "the", "a", "an", "of", "in", "for", "and", "or", "is", "are", "was", "were",
    "to", "at", "on", "by", "with", "this", "that", "these", "those", "its",
    "it", "we", "our", "their", "be", "been", "has", "have", "had", "will",
    "would", "about", "approximately", "roughly", "over", "under", "more",
    "less", "than", "per", "total", "estimated", "estimate", "estimates",
    "reports", "reported", "according", "source", "study", "data", "figure",
    "market", "industry", "segment", "category", "business", "businesses",
    "company", "companies", "firm", "firms", "annual", "year", "years",
    "billion", "million", "trillion", "thousand", "usd", "dollars",
    "percent", "figures", "size", "sized", "sizing",
}


@dataclass
class MetricID:
    """A coarse identity for what a number measures."""

    measure: str = UNKNOWN
    unit: str = ""
    basis: str = NO_BASIS
    #: Content words naming the thing measured, normalized and sorted.
    subject: frozenset = frozenset()
    #: The named thing the statement is *about*, when it opens with one — the
    #: leading run of capitalised words, lowercased and split.
    #:
    #: `subject` alone cannot carry this. It is a bag of content words, so
    #: "WS Audiology holds approximately 27% of the global hearing aid market"
    #: and "GN Group holds approximately 17% of the global hearing aid market"
    #: overlap on eight words and differ on two, which reads as the same
    #: subject at any sane threshold. In a share table that is the whole
    #: question: every row shares the boilerplate and differs only in the name.
    entity: frozenset = frozenset()
    #: The year the figure is true of, when one is stated.
    period: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["subject"] = sorted(self.subject)
        d["entity"] = sorted(self.entity)
        return d

    @property
    def identified(self) -> bool:
        """Whether the measure was recognized at all.

        Informational now rather than gating. `comparable()` refuses on a known
        mismatch, not on ignorance — see the comment there.
        """
        return self.measure != UNKNOWN and bool(self.subject)


def classify(statement: str, *, unit: str = "", value_text: str = "",
             as_of: str = "") -> MetricID:
    """Read a metric identity off a finding.

    Text matching, and openly so. It exists to catch the gross mismatches that
    silently pass a numeric tolerance check — a market against a funding round,
    a monthly price against an annual contract — not to build a semantic model
    of the sentence.
    """
    text = f"{statement} {value_text}".lower()

    measure = UNKNOWN
    for name, pattern in _MEASURE_PATTERNS:
        if re.search(pattern, text):
            measure = name
            break

    basis = NO_BASIS
    for name, pattern in _BASIS_PATTERNS:
        if re.search(pattern, text):
            basis = name
            break

    period = ""
    stamp = _YEAR.search(as_of or "") or _YEAR.search(text)
    if stamp:
        period = stamp.group(0)

    subject = frozenset(
        w for w in re.findall(r"[a-z][a-z0-9-]{2,}", text) if w not in _STOP)

    return MetricID(measure=measure, unit=_norm_unit(unit or value_text),
                    basis=basis, subject=subject, period=period,
                    entity=_entity(statement))


#: Words that open a sentence in capitals without naming anything.
_NOT_A_NAME = frozenset((
    "the", "a", "an", "this", "that", "these", "those", "market", "markets",
    "global", "worldwide", "total", "revenue", "sales", "share", "shares",
    "growth", "industry", "sector", "company", "companies", "it", "its",
    "there", "no", "not", "in", "on", "at", "by", "for", "of", "and", "or",
    "per", "about", "approximately", "around", "over", "under", "between",
    "one", "two", "three", "four", "five", "top", "leading", "largest",
))

#: The leading run of capitalised tokens. Anchored at the start because that is
#: where the subject of an English declarative sentence is, and the reader is
#: told to write one plain sentence of what a source establishes.
_LEADING_CAPS = re.compile(r"^\W*((?:[A-Z][\w&./'-]*)(?:\s+[A-Z][\w&./'-]*)*)")


def _entity(statement: str) -> frozenset:
    """The named thing a statement opens with, if it opens with one.

    Returns an empty set for anything generic, which keeps the check
    permissive: an empty entity never blocks a comparison. Only two findings
    that each name something, and name different things, are separated.
    """
    match = _LEADING_CAPS.match(statement or "")
    if not match:
        return frozenset()
    words = frozenset(w.lower().strip(".,;:") for w in match.group(1).split())
    words = frozenset(w for w in words if w and w not in _NOT_A_NAME)
    # A single letter or digit run is noise, not a name.
    return frozenset(w for w in words if len(w) > 1 and not w.isdigit())


def _norm_unit(raw: str) -> str:
    s = (raw or "").strip().lower()
    if not s or s in ("n/a", "unknown", "none"):
        return ""
    if "%" in s or "percent" in s:
        return "%"
    if "$" in s or "usd" in s or "dollar" in s:
        return "USD"
    return s


#: How much subject vocabulary two findings must share to be about the same
#: thing. Jaccard overlap, deliberately low — two sources rarely phrase a fact
#: the same way, and the measure check is doing most of the work.
SUBJECT_OVERLAP = 0.18


def comparable(a: MetricID, b: MetricID) -> tuple:
    """Whether two metrics may be compared, and why not when they may not.

    Returns `(ok, reason)`. `reason` is written to be shown to a reader, because
    "these were not compared" is a finding in its own right and a bare False
    would be indistinguishable from "these disagree".
    """
    # Refuse only on POSITIVE evidence of a mismatch.
    #
    # The first version of this refused whenever either metric was
    # unidentified, which blocked the audit's bad pair — and also blocked two
    # sources genuinely agreeing on a market size, because the classifier is
    # regex over prose and misses constantly. That trade is wrong: a missed
    # confirmation is a cost, an invented one is a defect, but refusing
    # everything the classifier cannot read turns the loop into a machine that
    # never concludes anything.
    #
    # So an unknown measure is permissive and a *known, different* measure is
    # not. The subject-overlap check below still catches the unclassifiable
    # mismatches, because two findings about genuinely different things do not
    # share vocabulary.
    if a.measure != UNKNOWN and b.measure != UNKNOWN and a.measure != b.measure:
        return False, (f"one measures {a.measure} and the other measures "
                       f"{b.measure} — different quantities, not a disagreement")

    if a.unit and b.unit and a.unit != b.unit:
        return False, f"different units ({a.unit} and {b.unit})"

    if a.period and b.period and a.period != b.period:
        return False, (f"different periods ({a.period} and {b.period}) — a "
                       f"change over time is not a contradiction")

    # Same principle again: only a *demonstrated* difference of subject blocks
    # the comparison. When either side carries no subject vocabulary at all —
    # a bare "Market is $7B" — there is nothing to disagree with, and refusing
    # would make the check fire hardest on the thinnest statements, which is
    # backwards.
    # Two findings that each name something, and name different things, are
    # about different things — however much boilerplate they share. Disjoint
    # rather than unequal, so "Sonova" and "Sonova Holding AG" still compare.
    if a.entity and b.entity and not (a.entity & b.entity):
        return False, (f"one is about {' '.join(sorted(a.entity))} and the "
                       f"other about {' '.join(sorted(b.entity))} — two "
                       f"different subjects, not two views of one")

    if a.subject and b.subject:
        if _overlap(a.subject, b.subject) < SUBJECT_OVERLAP:
            return False, ("these describe different subjects; they share "
                           "almost no vocabulary beyond the units")

    return True, ""


def _overlap(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def to_annual(value: Optional[float], metric: MetricID) -> Optional[float]:
    """Put a value on an annual footing so bases can be compared.

    "$2,000 per month" and "$19,000 average annual contract value" are not a
    contradiction — the first is $24,000 a year and sits inside the second's
    range. Comparing them unnormalized is exactly the error the audit found in
    the shipped demo.
    """
    if value is None:
        return None
    return value * _TO_ANNUAL.get(metric.basis, 1.0)


def answers(question_text: str, metric: MetricID) -> bool:
    """Whether a finding plausibly answers the question it was retrieved for.

    The loop reads sources fetched *for a question*, and a reader that returns
    the first figure on the page produces a sourced, well-formed finding about
    something else entirely. Those findings reach the closing rules and change
    the outcome.

    Compares **measures**, not words. The first version required lexical
    overlap with the question, which correctly killed a finding about a
    competitor called "END RESEARCH MATERIAL" and also killed "a wider category
    boundary is measured at $41B" — a perfectly good answer to a market-size
    question that happened to paraphrase rather than echo. It dropped eighteen
    findings in a fourteen-question demo and left nothing to contest.

    A question about market size is not answered by a startup cost. That much
    is checkable. Whether two sentences share adjectives is not the same
    question and should not be asked here.
    """
    q = classify(question_text)
    if q.measure != UNKNOWN and metric.measure != UNKNOWN:
        return q.measure == metric.measure

    # Measure unknown on one side, so there is no evidence of a mismatch.
    # Permissive, for the same reason `comparable()` is: a guard that fires on
    # ignorance rejects the thinnest statements hardest, and "The market is $7
    # billion" reduces to no subject vocabulary at all once stopwords are
    # removed. Junk like a fence marker read as a company is handled where it
    # is created, not by making this check paranoid.
    return True
