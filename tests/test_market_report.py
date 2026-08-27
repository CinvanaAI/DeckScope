"""The market report: questions, closure, structure arithmetic, assembly.

The design claim is that a report is a set of questions with answers, and that a
reader who finishes it with questions has been failed by it. These check the
parts of that claim that are checkable.

  M1  the standing questions form a dependency order with no cycle
  M2  an unanswered question is a recorded state, never an absent section
  M3  completeness means BOTH no open follow-ups AND no unanswered questions
  M4  concentration is computed with published thresholds, not judged
  M5  saturation reads penetration and growth together, never alone
  M6  the two sizing agents cannot see each other
  M7  derived agents read answers, never raw evidence
"""
from __future__ import annotations

import unittest

import marketreport.agents as _agents   # importing registers them
assert _agents  # noqa: S101 - the import is the point
from marketreport.questions import (COMPUTED, STANDING, Answer, AnswerSet,
                                    BY_ID, order)
from marketreport.report import MarketDefinition, agent_for, build
from marketreport.render import summary, text
from marketreport.structure import (HHI_MODERATE, HHI_UNCONCENTRATED,
                                    Concentration, barriers, cr, from_shares,
                                    from_size_bands, hhi, lifecycle, read_hhi,
                                    saturation)

LANDSCAPING = dict(label="Landscaping services", naics="561730",
                   state_fips="04", county_fips="013")


class M1_QuestionSet(unittest.TestCase):

    def test_every_question_has_a_section_and_a_reason_to_exist(self):
        for question in STANDING:
            with self.subTest(q=question.id):
                self.assertTrue(question.text)
                self.assertTrue(question.section)
                self.assertTrue(question.why,
                                "a question without a stated reason drifts")

    def test_the_dependency_order_resolves(self):
        ordered = [q.id for q in order()]
        self.assertEqual(len(STANDING), len(ordered))
        for question in STANDING:
            for need in question.needs:
                self.assertLess(ordered.index(need), ordered.index(question.id),
                                f"{question.id} runs before {need} which it needs")

    def test_the_two_sizing_questions_are_independent(self):
        """M6 — they are the same question asked twice on purpose, and either
        seeing the other would manufacture the agreement signal."""
        self.assertNotIn("Q3", BY_ID["Q2"].needs)
        self.assertNotIn("Q2", BY_ID["Q3"].needs)
        self.assertIn("top-down", BY_ID["Q3"].denied)
        self.assertIn("bottom-up", BY_ID["Q2"].denied)

    def test_derived_questions_are_denied_raw_sources(self):
        """M7 — the hand-off that killed the old pipeline was prose."""
        for qid in ("Q9", "Q10"):
            self.assertIn("raw sources", BY_ID[qid].denied)

    def test_the_gaps_question_belongs_to_neither_profession(self):
        self.assertEqual((), BY_ID["Q11"].seen_in)


class M2_UnansweredIsAState(unittest.TestCase):

    def test_a_run_with_no_data_still_produces_every_section(self):
        answers = build(MarketDefinition(**LANDSCAPING))
        for question in STANDING:
            with self.subTest(q=question.id):
                self.assertIsNotNone(answers.get(question.id),
                                     "a missing section reads as an oversight")

    def test_an_unanswered_question_carries_its_reason(self):
        answers = build(MarketDefinition(**LANDSCAPING))
        for answer in answers.unanswered():
            with self.subTest(q=answer.question_id):
                self.assertTrue(answer.unanswered_because)

    def test_a_question_whose_inputs_are_missing_names_them(self):
        answers = build(MarketDefinition(**LANDSCAPING))
        barriers_answer = answers.get("Q9")
        self.assertFalse(barriers_answer.answered)
        self.assertIn("Q5", barriers_answer.unanswered_because)

    def test_a_bad_industry_code_is_refused_at_the_boundary(self):
        answers = build(MarketDefinition(label="Too broad", naics="56"))
        definition = answers.get("Q1")
        self.assertFalse(definition.answered)
        self.assertIn("sector", definition.unanswered_because)

    def test_an_agent_that_raises_does_not_end_the_run(self):
        from marketreport import report as report_module

        original = report_module._AGENTS.get("regulation")

        def explode(**kwargs):
            raise RuntimeError("backend on fire")

        report_module._AGENTS["regulation"] = explode
        try:
            answers = build(MarketDefinition(**LANDSCAPING))
            self.assertIn("backend on fire",
                          answers.get("Q8").unanswered_because)
            self.assertIsNotNone(answers.get("Q11"))
        finally:
            if original:
                report_module._AGENTS["regulation"] = original


