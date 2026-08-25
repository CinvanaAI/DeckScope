"""Tests for the market sizing engine.

The invariants here are the ones that decide whether a number in a report can be
trusted. Each corresponds to a failure that has actually happened in this
project or that the corpus shows happening in real filings.

  S1  a missing term produces None, never zero and never a partial answer
  S2  a negative magnitude is refused — the "$6-8B parsed as -$1B" bug class
  S3  a rate above 1.0 is refused (percent that was never divided)
  S4  a child ring larger than its parent is caught and named
  S5  an assumption without a range is marked as one
  S6  the arithmetic string always shows its operands
  S7  agilon's three published rings reproduce exactly
  S8  a term nobody can check is reported as uncheckable, even when it has a value
"""
from __future__ import annotations

import unittest

from marketreport.cases.agilon_2021 import PUBLISHED, check
from marketreport.sizing import (ASSUMED, MEASURED, UNAVAILABLE, Ring, Sizing,
                                 SizingError, Term)


def count(v, **kw):
    kw.setdefault("source", "Census CBP")
    kw.setdefault("unit", "establishments")
    return Term(kind="count", value=v, **kw)


def value(v, **kw):
    kw.setdefault("source", "Economic Census")
    kw.setdefault("unit", "$ per establishment per year")
    return Term(kind="value", value=v, **kw)


class MissingTerms(unittest.TestCase):

    def test_a_missing_value_makes_the_size_unknown_not_zero(self):
        """S1 — the tempting failure is to substitute something plausible."""
        ring = Ring(label="Arizona", count=count(1000),
                    value=Term(kind="value", value=None, method=UNAVAILABLE,
                               note="no free source publishes revenue per "
                                    "establishment for this industry"))
        self.assertIsNone(ring.size)
        self.assertEqual(["value"], ring.missing)

    def test_a_missing_value_does_not_leak_the_count_as_a_dollar_figure(self):
        ring = Ring(label="Arizona", count=count(1000),
                    value=Term(kind="value", value=None, method=UNAVAILABLE))
        self.assertIsNone(ring.size)
        self.assertNotEqual(1000, ring.size)

    def test_the_qualified_count_survives_an_unknown_value(self):
        """Knowing there are 1,000 firms is useful even without a dollar figure."""
        ring = Ring(label="Arizona", count=count(1000),
                    rate=Term(kind="rate", value=0.4, source="BLS"),
                    value=Term(kind="value", value=None, method=UNAVAILABLE))
        self.assertIsNone(ring.size)
        self.assertAlmostEqual(400.0, ring.qualified_count)

    def test_the_arithmetic_says_which_term_was_missing(self):
        ring = Ring(label="Arizona", count=count(1000),
                    value=Term(kind="value", value=None, method=UNAVAILABLE))
        self.assertIn("not established", ring.arithmetic())
        self.assertIn("value", ring.arithmetic())


class RefusedInputs(unittest.TestCase):

    def test_a_negative_magnitude_is_refused(self):
        """S2 — '$6-8B' once parsed to NEGATIVE one billion and flowed onward."""
        with self.assertRaises(SizingError) as ctx:
            count(-1e9)
        self.assertIn("parsing bug", str(ctx.exception))

    def test_a_rate_above_one_is_refused(self):
        """S3 — 85% must arrive as 0.85, not as 85."""
        with self.assertRaises(SizingError):
            Term(kind="rate", value=85.0, source="Frost & Sullivan")

    def test_a_rate_of_exactly_one_is_allowed(self):
        Term(kind="rate", value=1.0, source="all of them qualify")


class Nesting(unittest.TestCase):

    def test_a_child_larger_than_its_parent_is_caught(self):
        """S4 — mismatched vintages produce this and it looks normal in a table."""
        s = Sizing("test")
        s.add(Ring(label="United States", count=count(100), value=value(1_000)))
        s.add(Ring(label="Arizona", count=count(500), value=value(1_000)))
        self.assertTrue(s.warnings)
        self.assertIn("nesting", s.warnings[0])
        self.assertIn("Arizona", s.warnings[0])

    def test_proper_nesting_produces_no_warning(self):
        s = Sizing("test")
        s.add(Ring(label="United States", count=count(1000), value=value(1_000)))
        s.add(Ring(label="Arizona", count=count(100), value=value(1_000)))
        s.add(Ring(label="Maricopa County", count=count(40), value=value(1_000)))
        self.assertEqual([], s.warnings)

    def test_small_rounding_between_vintages_is_tolerated(self):
        s = Sizing("test")
        s.add(Ring(label="United States", count=count(1000), value=value(1_000)))
        s.add(Ring(label="Arizona", count=count(1010), value=value(1_000)))
        self.assertEqual([], s.warnings, "1% over should not be an error")

    def test_an_unknown_ring_does_not_break_the_nesting_check(self):
        s = Sizing("test")
        s.add(Ring(label="United States", count=count(1000), value=value(1_000)))
        s.add(Ring(label="Arizona",
                   count=count(100),
                   value=Term(kind="value", value=None, method=UNAVAILABLE)))
        s.add(Ring(label="Maricopa County", count=count(40), value=value(1_000)))
        self.assertEqual([], s.warnings)


