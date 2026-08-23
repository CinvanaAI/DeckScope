"""Plain text, for email bodies and terminals."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List

from .markdown_renderer import build_markdown


def markdown_to_text(md: str) -> str:
    out = []
    for line in md.split("\n"):
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            out.append("  " + "  ·  ".join(cells))
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", line)
        line = line.replace("**", "").replace("`", "")
        line = re.sub(r"</?details>|</?summary>", "", line)
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def render(result, out_dir: Path, base: str, **kw: Any) -> List[str]:
    paths = []
    for lens in result.comparisons:
        p = out_dir / f"{base}_{lens}.txt"
        p.write_text(markdown_to_text(build_markdown(result, lens)), encoding="utf-8")
        paths.append(str(p))
    return paths
