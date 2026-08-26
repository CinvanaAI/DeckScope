"""Tests for the research engine.

Grouped around the properties the design claims, because those are what a later
change will quietly break. Every one of these corresponds to something that
either went wrong on the first end-to-end run or would have gone unnoticed:

  I1  a question closes only on a stated rule, never on a model's satisfaction
  I2  agreement from one publisher is not corroboration
  I3  a database question never goes to web search
  I4  reading raises new questions, and they may land on another beat
  I5  an unsourced finding never reaches the output
  I6  NDA mode refuses, it does not warn
  I7  claim-bound questions cannot be starved by generic ones
  I8  the same query is never run twice
  I9  the closing note says what actually stopped the research

The loop's reader is a callable precisely so these can run with no model.
"""
from __future__ import annotations

import unittest

from deckscope.claims import ClaimRegister
from deckscope.compare import (MATERIAL_RATIO, MISMATCH_CEILING,
                               OVER_ASK_CEILING, assess_claims,
                               ask_versus_requirement, build, detect_omissions)
from deckscope.config import ProviderConfig
from deckscope.research.base import Researcher, SearchResult
from deckscope.research.closing import decide
from deckscope.research.findings import FindingRegistry, parse_number
from deckscope.research.loop import Budget, ResearchLoop
from deckscope.research.questions import (CONFIRMED, CONTESTED, OPEN,
                                          UNANSWERABLE, QuestionQueue)
from deckscope.research.reader import _clean
from deckscope.research import router
from deckscope.security.policy import SecurityPolicy
from deckscope.sources import SourceRegistry
from deckscope.tiering import (JUDGE, EXTRACT, ModelPlan, NDAGuard, NDAViolation,
                               is_local)


class StubSearch(Researcher):
    """Two sources on different domains, so independence checks can pass."""

    name = "stub"

    def __init__(self, snippets=None):
        self.queries = []
        self.snippets = snippets or [
            ("Estimate A", "https://alpha.example.com/1", "The market is $7B."),
            ("Estimate B", "https://beta.example.org/2", "The market is $7.2B."),
        ]

    def search(self, query, max_results=8):
        self.queries.append(query)
        return [SearchResult(t, u, s, "2026-01", query)
                for t, u, s in self.snippets]


def make_loop(reader, *, queue=None, budget=None, researcher=None):
    q = queue or QuestionQueue()
    if not q.questions:
        q.add("How large is the market?", beat="sizing", weight="high")
    return ResearchLoop(
        researcher=researcher or StubSearch(), registry=SourceRegistry(),
        queue=q, findings=FindingRegistry(), reader=reader,
        policy=SecurityPolicy(), budget=budget or Budget(max_iterations=6))


def reader_returning(findings, questions=()):
    def read(*, question, evidence, citable_ids):
        rows = []
        for row in findings:
            row = dict(row)
            # Cite whatever this question actually retrieved, so the fixture
            # never accidentally tests the citation-stripping path.
            row.setdefault("source_ids", list(citable_ids[:1]))
            rows.append(row)
        return {"findings": rows, "new_questions": [dict(q) for q in questions]}
    return read


# ---------------------------------------------------------------- I1: closing

