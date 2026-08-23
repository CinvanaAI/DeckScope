"""The two screening entry points the pipeline calls, plus web-source checks."""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, List, Tuple

from ..ingest.loader import DeckDocument
from .forensics import scan_file
from .policy import Mode, SecurityPolicy
from .report import Finding, ScanReport, SecurityAbort
from .sanitizer import fence, sanitize
from .text_scanner import scan_text


# ====================================================================== deck

def screen_deck(doc: DeckDocument, policy: SecurityPolicy,
                deck_path: str | None = None) -> Tuple[DeckDocument, ScanReport]:
    """Screen a loaded deck before a single token reaches the model.

    Runs three passes: file forensics (what rendering hid), text scanning (what the
    words say), and sanitization (what gets removed). Returns the cleaned document
    and the report.
    """
    report = ScanReport(target="pitch deck")
    if not policy.enabled:
        return doc, report

    # 1. forensics on the original file — recovers what extraction flattened
    if policy.scan_deck_forensics and deck_path:
        report.extend(scan_file(deck_path, policy))

    # 2. scan the extracted text itself
    report.extend(scan_text(doc.text, "deck text"))
    report.scanned_items = max(report.scanned_items, doc.n_slides)
    report.scanned_chars = len(doc.text)

    # 3. abort or clean
    for f in report.findings:
        if policy.should_abort(f.severity):
            raise SecurityAbort(report)

    cleaned = sanitize(doc.text, policy, report, "deck text")
    doc.text = fence(cleaned, "PITCH DECK CONTENT")
    if report.findings:
        doc.warnings.append(report.summary_line())
    return doc, report


# =============================================================== web sources

SUSPICIOUS_TLDS = {".zip", ".mov", ".xyz", ".top", ".click", ".rest", ".cfd"}
URL_SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd",
                  "buff.ly", "rebrand.ly", "cutt.ly", "shorturl.at"}


def screen_sources(results: List[Any], policy: SecurityPolicy) -> Tuple[List[Any], ScanReport]:
    """Screen every search result before the market agent reads it.

    Web pages are the softer target: anyone can publish a page that a search engine
    indexes, and an attacker who guesses the queries a deck will trigger can seed
    content designed to be retrieved. Each result is scanned, sanitized, length-capped,
    and fenced with its own provenance.
    """
    report = ScanReport(target="web sources")
    if not policy.enabled or not policy.scan_web_sources:
        return results, report

    kept: List[Any] = []
    for i, r in enumerate(results, 1):
        domain = _domain(getattr(r, "url", "") or "")
        where = f"source {i} ({domain or 'no URL'})"
        report.scanned_items += 1

        if domain and any(domain == d or domain.endswith("." + d)
                          for d in policy.block_untrusted_domains):
            report.add(Finding("blocked_domain", "high", where,
                               f"{domain} is on your blocklist; the result was dropped.",
                               action="quarantined"))
            continue

        report.extend(_scan_url(getattr(r, "url", "") or "", where))

        body = f"{getattr(r, 'title', '')}\n{getattr(r, 'snippet', '')}"
        sub = scan_text(body, where)
        report.extend(sub)
        report.scanned_chars += len(body)

        critical = [f for f in sub.findings if f.severity == "critical"]
        if critical:
            if policy.mode is Mode.STRICT:
                raise SecurityAbort(report)
            report.add(Finding(
                "source_quarantined", "critical", where,
                f"This page contains text aimed at the AI reading it "
                f"({', '.join(sorted({f.code for f in critical}))}). The result was "
                f"dropped rather than sanitized — a source that behaves this way is not "
                f"trustworthy evidence.",
                excerpt=(getattr(r, "url", "") or "")[:120], action="quarantined"))
            continue

        r.title = sanitize(str(getattr(r, "title", "") or ""), policy, report, where)
        snippet = sanitize(str(getattr(r, "snippet", "") or ""), policy, report, where)
        if len(snippet) > policy.max_source_chars:
            snippet = snippet[:policy.max_source_chars] + "\n[truncated by DeckScope]"
        r.snippet = snippet
        kept.append(r)

    dropped = report.scanned_items - len(kept)
    if dropped:
        report.add(Finding("sources_dropped", "info", "web sources",
                           f"{dropped} of {report.scanned_items} sources were dropped as "
                           f"untrustworthy. The market analysis was built from the "
                           f"remaining {len(kept)}.", action="quarantined"))
    return kept, report


def _scan_url(url: str, where: str) -> ScanReport:
    rep = ScanReport(target=where)
    if not url:
        return rep
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:  # noqa: BLE001
        return rep

    host = (parsed.hostname or "").lower()

    if parsed.scheme in ("data", "javascript", "file"):
        rep.add(Finding("dangerous_scheme", "high", where,
                        f"Result uses a `{parsed.scheme}:` URL rather than http(s).",
                        excerpt=url[:120], action="quarantined"))
    if "@" in (parsed.netloc or ""):
        rep.add(Finding("url_userinfo", "medium", where,
                        "URL embeds credentials before the host — a classic way to make "
                        "a hostile domain look like a trusted one.",
                        excerpt=url[:120]))
    if host.startswith("xn--") or "xn--" in host:
        rep.add(Finding("punycode_domain", "medium", where,
                        f"Domain `{host}` is punycode-encoded and may be imitating a "
                        f"well-known site.", excerpt=url[:120]))
    if host in URL_SHORTENERS:
        rep.add(Finding("shortened_url", "low", where,
                        f"`{host}` hides the real destination.", excerpt=url[:120]))
    if any(host.endswith(t) for t in SUSPICIOUS_TLDS):
        rep.add(Finding("suspicious_tld", "low", where,
                        f"Uncommon TLD on `{host}`; weigh this source accordingly.",
                        excerpt=url[:120]))
    if len(url) > 400:
        rep.add(Finding("overlong_url", "low", where,
                        "Unusually long URL — sometimes used to carry a payload.",
                        excerpt=url[:120]))
    return rep


def _domain(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""
