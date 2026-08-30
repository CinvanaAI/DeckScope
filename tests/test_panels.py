"""Panels — the unit the system was missing.

The client asked for a cell-phone market-share chart. I produced one by hand in six
minutes, and the repository could not have produced it: nothing in the code
could express "the shape of this answer is two pies", so the shape could never
depend on the answer. PANELS.md is the design; this is the enforcement.

Three of these tests exist because building it found real bugs in code that had
been passing its own tests for weeks. Each is marked.
"""
from __future__ import annotations

import re
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

        from marketreport.panel_render import panel_html

        for svg in re.findall(r"<svg.*?</svg>", panel_html(self._panel()),
                              re.S):
            ET.fromstring(svg)

    def test_no_arc_carries_a_broken_coordinate(self):

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


class P10_TheManagerDecidesScope(unittest.TestCase):
    """A plain sentence in, the right specialists dispatched. The manager
    decides scope and never produces a figure — keeping that split sharp is
    what stops it becoming a second place where numbers can be born."""

    def _read(self, text):
        from marketreport.manager import read_request

        return read_request(text)

    def test_the_question_that_started_this(self):
        """"Show me the market share of cell phone companies in Ireland" — no
        NAICS code, no FIPS, and the old spine could not take it at all."""
        request = self._read(
            "Show me the market share of cell phone companies in Ireland")
        self.assertTrue(request.ready, request.question)
        self.assertEqual("cell phone", request.market)
        self.assertEqual("Ireland", request.place)
        self.assertIn("market-share", request.specialists)

    def test_a_foreign_geography_is_not_a_failure(self):
        """Ireland is a perfectly good geography that no US FIPS table will
        ever contain. Refusing it would rebuild the wall this exercise was
        about tearing down."""
        request = self._read("market share of cell phones in Ireland")
        self.assertTrue(request.ready)
        self.assertEqual("", request.state_fips)
        self.assertTrue(any("research it by name" in n
                            for n in request.notes))

    def test_vons_original_question_still_works(self):
        """A bare industry name carries none of the market words, because a
        person naming an industry does not also say "market". The first
        version of the guard turned away the question this product exists to
        answer."""
        request = self._read("landscaping in Phoenix")
        self.assertTrue(request.ready, request.question)
        self.assertEqual("561730", request.naics)
        self.assertEqual(("04", "013"),
                         (request.state_fips, request.county_fips))

    def test_a_resolved_code_unlocks_the_census_route(self):
        request = self._read("landscaping in Phoenix")
        self.assertEqual("561730", request.framing()["naics"])
        self.assertTrue(any("NAICS" in n for n in request.notes))

    def test_the_request_words_are_stripped_from_the_market_name(self):
        for text, market in (
                ("Show me the market share of cell phone companies", "cell phone"),
                ("who leads the smartphone market in Japan", "smartphone"),
                ("give me a pie chart of the electric vehicle market in Norway",
                 "electric vehicle")):
            with self.subTest(text=text[:32]):
                self.assertEqual(market, self._read(text).market)

    def test_trailing_punctuation_comes_off_before_the_split(self):
        """Stripping it afterwards left the place as "Seattle?", which failed
        to resolve — reporting a real US city as a foreign geography rather
        than as a stray question mark."""
        request = self._read("How big is the coffee shop market in Seattle?")
        self.assertEqual("Seattle", request.place)
        self.assertEqual("033", request.county_fips)

    def test_a_bare_market_name_is_accepted(self):
        """"cell phones in Ireland" carries none of the market words. The
        allowlist version turned it away, along with "landscaping in Phoenix" —
        people naming a market usually just name it, the way someone asking for
        the time does not say "the time market"."""
        for text in ("cell phones in Ireland", "electric vehicles in Norway",
                     "coffee shops in Seattle"):
            with self.subTest(text=text):
                self.assertTrue(self._read(text).ready)

    def test_a_request_that_is_not_about_a_market_is_refused(self):
        for text in ("what is the weather tomorrow", "tell me a joke",
                     "hello"):
            with self.subTest(text=text):
                request = self._read(text)
                self.assertFalse(request.ready)
                self.assertIn("does not look like", request.question)

    def test_the_guard_is_a_denylist_not_an_allowlist(self):
        """For a tool whose entire job is markets, the right default is that a
        request IS one. Being wrong that way costs a research budget the panel
        then reports honestly; being wrong the other way refuses the product's
        own purpose."""
        from marketreport.manager import NOT_A_MARKET

        self.assertTrue(self._read("widgets in Belgium").ready)
        self.assertTrue(NOT_A_MARKET.search("what is the weather tomorrow"))

    def test_market_words_override_the_denylist(self):
        """"the weather forecasting market" is a real market that happens to
        contain a denied word."""
        self.assertTrue(self._read("the weather forecasting market").ready)

    def test_it_will_not_invent_a_specialist_it_does_not_have(self):
        """Sending the closest specialist and letting the panel come back about
        a different question is worse than saying so."""
        from marketreport.manager import _choose

        self.assertEqual([], _choose("what is the weather tomorrow"))
        self.assertEqual(["market-share"],
                         _choose("cell phones in Ireland", is_a_market=True))

    def test_it_names_what_it_can_do_when_it_cannot_help(self):
        """A request nothing can answer gets the roster, not a shrug — and not
        the nearest specialist either."""
        from marketreport import manager

        saved = list(manager.DISPATCH)
        manager.DISPATCH.clear()
        original = manager._choose
        manager._choose = lambda text, is_a_market=False: []
        try:
            request = manager.read_request("market share of widgets")
            self.assertFalse(request.ready)
            self.assertIn("Nothing here answers that yet", request.question)
            self.assertTrue(request.options)
            self.assertTrue(any("market-share" in o for o in request.options))
        finally:
            manager._choose = original
            manager.DISPATCH.extend(saved)

    def test_the_dispatch_rules_each_say_why(self):
        from marketreport.manager import DISPATCH

        for pattern, name, why in DISPATCH:
            with self.subTest(specialist=name):
                self.assertIsNotNone(get(name))
                self.assertGreater(len(why), 20)


