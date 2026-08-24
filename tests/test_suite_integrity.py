"""The evaluation cases have to be checkable before they can check anything.

Every expectation in a case is a string or a pattern asserted by its author, and
each one has a way of being quietly wrong that no analysis could ever survive:

* a `must_not_fabricate` string that actually appears in the case's own deck or
  corpus fails every correct analysis, because quoting the evidence is scored as
  inventing it;
* a `blind_spots` entry whose phrases appear nowhere in the corpus can never be
  found, so it fails everything for the opposite reason;
* a `claims` pattern that matches nothing is scored as "not raised", which looks
  like an analysis defect and is a fixture defect.

Those three would all show up as a low score with a plausible-looking
explanation, which is the worst way for a benchmark to be broken. The first two
are decidable from the fixtures alone and are enforced here.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.evaluation.cases import default_suite_dir, load_suite


def _fixture_text(case, root):
    text = case.deck_path(root).read_text(encoding="utf-8")
    corpus = case.corpus_path(root)
    if corpus:
        text += "\n" + corpus.read_text(encoding="utf-8")
    return text.lower()


def _suite():
    root = default_suite_dir()
    return load_suite(str(root)), root.parent


def test_no_case_forbids_a_string_its_own_evidence_contains():
    """Otherwise the correct analysis — the one that quotes the source — is the
    one scored as fabricating."""
    cases, root = _suite()
    offenders = []
    for case in cases:
        text = _fixture_text(case, root)
        for forbidden in case.expect.must_not_fabricate:
            if forbidden.lower() in text:
                offenders.append(f"{case.id}: {forbidden!r} is in its own fixtures")
    assert not offenders, "; ".join(offenders)


def test_every_blind_spot_is_actually_present_in_the_corpus():
    """A blind spot is 'what the corpus has and the deck omits'. If no phrasing
    of it appears in the corpus, no analysis can name it and the case fails
    everything for a reason that is not about the analysis."""
    cases, root = _suite()
    offenders = []
    for case in cases:
        corpus = case.corpus_path(root)
        if not corpus:
            continue
        text = corpus.read_text(encoding="utf-8").lower()
        for spot in case.expect.blind_spots:
            if not any(m.lower() in text for m in spot.must_mention):
                offenders.append(f"{case.id}: none of {spot.must_mention} is in the corpus")
    assert not offenders, "; ".join(offenders)


def test_a_blind_spot_the_deck_already_states_is_not_a_blind_spot():
    """If the deck names it, an analysis repeating it has demonstrated nothing.
    At least one phrasing must be absent from the deck."""
    cases, root = _suite()
    offenders = []
    for case in cases:
        deck = case.deck_path(root).read_text(encoding="utf-8").lower()
        for spot in case.expect.blind_spots:
            if all(m.lower() in deck for m in spot.must_mention):
                offenders.append(f"{case.id}: the deck already says {spot.must_mention}")
    assert not offenders, "; ".join(offenders)


#: Vocabulary any analyst may legitimately use without having invented anything.
#: A `must_not_fabricate` entry drawn from this set produces a false accusation:
#: "Series B" was listed once, and a correct analysis failed the fabrication
#: check for asking "what would make this a Series B rather than a bridge?".
#: The entry has to name a specific invented fact — a figure, a company, a date —
#: not a word that belongs to the register.
GENERIC_TERMS = {
    "series a", "series b", "series c", "series d", "seed", "pre-seed",
    "ipo", "arr", "nrr", "cac", "ltv", "tam", "sam", "som", "churn",
    "bridge", "runway", "burn", "valuation", "term sheet", "due diligence",
}


def test_must_not_fabricate_entries_are_specific_not_vocabulary():
    """Otherwise the check punishes an analysis for speaking the language."""
    cases, _ = _suite()
    offenders = []
    for case in cases:
        for forbidden in case.expect.must_not_fabricate:
            if forbidden.strip().lower() in GENERIC_TERMS:
                offenders.append(
                    f"{case.id}: {forbidden!r} is ordinary analyst vocabulary, not "
                    f"an invented fact — any correct analysis may use it")
    assert not offenders, "; ".join(offenders)


def test_every_claim_pattern_compiles():
    cases, _ = _suite()
    for case in cases:
        for expectation in case.expect.claims:
            re.compile(expectation.matches, re.I)  # raises if malformed


def test_claim_expectations_name_assessments_the_scorer_understands():
    """A typo in an assessment label can never be matched, so the check fails
    silently and permanently."""
    valid = {"supported", "partially-supported", "contradicted", "unverifiable"}
    cases, _ = _suite()
    offenders = []
    for case in cases:
        for expectation in case.expect.claims:
            unknown = {a for a in expectation.assessment if a.lower() not in valid}
            if unknown:
                offenders.append(f"{case.id}: unknown assessment(s) {sorted(unknown)}")
            if not expectation.assessment:
                offenders.append(f"{case.id}: a claim expectation allows no assessment at all")
    assert not offenders, "; ".join(offenders)


def test_verdict_expectations_use_the_documented_calls():
    valid = {"STRONG YES", "YES WITH CONDITIONS", "LEAN NO", "PASS"}
    cases, _ = _suite()
    for case in cases:
        unknown = set(case.expect.verdict_in) - valid
        assert not unknown, f"{case.id}: unknown verdict(s) {sorted(unknown)}"


# ===================================== the anchoring set needs its control

def test_the_anchoring_set_contains_a_case_that_must_not_be_contradicted():
    """Three cases where the right answer is 'the deck's frame is wrong' would be
    passed by an analysis that says that about everything. The control is what
    makes the other three mean something, so its absence is a suite defect."""
    cases, _ = _suite()
    anchoring = [c for c in cases if "anchoring" in c.tags]
    assert anchoring, "the anchoring cases are missing from the suite"

    controls = [c for c in anchoring
                if any("supported" in [a.lower() for a in e.assessment]
                       for e in c.expect.claims)]
    assert controls, (
        "no anchoring case expects 'supported' anywhere, so an analysis that "
        "contradicts every claim would score perfectly on the whole set")


def test_the_control_case_rules_out_walking_away_from_an_honest_deck():
    """The control tests reflexive rejection, and PASS is what that looks like.

    It does not test for a positive verdict. An earlier version did, and two
    independent analyses split between YES WITH CONDITIONS and a LEAN NO argued
    on price — a judgement competent readers can differ on. Pinning it was
    scoring taste rather than accuracy. The claim-level expectations carry this
    control: contradicting a correct market figure is the failure it catches.
    """
    cases, _ = _suite()
    control = next((c for c in cases if c.id == "frame_holds"), None)
    assert control is not None
    assert control.expect.verdict_in, "the control must exclude something"
    assert "PASS" not in control.expect.verdict_in, (
        "walking away from a deck whose every number checks out is the "
        "over-correction this case exists to catch")
    assert any("supported" in [a.lower() for a in e.assessment]
               for e in control.expect.claims), (
        "the control's real teeth are its claim expectations")
