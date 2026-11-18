"""مخفی‌سازی PII پیش از ارسال به سرویس خارجی."""
from __future__ import annotations

import re

from app.util import normalize_digits

_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){16}(?!\d)")
_NID = re.compile(r"(?<!\d)\d{10}(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)|(?<!\d)0\d{10}(?!\d)")


def redact(text: str) -> str:
    t = normalize_digits(text)
    t = _CARD.sub("[CARD]", t)
    t = _PHONE.sub("[PHONE]", t)
    t = _NID.sub("[ID]", t)
    return t
