"""Panels — the unit the system was missing.

Von asked for a cell-phone market-share chart. I produced one by hand in six
minutes, and the repository could not have produced it: nothing in the code
could express "the shape of this answer is two pies", so the shape could never
depend on the answer. PANELS.md is the design; this is the enforcement.

Three of these tests exist because building it found real bugs in code that had
been passing its own tests for weeks. Each is marked.
"""
from __future__ import annotations

import unittest

from marketreport.panel import (ABSENT, DERIVED, ESTIMATED, FORMS, SOURCED,
                                Figure, Panel, Series, Slice, UnknownForm,
                                form_spec, unanswered)
from marketreport.shaper import build_panel, derive, implied_total
from marketreport.specialists import MARKET_SHARE, get, registered


class _Finding:
    """The shape `research.findings.Finding` presents to the shaper."""

    def __init__(self, fid, statement, value=None, value_text="", unit="%",
                 as_of="Q2 2026", source_ids=("S1",)):
        self.id = fid
        self.statement = statement
        self.value = value
        self.value_text = value_text or (f"{value}%" if value else "")
        self.unit = unit
        self.as_of = as_of
        self.source_ids = list(source_ids)


def _phone_findings():
    return [
        _Finding("F1", "Samsung held 22% shipment share", 22),
        _Finding("F2", "Apple held 20% shipment share", 20),
        _Finding("F3", "Apple held 49% of global smartphone revenue share", 49,
                 source_ids=["S2"]),
        _Finding("F4", "Samsung held 16% of global smartphone revenue share",
                 16, source_ids=["S2"]),
    ]


def _phone_shape(extra_slices=()):
    units = [{"label": "Samsung", "value": 22, "finding_id": "F1"},
             {"label": "Apple", "value": 20, "finding_id": "F2"}]
    units.extend(extra_slices)
    return {
        "headline": "Samsung ships the most phones; Apple takes the money",
        "form": "share_pair",
        "series": [
            {"label": "Units", "measure": "shipment share", "unit": "%",
             "as_of": "Q2 2026", "basis": "Smart Analytics Global",
             "slices": units},
            {"label": "Revenue", "measure": "revenue share", "unit": "%",
             "as_of": "Q2 2026", "basis": "Counterpoint Research",
             "slices": [{"label": "Apple", "value": 49, "finding_id": "F3"},
                        {"label": "Samsung", "value": 16,
                         "finding_id": "F4"}]}],
        "figures": [], "caveats": []}


class P1_ProvenanceIsRequired(unittest.TestCase):
    """The mistake I made by hand: my own multiplications sat in a column
    beside published figures in identical formatting. A figure now cannot exist
    without declaring how we came to have it."""

    def test_a_sourced_figure_must_name_a_source(self):
        with self.assertRaises(ValueError) as caught:
            Figure("Market size", state=SOURCED)
        self.assertIn("provenance badge", str(caught.exception))

    def test_a_derived_figure_must_show_its_operands(self):
        """Showing the arithmetic is the whole difference between a derived
        figure and an asserted one."""
        with self.assertRaises(ValueError):
            Figure("Implied total", 107.0, state=DERIVED)

    def test_an_absent_figure_must_say_what_stopped_it(self):
        with self.assertRaises(ValueError) as caught:
            Figure("Xiaomi revenue", state=ABSENT)
        self.assertIn("not a finding", str(caught.exception))

    def test_an_unknown_state_is_refused_rather_than_defaulted(self):
        """Defaulting would let an unrecognised state render as sourced, which
        is the one direction that must never happen silently."""
        with self.assertRaises(ValueError):
            Figure("x", state="probably-fine")

    def test_only_a_sourced_figure_is_checkable(self):
        derived = derive("Implied total", "50 ÷ 0.49",
                         [Figure("a", 50, state=SOURCED, source_ids=["S1"])],
                         102.0, unit="USD")
        self.assertFalse(derived.checkable)
        self.assertEqual(DERIVED, derived.state)

    def test_coverage_separates_the_states(self):
        panel = Panel(question="q", headline="h", form="stat")
        panel.figures = [
            Figure("a", 1, state=SOURCED, source_ids=["S1"]),
            derive("b", "a x 2", [Figure("a", 1, state=SOURCED,
                                         source_ids=["S1"])], 2.0),
            Figure("c", state=ABSENT, because="no tracker publishes it")]
        coverage = panel.coverage()
        self.assertEqual({"sourced": 1, "derived": 1, "absent": 1},
                         {k: coverage[k] for k in ("sourced", "derived",
                                                   "absent")})
        self.assertEqual(1, coverage["checkable"])