class Provenance(unittest.TestCase):

    def test_an_assumption_without_a_range_is_marked(self):
        """S5 — an unranged assumption reads exactly like a measurement."""
        t = Term(kind="value", value=10_000.0, method=ASSUMED, source="stated")
        self.assertIn("without a stated range", t.note)

    def test_an_assumption_with_a_range_is_not_marked(self):
        t = Term(kind="value", value=10_000.0, method=ASSUMED, source="stated",
                 low=8_000.0, high=12_000.0)
        self.assertNotIn("without a stated range", t.note)

    def test_an_assumed_term_is_known_but_not_sourced(self):
        """S8 — it has a value, and a reader still cannot go and check it."""
        t = Term(kind="value", value=10_000.0, method=ASSUMED, source="filing",
                 low=8e3, high=12e3)
        self.assertTrue(t.known)
        self.assertFalse(t.sourced)

    def test_unsourced_lists_assumed_and_missing_terms_alike(self):
        s = Sizing("test")
        s.add(Ring(label="US",
                   count=count(1000),
                   value=Term(kind="value", value=5.0, method=ASSUMED,
                              source="stated", low=4.0, high=6.0)))
        self.assertEqual(1, len(s.unsourced()))
        self.assertIn("value", s.unsourced()[0])

    def test_a_measured_term_with_no_source_is_not_sourced(self):
        t = Term(kind="count", value=10.0, method=MEASURED, source="")
        self.assertFalse(t.sourced)


class Arithmetic(unittest.TestCase):

    def test_the_operands_are_always_shown(self):
        """S6 — the arithmetic is the product, not a debugging aid."""
        ring = Ring(label="US", count=count(20e6, unit="professionals"),
                    rate=Term(kind="rate", value=0.85, source="Frost & Sullivan"),
                    value=value(600, unit="$ per professional per year"))
        text = ring.arithmetic()
        self.assertIn("20.0M", text)
        self.assertIn("85.0%", text)
        self.assertIn("$600", text)
        self.assertIn("=", text)

    def test_the_figs_shape_computes(self):
        """20M healthcare professionals x 85% x ~$600 lands near the filed $12.0B."""
        ring = Ring(label="US", count=count(20e6, unit="professionals"),
                    rate=Term(kind="rate", value=0.85, source="Frost & Sullivan"),
                    value=value(706, unit="$ per professional per year"))
        self.assertAlmostEqual(12.0e9, ring.size, delta=0.1e9)

    def test_rate_is_optional(self):
        ring = Ring(label="US", count=count(100), value=value(10))
        self.assertAlmostEqual(1000.0, ring.size)


class Blockers(unittest.TestCase):
    """One unset key blocks six terms. That is one problem, not six."""

    def _blocked(self):
        s = Sizing("landscaping")
        why = "CENSUS_API_KEY is not set. Get one free at <url>."
        for label in ("United States", "Arizona", "Maricopa County"):
            s.add(Ring(label=label,
                       count=Term(kind="count", value=None,
                                  method=UNAVAILABLE, note=why),
                       value=Term(kind="value", value=None,
                                  method=UNAVAILABLE, note=why)))
        return s

    def test_one_cause_is_reported_once(self):
        self.assertEqual(1, len(self._blocked().blockers()))

    def test_the_remedy_is_not_repeated_per_ring(self):
        text = self._blocked().render()
        self.assertEqual(1, text.count("Get one free at <url>."),
                         "the fix should appear once, not once per blocked term")
        self.assertEqual(6, text.count("see above"))

    def test_the_reader_is_told_nothing_could_be_sized(self):
        self.assertIn("NOTHING COULD BE SIZED", self._blocked().render())

    def test_two_distinct_causes_are_both_reported(self):
        s = Sizing("test")
        s.add(Ring(label="US",
                   count=Term(kind="count", value=None, method=UNAVAILABLE,
                              note="no API key"),
                   value=Term(kind="value", value=None, method=UNAVAILABLE,
                              note="suppressed to protect individual firms")))
        self.assertEqual(2, len(s.blockers()))

    def test_a_partially_sized_report_does_not_claim_nothing_was_sized(self):
        s = Sizing("test")
        s.add(Ring(label="US", count=count(1000), value=value(5000)))
        s.add(Ring(label="AZ", count=count(50),
                   value=Term(kind="value", value=None, method=UNAVAILABLE,
                              note="county receipts suppressed")))
        text = s.render()
        self.assertNotIn("NOTHING COULD BE SIZED", text)
        self.assertIn("blocking 1 term", text)


class AgilonReproduction(unittest.TestCase):
    """S7 — the first check in this project whose answer key I did not write."""

    def setUp(self):
        self.result = check()

    def test_every_published_ring_reproduces(self):
        for row in self.result["rows"]:
            with self.subTest(ring=row["ring"]):
                self.assertTrue(
                    row["matches"],
                    f"published {row['published']:,.0f}, ours {row['ours']}")

    def test_the_rings_nest_without_warning(self):
        self.assertEqual([], self.result["nesting_warnings"])

    def test_the_value_term_is_reported_as_uncheckable_on_every_ring(self):
        """The whole point. It reproduces the number AND admits the number
        rests on something no outside party can source."""
        self.assertEqual(3, len(self.result["unsourceable"]))
        for row in self.result["unsourceable"]:
            self.assertIn("value", row)

    def test_the_published_figures_are_the_ones_from_the_filing(self):
        self.assertEqual([175e9, 80e9, 24e9], list(PUBLISHED.values()))


if __name__ == "__main__":
    unittest.main()