class M3_Closure(unittest.TestCase):
    """A reader who finishes with questions has been failed by the report."""

    def test_a_mostly_empty_report_is_not_complete(self):
        """The gate-that-cannot-fail pattern: closure once reported True over a
        report that answered two of twelve questions, because the ten it
        skipped raised nothing."""
        answers = build(MarketDefinition(**LANDSCAPING))
        closure = answers.closure()
        self.assertFalse(closure["complete"])
        self.assertGreater(len(closure["unanswered_standing"]), 0)

    def test_the_note_says_what_is_missing(self):
        answers = build(MarketDefinition(**LANDSCAPING))
        self.assertIn("unanswered", answers.closure()["note"])

    def test_a_follow_up_closes_when_its_field_is_populated(self):
        """Structural, not lexical. The version this replaces counted word
        overlap against our own prose, so a section using the right vocabulary
        passed without answering anything."""
        answers = AnswerSet("test")
        answers.record(Answer(
            "Q5", kind=COMPUTED, statement="Concentration measured.",
            detail={"concentration": {"basis": "estimated", "cr4": 0.12}}))
        closure = answers.closure()
        self.assertEqual(2, closure["closed"])
        self.assertEqual([], closure["open"])

    def test_the_right_words_no_longer_close_a_follow_up(self):
        """The exact defect: prose that mentions the concepts without carrying
        the values used to pass."""
        answers = AnswerSet("test")
        answers.record(Answer(
            "Q5", kind=COMPUTED,
            statement=("Concentration is estimated rather than measured, and "
                       "the largest four hold a modest share.")))
        self.assertEqual(2, len(answers.closure()["open"]))

    def test_a_field_that_exists_but_is_empty_does_not_close(self):
        answers = AnswerSet("test")
        answers.record(Answer("Q5", kind=COMPUTED, statement="x",
                              detail={"concentration": {"basis": "", "cr4": 0.1}}))
        open_paths = [o["needs"] for o in answers.closure()["open"]]
        self.assertIn("Q5.detail.concentration.basis", open_paths)

    def test_a_thin_answer_leaves_its_follow_ups_open(self):
        answers = AnswerSet("test")
        answers.record(Answer("Q5", kind=COMPUTED, statement="It is busy."))
        self.assertTrue(answers.closure()["open"])

    def test_every_follow_up_names_the_field_that_closes_it(self):
        """A follow-up with no path is unclosable and would sit open forever."""
        for question in STANDING:
            for follow_up, path in question.raises:
                with self.subTest(q=question.id):
                    self.assertTrue(path, f"{follow_up!r} names no field")
                    self.assertIn(".", path)

    def test_an_unanswered_section_raises_nothing(self):
        """It has not made a claim, so it cannot leave a claim dangling."""
        answers = AnswerSet("test")
        answers.record(Answer("Q5", unanswered_because="no data"))
        self.assertEqual([], answers.closure()["open"])


