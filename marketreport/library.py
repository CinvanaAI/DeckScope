"""Where panels live after they are made.

A panel is a record, not a rendering — that is what replaces determinism once a
model is in the loop. This is the part that makes the claim true: panels are
written to disk when they are produced, and read back without re-running
anything.

The consequence a user cares about: a question answered once does not have to be
paid for twice. The consequence that matters more: two people looking at the
same panel see the same panel, forever, and a panel produced in March can be put
beside one produced in August and the difference read off — which is more useful
than determinism, because the market genuinely changes and a report that cannot
change with it is wrong in a quieter way.

Deliberately files and not a database. One JSON file per panel in a directory,
named by a stable id. It can be inspected with `cat`, backed up with `cp`,
deleted with `rm`, and read by anything. A database would buy queries nobody has
asked for and cost the ability to look at the thing.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .panel import Panel

__all__ = ["Library", "PanelRef", "default_dir"]


def default_dir() -> str:
    home = (os.environ.get("DECKSCOPE_HOME")
            or os.path.join(os.path.expanduser("~"), ".deckscope"))
    return os.path.join(home, "panels")


_SAFE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, limit: int = 40) -> str:
    body = _SAFE.sub("-", (text or "").lower()).strip("-")
    return (body[:limit].strip("-") or "panel")


@dataclass
class PanelRef:
    """A panel's entry in the library, without loading the whole thing.

    The listing is built from these so opening a gallery of two hundred panels
    reads two hundred short headers rather than two hundred full records.
    """

    id: str
    question: str = ""
    headline: str = ""
    agent: str = ""
    form: str = ""
    generated: str = ""
    market: str = ""
    place: str = ""
    answered: bool = True
    figures: int = 0
    checkable: int = 0
    sources: List[str] = field(default_factory=list)
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "question": self.question,
                "headline": self.headline, "agent": self.agent,
                "form": self.form, "generated": self.generated,
                "market": self.market, "place": self.place,
                "answered": self.answered, "figures": self.figures,
                "checkable": self.checkable, "sources": list(self.sources)}


class Library:
    """Panels on disk, listed newest first."""

    def __init__(self, directory: Optional[str] = None) -> None:
        self.directory = directory or default_dir()

    # ------------------------------------------------------------- writing
    def _id_for(self, panel: Panel, market: str, place: str) -> str:
        """A stable, readable, collision-resistant id.

        Readable because someone will look at the directory. Stable because the
        same question re-asked should be recognisable as the same question.
        Hashed on the end because two runs of the same question ARE different
        panels — the market moved, or the sources did — and overwriting the
        first would destroy the comparison that makes a re-run worth doing.
        """
        stamp = (panel.generated or "")[:19]
        seed = f"{panel.question}|{panel.agent}|{stamp}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
        name = _slug(f"{market} {place}".strip() or panel.question)
        day = (stamp[:10] or _dt.date.today().isoformat()).replace("-", "")
        return f"{day}-{name}-{digest}"

    def save(self, panel: Panel, *, market: str = "", place: str = "",
             request: str = "") -> PanelRef:
        """Write one panel and return its reference.

        Serialize first, then write via a temp file, then replace — the same
        rule as everywhere else here. A crash mid-write must not leave a file
        with a plausible name that stops in the middle of a key.
        """
        os.makedirs(self.directory, exist_ok=True)
        panel_id = self._id_for(panel, market, place)
        record = {
            "id": panel_id,
            "market": market,
            "place": place,
            "request": request,
            "panel": panel.to_dict(),
        }
        body = json.dumps(record, indent=1, ensure_ascii=False, default=str)
        path = os.path.join(self.directory, f"{panel_id}.json")
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        return self._ref(record, path)

    def save_all(self, panels: List[Panel], *, market: str = "",
                 place: str = "", request: str = "") -> List[PanelRef]:
        return [self.save(p, market=market, place=place, request=request)
                for p in panels]

    # ------------------------------------------------------------- reading
    @staticmethod
    def _ref(record: Dict[str, Any], path: str) -> PanelRef:
        raw = record.get("panel") or {}
        coverage = raw.get("coverage") or {}
        return PanelRef(
            id=str(record.get("id") or ""),
            question=str(raw.get("question") or ""),
            headline=str(raw.get("headline") or ""),
            agent=str(raw.get("agent") or ""),
            form=str(raw.get("form") or ""),
            generated=str(raw.get("generated") or ""),
            market=str(record.get("market") or ""),
            place=str(record.get("place") or ""),
            answered=bool(raw.get("answered")),
            figures=int(coverage.get("figures") or 0),
            checkable=int(coverage.get("checkable") or 0),
            sources=list(raw.get("source_labels") or []),
            path=path)

    def list(self, *, limit: int = 200,
             market: str = "") -> List[PanelRef]:
        """Every stored panel, newest first.

        A file that will not parse is skipped rather than raising. One corrupt
        record must not make the whole gallery unopenable — the failure mode
        that turns "something went wrong once" into "nothing works".
        """
        refs: List[PanelRef] = []
        try:
            names = sorted(os.listdir(self.directory), reverse=True)
        except OSError:
            return []
        for name in names:
            if not name.endswith(".json"):
                continue
            path = os.path.join(self.directory, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    record = json.load(handle)
            except (OSError, ValueError):
                continue
            if not isinstance(record, dict):
                continue
            ref = self._ref(record, path)
            if market and market.lower() not in (
                    f"{ref.market} {ref.question}".lower()):
                continue
            refs.append(ref)
            if len(refs) >= limit:
                break
        refs.sort(key=lambda r: r.generated or "", reverse=True)
        return refs

    def load(self, panel_id: str) -> Optional[Panel]:
        """One panel, rebuilt from its record. Re-runs nothing."""
        safe = _SAFE.sub("-", (panel_id or "").lower()).strip("-")
        if not safe:
            return None
        path = os.path.join(self.directory, f"{safe}.json")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, ValueError):
            return None
        raw = (record or {}).get("panel")
        if not isinstance(raw, dict):
            return None
        return Panel.from_dict(raw)

    def delete(self, panel_id: str) -> bool:
        safe = _SAFE.sub("-", (panel_id or "").lower()).strip("-")
        if not safe:
            return False
        try:
            os.unlink(os.path.join(self.directory, f"{safe}.json"))
            return True
        except OSError:
            return False

    def related(self, panel_id: str) -> List[PanelRef]:
        """Other panels answering the same question, newest first.

        This is the comparison a stored panel exists to make possible: the same
        market asked in March and in August, side by side, so the change is read
        off rather than asserted.
        """
        me = None
        for ref in self.list(limit=1000):
            if ref.id == panel_id:
                me = ref
                break
        if me is None:
            return []
        return [r for r in self.list(limit=1000)
                if r.id != panel_id and r.question == me.question]
