"""The report as a document.

The failure these guard against is a renderer that drops something. A report
that omits a section it could not answer reads as complete; a report that omits
the demo warning reads as measured. Both are the same bug — the artifact
claiming more than the run behind it — and both are invisible unless something
compares the formats against each other.
"""
from __future__ import annotations

import re
import unittest

import marketreport.agents  # noqa: F401 - importing registers the agents
from marketreport.document import (FORMATS, as_html, infer_format, markdown,
                                   render_as)
from marketreport.questions import STANDING
from marketreport.render import HEADINGS, text
from marketreport.report import MarketDefinition, build
from marketreport.request import interpret


def _demo():
    return build(interpret("landscaping in phoenix",
                           offline=True).definition(demo=True))


def _live():
    return build(MarketDefinition(label="Landscaping", naics="561730",
                                  state_fips="04"))


class D1_EveryFormatCarriesEverySection(unittest.TestCase):
    """One source, four renderers. A heading present in one and missing from
    another means a reader gets a different report depending on how they
    asked for it."""

    def setUp(self):
        self.answers = _demo()

    def test_html_has_every_heading(self):
        body = as_html(self.answers)
        for question in STANDING:
            heading = HEADINGS.get(question.section, "")
            with self.subTest(q=question.id):
                self.assertIn(heading, body)

    def test_markdown_has_every_heading(self):
        body = markdown(self.answers)
        for question in STANDING:
            with self.subTest(q=question.id):
                self.assertIn(HEADINGS.get(question.section, ""), body)

    def test_all_four_formats_produce_something_substantial(self):
        for name in FORMATS:
            with self.subTest(fmt=name):
                body = render_as(name, self.answers)
                self.assertGreater(len(body), 2000)
                self.assertIn("Landscaping Services", body)

    def test_the_sections_appear_in_the_same_order_everywhere(self):
        """Reading order is part of the argument: what this market is, how big,
        how shaped, how hard to enter, and what could not be established. A
        renderer that reorders it makes a different case."""
        def order(body):
            found = []
            for question in STANDING:
                heading = HEADINGS.get(question.section, "")
                position = body.find(heading)
                if position >= 0:
                    found.append((position, heading))
            return [h for _, h in sorted(found)]

        self.assertEqual(order(text(self.answers)),
                         order(markdown(self.answers)))
        self.assertEqual(order(text(self.answers)),
                         order(as_html(self.answers)))


class D2_ProvenanceSurvivesTheRendering(unittest.TestCase):

    def test_a_demo_figure_is_warned_about_in_every_format(self):
        answers = _demo()
        for name in ("html", "md", "txt"):
            with self.subTest(fmt=name):
                body = render_as(name, answers).lower()
                self.assertTrue(
                    "illustrative" in body or "sample data" in body,
                    f"{name} lost the demo warning")

    def test_the_demo_warning_reaches_the_top_of_the_document(self):
        """Before the first number, not in a footnote after it."""
        body = as_html(_demo())
        self.assertLess(body.lower().index("recorded sample data"),
                        body.index(HEADINGS["definition"]))

    def test_a_demo_answer_shows_no_source_line(self):
        """Listing a dataset that was never queried is the provenance badge
        over invented numbers, one layer further out."""
        answers = _demo()
        demo_ids = {q.id for q in STANDING
                    if answers.get(q.id) and answers.get(q.id).demo}
        self.assertTrue(demo_ids, "the demo produced no demo answers")
        body = markdown(answers)
        for block in body.split("\n## "):
            if "Illustrative figure" in block:
                self.assertNotIn("\nSources:", block)

    def test_an_unanswered_section_says_why_rather_than_vanishing(self):
        """A section that disappears reads as an oversight. A section that
        says what stopped it is a finding."""
        answers = _live()
        body = as_html(answers)
        for question in STANDING:
            answer = answers.get(question.id)
            if answer is not None and not answer.answered:
                with self.subTest(q=question.id):
                    self.assertIn(HEADINGS.get(question.section, ""), body)
                    self.assertIn("Not established", body)

    def test_coverage_is_stated_not_implied(self):
        for name in ("html", "md"):
            with self.subTest(fmt=name):
                body = render_as(name, _demo())
                self.assertIn("Independently checkable", body)
                self.assertIn("From recorded samples", body)


