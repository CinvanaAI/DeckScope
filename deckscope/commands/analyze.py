"""`deckscope analyze <file>` — the generic front door.

The Intake Analyst's job: read the document, determine what kind of
scrutiny it warrants, and dispatch the vertical that provides it. The
role is performed under the engine's standing law — model proposes, code
disposes:

1. **Deterministic first.** Transparent cue arithmetic over the declared
   verticals (`verticals.classify_document`). A clear winner dispatches
   with the arithmetic shown; a tie or a weak field refuses rather than
   guesses — exactly like the NAICS resolver, and for the same reason: a
   document routed to the wrong vertical produces an internally
   consistent report about the wrong kind of scrutiny.
2. **The analyst consults the model only where arithmetic refused**, and
   the model's answer must name a DECLARED vertical or "none" — an
   undeclared answer is discarded, not obeyed.
3. **No match is an honest outcome**: the refusal names the nearest
   vertical and the explicit command to run it anyway, and `--propose`
   writes a typed declaration draft for a NEW vertical — marked ungraded,
   for the operator to review and register. An unreviewed vertical never
   runs implicitly.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from ..console import out as _out
from ..verticals import Classification, classify_document, get, registered


def _err(msg: str) -> None:
    _out(msg, file=sys.stderr)


INTAKE_SYSTEM = """You are the Intake Analyst for a document-scrutiny \
engine. You are shown the opening of a document and a fixed catalog of \
declared verticals (document types the engine knows how to scrutinize). \
Answer with EXACTLY one catalog name, or the word none. Never invent a \
category: a document that fits nothing declared is 'none', and saying so \
is the correct answer."""


def _consult_model(text: str, provider: Any) -> Optional[str]:
    """The analyst's model consult — validated to the declared catalog."""
    from ..providers.base import Message

    catalog = "\n".join(
        f"- {v.name}: {v.label} — {v.document}"
        for v in registered() if v.intake)
    user = (f"CATALOG:\n{catalog}\n\nDOCUMENT (opening):\n"
            f"<<<BEGIN DOCUMENT\n{text[:6000]}\nEND DOCUMENT>>>\n\n"
            f"One catalog name, or none.")
    try:
        completion = provider.complete(INTAKE_SYSTEM, [Message("user", user)],
                                       max_tokens=20, temperature=0.0)
        answer = (completion.text or "").strip().lower().split()[0].strip(".,")
    except Exception:  # noqa: BLE001 - a failed consult is a non-answer
        return None
    if answer == "none":
        return None
    v = get(answer)
    return v.name if (v is not None and v.intake) else None


_PROPOSAL_TEMPLATE = '''# Vertical proposal — UNGRADED, requires review
#
# `deckscope analyze` could not match this document to a declared
# vertical, and --propose was passed. This is a TYPED DECLARATION DRAFT,
# not a working vertical: fill it in, add it to
# deckscope/verticals/catalog.py, write the coupling tests that pin each
# field to real code, and give it a graded case before trusting a single
# report it produces. Everything it emits before then must carry the
# ungraded notice (graded=False does that).
#
# The engine's law applies unchanged: claims the public evidence can
# check are checked; claims only the author can know become questions;
# a section without evidence says NOT ESTABLISHED.
#
# Nothing runs from a draft: an unreviewed vertical never executes.

from deckscope.verticals import Vertical, register

register(Vertical(
    name="TODO_short_key",
    label="TODO: human name",
    document="TODO: what kind of document this reads",
    cues=(
        # TODO: phrases whose presence votes for this vertical. At least
        # {min_hits} must appear in a typical document (MIN_HITS).
    ),
    claim_types=(
        # TODO: the claim vocabulary. Name the kinds of assertion this
        # document makes.
    ),
    publicly_checkable=(
        # TODO: the subset checkable against evidence OUTSIDE the author,
        # and name where that evidence lives (free, public, reachable).
    ),
    lenses=("TODO",),
    evidence_homes=("search",),
    report_types=(),
    runner="deck_pipeline",
    graded=False,   # stays False until the harness holds a graded case
    intake=True,
))
'''