class M4_Concentration(unittest.TestCase):

    def test_hhi_of_a_monopoly_is_ten_thousand(self):
        self.assertAlmostEqual(10_000.0, hhi([1.0]), places=1)

    def test_hhi_of_ten_equal_firms(self):
        self.assertAlmostEqual(1_000.0, hhi([0.1] * 10), places=1)

    def test_hhi_weights_large_firms_more_than_a_count_would(self):
        even = hhi([0.1] * 10)
        lopsided = hhi([0.91] + [0.01] * 9)
        self.assertGreater(lopsided, even,
                           "squaring is the point — it separates these")

    def test_partial_share_lists_are_normalized(self):
        """We rarely know every firm, and an un-normalized HHI over a partial
        list understates concentration without saying so."""
        self.assertAlmostEqual(hhi([0.5, 0.5]), hhi([0.25, 0.25]), places=1)

    def test_the_reading_quotes_the_threshold_that_produced_it(self):
        reading, because = read_hhi(3_000.0)
        self.assertEqual("highly concentrated", reading)
        self.assertIn(str(HHI_MODERATE), because.replace(",", ""))

    def test_an_unconcentrated_market_reads_as_one(self):
        self.assertEqual("unconcentrated", read_hhi(HHI_UNCONCENTRATED - 1)[0])

    def test_cr4_is_the_largest_four(self):
        self.assertAlmostEqual(0.9, cr([0.4, 0.3, 0.1, 0.1, 0.05, 0.05], 4),
                               places=3)

    def test_size_bands_produce_an_estimate_that_says_it_is_one(self):
        conc = from_size_bands({"1-4": 5_000, "5-9": 500, "1000+": 1})
        self.assertEqual("estimated", conc.basis)
        self.assertIn("not a measured HHI", conc.caveat)
        self.assertEqual(5_501, conc.firms)

    def test_a_fragmented_trade_reads_as_fragmented(self):
        conc = from_size_bands({"1-4": 20_000, "5-9": 3_000})
        self.assertEqual("unconcentrated", conc.reading)

    def test_a_concentrated_market_reads_as_concentrated(self):
        conc = from_shares([0.6, 0.3, 0.05, 0.05])
        self.assertEqual("highly concentrated", conc.reading)
        self.assertEqual("measured", conc.basis)

    def test_no_usable_bands_yields_no_number_rather_than_zero(self):
        conc = from_size_bands({})
        self.assertIsNone(conc.hhi)
        self.assertTrue(conc.because or conc.caveat)


class M5_SaturationAndLifecycle(unittest.TestCase):

    def test_high_penetration_and_no_growth_is_saturated(self):
        self.assertEqual("saturated", saturation(0.8, 0.01).reading)

    def test_high_penetration_with_growth_is_not_saturated(self):
        """M5 — reporting penetration alone would flatter the wrong markets."""
        self.assertEqual("penetrated but expanding",
                         saturation(0.8, 0.20).reading)

    def test_low_penetration_and_growth_is_open(self):
        self.assertEqual("open and growing", saturation(0.05, 0.20).reading)

    def test_low_penetration_and_no_growth_is_the_interesting_case(self):
        result = saturation(0.05, 0.0)
        self.assertEqual("open but static", result.reading)
        self.assertIn("does not want", result.because)

    def test_one_number_alone_says_what_is_unknown(self):
        self.assertIn("unknown", saturation(0.8, None).because)
        self.assertIn("unknown", saturation(None, 0.2).because)

    def test_neither_number_yields_no_reading(self):
        self.assertEqual("", saturation(None, None).reading)

    def test_a_shrinking_market_is_declining(self):
        self.assertEqual("declining", lifecycle(-0.03, None)[0])

    def test_fast_growth_and_fragmentation_is_emerging(self):
        conc = Concentration(hhi=400.0)
        self.assertEqual("emerging", lifecycle(0.30, conc)[0])

    def test_fast_growth_with_structure_is_growth_not_emerging(self):
        conc = Concentration(hhi=3_000.0)
        self.assertEqual("growth", lifecycle(0.30, conc)[0])

    def test_slow_growth_is_mature(self):
        self.assertEqual("mature", lifecycle(0.01, None)[0])

    def test_without_growth_there_is_no_stage(self):
        stage, because = lifecycle(None, Concentration(hhi=400.0))
        self.assertEqual("", stage)
        self.assertIn("growth could not be established", because)