class ClosingRules(unittest.TestCase):

    def test_a_question_cannot_be_closed_without_a_reason(self):
        q = QuestionQueue()
        question = q.add("How large is the market?")
        with self.assertRaises(ValueError):
            q.close(question.id, CONFIRMED, "   ")

    def test_only_terminal_statuses_close(self):
        q = QuestionQueue()
        question = q.add("How large is the market?")
        with self.assertRaises(ValueError):
            q.close(question.id, OPEN, "because I said so")

    def test_two_independent_sources_agreeing_confirms(self):
        reg = FindingRegistry()
        a = reg.add("Market is $7B", value_text="$7B", source_ids=["S1"])
        b = reg.add("Market is $7.2B", value_text="$7.2B", source_ids=["S2"])
        sources = {"S1": type("S", (), {"url": "https://alpha.example.com/x"})(),
                   "S2": type("S", (), {"url": "https://beta.example.org/y"})()}
        verdict = decide([a, b], sources.get)
        self.assertEqual(verdict.status, CONFIRMED)
        self.assertIn("independent", verdict.because)

    def test_agreement_from_one_publisher_is_not_corroboration(self):
        """I2 — the failure that makes a content farm look like consensus."""
        reg = FindingRegistry()
        a = reg.add("Market is $7B", value_text="$7B", source_ids=["S1"])
        b = reg.add("Market is $7.1B", value_text="$7.1B", source_ids=["S2"])
        same = {"S1": type("S", (), {"url": "https://one.example.com/a"})(),
                "S2": type("S", (), {"url": "https://one.example.com/b"})()}
        verdict = decide([a, b], same.get, attempts=3, max_attempts=3)
        self.assertEqual(verdict.status, UNANSWERABLE)
        self.assertIn("single publisher", verdict.because)

    def test_disagreement_survives_as_contested(self):
        reg = FindingRegistry()
        a = reg.add("Market is $7B", value_text="$7B", source_ids=["S1"])
        b = reg.add("Market is $41B", value_text="$41B", source_ids=["S2"])
        srcs = {"S1": type("S", (), {"url": "https://a.example.com/"})(),
                "S2": type("S", (), {"url": "https://b.example.org/"})()}
        self.assertIsNone(decide([a, b], srcs.get, attempts=0).status)
        late = decide([a, b], srcs.get, attempts=3, max_attempts=3)
        self.assertEqual(late.status, CONTESTED)

    def test_absence_closes_before_the_loop_spends_more(self):
        reg = FindingRegistry()
        a = reg.add("No source publishes this", method="absent")
        verdict = decide([a], lambda _sid: None)
        self.assertEqual(verdict.status, UNANSWERABLE)
        self.assertIn("no source addresses this", verdict.because)

    def test_one_source_is_not_reported_as_no_backend_answering(self):
        """I9 — the message said 'no backend can answer this' over a sourced figure."""
        reg = FindingRegistry()
        a = reg.add("Startup capital is $10,000", value_text="$10,000",
                    source_ids=["S1"])
        verdict = decide([a], lambda _s: type("S", (), {"url": "https://x.example"})(),
                         attempts=3, max_attempts=3)
        self.assertEqual(verdict.status, UNANSWERABLE)
        self.assertNotIn("no backend can answer", verdict.because)
        self.assertIn("corroborat", verdict.because)

    def test_the_closing_note_distinguishes_budget_from_no_new_query(self):
        """I9 — blaming the budget when the budget was fine sends the reader wrong."""
        reg = FindingRegistry()
        a = reg.add("Something", value_text="$1", source_ids=["S1"])
        lookup = (lambda _s: type("S", (), {"url": "https://x.example"})())
        budget = decide([a], lookup, budget_exhausted=True)
        repeat = decide([a], lookup, budget_exhausted=True,
                        exhausted_reason="every query the loop could form for this "
                                         "had already been run")
        self.assertIn("budget", budget.because)
        self.assertNotIn("budget", repeat.because)


# ---------------------------------------------------------------- I3: routing

class Routing(unittest.TestCase):

    def test_a_count_question_goes_to_a_dataset_not_search(self):
        route = router.classify("How many landscaping businesses operate in "
                                "Maricopa County?")
        self.assertEqual(route.kind, router.DATASET)
        self.assertTrue(route.backend)

    def test_a_survival_question_goes_to_the_survival_series(self):
        route = router.classify("What fraction of new firms make it to 5 years?")
        self.assertEqual(route.kind, router.DATASET)

    def test_a_market_size_question_still_goes_to_search(self):
        route = router.classify("What is the TAM for workflow automation?")
        self.assertEqual(route.kind, router.SEARCH)

    def test_a_dataset_backend_refuses_rather_than_guessing(self):
        """Without a NAICS code the honest answer is nothing, not a plausible number."""
        from deckscope.research.datasets import Unavailable, get_backend
        backend = get_backend("census_cbp")
        if backend is None:
            self.skipTest("census backend not registered")
        with self.assertRaises(Unavailable):
            backend.answer("How many businesses?", {})


# ------------------------------------------------------- I4/I5: the loop runs

