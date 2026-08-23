"""Detects text written for the AI rather than for a human reader.

Two independent signals are used, because either alone produces false positives:
  1. *Intent* — imperative language aimed at a model ("ignore previous instructions",
     "you are now", "output only", "score this 10/10").
  2. *Concealment* — invisible characters, homoglyphs, fake role delimiters, encoded
     payloads. Concealment is what separates an injection from a founder simply
     writing the word "instructions" on a slide.

A finding's severity rises when both signals appear in the same span.
"""
from __future__ import annotations

import base64
import re
import unicodedata
from typing import Dict, List, Tuple

from .report import Finding, ScanReport

# ---------------------------------------------------------------- character sets

#: Zero-width, bidi-override, and other characters with no legitimate place in a deck.
INVISIBLE_CHARS = {
    "​": "zero-width space", "‌": "zero-width non-joiner",
    "‍": "zero-width joiner", "⁠": "word joiner",
    "﻿": "zero-width no-break space", "­": "soft hyphen",
    "᠎": "Mongolian vowel separator",
    "‪": "bidi LTR embedding", "‫": "bidi RTL embedding",
    "‬": "bidi pop directional", "‭": "bidi LTR override",
    "‮": "bidi RTL override", "⁦": "bidi LTR isolate",
    "⁧": "bidi RTL isolate", "⁨": "bidi first-strong isolate",
    "⁩": "bidi pop isolate",
}

#: Unicode "tag" block — invisible by design, used to smuggle whole prompts.
TAG_BLOCK = range(0xE0000, 0xE0080)

#: Common lookalikes used to slip past keyword filters.
HOMOGLYPHS: Dict[str, str] = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
    "і": "i", "ѕ": "s", "ԁ": "d", "ɡ": "g", "ⅼ": "l", "ᴏ": "o", "һ": "h",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Χ": "X", "Υ": "Y",
    "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "К": "K", "М": "M",
    "О": "O", "Р": "P", "Т": "T", "Х": "X",
}

# ---------------------------------------------------------------- patterns

def _p(rx: str) -> re.Pattern:
    return re.compile(rx, re.I)


#: (pattern, code, severity, human explanation)
INTENT_PATTERNS: List[Tuple[re.Pattern, str, str, str]] = [
    # Two forms, because the object of the verb decides how suspicious it is.
    # "ignore your instructions" needs no qualifier to be an attack; "override
    # rules" without one is ordinary language for a rules-engine company, so that
    # form still requires previous/prior/above/all.
    (_p(r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b"
        r"(instructions?|prompts?|system[- ]?prompts?)\b"),
     "override_instruction", "critical",
     "Text instructing the AI to ignore its instructions."),

    (_p(r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b"
        r"(previous|prior|above|earlier|all|your)\b[^.\n]{0,30}\b"
        r"(direction|rule|system|context|guideline|constraint)"),
     "override_instruction", "critical",
     "Text instructing the AI to disregard the rules it operates under."),

    (_p(r"\b(you are now|from now on,? you|act as|pretend (to be|you)|"
        r"roleplay as|new persona|assume the role)\b"),
     "role_hijack", "critical",
     "Text attempting to reassign the AI's role or persona."),

    (_p(r"(^|\n)\s*(system|assistant|developer|human|user)\s*[:>\]]\s"),
     "fake_role_marker", "high",
     "Fake conversation-role markers, used to make injected text look like a system message."),

    (_p(r"(\[/?(INST|SYS|SYSTEM|s)\]|<\|(im_start|im_end|system|endoftext|"
        r"start_header_id|eot_id)\|>|###\s*(Instruction|System)\b|<system>)"),
     "delimiter_spoof", "critical",
     "Chat-template control tokens embedded in document text."),

    (_p(r"\b(do not|don'?t|never)\b[^.\n]{0,30}\b"
        r"(mention|report|reveal|disclose|tell|show|include|flag|warn)\b"
        r"[^.\n]{0,40}\b(this|these|instruction|text|note|user|human|analyst)"),
     "conceal_directive", "critical",
     "Text telling the AI to hide something from the person reading the report."),

    (_p(r"\b(rate|score|grade|rank|evaluate)\b[^.\n]{0,30}"
        r"(10/10|100%|perfect|highest|maximum|top score|as (excellent|outstanding))"),
     "score_manipulation", "critical",
     "Text attempting to dictate the score this analysis produces."),

    (_p(r"\b(recommend|conclude|state|say|write|output|report)\b[^.\n]{0,40}\b"
        r"(invest|strong buy|fund (this|them)|highly recommend|no risks?|"
        r"no concerns?|excellent opportunity)\b"),
     "verdict_manipulation", "critical",
     "Text attempting to dictate the verdict this analysis produces."),

    (_p(r"\b(output|respond|reply|answer|return)\b[^.\n]{0,25}\b"
        r"(only|exactly|verbatim|nothing else|with the following)\b"),
     "output_control", "high",
     "Text attempting to control the format or content of the AI's output."),

    (_p(r"\b(prompt|system prompt|instructions?|configuration|api[_ ]?key|"
        r"secret|credential)\b[^.\n]{0,30}\b(reveal|print|show|repeat|dump|leak|"
        r"disclose|what (are|were))\b"),
     "exfiltration", "critical",
     "Text attempting to extract the AI's own instructions or credentials."),

    (_p(r"\b(send|post|upload|transmit|email|fetch|curl|GET|POST)\b[^.\n]{0,40}"
        r"(https?://|www\.)"),
     "exfil_channel", "high",
     "Text instructing the AI to send data to an external address."),

    (_p(r"\b(this is (a|an) (test|authorized|approved)|"
        r"(developer|admin|security) (mode|override|note)|"
        r"you have permission to|bypass (the )?(safety|filter|guard))\b"),
     "authority_spoof", "high",
     "Text falsely claiming special authority or permission."),

    (_p(r"\bDAN\b|\bjailbreak\b|\bunrestricted mode\b|\bno (ethical )?guidelines\b"),
     "jailbreak_lexicon", "high",
     "Known jailbreak vocabulary."),

    (_p(r"\b(AI|assistant|model|language model|LLM|GPT|Claude|Gemini|analyst bot)\b"
        r"[^.\n]{0,25}\b(reading|analyzing|processing|evaluating) (this|the deck)"),
     "ai_addressed", "medium",
     "Text addressed to an AI reader rather than a human one."),

    (_p(r"<<<\s*(BEGIN|END)[^>]{0,60}>>>"
        r"|</?(untrusted|document|deck|research|source|data)[ _-]?(content|material|"
        r"block|begin|end)?>"
        r"|--- ?(BEGIN|END) (DECK|RESEARCH)"),
     "fence_break", "critical",
     "Text mimicking DeckScope's own content delimiters, to escape the data block."),
]