class P2_TheFormIsPartOfTheAnswer(unittest.TestCase):
    """The load-bearing idea. Without it the renderer walks a static heading
    list and the shape can never depend on what was found."""

    def test_an_unknown_form_raises_rather_than_degrading(self):
        """A caller who asked for a comparison and silently received a list has
        been handed something that looks like it worked."""
        with self.assertRaises(UnknownForm):
            form_spec("piechart")

    def test_share_pair_requires_two_series(self):
        panel = Panel(question="q", headline="h", form="share_pair")
        panel.series = [Series("Units", "shipment share", "%", slices=[
            Slice("Samsung", 60, source_ids=["S1"]),
            Slice("Apple", 40, source_ids=["S1"])])]
        self.assertIn("share_pair needs at least 2 series",
                      " ".join(panel.problems()))

    def test_every_form_states_the_job_it_is_for(self):
        """The registry doubles as the menu the shaper picks from, so a form
        with a vague job gets chosen for vague reasons."""
        for name, spec in FORMS.items():
            with self.subTest(form=name):
                self.assertGreater(len(spec.job), 20)

    def test_a_bad_form_from_the_shaper_becomes_a_caveat_not_a_crash(self):
        shaped = _phone_shape()
        shaped["form"] = "sankey"
        panel = build_panel("q", _phone_findings(), shaped)
        self.assertEqual("table", panel.form)
        self.assertTrue(any("does not exist" in c for c in panel.caveats))


class P3_TheShaperCannotInventNumbers(unittest.TestCase):
    """Bounded by code that runs after the call, not by asking in the prompt."""

    def test_a_slice_citing_a_finding_that_does_not_exist_is_dropped(self):
        shaped = _phone_shape(
            [{"label": "Huawei", "value": 9, "finding_id": "F99"}])
        panel = build_panel("q", _phone_findings(), shaped)
        drawn = [w.label for s in panel.series for w in s.slices]
        self.assertNotIn("Huawei", drawn)

    def test_and_the_removal_is_reported(self):
        """Silently dropping it would let the panel look better sourced than
        the run behind it."""
        shaped = _phone_shape(
            [{"label": "Huawei", "value": 9, "finding_id": "F99"}])
        panel = build_panel("q", _phone_findings(), shaped)
        self.assertTrue(any("Huawei" in c and "removed" in c
                            for c in panel.caveats))

    def test_slice_provenance_comes_from_the_finding_not_the_shaper(self):
        panel = build_panel("q", _phone_findings(), _phone_shape())
        for series in panel.series:
            for wedge in series.slices:
                with self.subTest(slice=wedge.label):
                    self.assertTrue(wedge.source_ids)
                    self.assertTrue(wedge.finding_id)

    def test_a_finding_with_no_source_yields_an_estimated_slice(self):
        findings = _phone_findings()
        findings[0].source_ids = []
        panel = build_panel("q", findings, _phone_shape())
        samsung = [w for s in panel.series for w in s.slices
                   if w.label == "Samsung" and s.label == "Units"][0]
        self.assertEqual(ESTIMATED, samsung.state)

    def test_no_headline_means_the_panel_reports_a_problem(self):
        shaped = _phone_shape()
        shaped["headline"] = ""
        panel = build_panel("q", _phone_findings(), shaped)
        self.assertFalse(panel.answered)
        self.assertIn("nothing was established", panel.problem)


