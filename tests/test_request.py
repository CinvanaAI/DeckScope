"""The step that turns what somebody said into what the Census API wants.

This is the layer where a mistake is least visible. Every other component fails
loudly — a missing term is `None`, an unavailable source raises. A market
resolved to the wrong NAICS code fails *quietly*: the report is internally
consistent, every figure traces to a real source, the arithmetic is right, and
it is about a different industry than the one asked for. Nothing downstream can
detect it.

So the tests here are mostly about what the resolver REFUSES to do.
"""
from __future__ import annotations

import unittest

from marketreport import geography as geo
from marketreport.naics import (FLOOR, MARGIN, STARTER, Resolution, index,
                                resolve)
from marketreport.request import interpret


class R1_TheOriginalQuestion(unittest.TestCase):
    """the client's first question was "landscaping in Phoenix". Until now the
    product could not take it — it wanted `561730 --state 04 --county 013`."""

    def test_it_resolves_end_to_end(self):
        read = interpret("landscaping in phoenix", offline=True)
        self.assertTrue(read.ready, read.question)
        self.assertEqual("561730", read.naics)
        self.assertEqual("04", read.state_fips)
        self.assertEqual("013", read.county_fips)

    def test_the_definition_carries_a_readable_label(self):
        definition = interpret("landscaping in phoenix",
                               offline=True).definition(demo=True)
        self.assertIn("Landscaping Services", definition.label)
        self.assertIn("Maricopa", definition.label)

    def test_a_place_given_separately_works_the_same(self):
        joined = interpret("gyms in seattle", offline=True)
        split = interpret("gyms", place="seattle", offline=True)
        self.assertEqual((joined.naics, joined.state_fips, joined.county_fips),
                         (split.naics, split.state_fips, split.county_fips))


class R2_ItRefusesToGuess(unittest.TestCase):

    def test_an_ambiguous_industry_is_ranked_not_chosen(self):
        """Management consulting and IT consulting are different industries
        with different economics. Picking the higher-scoring one silently is
        how a report about one gets filed as a report about the other."""
        found = resolve("consulting", offline=True)
        self.assertFalse(found.certain)
        self.assertIsNone(found.code)
        self.assertGreater(len(found.candidates), 1)

    def test_the_ambiguity_reaches_the_caller_as_a_question(self):
        read = interpret("consulting in phoenix", offline=True)
        self.assertFalse(read.ready)
        self.assertIn("Which one?", read.question)
        self.assertTrue(read.options)

    def test_an_unresolved_interpretation_will_not_produce_a_definition(self):
        """Belt and braces: the refusal has to survive a caller who ignores
        `ready` and asks for the definition anyway."""
        read = interpret("consulting", offline=True)
        with self.assertRaises(ValueError):
            read.definition()

    def test_a_city_spanning_counties_is_refused_by_name(self):
        """New York City is five counties. Resolving it to any one of them
        would be a factual error dressed as a convenience."""
        read = interpret("dentists in new york", offline=True)
        self.assertFalse(read.ready)
        self.assertIn("five counties", read.question)

    def test_an_unknown_industry_says_which_list_it_searched(self):
        """"Not found" means something entirely different in a 32-entry
        starter set than in the full 1,012."""
        found = resolve("underwater basket weaving", offline=True)
        self.assertIn("starter index", found.problem)
        self.assertIn("1,012", found.problem)

    def test_an_unknown_city_offers_the_precise_route_instead(self):
        place = geo.resolve_city("Boise")
        self.assertFalse(place.resolved)
        self.assertIn("--state", place.problem)


class R3_NoGeographyIsInvented(unittest.TestCase):

    def test_no_place_means_national_not_nowhere(self):
        read = interpret("landscaping", offline=True)
        self.assertTrue(read.ready)
        self.assertEqual("", read.state_fips)
        self.assertEqual("", read.county_fips)
        self.assertIn("United States", read.geography_label)

    def test_it_says_so_in_its_notes(self):
        read = interpret("landscaping", offline=True)
        self.assertTrue(any("national" in n for n in read.notes))


class R4_Parsing(unittest.TestCase):

    def test_it_splits_on_the_last_separator_not_the_first(self):
        """"Internet publishing in Chicago" must keep the industry whole.
        Splitting on the first " in " hands the resolver "Internet" and the
        geography "publishing in Chicago" — rare, and silently wrong."""
        from marketreport.request import _split

        self.assertEqual(("Internet publishing", "Chicago"),
                         _split("Internet publishing in Chicago"))

    def test_a_bare_code_is_taken_as_a_code(self):
        found = resolve("561730", offline=True)
        self.assertTrue(found.certain)
        self.assertEqual("561730", found.code)

    def test_a_code_of_the_wrong_length_is_rejected(self):
        self.assertIn("2 to 6 digits", resolve("5617301", offline=True).problem)

    def test_county_state_form_resolves_without_a_key(self):
        """The city list already carries county names and FIPS, so naming the
        county explicitly must not be harder than naming a city inside it."""
        read = interpret("landscaping in Maricopa County, Arizona",
                         offline=True)
        self.assertTrue(read.ready, read.question)
        self.assertEqual(("04", "013"), (read.state_fips, read.county_fips))

    def test_a_trailing_state_name_is_peeled_off(self):
        read = interpret("gyms in Phoenix Arizona", offline=True)
        self.assertTrue(read.ready, read.question)
        self.assertEqual("013", read.county_fips)


