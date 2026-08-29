"""The consolidated findings layer, and the hierarchy it drives.

The headline is composed in Python from counts, never written by a model, so it
can be tested exactly. These tests pin the properties that make it trustworthy:
it never claims evidence it does not have, it never converts an absence of
evidence into a negative finding, and it says the same thing in every format.
"""
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckscope.findings import collect


class FakeRegistry:
    def __init__(self, total=0, cited=0):
        self._total, self._cited = total, cited

    def stats(self):
        return {"total": self._total, "cited": self._cited,
                "consulted_uncited": 0, "quarantined": 0, "omitted_for_length": 0}


def _claim(claim, assessment, quality="strong", sources=("S1",), **kw):
    row = {"id": kw.get("id", "C1"), "claim": claim, "assessment": assessment,
           "evidence_quality": quality, "source_ids": list(sources),
           "delta": kw.get("delta", ""), "so_what": kw.get("so_what", "")}
    return row


def _comparison(claims=(), blind_spots=(), questions=(), actions=()):
    return {"claim_audit": list(claims),
            "alignment": {"blind_spots": list(blind_spots)},
            "questions": list(questions),
            "actions": list(actions)}


# =========================================== never assert evidence we don't have

def test_a_run_with_no_sources_never_says_the_evidence_contests_anything():
    """The headline exists to stop the report overclaiming. Its own first job is
    not to overclaim: with zero sources retrieved, nothing was tested."""
    comp = _comparison(
        claims=[_claim("TAM is $47B", "contradicted", sources=[])],
        blind_spots=["Microsoft Power Automate ships inside E5"])
    found = collect(comp, FakeRegistry(total=0))

    assert found.evidence_too_thin
    assert found.evidence_reason == "none_retrieved"
    assert "No external evidence was retrieved" in found.headline
    assert "contradicted by cited evidence" not in found.headline
    assert "questions" in found.headline


def test_sources_retrieved_but_never_cited_says_so_precisely():
    """Different failure, different sentence. Claiming "no evidence was
    retrieved" when three sources came back is itself a false statement."""
    comp = _comparison(
        claims=[_claim("TAM is $47B", "contradicted", sources=[])],
        blind_spots=["An incumbent the deck omits"])
    found = collect(comp, FakeRegistry(total=3, cited=1))

    assert found.evidence_too_thin
    assert found.evidence_reason == "none_cited"
    assert "Evidence was retrieved" in found.headline
    assert "No external evidence was retrieved" not in found.headline


def test_an_uncited_contradiction_is_never_described_as_sourced():
    """`evidence_quality` is the model's own opinion; `source_ids` is checkable.
    When they disagree the checkable field wins, or a model could assert
    "strong" evidence, cite nothing, and have the report dress its unsupported
    disagreement up as a sourced finding."""
    comp = _comparison(claims=[
        _claim("TAM is $47B", "contradicted", quality="strong", sources=[])])
    found = collect(comp, FakeRegistry(total=5, cited=2))

    assert found.contested[0].severity == "low"
    assert not found.contested[0].is_citable


def test_a_cited_contradiction_keeps_its_severity():
    comp = _comparison(claims=[
        _claim("TAM is $47B", "contradicted", quality="strong", sources=["S1"])])
    found = collect(comp, FakeRegistry(total=5, cited=2))

    assert found.contested[0].severity == "high"
    assert found.contested[0].is_citable


# ======================== an absence of evidence is not a negative finding

def test_unverifiable_claims_become_next_steps_not_strikes():
    """A deck with six unverifiable claims and no contradictions is a research
    problem. Rendering them alongside contradictions let the analysis quietly
    convert its own ignorance into a signal against the company."""
    comp = _comparison(claims=[
        _claim(f"Claim {i}", "unverifiable", quality="none", sources=[], id=f"C{i}")
        for i in range(6)])
    found = collect(comp, FakeRegistry(total=8, cited=3))

    assert found.counts["contested"] == 0
    assert found.counts["unverified"] == 6
    assert len(found.next_steps) >= 6
    assert "could be confirmed or refuted" in found.headline
    assert found.headline.startswith("None of the deck's")
    # And the trailing clause starts a new sentence, so it capitalises.
    assert "Six questions to resolve" in found.headline


def test_a_clean_deck_is_not_reported_as_a_pass():
    """An absence of contradictions is not proof, and the headline must not let
    a reader take it as one."""
    comp = _comparison(claims=[
        _claim(f"Claim {i}", "supported", sources=["S1"], id=f"C{i}")
        for i in range(4)])
    found = collect(comp, FakeRegistry(total=9, cited=4))

    assert found.counts["contested"] == 0
    assert "not proof" in found.headline
    assert "PASS" not in found.headline.upper()


# ============================================ the counts drive the sentence

def test_the_headline_counts_match_the_findings_exactly():
    comp = _comparison(
        claims=[_claim("A", "contradicted", sources=["S1"], id="C1",
                       delta="deck says $47B; evidence says $3-5B"),
                _claim("B", "contradicted", sources=["S2"], id="C2"),
                _claim("C", "supported", sources=["S3"], id="C3")],
        blind_spots=["An omitted incumbent"],
        questions=["What is net revenue retention?"])
    found = collect(comp, FakeRegistry(total=10, cited=3))

    assert found.counts["contested"] == 2
    assert "Two claims are contradicted" in found.headline
    assert found.counts["holds"] == 1
    # The delta is the specific half; the semicolon is its pivot and must survive.
    assert "$47B" in found.headline


