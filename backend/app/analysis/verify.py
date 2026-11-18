"""راستی‌آزمایی شواهد: هر نقل‌قول باید در ترنسکریپت وجود داشته باشد (fuzzy)."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.util import normalize_digits, normalize_fa_text

_PUNCT = re.compile(r"[\s\.,،؛؟!?\"'«»()\-–—…:]+")


def norm(s: str) -> str:
    s = normalize_fa_text(normalize_digits(s)).replace("‌", "")
    return _PUNCT.sub("", s)


def quote_found(quote: str, transcript_text: str, threshold: float = 0.85) -> bool:
    q, t = norm(quote), norm(transcript_text)
    if not q:
        return False
    if q in t:
        return True
    if len(q) > len(t):
        return False
    # پنجره‌ی لغزان با نسبت شباهت
    best = 0.0
    step = max(1, len(q) // 4)
    for i in range(0, max(1, len(t) - len(q) + 1), step):
        for w in (len(q), int(len(q) * 1.15)):
            r = SequenceMatcher(None, q, t[i:i + w]).ratio()
            if r > best:
                best = r
                if best >= threshold:
                    return True
    return best >= threshold


def verify_evidence(result: dict, transcript_text: str, threshold: float = 0.85) -> dict:
    """به هر شاهد verified=true/false اضافه می‌کند و تعداد تأییدنشده‌ها را در warnings می‌آورد."""
    unverified = 0
    total = 0

    def mark(items):
        nonlocal unverified, total
        for it in items or []:
            if isinstance(it, dict) and it.get("quote") is not None:
                total += 1
                ok = quote_found(it["quote"], transcript_text, threshold)
                it["verified"] = ok
                if not ok:
                    unverified += 1

    for c in result.get("criteria", []):
        mark(c.get("evidence"))
    cs = result.get("customer_status", {})
    mark(cs.get("buying_signals"))
    mark(cs.get("objections"))
    mark(result.get("seller_performance", {}).get("compliance_flags"))
    if unverified:
        result.setdefault("warnings", []).append(
            f"{unverified} از {total} نقل‌قول در ترنسکریپت یافت نشد و «تأییدنشده» علامت خورد.")
    return result


def drop_unverified_compliance(result: dict) -> dict:
    """تخلف بدون شاهد معتبر نباید جریمه‌ی خودکار بسازد."""
    sp = result.get("seller_performance", {})
    kept = [f for f in sp.get("compliance_flags", []) if f.get("verified", False)]
    dropped = len(sp.get("compliance_flags", [])) - len(kept)
    sp["compliance_flags"] = kept
    if dropped:
        result.setdefault("warnings", []).append(
            f"{dropped} مورد تخلف احتمالی به‌دلیل نبود شاهد قابل‌تأیید کنار گذاشته شد.")
    return result
