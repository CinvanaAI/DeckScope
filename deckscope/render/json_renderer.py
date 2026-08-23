"""Machine-readable output: the whole run, including the bibliography."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List


def render(result, out_dir: Path, base: str, **kw: Any) -> List[str]:
    p = out_dir / f"{base}_full.json"
    p.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
    return [str(p)]