class LoopMechanics(unittest.TestCase):

    def test_reading_can_post_a_question_to_another_beat(self):
        """I4 — the cross-posting that makes this more than a for-loop."""
        queue = QuestionQueue()
        queue.add("How large is the market?", beat="sizing", weight="high")
        loop = make_loop(
            reader_returning(
                [{"statement": "Market is $7B", "value": "$7B"}],
                [{"text": "Does a licence exemption apply below $50k revenue?",
                  "beat": "regulation", "weight": "high"}]),
            queue=queue, budget=Budget(max_iterations=1))
        loop.run()
        beats = {q.beat for q in queue.questions}
        self.assertIn("regulation", beats)
        child = [q for q in queue.questions if q.beat == "regulation"][0]
        self.assertEqual(child.parent, "Q1", "parentage is the audit trail")

    def test_an_unsourced_finding_never_reaches_the_output(self):
        """I5 — the same invariant as the citation audit, one layer down."""
        loop = make_loop(reader_returning(
            [{"statement": "Something nobody wrote down", "source_ids": []}]),
            budget=Budget(max_iterations=1))
        report = loop.run()
        statements = [f["statement"] for f in report["findings"]["findings"]]
        self.assertNotIn("Something nobody wrote down", statements)

    def test_a_citation_to_a_source_this_question_never_saw_is_dropped(self):
        def read(*, question, evidence, citable_ids):
            return {"findings": [{"statement": "Invented", "source_ids": ["S999"]}],
                    "new_questions": []}
        loop = make_loop(read, budget=Budget(max_iterations=1))
        report = loop.run()
        self.assertEqual([], [f for f in report["findings"]["findings"]
                              if "S999" in f.get("source_ids", [])])

    def test_the_budget_stops_the_loop_and_says_so(self):
        queue = QuestionQueue()
        for i in range(10):
            queue.add(f"Question number {i} about market size", beat="sizing")
        loop = make_loop(reader_returning([{"statement": "A fact", "value": "$1B"}]),
                         queue=queue, budget=Budget(max_iterations=3))
        report = loop.run()
        self.assertEqual(3, report["budget"]["iterations"])
        self.assertTrue(report["budget"]["stopped_because"])
        self.assertEqual([], queue.open_questions(),
                         "nothing may be left dangling when the run ends")

    def test_the_same_query_is_never_run_twice(self):
        """I8 — three identical retrievals produced three copies of one finding."""
        researcher = StubSearch()
        queue = QuestionQueue()
        queue.add("How large is the market?", beat="sizing", weight="high")
        loop = make_loop(
            reader_returning([{"statement": "A is $7B", "value": "$7B"},
                              {"statement": "B is $41B", "value": "$41B"}]),
            queue=queue, budget=Budget(max_iterations=6), researcher=researcher)
        loop.run()
        self.assertEqual(len(researcher.queries), len(set(researcher.queries)),
                         "the loop re-ran a query it had already run")

    def test_a_repeated_finding_is_not_counted_twice(self):
        reg = FindingRegistry()
        a = reg.add("Market is $7B", value_text="$7B", source_ids=["S1"])
        b = reg.add("Market is $7B", value_text="$7B", source_ids=["S1"])
        self.assertIs(a, b)
        self.assertEqual(1, len(reg.findings))

    def test_the_same_statement_from_a_different_source_is_corroboration(self):
        reg = FindingRegistry()
        reg.add("Market is $7B", value_text="$7B", source_ids=["S1"])
        reg.add("Market is $7B", value_text="$7B", source_ids=["S2"])
        self.assertEqual(2, len(reg.findings),
                         "collapsing these would destroy the independence check")

    def test_max_depth_stops_a_runaway_chain(self):
        queue = QuestionQueue(max_depth=1)
        root = queue.add("Root question about the market")
        child = queue.add("Child question about the market", parent=root.id)
        grandchild = queue.add("Grandchild question about the market",
                               parent=child.id)
        self.assertIsNone(grandchild)
        self.assertTrue(queue.refused)

    def test_claim_bound_questions_cannot_be_starved(self):
        """I7 — every claim came back unverifiable because of the scheduler."""
        queue = QuestionQueue()
        for i in range(8):
            queue.add(f"Generic market question number {i}", beat="sizing",
                      weight="high")
        queue.add("Is this supported: the market is $47B", beat="sizing",
                  claims=["C1"], weight="high")
        seen = set()
        for _ in range(6):
            q = queue.next()
            seen.add(q.id)
            queue.record_attempt(q.id, "search", q.text, 1)
            queue.close(q.id, UNANSWERABLE, "test")
        bound = [q for q in queue.questions if q.claims][0]
        self.assertIn(bound.id, seen,
                      "a run that never checks a claim has failed at its job")


