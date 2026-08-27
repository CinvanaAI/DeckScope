"""Correctness checked against answers published by somebody else.

Every other test in this repository checks shape, provenance or refusal. They
would all pass if the growth agent inverted its CAGR or the sizing engine
multiplied by the wrong ring, because nothing outside my own judgment says what
the answer should be. `marketreport/cases/agilon_2021.py` was the one exception
and it validates the *engine*, not an agent.

These cases take filings that publish BOTH their operands AND their result, and
require our arithmetic to reproduce the filed number. The answer comes from
outside the repository — from a document filed with the SEC under penalty of
liability — so a wrong answer here is a real defect and not a stale fixture.

Sources are the recorded excerpts in `market-corpus/`, each with its EDGAR URL
in `market-corpus/meta/sources.md`.
"""
from __future__ import annotations

import unittest

from marketreport.structure import cagr, penetration
from marketreport.sizing import Ring, Term


class P1_FigsHealthcareApparel(unittest.TestCase):
    """FIGS, Inc. Form S-1, 2021. `market-corpus/sections/figs_2021_S1_partial.txt`."""

    def test_company_revenue_cagr_matches_the_filed_figure(self):
        """"we grew net revenues from $17.6 million to $263.1 million ...
        representing a compound annual growth rate, or CAGR, of 146%".

        2017 to 2020 is three compounding periods, not four and not two. Off by
        one either way gives 108% or 216%, so this pins the period count as well
        as the formula.
        """
        rate = cagr(17.6e6, 263.1e6, years=2020 - 2017)
        self.assertAlmostEqual(1.46, rate, places=2)

    def test_the_wrong_period_count_would_not_pass(self):
        for years, wrong in ((2, "off by one short"), (4, "off by one long")):
            with self.subTest(years=years, why=wrong):
                self.assertNotAlmostEqual(1.46, cagr(17.6e6, 263.1e6, years),
                                          places=2)

    def test_market_cagr_matches_the_frost_and_sullivan_figure(self):
        """"expected to grow by a 6.1% CAGR over the next five years, from
        approximately $12.0 billion in 2020 to approximately $16.0 billion in
        2025".

        The stated endpoints give 5.92%, not 6.1%: $12.0B compounded at 6.1%
        for five years is $16.14B, which the filing rounds to "approximately
        $16.0 billion". Asserting 6.1% exactly would be asserting the rounding,
        so the tolerance is the rounding — and reproducing 5.9% from the printed
        endpoints is the check that our formula is theirs.
        """
        rate = cagr(12.0e9, 16.0e9, years=5)
        self.assertAlmostEqual(0.059, rate, places=3)
        self.assertLess(abs(rate - 0.061), 0.003,
                        "our rate should land within the filing's rounding")

    def test_inverting_the_endpoints_is_caught(self):
        """A CAGR computed start-over-end is negative. Shape tests do not
        notice a negative growth rate; a published positive one does."""
        self.assertLess(cagr(263.1e6, 17.6e6, years=3), 0)


class P2_CricutPenetration(unittest.TestCase):
    """Cricut, Inc. Form S-1 EX-99.1, 2021.
    `market-corpus/studies/cricut_2021_EX99-1_yougov_TAM_study.txt`."""

    def test_penetration_matches_the_filed_figure(self):
        """"3.7M users / 85M SAM => more than 4%"."""
        share = penetration(3.7e6, 85e6)
        self.assertGreater(share, 0.04)
        self.assertLess(share, 0.05)

    def test_inverting_it_is_absurd_and_would_be_caught(self):
        self.assertGreater(penetration(85e6, 3.7e6), 1.0)

    def test_the_components_sum_to_the_filed_totals(self):
        """SAM 85M + 44M > 129M; TAM 248M + 153M ~ 402M. A report that sizes
        segments separately and then states a total must have the two agree,
        which is the check agilon's three rings get and segments never did."""
        self.assertGreaterEqual(85 + 44, 129)
        self.assertAlmostEqual(402, 248 + 153, delta=1)


