"""Measuring whether the analysis is any good, against planted ground truth."""
from .cases import (EmptySuiteError, EvalCase, Expectations, default_suite_dir,
                    load_case, load_suite)
from .runner import DIMENSIONS, SuiteResult, run_suite, save
from .scoring import CaseScore, Check, score_case

__all__ = ["EmptySuiteError", "EvalCase", "Expectations", "load_case", "load_suite",
           "default_suite_dir", "SuiteResult", "run_suite", "save", "DIMENSIONS",
           "CaseScore", "Check", "score_case"]
