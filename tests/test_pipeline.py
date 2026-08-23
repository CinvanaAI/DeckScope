"""End-to-end: the pipeline must produce every format from a deck, offline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.config import Lens, OutputConfig, ProviderConfig, ResearchConfig, RunConfig
from deckscope.ingest.loader import load_deck
from deckscope.orchestrator import Pipeline
from deckscope.research.base import Researcher, SearchResult
from deckscope.research.registry import register_researcher
from deckscope.schemas import scorecard_total

DECK = Path(__file__).resolve().parent.parent / "examples" / "sample_deck.md"


class StubSearch(Researcher):
    name = "stub"

    def search(self, query, max_results=8):
        return [SearchResult(f"Analyst note: {query[:30]}",
                             f"https://research.example.org/{abs(hash(query)) % 999}",
                             "Serviceable slice $3-5B; category $18-24B; CAGR 15-22%.",
                             "2026-03", query)]


register_researcher(StubSearch)


def _cfg(tmp_path, formats, lenses=("investor",)):
    return RunConfig(
        deck_path=str(DECK), lenses=[Lens.parse(x) for x in lenses],
        provider=ProviderConfig(name="mock"),
        research=ResearchConfig(name="stub", max_queries=2),
        output=OutputConfig(formats=list(formats), out_dir=str(tmp_path)),
        cache_dir=None, verbose=False)


def test_loader_reads_slide_markers():
    doc = load_deck(str(DECK))
    assert doc.n_slides == 10
    assert not doc.is_thin


def _available_formats():
    """Formats whose optional dependency is actually installed.

    The core install has one dependency. Requiring python-docx here made the
    suite fail on exactly the machine the README tells people to use — a minimal
    install — which turned an expected limitation into a red test.
    """
    needs = {"docx": "docx", "pptx": "pptx", "xlsx": "openpyxl", "pdf": "reportlab"}
    available = ["md", "html", "json", "txt"]
    for fmt, module in needs.items():
        try:
            __import__(module)
        except ImportError:
            continue
        available.append(fmt)
    return available


def test_full_pipeline_all_formats(tmp_path):
    formats = _available_formats()
    pipe = Pipeline(_cfg(tmp_path, formats))
    result = pipe.run()
    files = pipe.render(result)
    pipe.close()

    assert result.company == "Acme Flow"
    suffixes = {Path(f).suffix for f in files}
    # These four need nothing beyond the standard library and PyYAML.
    assert suffixes >= {".md", ".html", ".json", ".txt"}
    # Everything the environment CAN produce must have been produced.
    for fmt in formats:
        assert f".{fmt}" in suffixes, f"{fmt} was requested and is installed, but missing"
    for f in files:
        assert Path(f).stat().st_size > 500, f


def test_three_lenses_produce_three_reports(tmp_path):
    pipe = Pipeline(_cfg(tmp_path, ["md"], ("investor", "founder", "neutral")))
    result = pipe.run()
    files = pipe.render(result)
    pipe.close()
    assert set(result.comparisons) == {"investor", "founder", "neutral"}
    assert len([f for f in files if f.endswith(".md")]) == 3


def test_references_are_tracked(tmp_path):
    pipe = Pipeline(_cfg(tmp_path, ["md"]))
    result = pipe.run()
    pipe.render(result)
    pipe.close()

    stats = result.registry.stats()
    assert stats["total"] >= 1
    assert stats["cited"] >= 1, "at least one source should be resolved from source_ids"

    md = Path(next(f for f in result.written_files if f.endswith(".md"))).read_text("utf-8")
    assert "## References" in md
    assert "## Input integrity screen" in md
    for src in result.registry.sources:
        assert src.sid in md, f"{src.sid} missing from the report"


def test_injected_deck_is_neutralized(tmp_path):
    bad = Path(__file__).resolve().parent.parent / "examples" / "sample_deck_with_injection.md"
    cfg = _cfg(tmp_path, ["md"])
    cfg.deck_path = str(bad)
    pipe = Pipeline(cfg)
    result = pipe.run()
    pipe.render(result)
    pipe.close()

    assert result.security["overall_risk"] == "critical"
    md = Path(result.written_files[0]).read_text("utf-8")
    assert "Input integrity screen" in md
    assert "CRITICAL" in md


def test_scorecard_total_is_weighted():
    rows = [{"score": 10, "weight": 5}, {"score": 0, "weight": 5}]
    assert scorecard_total(rows)["score"] == 50.0
    assert scorecard_total([])["score"] == 0.0