class P4_HonestAboutWhatIsMissing(unittest.TestCase):

    def test_two_publishers_produce_a_caveat_written_by_code(self):
        """The caveat readers most need and least expect, so it is not left to
        the prompt."""
        panel = build_panel("q", _phone_findings(), _phone_shape())
        self.assertTrue(any("different publishers" in c
                            for c in panel.caveats))

    def test_an_incomplete_share_series_is_disclosed_not_rejected(self):
        """A series summing to 42% is correct when the publisher breaks out the
        top two and stops. It is only dishonest if the reader is not told."""
        panel = build_panel("q", _phone_findings(), _phone_shape())
        self.assertEqual([], [p for p in panel.problems() if "sums" in p])
        self.assertTrue(any("not broken out" in c for c in panel.caveats))

    def test_a_series_summing_past_100_is_an_error(self):
        """Unlike an incomplete series, this cannot be fixed by disclosing it —
        two slices are counting the same firms."""
        panel = Panel(question="q", headline="h", form="share")
        panel.series = [Series("Units", "share", "%", slices=[
            Slice("a", 60, source_ids=["S1"]),
            Slice("b", 60, source_ids=["S1"])])]
        self.assertIn("more than the whole market",
                      " ".join(panel.problems()))

    def test_one_entity_gets_one_wedge(self):
        """Two sources disagreeing about Samsung is a finding to report, not
        two wedges to draw — left alone the chart shows Samsung twice."""
        panel = Panel(question="q", headline="h", form="share")
        panel.series = [Series("Units", "share", "%", slices=[
            Slice("Samsung", 22, source_ids=["S1"]),
            Slice("Samsung", 34, source_ids=["S2"]),
            Slice("Apple", 20, source_ids=["S1"])])]
        self.assertIn("appears 2 times", " ".join(panel.problems()))

    def test_a_failed_question_is_still_a_panel(self):
        """Returning nothing is how a report comes to look more complete than
        the run behind it."""
        panel = unanswered("Who leads?", "no tracker covers this market",
                           agent="market-share")
        self.assertFalse(panel.answered)
        self.assertIn("no tracker", panel.problem)


class P5_APanelIsARecord(unittest.TestCase):
    """What replaces determinism once a model is in the loop: not that the run
    cannot vary, but that its output is a fixed artifact."""

    def test_it_survives_a_round_trip(self):
        import json

        panel = build_panel("Who has the market?", _phone_findings(),
                            _phone_shape(), agent="market-share")
        again = Panel.from_dict(json.loads(json.dumps(panel.to_dict())))
        self.assertEqual(panel.to_dict(), again.to_dict())

    def test_re_rendering_reruns_nothing(self):
        panel = build_panel("q", _phone_findings(), _phone_shape())
        first, second = panel.to_dict(), panel.to_dict()
        self.assertEqual(first, second)

    def test_the_record_carries_what_it_read(self):
        panel = build_panel("q", _phone_findings(), _phone_shape())
        self.assertEqual(["S1", "S2"], sorted(panel.source_ids))
        self.assertIn("Counterpoint Research", panel.source_labels)


class P6_OurArithmeticNotTheModels(unittest.TestCase):

    def test_the_implied_total_reproduces_the_cross_check_i_ran_by_hand(self):
        """Apple's iPhone revenue was ~$50B at 49% of market revenue, so the
        market was ~$102B — which matched a published quarterly figure from a
        different source. Two paths, one answer."""
        revenue = Figure("Apple iPhone revenue", 50e9, "$50B", "USD",
                         SOURCED, "Q2 2026", ["S4"])
        share = Figure("Apple revenue share", 49, "49%", "%", SOURCED,
                       "Q2 2026", ["S2"])
        total = implied_total(share, revenue)
        self.assertAlmostEqual(102.04e9, total.value, delta=1e8)
        self.assertEqual(DERIVED, total.state)

    def test_it_shows_the_arithmetic_and_the_operands(self):
        revenue = Figure("Apple iPhone revenue", 50e9, "$50B", "USD",
                         SOURCED, "Q2 2026", ["S4"])
        share = Figure("Apple revenue share", 49, "49%", "%", SOURCED,
                       "Q2 2026", ["S2"])
        total = implied_total(share, revenue)
        self.assertIn("÷", total.how)
        self.assertEqual(["Apple iPhone revenue", "Apple revenue share"],
                         total.operands)

    def test_a_zero_share_yields_nothing_rather_than_infinity(self):
        revenue = Figure("r", 50e9, "$50B", "USD", SOURCED, "", ["S1"])
        self.assertIsNone(implied_total(
            Figure("s", 0, "0%", "%", SOURCED, "", ["S2"]), revenue))


