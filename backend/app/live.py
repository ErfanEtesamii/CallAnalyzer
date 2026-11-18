"""چت زنده: حباب‌های رونویسی هم‌زمان با پردازش (کارشناس راست، مشتری چپ) + برچسب گوینده با مدل زبانی.

جدول جدا و خودکفا (بدون دست‌زدن به SCHEMA اصلی). هیچ خطایی از این ماژول نباید پایپ‌لاین را بشکند.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from app.stt.base import Segment
from app.stt.nonspeech import IVR, MUSIC, SPECIAL, looks_ivr

log = logging.getLogger(__name__)

SELLER, CUSTOMER = "seller", "customer"

_DDL = """
CREATE TABLE IF NOT EXISTS live_segments(
 analysis_id INTEGER NOT NULL, idx INTEGER NOT NULL, start REAL, end REAL, text TEXT, speaker TEXT, created_at REAL,
 PRIMARY KEY(analysis_id, idx))
"""


class LiveStore:
    def __init__(self, db):
        self.db = db
        with db.lock:
            db.conn.execute(_DDL)
            db.conn.commit()

    def reset(self, aid: int) -> None:
        with self.db.lock:
            self.db.conn.execute("DELETE FROM live_segments WHERE analysis_id=?", (aid,))
            self.db.conn.commit()

    def count(self, aid: int) -> int:
        rows = self.db.q("SELECT COUNT(*) AS n FROM live_segments WHERE analysis_id=?", (aid,))
        return int(rows[0]["n"])

    def append(self, aid: int, segs: list[Segment]) -> None:
        base = self.count(aid)
        now = time.time()
        with self.db.lock:
            self.db.conn.executemany(
                "INSERT OR REPLACE INTO live_segments(analysis_id,idx,start,end,text,speaker,created_at) VALUES(?,?,?,?,?,?,?)",
                [(aid, base + i, s.start, s.end, s.text, s.speaker, now) for i, s in enumerate(segs)])
            self.db.conn.commit()

    def get(self, aid: int, after: int = 0) -> list[dict[str, Any]]:
        return self.db.q("SELECT idx AS i, start, end, text, speaker FROM live_segments WHERE analysis_id=? AND idx>=? ORDER BY idx",
                         (aid, max(0, after)))


# ---------------------------------------------------------------- برچسب گوینده

_SYSTEM = (
    "تو یک برچسب‌زن گوینده برای مکالمه‌ی تلفنی فروش هستی. مجموعه‌ی «فراز هنر» تولیدکننده‌ی هدایای سازمانی با محوریت صنایع دستی است. "
    "تماس‌ها معمولاً خروجی‌اند: «کارشناس فروش» (seller) زنگ می‌زند و با سلام و معرفی خود و مجموعه شروع می‌کند، سؤال می‌پرسد، "
    "کاتالوگ و قیمت و قدم بعدی را مطرح می‌کند. «مشتری» (customer) پاسخ می‌دهد، می‌پرسد یا اعتراض می‌کند. "
    "به هر قطعه‌ی شماره‌دار دقیقاً یک برچسب بده: seller یا customer. متن را عوض نکن. "
    "از ادامه‌ی گفتگوی قبلی (با برچسب‌های قطعی) و محتوا و نوبت‌ها استفاده کن؛ معمولاً گوینده‌ها نوبتی عوض می‌شوند. "
    "اگر قطعه پیام ضبط‌شده‌ی تلفن گویا/منوی صوتی/صندوق صوتی (مثل «برای ... عدد ۱ را فشار دهید»، «مشترک در دسترس نیست»، خوش‌آمدگویی خودکار) است برچسب ivr بده؛ "
    "اگر متن بی‌معنی/تکراری ناشی از موسیقی انتظار یا نویز است برچسب music. گفتگوی واقعی دو انسان هرگز ivr یا music نیست. "
    "تنها خروجی: یک شیء JSON با کلید labels (آرایه‌ای هم‌طول با قطعه‌های جدید)."
)
_TOOL = {"name": "label_speakers", "description": "برچسب گوینده برای هر قطعه",
         "input_schema": {"type": "object", "required": ["labels"],
                          "properties": {"labels": {"type": "array", "items": {"type": "string", "enum": [SELLER, CUSTOMER, IVR, MUSIC]}}}}}


def heuristic_labels(segs: list[Segment], prev_last: Segment | None, prev_speaker: str | None) -> list[str]:
    """جایگزین ساده هنگام خطای مدل: فاصله‌ی سکوت یا پایان با «؟» نوبت را عوض می‌کند؛ نفر اول کارشناس است."""
    out: list[str] = []
    last_seg, last_sp = prev_last, prev_speaker
    for s in segs:
        if last_sp is None:
            sp = SELLER
        else:
            gap = s.start - (last_seg.end if last_seg else s.start)
            ends_q = bool(last_seg and last_seg.text.strip().endswith(("؟", "?")))
            flip = gap > 0.7 or ends_q
            sp = (CUSTOMER if last_sp == SELLER else SELLER) if flip else last_sp
        out.append(sp)
        last_seg, last_sp = s, sp
    return out


_ALLOWED = (SELLER, CUSTOMER, IVR, MUSIC)


def _ctx_line(s: Segment) -> str:
    who = {SELLER: "کارشناس", CUSTOMER: "مشتری", IVR: "(تلفن گویا)", MUSIC: "(موسیقی)"}.get(s.speaker or "", "مشتری")
    return f"{who}: {s.text}"


class SpeakerLabeler:
    """برچسب‌زنی تدریجی هر تکه با یک مدل سبک؛ در صورت هر مشکل به heuristic برمی‌گردد."""

    def __init__(self, llm, model: str, context_lines: int = 14):
        self.llm, self.model, self.context_lines = llm, model, context_lines
        self.history: list[Segment] = []
        self.llm_batches = 0  # تعداد دسته‌هایی که واقعاً با مدل برچسب خورده‌اند

    async def label(self, segs: list[Segment]) -> list[Segment]:
        if not segs:
            return segs
        for s in segs:  # تلفن گویا با الگوهای قطعی (موسیقی را ارائه‌دهنده‌ی STT قبلاً علامت زده)
            if s.speaker not in SPECIAL and looks_ivr(s.text):
                s.speaker = IVR
        todo = [s for s in segs if s.speaker not in SPECIAL]
        if todo:
            labels = None
            if self.llm is not None:
                try:
                    labels = await self._ask(todo)
                    if labels and len(labels) == len(todo) and all(x in _ALLOWED for x in labels):
                        self.llm_batches += 1
                except Exception as e:  # noqa: BLE001 — برچسب‌زنی هرگز پایپ‌لاین را نمی‌شکند
                    log.warning("speaker labeling failed (%s); using heuristic", type(e).__name__)
            if not labels or len(labels) != len(todo) or any(x not in _ALLOWED for x in labels):
                human = [x for x in self.history if x.speaker not in SPECIAL]
                last = human[-1] if human else None
                labels = heuristic_labels(todo, last, last.speaker if last else None)
            for s, sp in zip(todo, labels, strict=True):
                s.speaker = sp
        self.history.extend(segs)
        return segs

    async def _ask(self, segs: list[Segment]) -> list[str] | None:
        ctx = "\n".join(_ctx_line(s) for s in self.history[-self.context_lines:])
        new = "\n".join(f"{i + 1}. {s.text}" for i, s in enumerate(segs))
        user = (f"<گفتگوی_قبلی>\n{ctx or '(شروع تماس)'}\n</گفتگوی_قبلی>\n<قطعه‌های_جدید>\n{new}\n</قطعه‌های_جدید>\n"
                f"فقط {len(segs)} برچسب برگردان.")
        out, _usage = await self.llm.call_tool(system=[{"type": "text", "text": _SYSTEM}], user=user, tool=_TOOL,
                                               model=self.model, temperature=0.0)
        labels = out.get("labels") if isinstance(out, dict) else None
        return [str(x).strip().lower() for x in labels] if isinstance(labels, list) else None


def label_model(settings) -> str:
    """مدل سبک برای برچسب‌زنی: LABEL_MODEL، وگرنه یک مدل سبک مناسب هر ارائه‌دهنده."""
    env = os.environ.get("LABEL_MODEL", "").strip()
    if env:
        return env
    return "gemini-3.5-flash-lite" if settings.llm_provider == "gemini" else settings.analysis_model


def add_routes(app, pipe, auth, owned) -> None:
    """GET /api/v1/analyses/{aid}/live?after=N — حباب‌های تازه (برای polling افزونه)."""
    from fastapi import Depends

    @app.get("/api/v1/analyses/{aid}/live")
    def live(aid: int, after: int = 0, _: str = Depends(auth)):
        a = owned(aid)
        segs = pipe.live.get(aid, after)
        return {"status": a["status"], "duration": a.get("real_duration"), "error_message": a.get("error_message"),
                "after": after, "next": (segs[-1]["i"] + 1) if segs else after, "segments": segs}
