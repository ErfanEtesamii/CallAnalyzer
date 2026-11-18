"""ابزارهای کمکی: ارقام فارسی، زمان، نام فایل Asterisk، ماسک شماره."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

_FA = "۰۱۲۳۴۵۶۷۸۹"
_AR = "٠١٢٣٤٥٦٧٨٩"
_TABLE = {ord(c): str(i) for i, c in enumerate(_FA)} | {ord(c): str(i) for i, c in enumerate(_AR)}


def normalize_digits(s: str) -> str:
    """ارقام فارسی/عربی را به لاتین تبدیل می‌کند."""
    return s.translate(_TABLE)


def normalize_fa_text(s: str) -> str:
    """یکسان‌سازی ي/ی و ك/ک، حذف کشیده و فاصله‌ی اضافه."""
    s = s.replace("ي", "ی").replace("ك", "ک").replace("ـ", "")
    s = s.replace("‌‌", "‌")
    return re.sub(r"[ \t]+", " ", s).strip()


def hms_to_seconds(s: str) -> int:
    parts = [int(p) for p in normalize_digits(s).strip().split(":") if p.strip().isdigit()]
    if not parts:
        return 0
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec


def mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def mmss_to_seconds(s: str) -> float:
    return float(hms_to_seconds(s))


_FILE_RE = re.compile(
    r"^(?P<dir>out|in)-(?P<number>[^-]+)-(?P<ext>\d+)-(?P<date>\d{8})-(?P<time>\d{6})-(?P<uid>\d+\.\d+)\.wav$"
)


@dataclass(frozen=True)
class ParsedFilename:
    direction: str
    number: str
    extension: str
    call_datetime: datetime
    unique_id: str


def parse_filename(name: str) -> ParsedFilename | None:
    """نام فایل ضبط‌شده را تجزیه می‌کند؛ در صورت نامعتبر بودن None."""
    if "/" in name or "\\" in name or ".." in name:
        return None
    m = _FILE_RE.match(name)
    if not m:
        return None
    try:
        dt = datetime.strptime(m["date"] + m["time"], "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return ParsedFilename(m["dir"], m["number"], m["ext"], dt, m["uid"])


def mask_phone(num: str) -> str:
    n = normalize_digits(num or "")
    digits = re.sub(r"\D", "", n)
    if len(digits) < 7:
        return "***"
    return f"{digits[:4]}***{digits[-4:]}"


def hash_phone(num: str, salt: str = "") -> str:
    digits = re.sub(r"\D", "", normalize_digits(num or ""))
    return hashlib.sha256((salt + digits).encode()).hexdigest()[:24]