class D3_TheHtmlIsSafeAndSelfContained(unittest.TestCase):

    def test_nothing_is_loaded_from_the_network(self):
        """A report that phones home is a report that stops working offline,
        and one that leaks who read it and when."""
        body = as_html(_demo())
        self.assertNotIn("http://", body)
        for pattern in ("<script", "src=", "@import", "url("):
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, body)

    def test_content_is_escaped(self):
        """Market labels come from user input, and this file is handed to a
        browser."""
        answers = build(MarketDefinition(
            label="<img src=x onerror=alert(1)>", naics="561730", demo=True))
        body = as_html(answers)
        self.assertNotIn("<img src=x", body)
        self.assertIn("&lt;img", body)

    def test_it_has_a_print_stylesheet(self):
        """There is no PDF writer on purpose — a second layout would be a
        second thing to keep in step. The browser already does it."""
        body = as_html(_demo())
        self.assertIn("@media print", body)
        self.assertIn("@page", body)

    def test_sections_do_not_break_across_pages(self):
        self.assertIn("page-break-inside:avoid", as_html(_demo()))

    def test_it_is_a_complete_document(self):
        body = as_html(_demo())
        self.assertTrue(body.startswith("<!doctype html>"))
        self.assertTrue(body.rstrip().endswith("</html>"))
        self.assertIn("<title>", body)


class D4_Dispatch(unittest.TestCase):

    def test_an_unknown_format_raises_rather_than_falling_back(self):
        """A caller who asked for --format pdf and silently received plain
        text has been handed something that looks like it worked."""
        with self.assertRaises(ValueError) as caught:
            render_as("pdf", _demo())
        self.assertIn("html", str(caught.exception))

    def test_the_extension_decides(self):
        self.assertEqual("html", infer_format("report.html"))
        self.assertEqual("md", infer_format("REPORT.MD"))
        self.assertEqual("json", infer_format("report.json"))

    def test_an_unknown_extension_falls_back_to_the_default(self):
        self.assertEqual("json", infer_format("report", default="json"))
        self.assertEqual("json", infer_format("report.docx", default="json"))

    def test_every_advertised_format_actually_renders(self):
        """The table is what the CLI's --format choices are documented from."""
        answers = _demo()
        for name in FORMATS:
            with self.subTest(fmt=name):
                self.assertTrue(render_as(name, answers).strip())

    def test_the_generated_date_can_be_pinned(self):
        """So a saved report is byte-identical on a re-run, which is what makes
        a diff between two runs mean something."""
        answers = _demo()
        first = as_html(answers, generated="2026-01-01")
        second = as_html(answers, generated="2026-01-01")
        self.assertEqual(first, second)
        self.assertIn("2026-01-01", first)


class D5_MarkdownIsPasteable(unittest.TestCase):

    def test_headings_are_real_markdown(self):
        body = markdown(_demo())
        self.assertTrue(re.search(r"^# Market report", body, re.M))
        self.assertTrue(re.search(r"^## ", body, re.M))

    def test_the_coverage_table_is_a_table(self):
        self.assertIn("|---|---|", markdown(_demo()))

    def test_it_ends_with_exactly_one_newline(self):
        body = markdown(_demo())
        self.assertTrue(body.endswith("\n"))
        self.assertFalse(body.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()


class D6_AWiringMistakeIsNotAFinding(unittest.TestCase):
    """Found while writing this file: the test module forgot to import
    `marketreport.agents`, and `build()` produced a full twelve-section report
    in which Q1 read "no agent is registered" and the other eleven read "needs
    Q1, which was not established".

    Eleven sections each stating an honest-looking limit of the evidence. A
    reader would conclude the data was not available. It was an import.

    This is the recurring shape in this repository — a defect rendering as a
    finding — and the fix is the same each time: make the impossible state
    loud rather than plausible.
    """

    def test_building_with_no_agents_raises(self):
        import marketreport.report as module

        saved = dict(module._AGENTS)
        module._AGENTS.clear()
        try:
            with self.assertRaises(RuntimeError) as caught:
                build(MarketDefinition(label="x", naics="561730", demo=True))
            self.assertIn("import marketreport.agents", str(caught.exception))
        finally:
            module._AGENTS.update(saved)

    def test_it_does_not_raise_when_they_are_registered(self):
        """The guard must fire on the wiring mistake and nothing else."""
        self.assertGreater(_demo().coverage()["answered"], 10)