# ------------------------------------------------------------- I6: NDA mode

class NDAMode(unittest.TestCase):

    def test_deck_content_cannot_reach_a_hosted_provider(self):
        guard = NDAGuard(enabled=True)
        deck = ("Acme Robotics builds autonomous forklift retrofits for "
                "third-party logistics warehouses across the midwest region")
        guard.protect(deck)
        hosted = ProviderConfig(name="openai", model="gpt-5.2")
        with self.assertRaises(NDAViolation):
            guard.check(hosted, f"Analyse this: {deck}", where="test")

    def test_the_taint_flag_alone_is_enough(self):
        guard = NDAGuard(enabled=True)
        with self.assertRaises(NDAViolation):
            guard.check(ProviderConfig(name="anthropic"), "anything",
                        tainted=True, where="test")

    def test_a_local_provider_is_allowed(self):
        guard = NDAGuard(enabled=True)
        deck = ("Acme Robotics builds autonomous forklift retrofits for "
                "third-party logistics warehouses across the midwest region")
        guard.protect(deck)
        local = ProviderConfig(name="openai_compatible",
                              base_url="http://localhost:11434/v1")
        guard.check(local, deck, tainted=True, where="test")   # must not raise

    def test_a_hosted_gateway_pretending_to_be_local_is_not_local(self):
        self.assertFalse(is_local(ProviderConfig(
            name="openai_compatible", base_url="https://api.together.xyz/v1")))
        self.assertTrue(is_local(ProviderConfig(
            name="openai_compatible", base_url="http://127.0.0.1:1234/v1")))

    def test_disabled_guard_does_nothing_at_all(self):
        guard = NDAGuard(enabled=False)
        guard.protect("secret deck text that would otherwise be fingerprinted")
        guard.check(ProviderConfig(name="openai"), "secret deck text",
                    tainted=True)   # must not raise

    def test_tiers_degrade_upward_never_downward(self):
        best = ProviderConfig(name="anthropic", model="claude-opus-5")
        plan = ModelPlan(best=best)
        self.assertIs(plan.for_task(EXTRACT), best,
                      "cheap work on a big model is wasteful but correct")
        self.assertIs(plan.for_task(JUDGE), best)
        small_only = ModelPlan(small=ProviderConfig(name="mock"))
        self.assertIsNotNone(small_only.for_task(JUDGE))


# ------------------------------------------------------- comparison stage