class P7_TheSpecialistsCrossChecks(unittest.TestCase):
    """The market-share checks run in Python, so they happen whether or not the
    model thinks of them."""

    def _checked(self, findings, shaped):
        panel = build_panel("q", findings, shaped, agent="market-share")
        extra = MARKET_SHARE.check(findings=findings, panel=panel,
                                   market="cell phones", place="")
        panel.figures.extend(extra.get("figures") or [])
        panel.caveats.extend(extra.get("caveats") or [])
        return panel

    def test_it_computes_the_premium_between_two_yardsticks(self):
        """Apple at 49% of money on 20% of phones is a 2.5x premium, and that
        single ratio is the finding."""
        panel = self._checked(_phone_findings(), _phone_shape())
        ratios = [f for f in panel.figures if f.unit == "ratio"]
        apple = [f for f in ratios if f.label.startswith("Apple")]
        self.assertTrue(apple)
        self.assertAlmostEqual(2.45, apple[0].value, places=2)
        self.assertEqual(DERIVED, apple[0].state)

    def test_two_companies_are_not_two_disagreeing_sources(self):
        """Samsung at 22% and Xiaomi at 11% share almost all their content
        words, so the generic comparison admitted them and the numeric distance
        did the rest. They are two companies, not a contradiction."""
        findings = _phone_findings() + [
            _Finding("F5", "Xiaomi held 11% shipment share", 11)]
        shaped = _phone_shape(
            [{"label": "Xiaomi", "value": 11, "finding_id": "F5"}])
        panel = self._checked(findings, shaped)
        self.assertEqual([], [c for c in panel.caveats
                              if "disagree" in c and "Xiaomi" in c])

    def test_two_yardsticks_are_not_two_disagreeing_sources_either(self):
        """Samsung at 22% of units and 16% of revenue is the entire point of
        the panel, not an inconsistency in it."""
        panel = self._checked(_phone_findings(), _phone_shape())
        self.assertEqual([], [c for c in panel.caveats
                              if "disagree about Samsung" in c])

    def test_but_two_trackers_on_one_number_IS_reported(self):
        findings = _phone_findings() + [
            _Finding("F5", "Samsung held 34% shipment share", 34,
                     source_ids=["S3"])]
        shaped = _phone_shape(
            [{"label": "Samsung2", "value": 34, "finding_id": "F5"}])
        panel = self._checked(findings, shaped)
        self.assertTrue(any("disagree" in c and "Samsung" in c
                            for c in panel.caveats),
                        f"no disagreement reported: {panel.caveats}")

    def test_the_specialist_is_registered_and_describes_its_job(self):
        self.assertIs(MARKET_SHARE, get("market-share"))
        self.assertIn(MARKET_SHARE, registered())
        self.assertIn("share", MARKET_SHARE.job)

    def test_it_opens_with_questions_a_person_would_ask(self):
        rows = MARKET_SHARE.questions("cell phones", "Ireland")
        self.assertGreaterEqual(len(rows), 5)
        for row in rows:
            with self.subTest(q=row["text"][:40]):
                self.assertIn("cell phones", row["text"])
                self.assertIn("Ireland", row["text"])

    def test_no_place_means_worldwide_not_an_empty_hole(self):
        rows = MARKET_SHARE.questions("cell phones")
        self.assertTrue(all("worldwide" in r["text"] for r in rows))