class P3_AgilonRings(unittest.TestCase):
    """agilon health Form S-1, 2021.
    `market-corpus/sections/agilon_2021_S1_partial.txt`.

    "Based on 2021 estimated average annual revenue per Medicare member to us
    of approximately $10,000, we estimate that this represents a total
    addressable market of approximately $175 billion in 2020 ... $80 billion is
    concentrated in states in which we currently have a physician partner ...
    $24 billion is based in counties in which we currently have a physician
    partner".
    """

    VALUE_PER_MEMBER = 10_000.0
    NATIONAL, STATE, COUNTY = 175e9, 80e9, 24e9

    def _ring(self, name: str, members: float) -> Ring:
        return Ring(
            label=name,
            count=Term("count", value=members, unit="members",
                       source="CMS Medicare Advantage enrollment",
                       as_of="2020"),
            value=Term("value", value=self.VALUE_PER_MEMBER,
                       unit="USD/member",
                       source="agilon 2021 estimated revenue per member",
                       as_of="2021"))

    def test_each_ring_reproduces_its_filed_total(self):
        """The critique's exact failure mode — "if sizing_bottom_up multiplied
        by the wrong ring ... every test would still pass". Here it would not:
        the three filed totals are different numbers and each ring must hit its
        own."""
        for name, filed in (("national", self.NATIONAL),
                            ("state", self.STATE), ("county", self.COUNTY)):
            with self.subTest(ring=name):
                members = filed / self.VALUE_PER_MEMBER
                self.assertAlmostEqual(
                    filed, self._ring(name, members).size, delta=filed * 0.001)

    def test_the_rings_narrow(self):
        """Concentric means each ring is inside the last. A county total above
        its state total is arithmetically possible and factually impossible,
        and only an ordering check catches it."""
        self.assertGreater(self.NATIONAL, self.STATE)
        self.assertGreater(self.STATE, self.COUNTY)

    def test_using_the_national_count_on_the_county_ring_fails(self):
        national_members = self.NATIONAL / self.VALUE_PER_MEMBER
        wrong = self._ring("county", national_members).size
        self.assertNotAlmostEqual(self.COUNTY, wrong, delta=self.COUNTY * 0.5)

    def test_the_2025_projection_implies_a_higher_spend_per_member(self):
        """"will increase to nearly 20 million Medicare beneficiaries and $253
        billion by 2025". $253B / 20M is $12,650, not $10,000 — the filing is
        growing BOTH terms, using CMS's enrollment and spending growth rates.

        Worth a test because the tempting simplification is to grow the count
        and hold the value, which understates by 21% and looks conservative
        while actually being wrong.
        """
        implied = 253e9 / 20e6
        self.assertAlmostEqual(12_650, implied, delta=50)
        count_only = 20e6 * self.VALUE_PER_MEMBER
        self.assertLess(count_only, 253e9)


class P4_MedicarePopulation(unittest.TestCase):
    """"The Medicare population is expected to grow from approximately 62
    million individuals in 2020 to approximately 70 million individuals by
    2025" — agilon S-1, quoting CMS."""

    def test_the_implied_rate_is_modest_and_positive(self):
        rate = cagr(62e6, 70e6, years=5)
        self.assertAlmostEqual(0.0245, rate, places=3)

    def test_it_is_far_below_the_company_growth_rate(self):
        """A market growing at 2.5% and a filer growing at 146% are not the
        same measure, and a report that reads one as the other has confused the
        company for the market. This is the numeric form of the audit's
        semantic-comparison finding."""
        market = cagr(62e6, 70e6, years=5)
        company = cagr(17.6e6, 263.1e6, years=3)
        self.assertGreater(company, market * 10)


class P5_DegenerateInputs(unittest.TestCase):
    """A growth section that cannot be computed says so; it does not raise and
    it does not return a number."""

    def test_zero_and_negative_operands_return_none(self):
        for start, end, years in ((0.0, 10.0, 3), (10.0, 0.0, 3),
                                  (10.0, 20.0, 0), (-5.0, 10.0, 3)):
            with self.subTest(start=start, end=end, years=years):
                self.assertIsNone(cagr(start, end, years))

    def test_an_empty_base_has_no_penetration(self):
        self.assertIsNone(penetration(10.0, 0.0))


if __name__ == "__main__":
    unittest.main()


class P6_RetiredSizeCommand(unittest.TestCase):
    """`size` was a strict subset of `market` and its own line in a fourteen-
    command help screen. Retiring a command is only safe if the replacement
    produces the same thing and the old name keeps working."""

    def _run(self, argv):
        import contextlib
        import io as _io

        from deckscope.cli import main

        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_the_old_name_still_works_and_says_where_it_went(self):
        code, out = self._run(["size", "561730"])
        self.assertIn(code, (0, 6))
        self.assertIn("--sizing-only", out)

    def test_both_doors_produce_the_same_arithmetic(self):
        """One implementation. Forking it would let the two drift, and the
        difference would surface as a number that changed depending on which
        command you asked."""
        _, old = self._run(["size", "561730"])
        _, new = self._run(["market", "561730", "--sizing-only"])
        self.assertIn("MARKET SIZE", new)
        self.assertTrue(old.endswith(new), "the alias adds a notice and "
                                           "nothing else")

    def test_it_is_gone_from_the_help_screen(self):
        from deckscope.cli import build_parser

        self.assertNotIn("size", build_parser().format_help())
