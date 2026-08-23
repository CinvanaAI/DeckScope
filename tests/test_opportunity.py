"""Opportunity-cost arithmetic, market-data lookup, and absorption reporting.

The arithmetic here is the part most likely to be trusted without checking, so it
is tested against figures worked by hand rather than against its own output.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.opportunity import (Assumptions, ComparableReturn, build_comparison,
                                   parse_growth, parse_money, parse_percent,
                                   required_outcome)

DECK = Path(__file__).resolve().parent.parent / "deckscope" / "examples" / "sample_deck.md"


# ==================================================================== parsing

def test_money_parsing_handles_what_decks_actually_write():
    assert parse_money("$4M") == 4_000_000
    assert parse_money("$24M post") == 24_000_000
    assert parse_money("$340k ARR") == 340_000
    assert parse_money("$1.2B") == 1_200_000_000
    assert parse_money("4,500,000") == 4_500_000
    assert parse_money("no figure here") is None
    assert parse_money(None) is None


def test_percent_parsing_returns_a_fraction():
    assert parse_percent("18% MoM") == 0.18
    assert parse_percent("23% CAGR") == 0.23
    assert parse_percent("nothing") is None


# ================================================================ arithmetic

def test_required_outcome_matches_hand_calculation():
    """$4M on $24M post, 50% dilution, 1x preference, 6x revenue, targeting 3x.

        entry ownership   = 4 / 24            = 16.67%
        at exit           = 16.67% x 0.5      =  8.33%
        proceeds needed   = 4M x 3            = 12M
        preference (senior, paid first)       =  4M
        exit value        = 4M + 12M / 0.0833 = 148M
        implied ARR       = 148M / 6          = 24.67M

    This test previously asserted $192M, from `(proceeds + preference) / ownership`.
    That divides the preference by ownership as though the investor had to fund the
    whole stack out of its own slice. A senior preference comes off the top of the
    exit and the residual is then split, so it adds its face value, not its face
    value grossed up 12x. The old expectation was wrong in the same direction as
    the old code, which is how it survived.
    """
    r = required_outcome(ask=4_000_000, post_money=24_000_000, target_multiple=3.0,
                         assumptions=Assumptions(), current_arr=340_000)
    assert round(r.entry_ownership, 4) == 0.1667
    assert round(r.ownership_at_exit, 4) == 0.0833
    assert abs(r.exit_value_required - 148_000_000) < 100_000
    assert abs(r.implied_arr_required - 24_666_667) < 20_000
    assert r.growth_multiple_required == round(24_666_667 / 340_000, 1)


def test_the_waterfall_actually_returns_the_proceeds_it_promises():
    """The inverse check: ownership x (exit - preference) must equal proceeds.

    This is the property the formula exists to satisfy, and stating it directly
    means no future refactor can reintroduce a plausible-looking variant that
    happens not to balance.
    """
    ask, target = 4_000_000.0, 3.0
    a = Assumptions()
    r = required_outcome(ask=ask, post_money=24_000_000, target_multiple=target,
                         assumptions=a)
    residual = r.exit_value_required - r.preference_stack_value
    investor_proceeds = r.ownership_at_exit * residual
    assert abs(investor_proceeds - ask * target) < 20_000, (
        f"investor receives ${investor_proceeds:,.0f} but needed ${ask * target:,.0f}")


def test_a_bigger_preference_stack_adds_its_face_value_not_a_multiple_of_it():
    """Doubling a 1x stack to 2x on a $4M round adds $4M to the required exit."""
    one = required_outcome(ask=4e6, post_money=24e6, target_multiple=3.0,
                           assumptions=Assumptions(preference_stack=1.0))
    two = required_outcome(ask=4e6, post_money=24e6, target_multiple=3.0,
                           assumptions=Assumptions(preference_stack=2.0))
    delta = two.exit_value_required - one.exit_value_required
    assert abs(delta - 4_000_000) < 1_000, (
        f"an extra $4M of senior preference moved the required exit by ${delta:,.0f}")


def test_higher_dilution_demands_a_bigger_exit():
    low = required_outcome(ask=4e6, post_money=24e6, target_multiple=3.0,
                           assumptions=Assumptions(future_dilution=0.3))
    high = required_outcome(ask=4e6, post_money=24e6, target_multiple=3.0,
                            assumptions=Assumptions(future_dilution=0.7))
    assert high.exit_value_required > low.exit_value_required


def test_a_richer_exit_multiple_lowers_the_revenue_needed():
    lean = required_outcome(ask=4e6, post_money=24e6, target_multiple=3.0,
                            assumptions=Assumptions(exit_revenue_multiple=4.0))
    rich = required_outcome(ask=4e6, post_money=24e6, target_multiple=3.0,
                            assumptions=Assumptions(exit_revenue_multiple=10.0))
    assert rich.implied_arr_required < lean.implied_arr_required
    # The exit VALUE is unchanged — only the revenue implied by it moves.
    assert abs(rich.exit_value_required - lean.exit_value_required) < 1


def test_missing_ask_reports_rather_than_guesses():
    r = required_outcome(ask=None, post_money=24e6, target_multiple=3.0,
                         assumptions=Assumptions())
    assert r.exit_value_required is None
    assert "does not state" in r.note


def test_growth_extrapolation_is_explicitly_caveated():
    """A monthly rate extrapolated for five years is not a schedule."""
    r = required_outcome(ask=4e6, post_money=24e6, target_multiple=3.0,
                         assumptions=Assumptions(), current_arr=340_000,
                         current_growth=parse_growth("18% MoM"))
    assert r.years_at_current_growth is not None
    assert "never does" in r.note and "not a timetable" in r.note


# =============================================================== comparison

def _comps():
    return [
        ComparableReturn(name="Microsoft", ticker="MSFT", total_return_5y=2.4,
                         source_ids=["S3"]),
        ComparableReturn(name="UiPath", ticker="PATH", total_return_5y=0.6,
                         source_ids=["S4"]),
        ComparableReturn(name="Zapier", note="privately held"),
    ]


def test_comparison_benchmarks_against_each_listed_competitor():
    c = build_comparison(company="Acme", ask=4e6, post_money=24e6,
                         current_arr=340_000, current_growth=parse_growth("18% MoM"),
                         comparables=_comps())
    assert any("Microsoft" in k for k in c.requirements)
    assert any("UiPath" in k for k in c.requirements)
    assert any("3x" in k for k in c.requirements), "the fixed reference must remain"
    # A competitor that underperformed is a LOWER bar, and the maths must show it.
    msft = next(v for k, v in c.requirements.items() if "Microsoft" in k)
    path = next(v for k, v in c.requirements.items() if "UiPath" in k)
    assert path.exit_value_required < msft.exit_value_required


def test_private_competitors_are_not_treated_as_benchmarks():
    c = build_comparison(company="Acme", ask=4e6, post_money=24e6, current_arr=None,
                         current_growth=None, comparables=_comps())
    assert not any("Zapier" in k for k in c.requirements)


def test_no_listed_competitors_says_so_rather_than_going_quiet():
    c = build_comparison(company="Acme", ask=4e6, post_money=24e6, current_arr=None,
                         current_growth=None,
                         comparables=[ComparableReturn(name="Zapier")])
    assert c.unavailable
    assert "None of the named competitors appear to be publicly traded" \
        in c.unavailable[0]


def test_the_output_never_claims_to_be_a_forecast():
    c = build_comparison(company="Acme", ask=4e6, post_money=24e6, current_arr=340_000,
                         current_growth=None, comparables=_comps())
    payload = c.to_dict()
    assert "not a forecast" in payload["disclaimer"]
    assert "Not investment advice" in payload["disclaimer"]
    assert "would need to reach" in c.headline or "would need to exit" in c.headline
    blob = str(payload).lower()
    for banned in ("expected return", "projected return", "you will", "we expect"):
        assert banned not in blob, f"the output must not predict: {banned!r}"


# ============================================================== market data

def test_search_backend_rejects_a_ticker_that_is_really_prose():
    from deckscope.market_data.search_backend import _clean_ticker, _multiple

    assert _clean_ticker("MSFT") == "MSFT"
    assert _clean_ticker("$PATH") == "PATH"
    assert _clean_ticker("not publicly traded") is None
    assert _clean_ticker("") is None
    # A percentage that was never converted would wreck the arithmetic.
    assert _multiple(240) is None
    assert _multiple(2.4) == 2.4


def test_none_backend_says_unknown_not_no():
    from deckscope.market_data.registry import get_market_data

    listing = get_market_data("none").lookup("Microsoft")
    assert listing.ticker is None
    assert "unknown — not 'no'" in listing.note


def test_market_data_auto_falls_back_when_there_is_no_research():
    from deckscope.market_data.registry import get_market_data

    assert get_market_data("auto", researcher=None).name == "none"


# ================================================================ end to end

def test_opportunity_pass_runs_and_drops_uncited_base_rates(tmp_path):
    from deckscope.config import (OpportunityConfig, OutputConfig, ProviderConfig,
                                  ResearchConfig, RunConfig)
    from deckscope.orchestrator import Pipeline
    from deckscope.research.base import Researcher, SearchResult
    from deckscope.research.registry import register_researcher

    class Stub(Researcher):
        name = "stub_opportunity"

        def search(self, query, max_results=8):
            # Names the incumbents explicitly: the market agent derives its
            # competitor list from the evidence, so a lookup can only happen for
            # companies the sources actually mention.
            return [SearchResult(
                "Note", "https://example.org/1",
                "Mid-market slice $3-5B. Microsoft Power Automate bundles this "
                "into E5, and UiPath is the incumbent RPA vendor. Zapier remains "
                "privately held.", "2026-03", query)]

    register_researcher(Stub)

    cfg = RunConfig(deck_path=str(DECK), provider=ProviderConfig(name="mock"),
                    research=ResearchConfig(name="stub_opportunity", max_queries=1),
                    opportunity=OpportunityConfig(enabled=True),
                    output=OutputConfig(formats=["md"], out_dir=str(tmp_path)),
                    cache_dir=None, verbose=False)
    pipe = Pipeline(cfg)
    result = pipe.run()
    pipe.render(result)
    pipe.close()

    opp = result.opportunity
    assert opp and not opp.get("error")
    listed = [c for c in opp["comparables"] if c["investable"]]
    assert len(listed) >= 1, "the mock lists MSFT and PATH"
    # The mock supplies three rates, one of them uncited.
    assert len(opp["base_rates"]) == 2
    assert all(r["source_ids"] for r in opp["base_rates"])

    text = Path(result.written_files[0]).read_text(encoding="utf-8")
    assert "## Compared to what?" in text
    assert "not a forecast" in text
    assert "The assumptions every number above rests on" in text


def test_opportunity_pass_is_off_by_default(tmp_path):
    from deckscope.config import (OutputConfig, ProviderConfig, ResearchConfig,
                                  RunConfig)
    from deckscope.orchestrator import Pipeline

    cfg = RunConfig(deck_path=str(DECK), provider=ProviderConfig(name="mock"),
                    research=ResearchConfig(name="none"),
                    output=OutputConfig(formats=["md"], out_dir=str(tmp_path)),
                    cache_dir=None, verbose=False)
    pipe = Pipeline(cfg)
    result = pipe.run()
    pipe.close()
    assert result.opportunity == {}


def test_a_failing_opportunity_pass_does_not_end_the_run(tmp_path):
    """It is an optional extra; it must never cost you the analysis."""
    from deckscope.config import (OpportunityConfig, OutputConfig, ProviderConfig,
                                  ResearchConfig, RunConfig)
    from deckscope.orchestrator import Pipeline

    cfg = RunConfig(deck_path=str(DECK), provider=ProviderConfig(name="mock"),
                    research=ResearchConfig(name="none"),
                    opportunity=OpportunityConfig(enabled=True,
                                                  market_data="does_not_exist"),
                    output=OutputConfig(formats=["md"], out_dir=str(tmp_path)),
                    cache_dir=None, verbose=False)
    pipe = Pipeline(cfg)
    result = pipe.run()
    pipe.close()
    assert result.comparisons, "the analysis itself must still be there"
    assert "error" in result.opportunity
