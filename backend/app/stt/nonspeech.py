"""بخش‌های غیرگفتاری: موسیقی (انتظار/پس‌زمینه) و تلفن گویا (پیام ضبط‌شده/منوی صوتی).
این بخش‌ها نه کارشناس‌اند نه مشتری؛ در چت به‌صورت «(موسیقی)» و «(تلفن گویا)» نمایش داده می‌شوند و در متریک‌ها نمی‌آیند."""
from __future__ import annotations

import re

MUSIC, IVR = "music", "ivr"
SPECIAL = frozenset({MUSIC, IVR})
LABEL_FA = {MUSIC: "موسیقی", IVR: "تلفن گویا"}

_NOTE = re.compile(r"[♪♫🎵🎶]")
_ONLY_SYMBOLS = re.compile(r"[\s\-–—_.…*#\[\]()♪♫🎵🎶]*")
_MUSIC_WORD = re.compile(r"^\W*(موسیقی|music|آهنگ)\W*$", re.I)
# توهم‌های رایج Whisper روی موسیقی/سکوت
_HALLUCINATION = re.compile(r"زیرنویس|تماشا کردید|ترجمه (شده )?توسط|Subtitles? by|Amara\.org|اشتراک.*کانال", re.I)
_IVR = re.compile(
    r"(عدد|شماره|کلید)\s*\S*\s*(را\s*)?(فشار|بزنید|وارد)|فشار\s*دهید|"
    r"مشترک.{0,25}(در دسترس|پاسخگو|خاموش)|"
    r"پس از (صدای )?بوق|پیام (خود|تان)? ?را (بعد|پس)|"
    r"(تماس|مکالمه) شما.{0,30}(انتظار|ضبط)|لطفاً? (چند لحظه )?(منتظر|پشت خط)|"
    r"در حال برقراری ارتباط|شماره داخلی.{0,20}(را )?(وارد|بگیرید)|"
    r"به (مجموعه|شرکت|سازمان).{0,40}خوش ?آمدید",
)


def is_music(seg: dict) -> bool:
    """seg: دیکشنری segment ورژن verbose_json (text, no_speech_prob, avg_logprob)."""
    txt = str(seg.get("text", "")).strip()
    if not txt or _NOTE.search(txt) or _ONLY_SYMBOLS.fullmatch(txt) or _MUSIC_WORD.match(txt) or _HALLUCINATION.search(txt):
        return True
    return float(seg.get("no_speech_prob") or 0) >= 0.6 and float(seg.get("avg_logprob") or 0) < -0.7


def looks_ivr(text: str) -> bool:
    return bool(_IVR.search(text or ""))