class M6_Barriers(unittest.TestCase):

    def test_barriers_carry_a_level_and_a_trend(self):
        """Copied from IBISWorld, which reports both. A level with a direction
        beats either alone and beats a paragraph."""
        graded = barriers(conc=Concentration(hhi=3_000.0),
                          startup_cost=2_000_000.0, licences=2)
        self.assertEqual("high", graded.level)
        self.assertIn(graded.trend, ("increasing", "steady", "decreasing"))

    def test_a_fragmented_cheap_unlicensed_market_is_low(self):
        graded = barriers(conc=Concentration(hhi=300.0), startup_cost=15_000.0)
        self.assertEqual("low", graded.level)

    def test_every_grade_lists_its_reasons(self):
        graded = barriers(conc=Concentration(hhi=3_000.0))
        self.assertTrue(graded.reasons,
                        "a grade a reader cannot argue with is not useful")

    def test_nothing_established_means_no_grade(self):
        graded = barriers()
        self.assertEqual("", graded.level)
        self.assertIn("cannot be graded", graded.because)

    def test_the_trend_says_why_it_is_steady(self):
        graded = barriers(conc=Concentration(hhi=3_000.0))
        self.assertIn("two vintages", graded.because)


class M7_Assembly(unittest.TestCase):

    def test_every_standing_question_has_a_registered_agent(self):
        for question in STANDING:
            if not question.agent:
                continue
            with self.subTest(q=question.id):
                self.assertIsNotNone(agent_for(question.agent),
                                     f"{question.agent} is not registered")

    def test_the_report_renders_without_a_single_source(self):
        body = text(build(MarketDefinition(**LANDSCAPING)))
        self.assertIn("MARKET REPORT", body)
        self.assertIn("INCOMPLETE", body)
        self.assertIn("WHAT COULD NOT BE ESTABLISHED", body)

    def test_the_completeness_statement_is_at_the_top(self):
        """A reader deciding whether to rely on this needs it before they read
        it, not after."""
        body = text(build(MarketDefinition(**LANDSCAPING)))
        self.assertLess(body.index("INCOMPLETE"),
                        body.index("WHAT THIS MARKET IS"))

    def test_every_section_shows_the_question_it_answers(self):
        body = text(build(MarketDefinition(**LANDSCAPING)))
        for question in STANDING:
            with self.subTest(q=question.id):
                self.assertIn(f"[{question.id}]", body)

    def test_the_summary_view_matches_the_question_set(self):
        view = summary(build(MarketDefinition(**LANDSCAPING)))
        self.assertEqual(len(STANDING), len(view["sections"]))
        self.assertFalse(view["closure"]["complete"])

    def test_the_answer_set_serializes(self):
        import json
        json.dumps(build(MarketDefinition(**LANDSCAPING)).to_dict(),
                   default=str)


if __name__ == "__main__":
    unittest.main()