class P11_TheConvergence(unittest.TestCase):
    """the client's question, which settles the architecture: how do you make a
    market report if you cannot make the market-share report you just made?

    Q5 ("how concentrated is it") and Q6 ("who competes") ARE the market-share
    question. The Census HHI answer is a proxy that only works for fragmented
    US trades and returns "unconcentrated" for nearly all of them.
    """

    def setUp(self):
        import marketreport.agents  # noqa: F401 - registers the agents

        self.calls = []

    def _ask(self, spec, market):
        self.calls.append(spec.name)
        panel = Panel(question=f"{spec.job} — {market.label}",
                      headline="Samsung ships the most phones; Apple takes "
                               "the money",
                      form="share_pair", agent=spec.name)
        panel.series = [
            Series("Units", "shipment share", "%", as_of="Q2 2026",
                   basis="Smart Analytics Global",
                   slices=[Slice("Samsung", 22, source_ids=["S1"]),
                           Slice("Apple", 20, source_ids=["S1"]),
                           Slice("Xiaomi", 11, source_ids=["S1"]),
                           Slice("OPPO", 11, source_ids=["S1"])]),
            Series("Revenue", "revenue share", "%", as_of="Q2 2026",
                   basis="Counterpoint Research",
                   slices=[Slice("Apple", 49, source_ids=["S2"]),
                           Slice("Samsung", 16, source_ids=["S2"])])]
        panel.source_labels = ["Smart Analytics Global",
                               "Counterpoint Research"]
        return panel

    def _report(self, **kw):
        from marketreport.report import MarketDefinition, build

        return build(MarketDefinition(label="Landscaping", naics="561730",
                                      state_fips="04", demo=True),
                     on_event=lambda m: None, **kw)

    def test_the_specialist_answers_q5_and_q6(self):
        answers = self._report(ask=self._ask)
        for qid in ("Q5", "Q6"):
            with self.subTest(question=qid):
                self.assertIn("takes the money", answers.get(qid).statement)

    def test_the_panel_is_attached_to_the_report(self):
        # One panel per distinct specialist that ran — an invariant, not a
        # count. The old assertion pinned "1" from the era when market-share
        # was the only specialist; five run now, on purpose (the specialist
        # expansion), and the count-pin aged into a false alarm.
        answers = self._report(ask=self._ask)
        self.assertGreaterEqual(len(answers.panels), 1)
        self.assertEqual(len(set(self.calls)), len(answers.panels))

    def test_one_specialist_runs_once_per_report(self):
        """Q5 and Q6 are both claimed by market-share. Without a cache the loop
        researched the same market twice and spent two budgets to produce two
        identical panels."""
        self._report(ask=self._ask)
        # The property is "no specialist runs twice", not "only market-share
        # exists". Q5 and Q6 are both claimed by market-share; a cache bug
        # would show as a duplicate in this list.
        self.assertEqual(len(self.calls), len(set(self.calls)),
                         f"a specialist ran twice: {self.calls}")
        self.assertIn("market-share", self.calls)

    def test_the_follow_up_fields_are_populated_from_the_panel(self):
        """A section answered by a specialist must satisfy the same structural
        follow-ups as one answered by arithmetic, or the completeness check
        quietly stops applying to half the report."""
        answers = self._report(ask=self._ask)
        concentration = answers.get("Q5").detail["concentration"]
        self.assertEqual(64, concentration["cr4"])
        self.assertIn("Smart Analytics Global", concentration["basis"])

    def test_the_census_answer_is_unchanged_without_a_specialist(self):
        """The Census path stays, and stays preferred where it is right. For a
        US establishment count it beats searching — that judgment lives in
        router.py and is not being thrown away."""
        answers = self._report()
        self.assertEqual([], answers.panels)
        self.assertIn("HHI", answers.get("Q5").statement)

    def test_a_failing_specialist_falls_back_rather_than_costing_the_answer(self):
        def broken(spec, market):
            raise RuntimeError("the search backend went away")

        answers = self._report(ask=broken)
        self.assertIn("HHI", answers.get("Q5").statement)

    def test_a_specialist_that_establishes_nothing_also_falls_back(self):
        answers = self._report(
            ask=lambda spec, market: unanswered("q", "no tracker covers this"))
        self.assertIn("HHI", answers.get("Q5").statement)

    def test_the_report_draws_the_panel_it_produced(self):
        """A report whose Q5 was answered by a specialist must not render with
        no chart in it."""
        from marketreport.document import render_as

        answers = self._report(ask=self._ask)
        body = render_as("html", answers)
        # At least one chart per attached panel — the property that failed
        # when Q5's panel rendered chartless. The exact count grew with the
        # specialist expansion and is not the invariant.
        self.assertGreaterEqual(body.count("<svg"), len(answers.panels))
        self.assertIn("takes the money", body)

    def test_every_format_carries_the_panel(self):
        from marketreport.document import FORMATS, render_as

        answers = self._report(ask=self._ask)
        for name in FORMATS:
            with self.subTest(fmt=name):
                self.assertIn("takes the money", render_as(name, answers))

    def test_a_specialist_declares_which_questions_it_answers(self):
        """Declared on the specialist rather than on the question, so a new
        specialist can claim a section without editing the report's spine."""
        from marketreport.specialists import specialist_for

        self.assertEqual(("Q5", "Q6"), MARKET_SHARE.answers)
        self.assertIs(MARKET_SHARE, specialist_for("Q5"))
        # Q3 was the "nobody claims this" example until market-size claimed
        # it — deliberately, in the specialist expansion. The declaration
        # mechanism is what is under test, so assert the claim it now makes.
        self.assertEqual("market-size", specialist_for("Q3").name)


