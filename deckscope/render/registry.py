"""Output-format registry. Adding a format is one `register_renderer()` call."""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, Dict, List

#: fmt -> (module path, human description)
_BUILTIN = {
    "md":    (".markdown_renderer", "Markdown report — the canonical text"),
    "html":  (".html_renderer", "Self-contained web page, prints cleanly"),
    "pdf":   (".pdf_renderer", "Print-ready PDF"),
    "docx":  (".docx_renderer", "Word document"),
    "pptx":  (".pptx_renderer", "Summary slide deck"),
    "xlsx":  (".xlsx_renderer", "Spreadsheet: scorecard, claims, references, security"),
    "json":  (".json_renderer", "Machine-readable, everything including the bibliography"),
    "txt":   (".text_renderer", "Plain text for email and terminals"),
    "memo": (".memo_renderer",
             "One-page IC deal memo — the verdict, the claims that decide "
             "it, the read, the questions"),
    "fixit": (".fixit_renderer",
              "Founder fix-it list — what a skeptical fund will find, "
              "worst first, with the evidence they'll be holding"),
    "questions": (".questions_renderer",
                  "Question pack — the founder-meeting agenda, each question "
                  "with the gap that produced it and the standard its answer "
                  "should meet"),
}

_ALIASES = {"ic": "memo", "founder": "fixit", "agenda": "questions", "markdown": "md", "word": "docx", "powerpoint": "pptx", "slides": "pptx",
            "excel": "xlsx", "spreadsheet": "xlsx", "web": "html", "text": "txt"}

_CUSTOM: Dict[str, Callable[..., List[str]]] = {}


def register_renderer(fmt: str, fn: Callable[..., List[str]],
                      description: str = "") -> None:
    """Register a renderer: fn(result, out_dir: Path, base: str, **kw) -> [paths]."""
    _CUSTOM[fmt.strip().lower()] = fn
    if description:
        DESCRIPTIONS[fmt.strip().lower()] = description


DESCRIPTIONS: Dict[str, str] = {k: v[1] for k, v in _BUILTIN.items()}


def list_formats() -> List[str]:
    return sorted(set(_BUILTIN) | set(_CUSTOM))


def resolve(fmt: str) -> str:
    f = (fmt or "").strip().lower().lstrip(".")
    return _ALIASES.get(f, f)


def render(fmt: str, result: Any, out_dir: Path, base: str, **kw: Any) -> List[str]:
    f = resolve(fmt)
    if f in _CUSTOM:
        return _CUSTOM[f](result, Path(out_dir), base, **kw)
    if f not in _BUILTIN:
        raise ValueError(f"Unknown output format {fmt!r}. "
                         f"Available: {', '.join(list_formats())}")
    mod = importlib.import_module(_BUILTIN[f][0], __package__)
    return mod.render(result, Path(out_dir), base, **kw)