CONCEALMENT_CODES = {"invisible_text", "tag_block", "homoglyph", "delimiter_spoof",
                     "fence_break", "encoded_payload", "invisible_render"}

#: Applied ONLY to decoded content. There is no legitimate reason to base64-encode
#: a sentence inside a pitch deck, so the act of encoding is itself the
#: concealment signal and the language bar can be far lower than it is for text a
#: human might actually have written on a slide.
ENCODED_INTENT = [
    _p(r"\b(ignore|disregard|forget|override|bypass|skip)\b"),
    _p(r"\b(you are|you're|act as|pretend|roleplay|behave as)\b"),
    _p(r"\b(rate|score|grade|rank)\b[^.\n]{0,20}\b(\d{1,3}|perfect|highest|max)"),
    _p(r"\b(recommend|approve|endorse|conclude|say|state|output|reply|respond)\b"),
    _p(r"\b(do not|don'?t|never)\b[^.\n]{0,25}\b(mention|reveal|tell|show|report)\b"),
    _p(r"\b(system|assistant|user|developer)\s*[:>]"),
    _p(r"\b(instruction|prompt|directive|command)s?\b"),
]

#: Candidate encoded runs. The length bar is deliberately low — 12 characters of
#: base64 is 9 bytes, and "rate 10/10" fits in 10.
#:
#: A length threshold was the wrong mechanism to begin with. It was 80, then 32,
#: and both let real payloads through: "ignore instructions" encodes to 28
#: characters, "you are now a promoter" to 32 including padding the regex did not
#: count. What actually separates a payload from noise is not its length but
#: whether it decodes to readable text that gives the model an order — so the
#: length bar is now only a cheap pre-filter and the decode does the real work.
#:
#: Both the standard and URL-safe alphabets, since either survives a copy-paste.
B64 = re.compile(r"[A-Za-z0-9+/_-]{12,}={0,2}")


def _excerpt(text: str, start: int, end: int, pad: int = 60) -> str:
    """A short, defanged sample. Newlines flattened so it can't reformat the report."""
    s = max(0, start - pad)
    e = min(len(text), end + pad)
    frag = text[s:e].replace("\n", " ⏎ ").replace("`", "'")
    frag = "".join(ch if ch.isprintable() else "·" for ch in frag)
    return ("…" if s else "") + frag.strip()[:280] + ("…" if e < len(text) else "")


#: How close a concealment signal must be to an intent match to count as
#: "the same span". Document-global correlation produced false escalations:
#: one zero-width space in a footer should not upgrade every later sentence.
CONCEAL_PROXIMITY_CHARS = 400


