from deckscope.orchestrator import AnalysisResult
from deckscope.render.html_renderer import build_html


def test_mock_report_identifies_fixture_before_findings():
    for provider in ("mock", "MOCK"):
        result = AnalysisResult(
            deck={"company": {"name": "Synthetic Example"}},
            comparisons={"investor": {}},
            stats={"provider": provider},
        )
        rendered = build_html(result, "investor")
        body = rendered[rendered.index("<body>"):]
        assert 'data-demo="mock"' in body
        assert "Synthetic demonstration — mock provider" in body
        assert "fixture-generated analysis" in body
        assert body.index('data-demo="mock"') < body.index('<div class="headline">')


def test_non_mock_report_is_not_mislabeled_synthetic():
    for provider in ("ollama", "anthropic", ""):
        result = AnalysisResult(
            deck={"company": {"name": "Example"}},
            comparisons={"investor": {}},
            stats={"provider": provider},
        )
        assert 'data-demo="mock"' not in build_html(result, "investor")