def test_counts_are_spelled_and_do_not_capitalise_mid_sentence():
    comp = _comparison(
        claims=[_claim("A", "contradicted", sources=[], id="C1")],
        blind_spots=["One gap", "Another gap"])
    found = collect(comp, FakeRegistry(total=0))
    # "and Two apparent gaps" would be wrong; so would "and 2 apparent gaps".
    assert "two apparent gaps" in found.headline
    assert " Two " not in found.headline


def test_findings_are_ordered_worst_and_best_evidenced_first():
    comp = _comparison(claims=[
        _claim("weak", "contradicted", quality="none", sources=[], id="C1"),
        _claim("strong", "contradicted", quality="strong", sources=["S1"], id="C2"),
        _claim("moderate", "partially-supported", quality="moderate",
               sources=["S2"], id="C3")])
    found = collect(comp, FakeRegistry(total=6, cited=3))
    assert found.contested[0].text == "strong", "best-evidenced must lead"


def test_next_steps_put_p0_actions_before_questions():
    comp = _comparison(
        claims=[],
        questions=["A question"],
        actions=[{"action": "Do the P1 thing", "priority": "P1", "owner": "x"},
                 {"action": "Do the P0 thing", "priority": "P0", "owner": "y"}])
    found = collect(comp, FakeRegistry(total=4, cited=2))
    assert found.next_steps[0] == "Do the P0 thing"
    assert found.next_steps[1] == "Do the P1 thing"
    assert "A question" in found.next_steps


def test_an_empty_comparison_does_not_crash_or_invent():
    found = collect({}, None)
    assert found.headline
    assert found.counts["claims_examined"] == 0
    assert not found.contested and not found.omissions


def test_malformed_rows_are_skipped_rather_than_crashing():
    comp = {"claim_audit": ["not a dict", None, 42,
                            _claim("real", "contradicted", sources=["S1"])]}
    found = collect(comp, FakeRegistry(total=3, cited=1))
    assert found.counts["contested"] == 1


# ================================================= the report hierarchy

def _demo(fmts, out):
    import subprocess
    root = Path(__file__).resolve().parent.parent
    subprocess.run([sys.executable, "-m", "deckscope", "demo",
                    "--format", *fmts, "--out", out],
                   cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return root


def test_the_report_leads_with_findings_not_a_verdict(tmp_path):
    out = str(tmp_path / "r")
    _demo(["md"], out)
    text = Path(next(Path(out).glob("*.md"))).read_text(encoding="utf-8")
    head = text[:1200]

    assert "LEAN NO" not in head, "the verdict must not be the first thing read"
    assert "45.7" not in head and "Weighted score" not in text, (
        "the composite score must not appear above the fold — it is the one "
        "figure in the report that cannot be traced to a source")

    order = [text.index(h) for h in (
        "## What the deck leaves out", "## What to do next",
        "## What this adds up to, for this lens", "## Scorecard")]
    assert order == sorted(order), "findings must precede the verdict and scorecard"


def test_every_format_leads_with_the_same_sentence(tmp_path):
    out = str(tmp_path / "r")
    _demo(["md", "html", "docx"], out)
    md = Path(next(Path(out).glob("*.md"))).read_text(encoding="utf-8")
    html = Path(next(Path(out).glob("*.html"))).read_text(encoding="utf-8")
    docx = re.sub(r"<[^>]+>", "", zipfile.ZipFile(
        next(Path(out).glob("*.docx"))).read("word/document.xml").decode("utf-8"))

    headline = [ln for ln in md.splitlines() if ln.startswith("> **")][0]
    key = headline.strip("> *")[:60]
    assert key in html, "HTML headline drifted from markdown"
    assert key in docx, "DOCX headline drifted from markdown"

    # Count headings, not raw occurrences: the HTML table of contents links to
    # every section by name, and a nav entry is not a duplicate section.
    headings = {
        "md": re.findall(r"^## (.+)$", md, re.M),
        "html": re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S),
        "docx": re.findall(r"What to do next", docx),
    }
    assert headings["md"].count("What to do next") == 1, "md repeats the section"
    assert sum(1 for h in headings["html"] if "What to do next" in h) == 1, \
        "html repeats the section"
    assert len(headings["docx"]) == 1, "docx repeats the section"

    for name, doc in (("md", md), ("html", html), ("docx", docx)):
        assert "What the evidence contests" in doc, f"{name} missing findings"


def test_the_scorecard_survives_but_says_why_there_is_no_total(tmp_path):
    """Per-dimension scores are traceable and stay. Only the composite goes."""
    out = str(tmp_path / "r")
    _demo(["md"], out)
    text = Path(next(Path(out).glob("*.md"))).read_text(encoding="utf-8")
    assert "## Scorecard" in text
    assert "| Dimension | Score | Weight | Why |" in text
    assert "cannot be traced to a source" in text