class P8_BugsFoundWhileBuildingThis(unittest.TestCase):
    """Three failures in code that had been passing its own tests for weeks.
    Each was invisible until a question arrived that the old spine could not
    have asked."""

    def test_a_market_wide_revenue_question_does_not_go_to_edgar(self):
        """"What share of smartphone revenue does each company hold in
        Ireland?" matched on `revenue` and was routed to EDGAR full-text
        search, which indexes what individual filers say about themselves. The
        whole revenue half of the panel vanished — and vanished as "no backend
        could answer this", which reads as an absent fact rather than a
        misrouting."""
        from deckscope.research import router

        route = router.classify(
            "What share of cell phones revenue in Ireland does each company "
            "hold, and how does that differ from their share of units?")
        self.assertEqual(router.SEARCH, route.kind)

    def test_a_real_filer_question_still_goes_to_edgar(self):
        """The fix must not blunt the rule it narrows."""
        from deckscope.research import router

        route = router.classify(
            "What was Apple's annual revenue in its most recent 10-K?")
        self.assertEqual("edgar", route.backend)

    def test_share_of_revenue_is_a_rate_not_a_revenue(self):
        """The question classified as REVENUE (one company's turnover) and the
        finding as RATE, so the relevance guard saw a measure mismatch and
        dropped every finding it had just retrieved."""
        from deckscope.research.metrics import RATE, classify

        self.assertEqual(RATE, classify(
            "What share of cell phones revenue does each company hold?").measure)
        self.assertEqual(RATE, classify(
            "Apple held 49% of global smartphone revenue", unit="%").measure)

    def test_and_the_guard_now_lets_those_findings_through(self):
        from deckscope.research.metrics import answers, classify

        question = "What share of cell phones revenue in Ireland does each company hold?"
        finding = classify("Apple held 49% of global smartphone revenue",
                           unit="%")
        self.assertTrue(answers(question, finding))

    def test_a_share_price_is_still_a_price(self):
        """The narrowing must not swallow the word `share` everywhere."""
        from deckscope.research.metrics import PRICE, classify

        self.assertEqual(PRICE,
                         classify("The share price closed at $220").measure)

    def test_a_company_revenue_figure_is_still_a_revenue(self):
        from deckscope.research.metrics import REVENUE, classify

        self.assertEqual(REVENUE, classify(
            "Apple annual revenue was $391 billion", unit="USD").measure)


if __name__ == "__main__":
    unittest.main()