class M8_DemoReport(unittest.TestCase):
    """The offline path exists so the assembled report can be tested at all.

    Unit tests can check HHI. Only an end-to-end run can check that the
    barriers agent reads the concentration the structure agent wrote, that the
    life-cycle stage follows from the growth figure, and that closure goes
    green when everything is answered. That path was untestable while every
    agent refused for want of a key.
    """

    def _demo(self, **over):
        args = dict(LANDSCAPING, demo=True)
        args.update(over)
        return build(MarketDefinition(**args))

    def test_the_demo_answers_almost_everything(self):
        answers = self._demo()
        self.assertGreaterEqual(answers.coverage()["answered"], 10)

    def test_the_derived_agents_actually_receive_what_they_need(self):
        """The whole point of the dependency graph, exercised end to end."""
        answers = self._demo()
        self.assertTrue(answers.get("Q9").answered, "barriers needs Q5/Q7/Q8")
        self.assertTrue(answers.get("Q10").answered, "lifecycle needs Q4/Q5")

    def test_barriers_read_the_concentration_that_structure_computed(self):
        answers = self._demo()
        reasons = " ".join(answers.get("Q9").detail.get("reasons") or [])
        self.assertIn("HHI", reasons)

    def test_the_lifecycle_stage_follows_from_the_growth_figure(self):
        answers = self._demo()
        stage = answers.get("Q10").detail["stage"]
        self.assertIn(stage, ("emerging", "growth", "mature", "declining"))
        self.assertIn("%", answers.get("Q10").detail["because"])

    def test_every_demo_figure_is_labelled_in_the_report_itself(self):
        """A demo number must never be quotable as a measurement. The label
        travels with the figure to the page, not just in the caller's head."""
        body = text(self._demo())
        self.assertIn("ILLUSTRATIVE DEMO", body)
        self.assertIn("not a measurement", body)

    def test_the_headline_is_the_geography_the_user_asked_about(self):
        """A county report that leads with the national figure has answered a
        question nobody asked, and the leading number is the quoted one."""
        answers = self._demo()
        statement = answers.get("Q3").statement
        self.assertIn("county 04013", statement)
        self.assertIn("$571.6M", statement)
        self.assertIn("national total", statement,
                      "the wider figure should still be there for context")

    def test_growth_says_which_geography_it_measured(self):
        self.assertIn("county 04013", self._demo().get("Q4").statement)

    def test_growth_says_it_counts_firms_rather_than_revenue(self):
        """These move in opposite directions when a market consolidates."""
        self.assertIn("NUMBER OF FIRMS", self._demo().get("Q4").statement)

    def test_the_sizing_rings_nest(self):
        answers = self._demo()
        sizes = [r["size"] for r in
                 answers.get("Q3").detail["sizing"]["rings"] if r["size"]]
        self.assertEqual(sizes, sorted(sizes, reverse=True))

    def test_an_industry_the_demo_does_not_cover_says_so(self):
        answers = self._demo(naics="722511", label="Restaurants")
        definition = answers.get("Q1")
        self.assertFalse(definition.answered)
        self.assertIn("561730", definition.unanswered_because)

    def test_licensing_without_a_state_is_refused_rather_than_generalized(self):
        """Licensing is per-state, so a national answer does not exist."""
        answers = self._demo(state_fips="", county_fips="")
        self.assertFalse(answers.get("Q8").answered)

    def test_the_report_still_reports_its_own_incompleteness(self):
        """The demo answers every question but leaves a follow-up open, because
        demo figures carry no sources. Saying 'INCOMPLETE — 12 of 12 answered'
        was a contradiction on its face, so the header distinguishes the two."""
        answers = self._demo()
        closure = answers.closure()
        self.assertFalse(closure["complete"])
        body = text(answers)
        self.assertNotIn("INCOMPLETE", body)
        self.assertIn("not answered in it", body)

    def test_the_two_sizings_are_compared(self):
        """The reason both were built, and it had never once run."""
        answers = self._demo()
        verdict = answers.get("Q12")
        self.assertTrue(verdict.answered)
        self.assertIn(verdict.detail["verdict"],
                      ("agree", "disagree", "incomparable"))

    def test_the_convergence_check_uses_the_shared_comparison_rule(self):
        """Merged, so a market size and a funding round cannot corroborate each
        other in the market report either."""
        size = Answer("Q3", statement="The market is $7 billion",
                      value_text="$7B", unit="USD")
        raise_ = Answer("Q2", statement="A competitor raised $7.2 billion",
                        value_text="$7.2B", unit="USD")
        self.assertEqual("incomparable", size.compare(raise_)[0])


