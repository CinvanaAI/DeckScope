"""Typed vertical declarations: the coupling tests that make drift a
suite failure, plus the intake's arithmetic and its refusals.
"""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.verticals import (MIN_HITS, classify_document, get,
                                 registered)

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------- declarations match code

def test_deck_lenses_are_exactly_the_lens_enum():
    from deckscope.config import Lens

    deck = get("deck")
    assert set(deck.lenses) == {lens.value for lens in Lens}, (
        "the declaration DESCRIBES the engine; a lens added to either "
        "side alone is drift")


def test_deck_claim_types_are_exactly_the_extraction_schemas():
    src = (ROOT / "deckscope" / "schemas.py").read_text(encoding="utf-8")
    m = re.search(r'"type":\s*"([a-z|-]+)"', src)
    assert m, "extraction claim-type alternation not found in schemas.py"
    schema_types = set(m.group(1).split("|"))
    assert set(get("deck").claim_types) == schema_types


def test_deck_publicly_checkable_is_exactly_the_scopers_set():
    from marketreport.scoping import PUBLICLY_CHECKABLE

    assert set(get("deck").publicly_checkable) == set(PUBLICLY_CHECKABLE), (
        "one truth: which claims the public evidence can check lives in "
        "the scoper, and the declaration mirrors it")


def test_declared_report_types_exist_in_the_report_registry():
    src = (ROOT / "marketreport" / "reports.py").read_text(encoding="utf-8")
    real = set(re.findall(r'^    key="([a-z-]+)"', src, re.M))
    for v in registered():
        missing = set(v.report_types) - real
        assert not missing, (
            f"{v.name} declares report types that do not exist: {missing}")


def test_graded_flags_tell_the_truth():
    # deck: the eval harness exists (deckscope/evaluation with cases).
    assert (ROOT / "deckscope" / "evaluation").is_dir()
    assert get("deck").graded
    # market: marketreport/cases holds the graded suite.
    assert (ROOT / "marketreport" / "cases" / "suite.py").is_file()
    assert get("market").graded


# ------------------------------------------------------------- the intake

_DECK_TEXT = """Acme Flow — Series A. We are raising $4M at a $16M
pre-money. TAM of $47B, strong traction: $600K ARR, zero churn. Use of
funds: 60% engineering. Our go-to-market is product-led."""


def test_a_deck_classifies_as_a_deck_by_arithmetic_alone():
    cls = classify_document(_DECK_TEXT)
    assert cls.matched and cls.vertical.name == "deck"
    assert cls.scores["deck"] >= MIN_HITS
    assert "cue match" in cls.because, "the arithmetic is shown, not vibes"


def test_an_unrelated_document_refuses_with_its_arithmetic_shown():
    cls = classify_document("Milk, eggs, bread, coffee. Back by noon.")
    assert not cls.matched
    assert "no declared vertical" in cls.because or "cue match" in cls.because


def test_a_tie_refuses_rather_than_guessing(monkeypatch):
    import deckscope.verticals as V

    a = V.Vertical(name="aaa", label="A", document="d",
                   cues=("alpha", "beta", "gamma"), intake=True)
    b = V.Vertical(name="bbb", label="B", document="d",
                   cues=("alpha", "beta", "gamma"), intake=True)
    monkeypatch.setattr(V, "_REGISTRY", {"aaa": a, "bbb": b})
    monkeypatch.setattr(V, "_LOADED", True)
    cls = V.classify_document("alpha beta gamma")
    assert not cls.matched
    assert "tie" in cls.because


def test_the_market_vertical_never_claims_a_document():
    assert get("market").intake is False
    cls = classify_document(_DECK_TEXT)
    assert "market" not in cls.scores


# --------------------------------------------------- the analyze command

def _args(**kw):
    base = dict(file="", vertical=None, propose=False, no_model=True,
                provider=None, config=None, out=None, nda=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_analyze_refuses_an_unmatched_document_with_exit_7(tmp_path):
    from deckscope.commands.analyze import command

    doc = tmp_path / "list.txt"
    doc.write_text("Milk, eggs, bread, coffee.", encoding="utf-8")
    assert command(_args(file=str(doc))) == 7, (
        "the resolver convention: ambiguity refuses, exit 7")


def test_analyze_propose_writes_an_ungraded_typed_draft(tmp_path):
    from deckscope.commands.analyze import command

    doc = tmp_path / "memo.txt"
    doc.write_text("A quarterly facilities memo about parking.",
                   encoding="utf-8")
    rc = command(_args(file=str(doc), propose=True, out=str(tmp_path)))
    assert rc == 7
    draft = tmp_path / "memo_vertical_proposal.py"
    text = draft.read_text(encoding="utf-8")
    assert "graded=False" in text
    assert "UNGRADED" in text
    assert "Nothing runs from a draft" in text or \
           "never runs" in text.lower() or "unreviewed" in text.lower()


def test_analyze_forced_vertical_must_be_declared(tmp_path):
    from deckscope.commands.analyze import command

    doc = tmp_path / "x.txt"
    doc.write_text("anything", encoding="utf-8")
    assert command(_args(file=str(doc), vertical="astrology")) == 2


def test_model_consult_only_accepts_declared_names():
    from deckscope.commands.analyze import _consult_model

    class _P:
        def complete(self, *a, **k):
            return types.SimpleNamespace(text="astrology")

    assert _consult_model("some doc", _P()) is None, (
        "an undeclared answer is discarded, not obeyed")

    class _P2:
        def complete(self, *a, **k):
            return types.SimpleNamespace(text="deck")

    assert _consult_model("some doc", _P2()) == "deck"


def test_unknown_runner_refuses_with_the_remedy_named(tmp_path):
    from deckscope.verticals import Vertical
    from deckscope.verticals.runners import dispatch

    ghost = Vertical(name="ghost", label="Ghost", document="d",
                     runner="does_not_exist")
    rc = dispatch(ghost, tmp_path / "x.txt", types.SimpleNamespace())
    assert rc == 2
