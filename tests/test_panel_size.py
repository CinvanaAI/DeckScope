"""How many analysts a panel may have, and what that costs.

The old answer was "at most eight", which came from a hardcoded string of eight
letters running out at "Panelist H" rather than from anything true about panels.
The limit is now the user's budget, stated plainly before they spend it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.config import Lens, OutputConfig, ProviderConfig, ResearchConfig, RunConfig
from deckscope.ensemble import (LARGE_PANEL_ADVISORY, MIN_PANELISTS, Panel,
                                panel_cost_note, panel_labels)


def _cfg():
    return RunConfig(
        deck_path=str(Path(__file__).resolve().parent.parent
                      / "deckscope" / "examples" / "sample_deck.md"),
        lenses=[Lens.parse("investor")], provider=ProviderConfig(name="mock"),
        research=ResearchConfig(name="none"),
        output=OutputConfig(formats=["json"], out_dir="/tmp/_panelsize"),
        cache_dir=None, verbose=False)


def _panel_of(n):
    return Panel(_cfg(), [ProviderConfig(name="mock", model=f"m{i}")
                          for i in range(n)], rounds=0)


# ================================================================ the labels

def test_labels_continue_past_z_instead_of_running_out():
    labels = panel_labels(60)
    assert labels[0] == "Panelist A"
    assert labels[25] == "Panelist Z"
    assert labels[26] == "Panelist AA"
    assert labels[27] == "Panelist AB"
    assert labels[51] == "Panelist AZ"
    assert labels[52] == "Panelist BA"


def test_labels_are_unique_at_any_size():
    for size in (2, 26, 27, 46, 100):
        labels = panel_labels(size)
        assert len(labels) == size
        assert len(set(labels)) == size, f"duplicate labels at size {size}"


# ================================================================ the bounds

def test_a_panel_larger_than_the_alphabet_is_allowed():
    """Twenty-six was never a real constraint, and neither was eight."""
    panel = _panel_of(46)
    labels = [p.label for p in panel.panelists]
    assert len(set(labels)) == 46
    assert labels[-1] == "Panelist AT"


def test_a_large_panel_is_not_refused():
    """It is the user's money. Make the cost legible, do not pick a ceiling."""
    assert _panel_of(30) is not None


def test_two_is_still_the_minimum_because_one_cannot_review_itself():
    try:
        _panel_of(1)
    except ValueError as exc:
        assert "cross-review itself" in str(exc)
        # And it must point at the thing the user should actually run.
        assert "deckscope run" in str(exc)
    else:
        raise AssertionError("a panel of one should not be constructible")
    assert MIN_PANELISTS == 2


# ================================================================== the cost

def test_the_cost_note_separates_call_count_from_token_growth():
    """Calls scale linearly at roughly six per panelist; tokens scale with the
    square, because each review call carries every peer's analysis inside it.
    Conflating the two overstates a big panel by an order of magnitude."""
    note = panel_cost_note(46)
    assert "276 API calls" in note, note
    assert "2070 peer readings" in note, note
    # The readings are inside the 46 review calls, not 2070 separate requests.
    assert "inside the 46 review calls" in note


def test_a_large_panel_gets_advice_rather_than_a_refusal():
    assert "rounds 0" in panel_cost_note(LARGE_PANEL_ADVISORY + 1)
    assert "rounds 0" not in panel_cost_note(3)


def test_call_count_really_is_linear_in_panel_size():
    """Pins the claim the cost note makes, against the actual call count."""
    import deckscope.providers.mock_provider as mock
    from deckscope.corpus import EvidenceCorpus

    corpus = EvidenceCorpus.load(
        str(Path(__file__).resolve().parent.parent
            / "deckscope" / "examples" / "sample_corpus.json"))
    counted = {"n": 0}
    original = mock.MockProvider.complete

    def spy(self, system, messages, **kw):
        counted["n"] += 1
        return original(self, system, messages, **kw)

    mock.MockProvider.complete = spy
    try:
        seen = {}
        for size in (2, 4):
            counted["n"] = 0
            panel = Panel(_cfg(), [ProviderConfig(name="mock", model=f"m{i}")
                                   for i in range(size)], rounds=1)
            panel.run(corpus=corpus)
            seen[size] = counted["n"]
    finally:
        mock.MockProvider.complete = original

    # Doubling the panel roughly doubles the calls. Quadratic growth would be 4x.
    ratio = seen[4] / seen[2]
    assert 1.6 < ratio < 2.6, f"calls grew {ratio:.1f}x when the panel doubled: {seen}"


# =========================================== one model is a run, not an error

def test_one_selected_model_is_reshaped_into_a_run_not_refused():
    """Selecting a single model is reasonable; it is just not a panel. Refusing
    it would be pedantry dressed as validation."""
    from deckscope.cli import _as_run_args, build_parser

    args = build_parser().parse_args(["panel", "deck.md", "--quiet"])
    run_args = _as_run_args(args, "anthropic:claude-sonnet-5")

    assert run_args.provider == "anthropic"
    assert run_args.model == "claude-sonnet-5"
    assert run_args.deck == "deck.md"
    # Every flag `run` reads must be present, or delegation dies on the first
    # one it touches.
    for required in ("dilution", "exit_multiple", "horizon", "opportunity",
                     "corpus", "save_corpus", "cold_discovery", "mode",
                     "max_queries"):
        assert hasattr(run_args, required), f"missing {required}"


def test_a_bare_provider_with_no_model_still_reshapes():
    from deckscope.cli import _as_run_args, build_parser

    args = build_parser().parse_args(["panel", "deck.md"])
    run_args = _as_run_args(args, "mock")
    assert run_args.provider == "mock"
    assert run_args.model is None