def command(args: Any) -> int:
    path = Path(args.file)
    if not path.is_file():
        _err(f"Not found: {path}")
        return 2

    from ..ingest.loader import load_deck

    try:
        doc = load_deck(str(path))
    except Exception as exc:  # noqa: BLE001
        _err(f"Could not read {path.name}: {exc}")
        return 2

    forced = (getattr(args, "vertical", None) or "").strip().lower()
    if forced:
        v = get(forced)
        if v is None or not v.intake:
            _err(f"No intake vertical named {forced!r}. Declared: "
                 + ", ".join(x.name for x in registered() if x.intake))
            return 2
        cls = Classification(v, {}, f"forced by --vertical {forced}")
    else:
        cls = classify_document(doc.text)
        if not cls.matched and not getattr(args, "no_model", False):
            # The analyst consults the model only where arithmetic refused.
            provider = _configured_provider(args)
            if provider is not None:
                name = _consult_model(doc.text, provider)
                if name:
                    cls = Classification(
                        get(name), cls.scores,
                        f"cue arithmetic was inconclusive "
                        f"({cls.because}); the intake analyst read the "
                        f"document and classified it as {name} — from the "
                        f"declared catalog only")

    if not cls.matched:
        _out(f"\nNo declared vertical matched {path.name}.")
        _out(f"  {cls.because}")
        if cls.scores:
            shown = ", ".join(f"{k}={v}" for k, v in
                              sorted(cls.scores.items(), key=lambda kv: -kv[1]))
            _out(f"  cue scores: {shown}")
        nearest = max(cls.scores, key=cls.scores.get) if cls.scores else ""
        if nearest and cls.scores[nearest] > 0:
            _out(f"  To run it as {nearest} anyway: deckscope analyze "
                 f"{path.name} --vertical {nearest}")
        if getattr(args, "propose", False):
            from ..verticals import MIN_HITS

            out_dir = Path(getattr(args, "out", None) or "deckscope_output")
            out_dir.mkdir(parents=True, exist_ok=True)
            draft = out_dir / f"{path.stem}_vertical_proposal.py"
            draft.write_text(_PROPOSAL_TEMPLATE.format(min_hits=MIN_HITS),
                             encoding="utf-8")
            _out(f"\nDeclaration draft written: {draft}")
            _out("  Review it, register it in verticals/catalog.py, pin "
                 "it with coupling tests, and grade it before trusting "
                 "its reports. Nothing runs from a draft.")
        else:
            _out("  Or: --propose writes a typed declaration draft for a "
                 "new vertical (reviewed and registered by you — an "
                 "unreviewed vertical never runs).")
        return 7  # the resolver convention: ambiguity refuses, exit 7

    v = cls.vertical
    _out(f"\nIntake: {v.label} — {cls.because}")
    if not v.graded:
        _out("  NOTE: this vertical is UNGRADED — no known-correct case "
             "in the evaluation harness holds its output to an answer "
             "key. Its reports say so too.")

    # -------- dispatch
    if v.runner == "deck_pipeline" and v.name == "deck":
        from ..cli import main as cli_main

        passthrough = ["run", str(path)]
        for flag, attr in (("--provider", "provider"), ("--out", "out")):
            val = getattr(args, attr, None)
            if val:
                passthrough += [flag, str(val)]
        if getattr(args, "nda", False):
            passthrough.append("--nda")
        return cli_main(passthrough)
    if v.runner == "question":
        _err(f"{v.label} is question-driven — use: deckscope report/market")
        return 2
    # Verticals with their own runners register a dispatcher here as they
    # land (grants and nonprofits arrive with theirs).
    from ..verticals.runners import dispatch

    return dispatch(v, path, args)


def _configured_provider(args: Any):
    from .. import settings
    from ..config import load_config
    from ..providers.registry import get_provider

    try:
        if getattr(args, "provider", None):
            cfg = load_config(getattr(args, "config", None))
            cfg.provider.name = args.provider
            return get_provider(cfg.provider)
        if settings.is_configured():
            return get_provider(settings.settings_to_runconfig({}).provider)
    except Exception:  # noqa: BLE001 - no provider is an answer, not a crash
        return None
    return None