class Comparison(unittest.TestCase):

    def _register(self, claim_text, value_text=""):
        reg = ClaimRegister()
        reg.add(claim_text, type="market-size", load_bearing="high",
                value_text=value_text)
        return reg

    def test_a_claim_far_from_the_evidence_is_contradicted_with_the_gap_measured(self):
        register = self._register("The market is $47B", value_text="$47B")
        findings = FindingRegistry()
        findings.add("Independent estimates put it at $7B", value_text="$7B",
                     source_ids=["S1"], claims=["C1"])
        [assessment] = assess_claims(register, findings)
        self.assertEqual("contradicted", assessment.assessment)
        self.assertGreater(assessment.ratio, MATERIAL_RATIO)
        self.assertIn("$47B", assessment.gap_text)
        self.assertIn("$7B", assessment.gap_text)

    def test_a_claim_inside_the_evidence_is_supported(self):
        register = self._register("The market is $7B", value_text="$7B")
        findings = FindingRegistry()
        findings.add("Estimates put it at $7.2B", value_text="$7.2B",
                     source_ids=["S1"], claims=["C1"])
        [assessment] = assess_claims(register, findings)
        self.assertEqual("supported", assessment.assessment)

    def test_a_dollar_claim_is_not_measured_against_a_percentage(self):
        """Matching units is necessary. The first version had no check at all,
        and compared '$28,000 ACV' against '104-112%' — a ratio of about 270,
        reported as a contradiction with a confident gap line."""
        register = self._register("Average contract value: $28,000",
                                  value_text="$28,000")
        findings = FindingRegistry()
        findings.add("Net revenue retention runs 104-112%", value_text="104-112%",
                     unit="%", source_ids=["S1"], claims=["C1"])
        [assessment] = assess_claims(register, findings)
        self.assertNotEqual("contradicted", assessment.assessment)

    def test_company_revenue_is_not_measured_against_market_size(self):
        """Both are dollars, and they measure entirely different things.

        The honest-control case produced 'claimed $520k ARR; evidence indicates
        $2.6-3.0B — roughly 5384.6x below' and called it contradicted. The
        control case exists to catch a system that calls everything contradicted,
        and this is what it caught.
        """
        register = self._register("$520k ARR across 41 customers",
                                  value_text="$520k")
        findings = FindingRegistry()
        findings.add("The category is $2.6-3.0B", value_text="$2.6-3.0B",
                     unit="USD", source_ids=["S1"], claims=["C1"])
        [assessment] = assess_claims(register, findings)
        self.assertEqual("partially-supported", assessment.assessment)
        self.assertGreater(assessment.ratio, MISMATCH_CEILING)
        self.assertIn("not checked rather than judged", assessment.because)

    def test_an_order_of_magnitude_overstatement_is_still_contradicted(self):
        """The mismatch ceiling must not swallow the case the product is for."""
        register = self._register("The market is $88B", value_text="$88B")
        findings = FindingRegistry()
        findings.add("The category is $6-8B", value_text="$6-8B", unit="USD",
                     source_ids=["S1"], claims=["C1"])
        [assessment] = assess_claims(register, findings)
        self.assertEqual("contradicted", assessment.assessment)

    def test_a_claim_with_no_research_is_unverifiable_not_supported(self):
        register = self._register("We have the best team in the industry")
        [assessment] = assess_claims(register, FindingRegistry())
        self.assertEqual("unverifiable", assessment.assessment)

    def test_the_under_ask_gap_is_reported_as_a_finding_about_the_pitcher(self):
        """The nephew case: asked $5,000, needs $10,000, and that is the finding."""
        findings = FindingRegistry()
        findings.add("Startup capital runs about $10,000 once equipment, "
                     "licensing and insurance are included",
                     beat="economics", value_text="$10,000", source_ids=["S1"])
        [signal] = ask_versus_requirement({"ask": {"amount": "$5,000"}}, findings)
        self.assertEqual("under-ask", signal.kind)
        self.assertAlmostEqual(2.0, signal.ratio, places=1)
        self.assertIn("person", signal.why_it_matters)

    def test_an_absurd_multiple_is_a_unit_mismatch_not_an_over_ask(self):
        """A $4M seed against a $10k setup cost is not a 400x over-ask."""
        findings = FindingRegistry()
        findings.add("Startup capital runs about $10,000",
                     beat="economics", value_text="$10,000", source_ids=["S1"])
        [signal] = ask_versus_requirement({"ask": {"amount": "$4M"}}, findings)
        self.assertEqual("unit-mismatch", signal.kind)
        self.assertGreater(signal.ratio, OVER_ASK_CEILING)
        self.assertIn("no conclusion is drawn", signal.why_it_matters)

    def test_a_plausible_over_ask_is_still_reported(self):
        findings = FindingRegistry()
        findings.add("Startup capital runs about $10,000",
                     beat="economics", value_text="$10,000", source_ids=["S1"])
        [signal] = ask_versus_requirement({"ask": {"amount": "$50,000"}}, findings)
        self.assertEqual("over-ask", signal.kind)

    def test_no_ask_produces_no_signal(self):
        self.assertEqual([], ask_versus_requirement({}, FindingRegistry()))

    def test_evidence_the_deck_never_addresses_becomes_an_omission(self):
        register = ClaimRegister()
        register.add("We grew 40% last quarter", type="traction")
        findings = FindingRegistry()
        findings.add("BlackLine already sells into this segment",
                     beat="competitors", source_ids=["S1"])
        rows = detect_omissions(register, findings,
                                assess_claims(register, findings),
                                deck_text="We grew 40% last quarter.")
        kinds = {r["kind"] for r in rows}
        self.assertIn("unaddressed-evidence", kinds)
        self.assertIn("BlackLine", rows[0]["names"])

    def test_a_competitor_the_deck_does_name_is_not_an_omission(self):
        register = ClaimRegister()
        findings = FindingRegistry()
        findings.add("BlackLine already sells into this segment",
                     beat="competitors", source_ids=["S1"])
        rows = detect_omissions(register, findings, [],
                                deck_text="Our competitors are BlackLine and Trintech.")
        self.assertEqual([], [r for r in rows
                              if r["kind"] == "unaddressed-evidence"])

    def test_an_omission_found_while_checking_a_claim_still_counts(self):
        """The route a finding arrived by says nothing about whether the deck
        mentions it. Testing `not f.claims` dropped most of the blind spots."""
        register = ClaimRegister()
        claim = register.add("The market is $47B", type="market-size")
        findings = FindingRegistry()
        findings.add("Trintech is an incumbent in this category",
                     beat="competitors", source_ids=["S1"], claims=[claim.id])
        rows = detect_omissions(register, findings, [],
                                deck_text="The market is $47B.")
        self.assertIn("unaddressed-evidence", {r["kind"] for r in rows})

    def test_a_missing_section_is_recorded_as_a_finding_about_the_company(self):
        register = ClaimRegister.from_extraction({"claims": [], "market": {}})
        sections = {o["section"] for o in register.omissions}
        self.assertIn("team", sections)
        self.assertIn("pricing", sections)

    def test_contested_findings_are_promoted_not_averaged(self):
        register = ClaimRegister()
        queue = QuestionQueue()
        q = queue.add("How large is the market?")
        findings = FindingRegistry()
        findings.add("It is $7B", question_id=q.id, value_text="$7B",
                     source_ids=["S1"])
        findings.add("It is $41B", question_id=q.id, value_text="$41B",
                     source_ids=["S2"])
        findings.detect_contradictions()
        out = build(register, findings, queue, {})
        self.assertTrue(out["contested"])
        positions = out["contested"][0]["positions"]
        self.assertEqual({"$7B", "$41B"}, {p["value"] for p in positions})