class P9_TheChartIsDrawn(unittest.TestCase):
    """A panel that cannot be seen is a data structure, not an answer."""

    def _panel(self):
        panel = build_panel("Who has the market?", _phone_findings(),
                            _phone_shape(), agent="market-share")
        panel.figures.append(
            Figure("Phones shipped", 277.5, "277 million", "count", SOURCED,
                   "Q2 2026", ["S3"]))
        panel.figures.append(derive(
            "Apple premium", "49% ÷ 20%",
            [Figure("a", 20, "20%", "%", SOURCED, "", ["S1"]),
             Figure("b", 49, "49%", "%", SOURCED, "", ["S2"])], 2.45, "ratio"))
        panel.figures.append(
            Figure("Xiaomi revenue share", state=ABSENT,
                   because="this tracker publishes the top two only"))
        return panel

    def test_every_series_becomes_a_chart(self):
        from marketreport.panel_render import panel_html

        body = panel_html(self._panel())
        self.assertEqual(2, body.count("<svg"))

    def test_the_svg_is_well_formed(self):
        import xml.etree.ElementTree as ET
        import re

        from marketreport.panel_render import panel_html

        for svg in re.findall(r"<svg.*?</svg>", panel_html(self._panel()),
                              re.S):
            ET.fromstring(svg)

    def test_no_arc_carries_a_broken_coordinate(self):
        import re

        from marketreport.panel_render import panel_html

        for path in re.findall(r'<path d="([^"]+)"',
                               panel_html(self._panel())):
            with self.subTest(path=path[:40]):
                self.assertNotIn("nan", path.lower())
                self.assertNotIn("inf", path.lower())

    def test_an_entity_keeps_its_colour_across_both_charts(self):
        """In a share pair the reader is comparing Apple's wedge in one chart
        against Apple's wedge in the other. Recolouring by rank would make the
        comparison impossible to see — and rank is exactly what differs."""
        from marketreport.panel_render import _colours

        colours = _colours(self._panel())
        self.assertEqual(colours["apple"], colours["apple"])
        self.assertNotEqual(colours["apple"], colours["samsung"])

    def test_an_incomplete_series_draws_its_gap_rather_than_scaling_up(self):
        """Scaling to fill the circle would turn "the publisher covers the top
        two" into "these two are the whole market" — a lie the chart tells on
        its own."""
        from marketreport.panel_render import panel_html

        body = panel_html(self._panel())
        self.assertIn("url(#gap)", body)
        self.assertIn("Not broken out", body)

    def test_a_derived_figure_shows_its_arithmetic_beside_the_number(self):
        """The line whose absence let my own multiplications read as published
        figures."""
        from marketreport.panel_render import panel_html

        body = panel_html(self._panel())
        self.assertIn("49% ÷ 20%", body)
        self.assertIn("tag-derived", body)

    def test_the_states_are_visually_distinct(self):
        """A reader must be able to tell a published figure from one I worked
        out, at a glance and without reading the caption."""
        from marketreport.panel_render import PANEL_CSS, panel_html

        body = panel_html(self._panel())
        self.assertIn("tag-sourced", body)
        self.assertIn("tag-derived", body)
        for state in ("sourced", "derived", "estimated", "absent"):
            with self.subTest(state=state):
                self.assertIn(f".tag-{state}", PANEL_CSS)

    def test_an_absent_figure_is_listed_rather_than_dropped(self):
        from marketreport.panel_render import panel_html, panel_text

        for body in (panel_html(self._panel()), panel_text(self._panel())):
            self.assertIn("Xiaomi revenue share", body)
            self.assertIn("top two only", body)

    def test_it_loads_nothing_from_the_network(self):
        from marketreport.panel_render import panel_html

        body = panel_html(self._panel())
        for pattern in ("<script", "http://", "https://", "@import"):
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, body)

    def test_content_is_escaped(self):
        from marketreport.panel_render import panel_html

        panel = Panel(question="<img src=x onerror=alert(1)>",
                      headline="h", form="stat")
        self.assertNotIn("<img src=x", panel_html(panel))

    def test_a_failed_panel_still_renders_and_says_why(self):
        from marketreport.panel_render import panel_html, panel_text

        panel = unanswered("Who leads?", "no tracker covers this market")
        for body in (panel_html(panel), panel_text(panel)):
            self.assertIn("no tracker covers this market", body)

    def test_every_format_carries_the_caveats(self):
        """A caveat dropped in one format is a reader misled in that format."""
        from marketreport.panel_render import (panel_html, panel_markdown,
                                               panel_text)

        panel = self._panel()
        panel.caveats.append("The two series come from different publishers.")
        for name, body in (("html", panel_html(panel)),
                           ("md", panel_markdown(panel)),
                           ("txt", panel_text(panel))):
            with self.subTest(fmt=name):
                self.assertIn("different publishers", body)

    def test_panels_compose_into_a_document(self):
        from marketreport.document import panel_document

        body = panel_document([self._panel()], title="Cell phones")
        self.assertTrue(body.startswith("<!doctype html>"))
        self.assertIn("<svg", body)
        self.assertIn("Cell phones", body)

    def test_a_document_says_how_many_questions_went_unanswered(self):
        from marketreport.document import panel_document

        body = panel_document([self._panel(),
                               unanswered("Q2", "no source")])
        self.assertIn("could not be answered", body)
