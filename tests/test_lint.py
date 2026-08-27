"""The linter is checked the way it checks everything else.

A checker with no tests reported 119 problems of which 118 were its own, and
that is the failure mode worth guarding: not that it misses something, but that
it is loud and wrong, because a noisy checker gets ignored on the day it is
right. Each test below is one of the false positives it actually produced.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import lint  # noqa: E402 - the path has to be set up first


class L1_NoFalsePositives(unittest.TestCase):

    def _check(self, source: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.py"
            path.write_text(source, encoding="utf-8")
            return [message for _, _, message in lint.check(path)]

    def test_a_format_spec_is_not_a_placeholder_free_fstring(self):
        """`f"{x:.1f}"` — reported twice by the first two versions."""
        self.assertEqual([], self._check('x = 1.0\ny = f"{x:.1f}"\n'))

    def test_a_thousands_separator_spec_is_not_either(self):
        self.assertEqual([], self._check('n = 1\ns = f"HHI {n:,.0f}"\n'))

    def test_a_future_import_is_not_unused(self):
        self.assertEqual([], self._check("from __future__ import annotations\n"))

    def test_a_name_in_dunder_all_is_used(self):
        self.assertEqual(
            [], self._check("from os import getcwd\n__all__ = ['getcwd']\n"))

    def test_noqa_suppresses_the_line(self):
        self.assertEqual(
            [], self._check("import os  # noqa: F401 - side effects\n"))

    def test_an_attribute_chain_counts_as_a_use(self):
        self.assertEqual([], self._check("import os\nos.path.join('a', 'b')\n"))


class L2_StillCatchesTheRealThing(unittest.TestCase):
    """The point of removing the noise is that the signal survives it."""

    def _messages(self, source: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.py"
            path.write_text(source, encoding="utf-8")
            return " ".join(m for _, _, m in lint.check(path))

    def test_a_genuinely_unused_import(self):
        self.assertIn("unused import: json", self._messages("import json\n"))

    def test_a_genuinely_empty_fstring(self):
        self.assertIn("nothing to interpolate", self._messages('s = f"hello"\n'))

    def test_a_bare_except(self):
        self.assertIn("bare except",
                      self._messages("try:\n    pass\nexcept:\n    pass\n"))

    def test_a_mutable_default(self):
        self.assertIn("mutable default",
                      self._messages("def f(items=[]):\n    return items\n"))

    def test_an_assert_outside_tests(self):
        """The MCP transport used one for type narrowing. `python -O` strips
        it, and the line after it then raised AttributeError on None."""
        self.assertIn("python -O", self._messages("def f(x):\n    assert x\n"))

    def test_a_syntax_error_is_reported_not_raised(self):
        self.assertIn("syntax error", self._messages("def (\n"))


class L3_TheRepositoryIsClean(unittest.TestCase):

    def test_no_problems_anywhere(self):
        problems = []
        for path in lint._sources():
            problems.extend(lint.check(path))
        self.assertEqual(
            [], [f"{p.relative_to(lint.ROOT)}:{n}: {m}" for p, n, m in problems])


if __name__ == "__main__":
    unittest.main()
