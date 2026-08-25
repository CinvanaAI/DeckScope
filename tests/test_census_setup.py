"""The Census key path: validation, storage, and retrieval.

An onboarding flow that saves a credential the product then cannot read is worse
than no onboarding flow at all — the user does the work, sees a success message,
and the first real run still fails. That is the specific bug these cover.

  C1  a key saved by the wizard is found by the sizing backend
  C2  the environment beats the saved file, so an override works
  C3  a malformed key is rejected at the prompt, not on first use
  C4  a valid-looking key is accepted
  C5  with no key, the backend refuses and says how to fix it
  C6  the refusal names the free signup URL, not just the variable
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path

from deckscope import settings
from deckscope.wizard import CENSUS_ENV, CENSUS_SIGNUP, _census_key_problem
from marketreport.sources.census import Unavailable, establishment_count

VALID = "a" * 40


class KeyValidation(unittest.TestCase):

    def test_a_short_key_is_rejected_with_its_length(self):
        """C3 — caught here, or it fails silently on the first real run."""
        problem = _census_key_problem("abc123")
        self.assertIn("40 characters", problem)
        self.assertIn("6", problem)

    def test_a_key_with_punctuation_is_rejected(self):
        problem = _census_key_problem("a" * 39 + "-")
        self.assertIn("letters and numbers", problem)

    def test_a_key_with_a_trailing_newline_is_accepted_after_stripping(self):
        """Pasting from an email brings whitespace with it."""
        self.assertEqual("", _census_key_problem(VALID + "\n"))

    def test_a_valid_key_is_accepted(self):
        self.assertEqual("", _census_key_problem(VALID))

    def test_the_signup_url_is_the_official_one(self):
        self.assertTrue(CENSUS_SIGNUP.startswith("https://api.census.gov/"))


class KeyStorageRoundTrip(unittest.TestCase):
    """C1/C2 — the wizard writes here; the backend must read from there."""

    def setUp(self):
        self._home = os.environ.get("DECKSCOPE_HOME")
        self._key = os.environ.pop(CENSUS_ENV, None)
        self._tmp = Path(__file__).parent / "_tmp_census_home"
        self._tmp.mkdir(parents=True, exist_ok=True)
        os.environ["DECKSCOPE_HOME"] = str(self._tmp)

    def tearDown(self):
        import shutil
        os.environ.pop(CENSUS_ENV, None)
        if self._home is None:
            os.environ.pop("DECKSCOPE_HOME", None)
        else:
            os.environ["DECKSCOPE_HOME"] = self._home
        if self._key is not None:
            os.environ[CENSUS_ENV] = self._key
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_a_saved_key_is_visible_to_has_key(self):
        settings.save_key(CENSUS_ENV, VALID)
        self.assertTrue(settings.has_key(CENSUS_ENV))

    def test_a_saved_key_survives_being_dropped_from_the_environment(self):
        """C1 — the exact bug. The wizard saves it, the process forgets it,
        and the backend must still find it on the next run."""
        settings.save_key(CENSUS_ENV, VALID)
        os.environ.pop(CENSUS_ENV, None)
        recovered = settings.load_env(into_environ=False).get(CENSUS_ENV)
        self.assertEqual(VALID, recovered)

    def test_the_environment_wins_over_the_saved_file(self):
        """C2 — so a user can override without editing the key store."""
        settings.save_key(CENSUS_ENV, VALID)
        os.environ[CENSUS_ENV] = "b" * 40
        settings.load_env(into_environ=True)
        self.assertEqual("b" * 40, os.environ[CENSUS_ENV])


class RefusalWithoutAKey(unittest.TestCase):

    def setUp(self):
        self._home = os.environ.get("DECKSCOPE_HOME")
        self._key = os.environ.pop(CENSUS_ENV, None)
        os.environ["DECKSCOPE_HOME"] = str(
            Path(__file__).parent / "_tmp_census_empty")

    def tearDown(self):
        if self._home is None:
            os.environ.pop("DECKSCOPE_HOME", None)
        else:
            os.environ["DECKSCOPE_HOME"] = self._home
        if self._key is not None:
            os.environ[CENSUS_ENV] = self._key

    def test_the_backend_refuses_rather_than_guessing(self):
        """C5 — never a plausible substitute."""
        with self.assertRaises(Unavailable):
            establishment_count("561730")

    def test_the_refusal_tells_the_user_how_to_fix_it(self):
        """C6 — 'unavailable' with no remedy trains people to ignore it."""
        try:
            establishment_count("561730")
        except Unavailable as exc:
            message = str(exc)
        self.assertIn("api.census.gov", message)
        self.assertIn("free", message.lower())
        self.assertIn("deckscope setup", message.lower())

    def test_a_bad_industry_code_is_refused_before_the_key_is_even_needed(self):
        """A 2-digit code is a whole sector and would look authoritative."""
        with self.assertRaises(Unavailable) as ctx:
            establishment_count("56")
        self.assertIn("sector", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