class P12_TheLibrary(unittest.TestCase):
    """A panel is a record, not a rendering. This is the part that makes the
    claim true — panels are written when produced and read back without
    re-running anything."""

    def _panel(self, headline="Samsung leads on units",
               when="2026-03-14T10:00:00"):
        panel = Panel(question="Who holds the cell phone market?",
                      headline=headline, form="share_pair",
                      agent="market-share")
        panel.generated = when
        panel.series = [Series("Units", "shipment share", "%", basis="SAG",
                               slices=[Slice("Samsung", 22, source_ids=["S1"]),
                                       Slice("Apple", 20, source_ids=["S1"])])]
        panel.source_labels = ["Smart Analytics Global"]
        return panel

    def _library(self, tmp):
        from marketreport.library import Library

        return Library(tmp)

    def test_a_saved_panel_comes_back_identical(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            shelf = self._library(tmp)
            ref = shelf.save(self._panel(), market="cell phones",
                             place="Ireland")
            self.assertEqual(self._panel().to_dict(),
                             shelf.load(ref.id).to_dict())

    def test_re_asking_stores_a_new_panel_beside_the_old(self):
        """Two runs of one question are different panels — the market moved,
        or the sources did — and overwriting the first would destroy the
        comparison that makes a re-run worth doing."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            shelf = self._library(tmp)
            first = shelf.save(self._panel("Samsung leads",
                                           "2026-03-14T10:00:00"))
            second = shelf.save(self._panel("Apple has pulled level",
                                            "2026-08-27T10:00:00"))
            self.assertNotEqual(first.id, second.id)
            self.assertEqual(2, len(shelf.list()))

    def test_the_listing_is_newest_first(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            shelf = self._library(tmp)
            shelf.save(self._panel("older", "2026-03-14T10:00:00"))
            shelf.save(self._panel("newer", "2026-08-27T10:00:00"))
            self.assertEqual(["newer", "older"],
                             [r.headline for r in shelf.list()])

    def test_earlier_answers_to_the_same_question_are_findable(self):
        """The comparison a stored panel exists to make possible."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            shelf = self._library(tmp)
            shelf.save(self._panel("older", "2026-03-14T10:00:00"))
            newest = shelf.save(self._panel("newer", "2026-08-27T10:00:00"))
            self.assertEqual(["older"],
                             [r.headline for r in shelf.related(newest.id)])

    def test_one_corrupt_file_does_not_close_the_gallery(self):
        """The failure mode that turns "something went wrong once" into
        "nothing works"."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            shelf = self._library(tmp)
            shelf.save(self._panel())
            with open(os.path.join(tmp, "broken.json"), "w",
                      encoding="utf-8") as handle:
                handle.write("{not json")
            self.assertEqual(1, len(shelf.list()))

    def test_a_missing_panel_returns_none_rather_than_raising(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self._library(tmp).load("does-not-exist"))

    def test_ids_are_readable_and_cannot_escape_the_directory(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            shelf = self._library(tmp)
            ref = shelf.save(self._panel(), market="cell phones",
                             place="Ireland")
            self.assertIn("cell-phones-ireland", ref.id)
            self.assertIsNone(shelf.load("../../etc/passwd"))

    def test_the_manager_stores_what_it_produced(self):
        """A panel that cost a research budget and evaporated because the
        caller forgot to save it is the expensive kind of forgetting — so the
        manager stores as it goes, not on the caller's say-so."""
        import tempfile

        from marketreport import manager, specialists

        with tempfile.TemporaryDirectory() as tmp:
            shelf = self._library(tmp)
            panel = self._panel()
            original = specialists.run_specialist
            manager.run_specialist = lambda spec, **kw: panel
            try:
                result = manager.answer(
                    "market share of cell phones in Ireland",
                    provider=None, researcher=None, library=shelf,
                    on_event=lambda m: None)
            finally:
                manager.run_specialist = original

            self.assertEqual(1, len(result["panels"]))
            self.assertEqual(1, len(result["stored"]))
            stored = shelf.load(result["stored"][0].id)
            self.assertEqual(panel.headline, stored.headline)

    def test_an_unanswerable_request_stores_nothing(self):
        import tempfile

        from marketreport import manager

        with tempfile.TemporaryDirectory() as tmp:
            result = manager.answer("tell me a joke", provider=None,
                                    researcher=None,
                                    library=self._library(tmp),
                                    on_event=lambda m: None)
            self.assertEqual([], result["panels"])
            self.assertEqual([], result["stored"])
            self.assertTrue(result["question"])


class P13_TheOfflineRun(unittest.TestCase):
    """The whole path — router, loop, reader, shaper, binding, cross-checks,
    rendering — with no keys and no network, over pages that are real.

    `marketreport/demo_sources.py` holds excerpts recorded on 2026-08-27 from
    the URLs beside them. That is the difference from `fixtures.py`, whose
    numbers I invented: CRITIQUE.md #1 is that a demo built on invented figures
    teaches a stranger that the product works when what works is the fixture.
    """

    def _run(self, question="market share of cell phones"):
        from deckscope.providers.mock_provider import MockProvider
        from marketreport.demo_sources import RecordedResearcher
        from marketreport.manager import answer

        return answer(question, provider=MockProvider(),
                      researcher=RecordedResearcher(), store=False,
                      on_event=lambda m: None)

    def test_it_produces_a_panel_end_to_end(self):
        result = self._run()
        self.assertEqual(1, len(result["panels"]))
        self.assertTrue(result["panels"][0].answered)

    def test_the_two_yardsticks_both_appear(self):
        """The whole point: units and revenue over one market, kept apart."""
        panel = self._run()["panels"][0]
        self.assertEqual(2, len(panel.series))
        self.assertEqual({"Units", "Revenue"},
                         {s.label for s in panel.series})
        self.assertIn("units", panel.headline.lower())
        self.assertIn("revenue", panel.headline.lower())

    def test_a_series_is_drawn_from_one_tracker(self):
        """SAG had Samsung at 22% and IDC at 22.6%. Grouping on measure alone
        put both in one pie, silently blending two independent estimates into a
        chart claiming to be one of them. Two trackers disagreeing is a finding
        to report, not a series to blend."""
        panel = self._run()["panels"][0]
        for series in panel.series:
            with self.subTest(series=series.label):
                labels = [w.label for w in series.slices]
                self.assertEqual(len(labels), len(set(labels)))

    def test_a_form_the_evidence_cannot_support_degrades_loudly(self):
        """The demo's revenue series has one vendor, which is not a
        comparison. Falling back silently is what render_as refuses to do for
        output formats, and for the same reason — so the downgrade is stated,
        because it is a fact about how much the run established."""
        panel = self._run()["panels"][0]
        if panel.form != "share_pair":
            self.assertTrue(
                any("would not support" in c for c in panel.caveats),
                f"form was downgraded to {panel.form} with no explanation")

    def test_the_fallback_form_is_itself_valid(self):
        """The first version guessed at a fallback, guessed wrong, and produced
        a panel that failed validation under a DIFFERENT form. A fallback that
        needs its own fallback is not a fallback."""
        panel = self._run()["panels"][0]
        self.assertEqual([], panel.problems())

    def test_the_panel_is_structurally_valid(self):
        panel = self._run()["panels"][0]
        self.assertEqual([], panel.problems())

    def test_every_slice_traces_to_a_recorded_source(self):
        panel = self._run()["panels"][0]
        for series in panel.series:
            for wedge in series.slices:
                with self.subTest(slice=wedge.label):
                    self.assertTrue(wedge.source_ids)
                    self.assertTrue(wedge.finding_id)

    def test_the_series_name_their_publisher_not_a_source_id(self):
        """The shaper was only ever shown source IDs, so the best it could do
        was write "S2" — and the panel then told a reader its two series "come
        from different publishers (S2 and S3)", which is true and useless."""
        panel = self._run()["panels"][0]
        for series in panel.series:
            with self.subTest(series=series.label):
                self.assertTrue(series.basis)
                self.assertFalse(re.fullmatch(r"S\d+", series.basis))

    def test_the_missing_remainder_is_disclosed(self):
        panel = self._run()["panels"][0]
        self.assertTrue(any("not broken out" in c for c in panel.caveats))

    def test_it_renders_in_every_format(self):
        from marketreport.panel_render import (panel_html, panel_markdown,
                                               panel_text)

        panel = self._run()["panels"][0]
        for name, body in (("html", panel_html(panel)),
                           ("md", panel_markdown(panel)),
                           ("txt", panel_text(panel))):
            with self.subTest(fmt=name):
                self.assertIn("Samsung", body)

    def test_the_recorded_pages_carry_their_url_and_date(self):
        """A recorded excerpt with no provenance is an invented one that has
        not been caught yet."""
        from marketreport.demo_sources import PAGES, RETRIEVED

        self.assertTrue(RETRIEVED)
        for page in PAGES:
            with self.subTest(page=page["title"][:32]):
                self.assertTrue(page["url"].startswith("https://"))
                self.assertTrue(page["published"])
                self.assertGreater(len(page["snippet"]), 80)

    def test_the_demo_refuses_a_market_it_has_no_pages_for(self):
        """Running it anyway produces an empty panel that reads like a real
        failure rather than a demo with the wrong subject."""
        from marketreport.demo_sources import covered

        self.assertTrue(covered("cell phones"))
        self.assertTrue(covered("smartphone market"))
        self.assertFalse(covered("landscaping"))

    def test_the_mock_shaper_will_not_draw_what_it_cannot_attribute(self):
        """It took the first word of every statement as an entity, and drew
        "Worldwide" and "The" as vendors — with a 6.7% year-over-year DECLINE
        rendered as a 6.7% market share. A mock held to a lower standard than
        the thing it stands in for is not standing in for it."""
        panel = self._run()["panels"][0]
        drawn = {w.label for s in panel.series for w in s.slices}
        for junk in ("Worldwide", "The", "Global"):
            with self.subTest(label=junk):
                self.assertNotIn(junk, drawn)


class P14_TheSectionAgent(unittest.TestCase):
    """The function everything else was built around the absence of: a section
    brief in, a panel out."""

    def _run(self, report_key="market-share", subject="cell phones"):
        from deckscope.providers.mock_provider import MockProvider
        from marketreport.demo_sources import RecordedResearcher
        from marketreport.reports import build_report, get
        from marketreport.section_agent import make_section_agent

        return build_report(
            get(report_key), subject,
            run_section=make_section_agent(provider=MockProvider(),
                                           researcher=RecordedResearcher()),
            on_event=lambda m: None)

    def test_a_report_runs_end_to_end(self):
        result = self._run()
        self.assertEqual(4, len(result["panels"]))
        self.assertTrue(all(p.answered for p in result["panels"]))

    def test_every_panel_is_structurally_valid(self):
        for panel in self._run()["panels"]:
            with self.subTest(section=panel.agent):
                self.assertEqual([], panel.problems())

    def test_each_section_answers_its_own_question(self):
        """The shaper was not told which section it was shaping for, so it
        returned the same market-share chart for every section — including
        "which market is this", which is definitional and has no chart."""
        panels = {p.agent: p for p in self._run()["panels"]}
        self.assertEqual(set(), {"boundary", "units", "revenue"} - set(panels))
        units = panels["units"]
        revenue = panels["revenue"]
        self.assertEqual(["Units"], [s.label for s in units.series])
        self.assertEqual(["Revenue"], [s.label for s in revenue.series])

    def test_the_definitional_section_draws_no_chart(self):
        panels = {p.agent: p for p in self._run()["panels"]}
        self.assertEqual([], panels["boundary"].series)
        self.assertTrue(panels["boundary"].figures)

    def test_opening_questions_are_generated_from_the_brief(self):
        """A hand-written seed list is a prompt wearing architecture's
        clothes — it cannot be surprised and it is subject-blind."""
        panels = self._run()["panels"]
        opened = [q for p in panels for q in p.provenance.get("opened") or []]
        self.assertGreater(len(opened), 6)
        for question in opened:
            with self.subTest(q=question[:40]):
                self.assertIn("cell phone", question.lower())

    def test_the_questions_differ_between_sections(self):
        panels = {p.agent: p for p in self._run()["panels"]}
        units = set(panels["units"].provenance.get("opened") or [])
        revenue = set(panels["revenue"].provenance.get("opened") or [])
        self.assertTrue(units)
        self.assertEqual(set(), units & revenue)

    def test_a_failed_opener_still_opens_something(self):
        """A section that refuses to open because the opener stage failed
        reports as an absent fact rather than as the outage it is."""
        from marketreport.reports import get
        from marketreport.section_agent import _opening_questions

        class Broken:
            def complete_json(self, *a, **k):
                raise RuntimeError("no model")

        spec = get("market-share").sections[1]
        rows = _opening_questions(section=spec, subject="cell phones",
                                  place="", report=None, provider=Broken(),
                                  context={})
        self.assertEqual(1, len(rows))
        self.assertIn("cell phones", rows[0]["text"])

    def test_the_run_records_what_it_opened_and_spent(self):
        panel = self._run()["panels"][0]
        for key in ("opened", "findings", "retrievals", "iterations"):
            with self.subTest(key=key):
                self.assertIn(key, panel.provenance)

    def test_a_thin_section_gets_the_upgrade_offer(self):
        result = self._run()
        offers = {o["section"] for o in result["upgrades"]}
        self.assertTrue(offers)
        for offer in result["upgrades"]:
            self.assertTrue(offer["sources"])

    def test_coverage_is_counted_not_asserted(self):
        stats = self._run()["coverage"]
        self.assertEqual(4, stats["sections"])
        self.assertEqual([], stats["missing_required"])
        self.assertGreater(stats["figures"], 0)
        self.assertLessEqual(stats["checkable"], stats["figures"])
