"""متریک‌های محاسبه‌شده از ترنسکریپت diarized (راهنمای مدل، نه قضاوت)."""
from __future__ import annotations

import re

from app.stt.base import Segment
from app.stt.nonspeech import IVR, LABEL_FA, SPECIAL
from app.util import mmss


def _words(t: str) -> int:
    return len(t.split())


def _count(patterns: list[str], text: str) -> int:
    return sum(len(re.findall(re.escape(p), text)) for p in patterns)


def compute_metrics(segments: list[Segment], seller: str | None, lex: dict, customer_name: str | None = None) -> dict:
    segments = [s for s in segments if s.speaker not in SPECIAL]  # موسیقی/تلفن گویا گفتگوی انسانی نیست
    if not seller or not any(s.speaker for s in segments):
        return {"available": False, "reason": "تفکیک گوینده در دسترس نیست"}
    sel = [s for s in segments if s.speaker == seller]
    cus = [s for s in segments if s.speaker and s.speaker != seller]
    st = sum(s.end - s.start for s in sel)
    ct = sum(s.end - s.start for s in cus)
    segs = sorted(segments, key=lambda s: s.start)
    interrupts = 0
    for a, b in zip(segs, segs[1:]):
        if a.speaker and b.speaker and a.speaker != b.speaker and b.start < a.end - 0.2 and b.speaker == seller:
            interrupts += 1
    # طولانی‌ترین مونولوگ: segmentهای پیاپی فروشنده
    longest = cur = 0.0
    for s in segs:
        if s.speaker == seller:
            cur += s.end - s.start
            longest = max(longest, cur)
        else:
            cur = 0.0
    # تأخیر پاسخ بعد از سؤال مشتری
    lat = []
    for a, b in zip(segs, segs[1:]):
        if a.speaker and a.speaker != seller and b.speaker == seller and re.search(r"[؟?]\s*$", a.text.strip()):
            lat.append(max(0.0, b.start - a.end))
    seller_text = " ".join(s.text for s in sel)
    wpm = _words(seller_text) / (st / 60) if st > 1 else None
    price = next((s.start for s in segs if s.speaker == seller and re.search(r"قیمت|تومان|هزینه|ریال", s.text)), None)
    name_cnt = seller_text.count(customer_name) if customer_name else None
    return {
        "available": True,
        "talk_ratio_seller_vs_customer": round(st / ct, 2) if ct > 0 else None,
        "seller_talk_seconds": round(st, 1), "customer_talk_seconds": round(ct, 1),
        "interruption_count_seller_over_customer": interrupts,
        "longest_seller_monologue_seconds": round(longest, 1),
        "avg_response_latency_after_customer_question": round(sum(lat) / len(lat), 2) if lat else None,
        "speech_rate_wpm_seller": round(wpm) if wpm else None,
        "hedging_word_count": _count(lex.get("hedging_words", []), seller_text),
        "invite_no_question_count": _count(lex.get("invite_no_patterns", []), seller_text),
        "name_usage_count": name_cnt,
        "seconds_until_greeting_intro_complete": round(sel[0].end, 1) if sel else None,
        "price_first_mentioned_at": mmss(price) if price is not None else None,
    }


def format_transcript(segments: list[Segment], roles: dict[str, str] | None = None) -> str:
    roles = roles or {}
    out = []
    for s in segments:
        if s.speaker in SPECIAL:  # مثل چت: «(موسیقی)» و «(تلفن گویا: متن پیام)»
            tag = LABEL_FA[s.speaker]
            out.append(f"[{mmss(s.start)}] ({tag}: {s.text})" if s.speaker == IVR else f"[{mmss(s.start)}] ({tag})")
            continue
        who = roles.get(s.speaker or "", s.speaker or "گوینده")
        out.append(f"[{mmss(s.start)}] {who}: {s.text}")
    return "\n".join(out)
