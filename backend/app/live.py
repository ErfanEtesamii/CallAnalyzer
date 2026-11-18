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
            if s.speaker is None and looks_ivr(s.text):
                s.speaker = IVR
        todo = [s for s in segs if s.speaker is None]  # برچسب‌دار از ارائه‌دهنده (Gemini) دست‌نخورده می‌ماند
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


_REFINE_SYSTEM = (
    "تو ویراستار رونوشت تماس تلفنی فارسی هستی. رونوشت را یک مدل گفتار-به-متن با تفکیک گوینده‌ی صوتی ساخته: "
    "شناسه‌ی spkN یعنی یک نفر مشخص (ثابت در کل تماس)، ولی نمی‌دانیم کدام کارشناس است و کدام مشتری. "
    "برای هر نوبت دو کار بکن: ۱) نقش: seller (کارشناس فروش؛ تماس‌گیرنده که خود و شرکتش را معرفی و پیشنهاد می‌دهد)، customer (مشتری)، "
    "ivr (پیام ضبط‌شده/تلفن گویا/صندوق صوتی/منوی صوتی) یا music (فقط موسیقی/نویز بی‌معنی). همه‌ی نوبت‌های یک spk معمولاً یک نقش دارند؛ اگر شناسه «؟» است نقش را از محتوا و نوبت گفتگو حدس بزن. "
    "۲) متن را ویرایش املایی و نگارشی کن: غلط‌های املایی و شنیداری آشکار را با کمک بافت گفتگو و واژگان تخصصی درست کن، علائم نگارشی بگذار. "
    "هرگز مطلب اضافه نکن، چیزی حذف نکن و معنی را عوض نکن؛ اگر مطمئن نیستی همان متن را نگه دار. "
    "تنها خروجی: یک شیء JSON با کلید turns (آرایه‌ای هم‌طول با نوبت‌های جدید، هر عنصر {speaker, text})."
)
_REFINE_TOOL = {"name": "refine_turns", "description": "نقش و متن ویرایش‌شده‌ی هر نوبت",
                "input_schema": {"type": "object", "required": ["turns"], "properties": {"turns": {"type": "array", "items": {
                    "type": "object", "required": ["speaker", "text"],
                    "properties": {"speaker": {"type": "string", "enum": [SELLER, CUSTOMER, IVR, MUSIC]}, "text": {"type": "string"}}}}}}}


def _is_spk(x: str | None) -> bool:
    return bool(x) and x.startswith("spk")