def _conceal_spans(text: str) -> List[Tuple[int, int]]:
    """Character ranges where concealment was detected, for proximity checks."""
    spans: List[Tuple[int, int]] = []
    for i, ch in enumerate(text):
        if ch in INVISIBLE_CHARS or ord(ch) in TAG_BLOCK or ch in HOMOGLYPHS:
            spans.append((max(0, i - CONCEAL_PROXIMITY_CHARS),
                          i + CONCEAL_PROXIMITY_CHARS))
    if not spans:
        return []
    spans.sort()
    merged = [spans[0]]
    for a, b in spans[1:]:
        if a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def scan_text(text: str, where: str = "text") -> ScanReport:
    """Find injection signals in a block of text. Never modifies the input."""
    rep = ScanReport(target=where)
    rep.scanned_chars = len(text or "")
    if not text:
        return rep

    concealed = False

    # --- concealment: invisible characters
    found_invis: Dict[str, int] = {}
    for ch, label in INVISIBLE_CHARS.items():
        n = text.count(ch)
        if n:
            found_invis[label] = n
    if found_invis:
        concealed = True
        rep.add(Finding(
            code="invisible_text", severity="high", where=where,
            detail=("Invisible control characters present ("
                    + ", ".join(f"{n}× {lbl}" for lbl, n in found_invis.items())
                    + "). These are not produced by normal authoring and are a common "
                      "way to hide instructions inside visible text."),
            action="stripped"))

    tag_chars = [c for c in text if ord(c) in TAG_BLOCK]
    if tag_chars:
        concealed = True
        decoded = "".join(chr(ord(c) - 0xE0000) for c in tag_chars if 0xE0020 <= ord(c) <= 0xE007E)
        rep.add(Finding(
            code="tag_block", severity="critical", where=where,
            detail=(f"{len(tag_chars)} Unicode tag characters found — an invisible "
                    f"channel with no legitimate use in a document."),
            excerpt=f"decodes to: {decoded[:200]!r}" if decoded else "",
            action="stripped"))

    # --- concealment: homoglyphs mixed into Latin words
    homo = [c for c in text if c in HOMOGLYPHS]
    if len(homo) >= 3 and _mixed_script_words(text):
        concealed = True
        rep.add(Finding(
            code="homoglyph", severity="medium", where=where,
            detail=(f"{len(homo)} Cyrillic/Greek characters appear inside otherwise "
                    f"Latin words — typically used to evade keyword detection."),
            excerpt=", ".join(sorted(set(homo))[:12]), action="stripped"))

    # --- concealment: encoded blobs that decode to instructions
    for m in B64.finditer(text):
        for decoded in _decode_candidates(m.group(0)):
            if len(decoded) < 8:
                continue
            printable = sum(c.isprintable() or c in "\n\t" for c in decoded)
            if printable / len(decoded) < 0.85:
                continue
            hits = [c for rx, c, _, _ in INTENT_PATTERNS if rx.search(decoded)]
            if not hits and any(rx.search(decoded) for rx in ENCODED_INTENT):
                hits = ["encoded imperative"]
            if not hits:
                continue
            concealed = True
            rep.add(Finding(
                code="encoded_payload", severity="critical", where=where,
                detail=("An encoded blob decodes to text containing AI instructions "
                        f"({', '.join(hits[:3])}). Encoding is not a legitimate way "
                        f"to put words in a pitch deck."),
                excerpt=decoded[:200], action="redacted",
                span=(m.start(), m.end())))
            break

    # --- intent patterns
    conceal_spans = _conceal_spans(text) if concealed else []
    for rx, code, severity, detail in INTENT_PATTERNS:
        for m in rx.finditer(text):
            sev = severity
            # Escalate only when the concealment is near THIS match, not merely
            # somewhere in the same document.
            near = any(a <= m.start() <= b for a, b in conceal_spans)
            if near and severity in ("medium", "high"):
                sev = {"medium": "high", "high": "critical"}[severity]
            rep.add(Finding(
                code=code, severity=sev, where=where, detail=detail
                + (" It sits inside deliberately concealed text." if near else ""),
                excerpt=_excerpt(text, m.start(), m.end()),
                action="redacted" if sev in ("critical", "high") else "flagged",
                span=(m.start(), m.end())))
            break  # one finding per pattern keeps the report readable

    return rep


def _decode_candidates(blob: str) -> List[str]:
    """Every plausible decoding of a candidate run.

    Tries the standard and URL-safe alphabets, and each of the three possible
    padding lengths, because a payload lifted out of a document often arrives
    with its padding stripped.
    """
    out: List[str] = []
    cleaned = blob.rstrip("=")
    for alphabet in (str.maketrans("", ""), str.maketrans("-_", "+/")):
        candidate = cleaned.translate(alphabet)
        for pad in range(3):
            try:
                raw = base64.b64decode(candidate + "=" * pad, validate=False)
            except Exception:  # noqa: BLE001
                continue
            try:
                out.append(raw.decode("utf-8"))
            except UnicodeDecodeError:
                continue
    return out


def _mixed_script_words(text: str) -> bool:
    """True if any single word mixes Latin with Cyrillic/Greek — the homoglyph tell."""
    for word in re.findall(r"\w{3,}", text):
        scripts = set()
        for ch in word:
            if not ch.isalpha():
                continue
            try:
                name = unicodedata.name(ch).split()[0]
            except ValueError:
                continue
            if name in ("LATIN", "CYRILLIC", "GREEK"):
                scripts.add(name)
        if len(scripts) > 1:
            return True
    return False