class M9_RequestFlow(unittest.TestCase):
    """A user names a market and gets the report — CLI and app window."""

    def _serve(self):
        import os as _os
        import tempfile as _tf
        import threading
        from http.server import ThreadingHTTPServer

        _os.environ["DECKSCOPE_HOME"] = _tf.mkdtemp()
        from deckscope import webapp

        srv = ThreadingHTTPServer(("127.0.0.1", 0), webapp.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, f"http://127.0.0.1:{srv.server_address[1]}", webapp

    def _post(self, base, path, obj, token=None):
        import json as _json
        import urllib.error
        import urllib.request

        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-DeckScope-Token"] = token
        req = urllib.request.Request(base + path,
                                     data=_json.dumps(obj).encode(),
                                     method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                return res.status, _json.loads(res.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _json.loads(exc.read())

    def test_the_app_produces_a_report_from_a_named_market(self):
        srv, base, webapp = self._serve()
        try:
            code, data = self._post(
                base, "/api/market",
                {"naics": "561730", "label": "Landscaping services",
                 "state": "04", "county": "013", "demo": True},
                webapp.SESSION_TOKEN)
            self.assertEqual(200, code)
            self.assertEqual(len(STANDING), len(data["sections"]))
            self.assertGreaterEqual(data["coverage"]["answered"], 10)
        finally:
            srv.shutdown()

    def test_a_sector_level_code_is_refused_with_the_reason(self):
        srv, base, webapp = self._serve()
        try:
            code, data = self._post(base, "/api/market", {"naics": "56"},
                                    webapp.SESSION_TOKEN)
            self.assertEqual(400, code)
            self.assertIn("sector", data["error"])
        finally:
            srv.shutdown()

    def test_the_report_endpoint_requires_the_session_token(self):
        srv, base, _ = self._serve()
        try:
            code, _ = self._post(base, "/api/market", {"naics": "561730"})
            self.assertEqual(401, code)
        finally:
            srv.shutdown()

    def test_every_section_reaches_the_client_answered_or_not(self):
        """A vanished section reads as an oversight; a section that says why it
        is empty reads as a limit of the evidence."""
        srv, base, webapp = self._serve()
        try:
            _, data = self._post(
                base, "/api/market",
                {"naics": "561730", "state": "04", "demo": True},
                webapp.SESSION_TOKEN)
            for section in data["sections"]:
                with self.subTest(s=section["id"]):
                    self.assertTrue(section["answered"] or section["because"])
        finally:
            srv.shutdown()

    def test_the_cli_exit_code_distinguishes_complete_from_incomplete(self):
        import subprocess
        import sys as _sys
        from pathlib import Path as _Path

        root = _Path(__file__).resolve().parent.parent
        res = subprocess.run(
            [_sys.executable, "-m", "deckscope", "market", "561730",
             "--state", "04", "--demo", "--json"],
            capture_output=True, text=True, cwd=str(root))
        self.assertEqual(6, res.returncode,
                         "an incomplete report is a real output and not a "
                         "success; a script must be able to tell")


class M10_CritiqueFixes(unittest.TestCase):
    """The six problems the critique found, each with the check that holds."""

    def _demo(self, **over):
        args = dict(LANDSCAPING, demo=True)
        args.update(over)
        return build(MarketDefinition(**args))

    # --- 1. demo honesty
    def test_a_demo_answer_is_never_checkable(self):
        """Its source_ids name a dataset that was not queried. Counting it as
        checkable would give invented numbers a provenance badge."""
        answer = Answer("Q3", statement="x", value_text="$1B",
                        source_ids=["County Business Patterns (demo)"],
                        demo=True)
        self.assertFalse(answer.checkable)

    def test_demo_taints_everything_derived_from_it(self):
        """A barriers grade derived from demo concentration is a demo answer.
        Without this it passed through one function and came out 'live'."""
        answers = self._demo()
        for qid in ("Q9", "Q10", "Q12"):
            with self.subTest(q=qid):
                self.assertTrue(answers.get(qid).demo)
                self.assertFalse(answers.get(qid).checkable)

    def test_coverage_separates_live_from_demo(self):
        coverage = self._demo().coverage()
        self.assertGreater(coverage["answered_from_demo"], 0)
        self.assertLess(coverage["answered_live"], coverage["answered"])

    def test_the_report_warns_before_the_first_number(self):
        body = text(self._demo())
        self.assertIn("RECORDED SAMPLE DATA", body)
        self.assertLess(body.index("RECORDED SAMPLE DATA"),
                        body.index("WHAT THIS MARKET IS"))

    # --- 2. one spine
    def test_an_answer_carries_a_metric_identity(self):
        answer = Answer("Q3", statement="The market is $7 billion",
                        value_text="$7B", unit="USD")
        self.assertIsNotNone(answer.metric)
        self.assertEqual("market-size", answer.metric.measure)

    def test_an_answer_parses_its_own_magnitude(self):
        """Without this the shared rule said 'neither carries a figure to
        compare' for two answers that plainly did."""
        self.assertEqual(7e9, Answer("Q3", value_text="$7B").value)

    def test_the_market_report_cannot_confirm_a_size_with_a_funding_round(self):
        """The audit's finding, now covering both halves of the repository."""
        size = Answer("Q3", statement="The market is $7 billion",
                      value_text="$7B", unit="USD")
        raised = Answer("Q2", statement="A competitor raised $7.2 billion",
                        value_text="$7.2B", unit="USD")
        verdict, why = size.compare(raised)
        self.assertEqual("incomparable", verdict)
        self.assertIn("funding", why)

    # --- 3. convergence
    def test_the_two_sizings_are_actually_compared(self):
        answers = self._demo()
        self.assertTrue(answers.get("Q12").answered)
        self.assertIn(answers.get("Q12").detail["verdict"],
                      ("agree", "disagree", "incomparable"))

    def test_top_down_never_sees_bottom_up(self):
        self.assertEqual(("Q1",), BY_ID["Q2"].needs)
        self.assertEqual(("Q1",), BY_ID["Q3"].needs)

    def test_disagreement_is_reported_as_a_finding_not_an_error(self):
        from marketreport.report import _AGENTS

        top = Answer("Q2", statement="The market is $10 billion",
                     value_text="$10B", unit="USD")
        bottom = Answer("Q3", statement="The market is $2 billion",
                        value_text="$2B", unit="USD")
        result = _AGENTS["convergence"](
            market=MarketDefinition(**LANDSCAPING), question=BY_ID["Q12"],
            seen={"Q2": top, "Q3": bottom})
        self.assertEqual("disagree", result.detail["verdict"])
        self.assertIn("not an error to reconcile", result.statement)

    # --- 5. fragmented-market measures
    def test_shape_tells_sole_traders_from_large_firms(self):
        """HHI gives both an identical number and an identical reading."""
        from marketreport.structure import from_size_bands, shape

        sole = {"1-4": 1422}
        large = {"1000+": 1422}
        self.assertEqual(from_size_bands(sole).hhi, from_size_bands(large).hhi)
        self.assertNotEqual(shape(sole).reading, shape(large).reading)

    def test_shape_reports_average_size_and_top_decile(self):
        from marketreport.structure import shape

        form = shape({"1-4": 760, "5-9": 285, "10-19": 195, "20-49": 124,
                      "50-99": 38, "100-249": 16, "250-499": 3, "500-999": 1})
        self.assertAlmostEqual(13.0, form.average_size, delta=1.0)
        self.assertGreater(form.top_decile_share, 0.4)

    def test_the_structure_section_carries_the_shape(self):
        detail = self._demo().get("Q5").detail
        self.assertIn("shape", detail)
        self.assertIsNotNone(detail["shape"]["average_size"])