# --------------------------------------------------------------- framing

class Framing(unittest.TestCase):

    def test_two_equally_ranked_readings_are_contested(self):
        reg = ClaimRegister()
        reg.add_framing("workflow automation", confidence="medium")
        reg.add_framing("robotic process automation", confidence="medium")
        self.assertTrue(reg.framing_is_contested)

    def test_a_clear_winner_is_not_contested(self):
        reg = ClaimRegister()
        reg.add_framing("landscaping services", confidence="high")
        reg.add_framing("lawn care", confidence="low")
        self.assertFalse(reg.framing_is_contested)

    def test_a_guessed_sector_code_is_dropped_rather_than_used(self):
        from deckscope.research.engine import _clean_naics
        self.assertEqual("", _clean_naics("56"),
                         "a 2-digit code is a whole sector; the count would be "
                         "meaningless and would look authoritative")
        self.assertEqual("561730", _clean_naics("561730"))
        self.assertEqual("", _clean_naics("not sure"))


# ----------------------------------------------------------------- parsing

class Parsing(unittest.TestCase):

    def test_ranges_become_midpoints(self):
        self.assertAlmostEqual(7e9, parse_number("$6-8B"), delta=1)

    def test_units_scale(self):
        self.assertAlmostEqual(4e6, parse_number("$4M"), delta=1)
        self.assertAlmostEqual(1e3, parse_number("1 thousand"), delta=1)

    def test_no_number_is_none_not_zero(self):
        self.assertIsNone(parse_number("a large and growing market"))
        self.assertIsNone(parse_number(None))

    def test_the_reader_drops_malformed_rows(self):
        cleaned = _clean({"findings": [{"statement": ""}, "nonsense",
                                       {"statement": "Real", "source_ids": ["S1"]}],
                          "new_questions": ["a bare string question"]},
                         {"S1"})
        self.assertEqual(1, len(cleaned["findings"]))
        self.assertEqual(1, len(cleaned["new_questions"]))

    def test_the_reader_returns_empty_on_garbage(self):
        self.assertEqual({"findings": [], "new_questions": []},
                         _clean("not a dict", {"S1"}))


if __name__ == "__main__":
    unittest.main()