class R5_StateCodes(unittest.TestCase):
    """56 entries, ANSI standard, unchanged since 1970 — so they can be typed.
    The set has a checkable shape, which is what makes typing them safe."""

    def test_the_unassigned_codes_stay_unassigned(self):
        """03, 07, 14, 43 and 52 were never reused. A fat-fingered digit that
        landed on one of them would otherwise point at a plausible state."""
        for code in geo.UNASSIGNED:
            self.assertNotIn(code, geo.STATES)

    def test_every_code_is_two_digits_and_in_range(self):
        for code in geo.STATES:
            self.assertEqual(2, len(code))
            self.assertTrue(code.isdigit())
            self.assertTrue(1 <= int(code) <= 72)

    def test_every_abbreviation_is_unique(self):
        abbreviations = [abbr for _, abbr in geo.STATES.values()]
        self.assertEqual(len(abbreviations), len(set(abbreviations)))

    def test_fifty_states_plus_dc_and_puerto_rico(self):
        self.assertEqual(52, len(geo.STATES))

    def test_name_abbreviation_and_code_all_resolve(self):
        for text in ("Arizona", "arizona", "AZ", "az", "04", "4"):
            with self.subTest(text=text):
                self.assertEqual("04", geo.state_fips(text))

    def test_nonsense_resolves_to_nothing(self):
        for text in ("", "Atlantis", "99", "AZZ"):
            with self.subTest(text=text):
                self.assertIsNone(geo.state_fips(text))


class R6_TheCityListIsHonestAboutBeingAList(unittest.TestCase):

    def test_every_entry_names_a_real_state(self):
        for city, (state, county, name) in geo.CITIES.items():
            with self.subTest(city=city):
                self.assertIn(state, geo.STATES)
                self.assertEqual(3, len(county))
                self.assertTrue(county.isdigit())
                self.assertTrue(name)

    def test_excluded_cities_explain_themselves(self):
        """A place left out on purpose says why, so nobody later "fixes" the
        gap by picking one county at random."""
        for city, reason in geo.SPANS_COUNTIES.items():
            with self.subTest(city=city):
                self.assertNotIn(city, geo.CITIES)
                self.assertGreater(len(reason), 30)

    def test_houston_is_excluded_and_says_which_counties(self):
        place = geo.resolve_city("Houston")
        self.assertFalse(place.resolved)
        self.assertIn("Harris", place.problem)


class R7_TheStarterIndexIsLabelled(unittest.TestCase):

    def test_it_names_itself_a_subset_every_time(self):
        table, label = index(offline=True)
        self.assertEqual(STARTER, table)
        self.assertIn("starter", label)
        self.assertIn("not the full", label)

    def test_every_resolution_records_which_index_it_searched(self):
        self.assertTrue(resolve("landscaping", offline=True).index)

    def test_a_supplied_table_is_searched_instead(self):
        """So a caller with the real 1,012-entry index is not silently
        answered from the starter set."""
        found = resolve("widgets", table={"999999": "Widget Manufacturing"})
        self.assertTrue(found.certain)
        self.assertEqual("999999", found.code)

    def test_the_thresholds_are_ordered_sensibly(self):
        """The margin required to be certain must not exceed the floor for
        being offered at all, or nothing could ever resolve."""
        self.assertLess(MARGIN, 1.0)
        self.assertGreater(FLOOR, 0.0)


class R8_KnownDistinctions(unittest.TestCase):
    """The resolver has to keep apart industries that sound alike, because
    that is precisely where a silent mis-resolution comes from."""

    CASES = (
        ("landscaping", "561730"),
        ("landscape architecture", "541320"),
        ("dentist", "621210"),
        ("plumber", "238220"),
        ("gym", "713940"),
        ("nail salon", "812113"),
    )

    def test_each_resolves_to_its_own_code(self):
        for phrase, code in self.CASES:
            with self.subTest(phrase=phrase):
                found: Resolution = resolve(phrase, offline=True)
                self.assertTrue(found.certain,
                                f"{phrase!r} was ambiguous: "
                                f"{[str(c) for c in found.candidates]}")
                self.assertEqual(code, found.code)

    def test_landscaping_is_not_landscape_architecture(self):
        """One is a trade with 100,000 establishments; the other is a licensed
        design profession. The words overlap almost entirely."""
        self.assertNotEqual(resolve("landscaping", offline=True).code,
                            resolve("landscape architecture",
                                    offline=True).code)


if __name__ == "__main__":
    unittest.main()


class R9_SectorCodesAreRefused(unittest.TestCase):
    """The most dangerous shape an answer can have: real, sourced, and about
    something other than what was asked.

    "56" is Administrative and Support and Waste Management Services —
    landscaping, security guards, call centres and landfills in one number.
    Every figure computed against it traces to a genuine Census response.
    """

    def test_two_and_three_digit_codes_are_refused(self):
        from marketreport.naics import too_broad

        for code in ("5", "56", "561"):
            with self.subTest(code=code):
                self.assertIn("sector", too_broad(code))

    def test_four_to_six_digit_codes_pass(self):
        from marketreport.naics import too_broad

        for code in ("5617", "56173", "561730"):
            with self.subTest(code=code):
                self.assertEqual("", too_broad(code))

    def test_the_refusal_explains_why_rather_than_just_refusing(self):
        from marketreport.naics import too_broad

        reason = too_broad("56")
        self.assertIn("different market", reason)
        self.assertIn("authoritative", reason)

    def test_it_stops_the_interpretation_before_a_definition_exists(self):
        read = interpret("56", offline=True)
        self.assertFalse(read.ready)
        self.assertIn("sector", read.question)
