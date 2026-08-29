"""Where the deck disagrees with itself — arithmetic, not opinion.

The cheapest findings in all of diligence are the ones the deck hands over
free: numbers that contradict each other between slides. A SAM larger than
its own TAM, a growth target whose implied monthly rate is half the rate
claimed two slides earlier, an ARR that price × customers cannot reach.
They need no search, no model, and no benefit of the doubt — the deck is
its own source, cited slide against slide — and a founder cannot argue with
them, because both numbers are theirs.

Every check here is deterministic and conservative. The parser recognizes a
narrow set of money/percent/count shapes and refuses everything else, because
a consistency engine that misreads "$774 per unit" as a market total (a
mistake this repository has already paid for once, in the market reports)
would manufacture contradictions instead of finding them. When a check cannot
run, the report says which inputs were missing rather than staying silent —
"could not check" and "checked, consistent" are different facts, and the
reader is owed both.

The output travels inside the deck extraction (`deck["_consistency"]`), which
puts it in front of the comparison model for free — the synthesist can build
questions from a slide-vs-slide conflict — and in front of every renderer.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["check_deck"]

_MONEY = re.compile(
    r"\$\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>billion|million|thousand|bn|[bmk])\b",
    re.I)
_PCT = re.compile(
    r"(?P<num>\d{1,3}(?:\.\d+)?)\s*%\s*(?P<per>MoM|month[- ]over[- ]month|monthly|"
    r"YoY|year[- ]over[- ]year|annual(?:ly)?|CAGR)?", re.I)
_COUNT = re.compile(r"\b(?P<num>\d[\d,]{0,6})\s*(?:paying\s+)?customers?\b", re.I)
_MONTHS = re.compile(r"\b(?P<num>\d{1,3})\s*months?\b", re.I)

_SCALE = {"billion": 1e9, "bn": 1e9, "b": 1e9,
          "million": 1e6, "m": 1e6,
          "thousand": 1e3, "k": 1e3}


def _money(text: Optional[str]) -> Optional[float]:
    """The first dollar amount in `text`, or None.

    Refuses per-unit prices ("$49 per seat") and plain unscaled dollars —
    a figure without B/M/K next to it is more often a price than a market.
    """
    if not text:
        return None
    m = _MONEY.search(text)
    if not m:
        return None
    tail = text[m.end():m.end() + 24].lower()
    if any(w in tail for w in ("per ", "/mo", "/seat", "/user", "a month",
                               "each", "apiece")):
        return None
    return float(m.group("num").replace(",", "")) * _SCALE[m.group("unit").lower()]


def _monthly_pct(text: Optional[str]) -> Optional[float]:
    """A percentage explicitly per month, or None. An annual or unlabelled
    rate is refused — comparing a CAGR against a monthly target is exactly
    the manufactured contradiction this module must never produce."""
    if not text:
        return None
    for m in _PCT.finditer(text):
        per = (m.group("per") or "").lower()
        if per.startswith(("mom", "month")):
            return float(m.group("num"))
    return None


def _count(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = _COUNT.search(text)
    return int(m.group("num").replace(",", "")) if m else None


def _first_months(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = _MONTHS.search(text)
    return int(m.group("num")) if m else None


def _fmt(value: float) -> str:
    for unit, scale in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if value >= scale:
            return f"${value / scale:g}{unit}"
    return f"${value:g}"


def _conflict(check: str, detail: str, arithmetic: str,
              refs: List[str]) -> Dict[str, Any]:
    return {"check": check, "state": "conflict", "detail": detail,
            "arithmetic": arithmetic, "refs": refs}


def _ok(check: str, detail: str) -> Dict[str, Any]:
    return {"check": check, "state": "consistent", "detail": detail}


def _skipped(check: str, missing: str) -> Dict[str, Any]:
    return {"check": check, "state": "not-runnable",
            "detail": f"needs {missing}, which the deck does not state plainly"}


def check_deck(deck: Dict[str, Any]) -> Dict[str, Any]:
    """Run every internal-consistency check the extraction supports.

    Returns {"results": [...], "conflicts": n, "ran": n} — one row per check,
    each either a conflict with its arithmetic shown, a clean pass, or an
    honest "not runnable" naming the missing input.
    """
    market = deck.get("market") or {}
    traction = deck.get("traction") or {}
    model = deck.get("business_model") or {}
    ask = deck.get("ask") or {}
    results: List[Dict[str, Any]] = []

    # ---- 1. TAM ≥ SAM ≥ SOM -------------------------------------------
    tam = _money(market.get("tam_claimed"))
    sam = _money(market.get("sam_claimed"))
    som = _money(market.get("som_claimed"))
    pairs: List[Tuple[str, Optional[float], str, Optional[float]]] = [
        ("TAM", tam, "SAM", sam), ("SAM", sam, "SOM", som),
        ("TAM", tam, "SOM", som)]
    ordering_ran = False
    for big_name, big, small_name, small in pairs:
        if big is None or small is None:
            continue
        ordering_ran = True
        if small > big:
            results.append(_conflict(
                "market-funnel ordering",
                f"the {small_name} is larger than the {big_name} it is "
                f"supposed to be a slice of",
                f"{small_name} {_fmt(small)} > {big_name} {_fmt(big)}",
                [f"{big_name}: {market.get(big_name.lower() + '_claimed')!r}",
                 f"{small_name}: {market.get(small_name.lower() + '_claimed')!r}"]))
    if ordering_ran and not any(r["check"] == "market-funnel ordering"
                                for r in results):
        results.append(_ok("market-funnel ordering",
                           "every stated market slice fits inside the one above it"))
    if not ordering_ran:
        results.append(_skipped("market-funnel ordering",
                                "two of TAM/SAM/SOM as dollar figures"))

    # ---- 2. growth claim vs promised trajectory ------------------------
    # "18% MoM" beside "reach $2M ARR in 18 months" from current revenue:
    # the target implies its own monthly rate. When the two rates disagree
    # materially, one of them is not the plan — and either direction is a
    # finding: a target below the claimed rate means the claimed rate is not
    # expected to hold; above means the plan assumes a step-change nobody
    # has explained.
    claimed_rate = _monthly_pct(traction.get("growth"))
    revenue_now = _money(traction.get("revenue"))
    target_money, target_months = None, None
    for line in (ask.get("milestones_promised") or []):
        money, months = _money(line), _first_months(line)
        if money and months and ("arr" in line.lower()
                                 or "revenue" in line.lower()):
            target_money, target_months, target_line = money, months, line
            break
    if claimed_rate and revenue_now and target_money and target_months:
        if not target_money > revenue_now > 0:
            # A milestone at or below current revenue derives no forward rate —
            # either it is already met or the parse latched onto the wrong
            # figure. Either way the check must SAY so: the first version
            # appended nothing on this branch, and a check that silently
            # vanishes from the results is the exact quiet shortfall this
            # module's own docstring promises never to produce.
            results.append(_skipped(
                "growth vs trajectory",
                "a revenue milestone above current revenue (the stated "
                "milestone is not, so no forward rate can be derived)"))
        else:
            implied = ((target_money / revenue_now) ** (1.0 / target_months)
                       - 1.0) * 100.0
            ratio = max(claimed_rate, implied) / max(min(claimed_rate, implied),
                                                     0.01)
            if ratio >= 1.5:
                direction = ("the plan quietly assumes growth well above the "
                             "rate the deck demonstrates"
                             if implied > claimed_rate else
                             "the deck's own plan does not expect the "
                             "headline growth rate to hold")
                results.append(_conflict(
                    "growth vs trajectory",
                    direction,
                    f"reaching {_fmt(target_money)} from {_fmt(revenue_now)} "
                    f"in {target_months} months implies "
                    f"{implied:.1f}%/month; the deck claims "
                    f"{claimed_rate:g}%/month",
                    [f"growth: {traction.get('growth')!r}",
                     f"milestone: {target_line!r}"]))
            else:
                results.append(_ok(
                    "growth vs trajectory",
                    f"the {_fmt(target_money)} milestone implies "
                    f"{implied:.1f}%/month, in line with the claimed "
                    f"{claimed_rate:g}%/month"))
    else:
        results.append(_skipped(
            "growth vs trajectory",
            "a monthly growth rate, current revenue, and a dated "
            "revenue milestone"))

    # ---- 3. price × customers vs revenue -------------------------------
    acv = _money(model.get("acv_or_arpu"))
    customers = _count(traction.get("customers"))
    if acv is None:
        # ACVs are usually written without B/M/K ("$30k" parses; "$30,000"
        # does not carry a unit) — accept a plain dollar figure here, where
        # a price is what the field means.
        raw = model.get("acv_or_arpu") or ""
        m = re.search(r"\$\s*(\d[\d,]*(?:\.\d+)?)", raw)
        if m and not _MONEY.search(raw):
            acv = float(m.group(1).replace(",", ""))
    if acv and customers and revenue_now:
        implied_rev = acv * customers
        ratio = max(implied_rev, revenue_now) / max(min(implied_rev, revenue_now),
                                                    0.01)
        if ratio >= 1.5:
            results.append(_conflict(
                "price × customers vs revenue",
                "the stated price and customer count cannot produce the "
                "stated revenue",
                f"{customers} customers × {_fmt(acv)} ≈ {_fmt(implied_rev)}, "
                f"but the deck states {_fmt(revenue_now)}",
                [f"pricing: {model.get('acv_or_arpu')!r}",
                 f"customers: {traction.get('customers')!r}",
                 f"revenue: {traction.get('revenue')!r}"]))
        else:
            results.append(_ok(
                "price × customers vs revenue",
                f"{customers} × {_fmt(acv)} ≈ {_fmt(implied_rev)}, consistent "
                f"with the stated {_fmt(revenue_now)}"))
    else:
        results.append(_skipped("price × customers vs revenue",
                                "a price (ACV/ARPU), a customer count, and a "
                                "revenue figure"))

    # ---- 4. LTV/CAC as stated vs as computed ---------------------------
    ltv, cac = _money(model.get("ltv_claimed")), _money(model.get("cac_claimed"))
    if ltv is None:
        raw = model.get("ltv_claimed") or ""
        m = re.search(r"\$\s*(\d[\d,]*(?:\.\d+)?)", raw)
        if m and not _MONEY.search(raw):
            ltv = float(m.group(1).replace(",", ""))
    if cac is None:
        raw = model.get("cac_claimed") or ""
        m = re.search(r"\$\s*(\d[\d,]*(?:\.\d+)?)", raw)
        if m and not _MONEY.search(raw):
            cac = float(m.group(1).replace(",", ""))
    if ltv and cac and cac > 0:
        computed = ltv / cac
        stated = None
        for blob in (model.get("unit_economics"), model.get("ltv_claimed")):
            m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*[x×:]\s*(?:1\b|CAC|LTV)?",
                          blob or "", re.I)
            if m:
                stated = float(m.group(1))
                break
        if stated and max(stated, computed) / max(min(stated, computed),
                                                  0.01) >= 1.5:
            results.append(_conflict(
                "LTV/CAC as stated vs computed",
                "the ratio the deck quotes is not the ratio its own "
                "figures produce",
                f"LTV {_fmt(ltv)} ÷ CAC {_fmt(cac)} = {computed:.1f}×, "
                f"but the deck quotes {stated:g}×",
                [f"LTV: {model.get('ltv_claimed')!r}",
                 f"CAC: {model.get('cac_claimed')!r}",
                 f"unit economics: {model.get('unit_economics')!r}"]))
        elif stated:
            results.append(_ok(
                "LTV/CAC as stated vs computed",
                f"{_fmt(ltv)} ÷ {_fmt(cac)} = {computed:.1f}×, matching the "
                f"quoted {stated:g}×"))
        else:
            results.append(_ok(
                "LTV/CAC as stated vs computed",
                f"the stated figures give {computed:.1f}×; the deck quotes "
                f"no ratio of its own to compare"))
    else:
        results.append(_skipped("LTV/CAC as stated vs computed",
                                "both an LTV and a CAC as dollar figures"))

    return {
        "results": results,
        "conflicts": sum(1 for r in results if r["state"] == "conflict"),
        "ran": sum(1 for r in results if r["state"] != "not-runnable"),
    }