class DiarizedRefiner:
    """برای STTهایی که گوینده را از صدا می‌دهند (spk0/spk1): مدل زبانی املا را اصلاح و نقش را تعیین می‌کند؛ بعد از آن منتشر می‌شود.
    نگاشت spk→نقش بعد از اولین دسته ثابت می‌ماند تا وسط تماس جابه‌جا نشود. هر خطا → نقش از ترتیب (نفر اول کارشناس) و متن اصلی."""

    def __init__(self, llm, model: str, context_lines: int = 12, vocab: str = ""):
        self.llm, self.model, self.context_lines, self.vocab = llm, model, context_lines, vocab
        self.history: list[Segment] = []
        self.roles: dict[str, str] = {}
        self.llm_batches = 0

    def _heur(self, s: Segment) -> str:
        human = [x for x in self.history if x.speaker not in SPECIAL]
        last = human[-1] if human else None
        return heuristic_labels([s], last, last.speaker if last else None)[0]

    def _fallback_role(self, spk: str) -> str:
        if spk not in self.roles:
            self.roles[spk] = SELLER if SELLER not in self.roles.values() else CUSTOMER
        return self.roles[spk]

    async def label(self, segs: list[Segment]) -> list[Segment]:
        todo = [s for s in segs if s.speaker not in SPECIAL]
        res = None
        if todo and self.llm is not None:
            try:
                res = await self._ask(todo)
                self.llm_batches += 1
            except Exception as e:  # noqa: BLE001 — ویرایش هرگز پایپ‌لاین را نمی‌شکند
                log.warning("refine failed (%s); using order-based roles", type(e).__name__)
        if res is not None:
            votes: dict[str, dict[str, int]] = {}
            for s, (sp, _) in zip(todo, res, strict=True):
                if sp in (SELLER, CUSTOMER) and _is_spk(s.speaker) and s.speaker not in self.roles:
                    votes.setdefault(s.speaker, {}).setdefault(sp, 0)
                    votes[s.speaker][sp] += 1
            for spk, v in votes.items():
                self.roles[spk] = max(v, key=lambda k: v[k])
            if len(set(self.roles.values())) < 2 and len(self.roles) >= 2:  # هر دو spk یک نقش شدند: دومی را برعکس کن
                first = next(iter(self.roles))
                for spk in self.roles:
                    if spk != first:
                        self.roles[spk] = CUSTOMER if self.roles[first] == SELLER else SELLER
        for i, s in enumerate(todo):
            llm_role, text = (res[i] if res is not None else (None, s.text))
            if llm_role in (IVR, MUSIC):
                s.speaker = llm_role
            elif res is None and looks_ivr(s.text):
                s.speaker = IVR
            elif _is_spk(s.speaker):
                s.speaker = self.roles.get(s.speaker) or llm_role or self._fallback_role(s.speaker)
            else:  # بدون تفکیک صوتی (Whisper): نقش از مدل، یا heuristic
                s.speaker = llm_role or self._heur(s)
            if res is not None:
                s.text = text
        self.history.extend(segs)
        return segs

    async def _ask(self, segs: list[Segment]) -> list[tuple[str, str]]:
        ctx = "\n".join(_ctx_line(s) for s in self.history[-self.context_lines:])
        hint = "، ".join(f"{k}={v}" for k, v in self.roles.items()) or "(هنوز تعیین نشده)"
        new = "\n".join(f"{i + 1}. [{s.speaker if _is_spk(s.speaker) else '؟'}] {s.text}" for i, s in enumerate(segs))
        voc = f"<واژگان>{self.vocab}</واژگان>\n" if self.vocab else ""
        user = (f"{voc}<نقش‌های_تعیین‌شده>{hint}</نقش‌های_تعیین‌شده>\n<گفتگوی_قبلی>\n{ctx or '(شروع تماس)'}\n</گفتگوی_قبلی>\n"
                f"<نوبت‌های_جدید>\n{new}\n</نوبت‌های_جدید>\nفقط {len(segs)} عنصر برگردان.")
        out, _ = await self.llm.call_tool(system=[{"type": "text", "text": _REFINE_SYSTEM}], user=user, tool=_REFINE_TOOL,
                                          model=self.model, temperature=0.0)
        turns = out.get("turns") if isinstance(out, dict) else None
        if not isinstance(turns, list) or len(turns) != len(segs):
            raise ValueError("bad refine output")
        res = []
        for s, t in zip(segs, turns, strict=True):
            sp = str(t.get("speaker", "")).strip().lower() if isinstance(t, dict) else ""
            if sp not in _ALLOWED:
                raise ValueError("bad role")
            tx = str(t.get("text", "")).strip()
            ok = tx and 0.6 <= len(tx) / max(1, len(s.text)) <= 1.6  # محافظ در برابر حذف/افزودن مطلب
            res.append((sp, tx if ok else s.text))
        return res


def label_model(settings) -> str:
    """مدل سبک برای برچسب‌زنی: LABEL_MODEL، وگرنه یک مدل سبک مناسب هر ارائه‌دهنده."""
    env = os.environ.get("LABEL_MODEL", "").strip()
    if env:
        return env
    return {"gemini": "gemini-3.5-flash-lite", "deepseek": settings.analysis_model}.get(settings.llm_provider, "claude-haiku-5-5")


def add_routes(app, pipe, auth, owned) -> None:
    """GET /api/v1/analyses/{aid}/live?after=N — حباب‌های تازه (برای polling افزونه)."""
    from fastapi import Depends

    @app.get("/api/v1/analyses/{aid}/live")
    def live(aid: int, after: int = 0, _: str = Depends(auth)):
        a = owned(aid)
        segs = pipe.live.get(aid, after)
        return {"status": a["status"], "duration": a.get("real_duration"), "error_message": a.get("error_message"),
                "after": after, "next": (segs[-1]["i"] + 1) if segs else after, "segments": segs}
