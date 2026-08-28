"""Known-correct cases a market report can be graded against.

`schema` defines what a case is and how one is scored, `suite` holds the cases
themselves, and `runner` produces a real report from a case's recorded pages
and grades what comes out.
"""
from .schema import Case, Expect, Result, Trap, get, register, registered, score

__all__ = ["Case", "Expect", "Trap", "Result", "score", "register", "get",
           "registered"]
