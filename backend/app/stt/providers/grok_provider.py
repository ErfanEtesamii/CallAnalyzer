"""رونویسی با Grok STT (xAI) — تفکیک گوینده از روی خود صدا (diarize) + زمان هر کلمه.

کل تماس در یک درخواست فرستاده می‌شود (تا شناسه‌ی گوینده‌ها بین تکه‌ها جابه‌جا نشود). خروجی کلمه‌به‌کلمه به «نوبت» تبدیل می‌شود و
با برچسب خام spk0/spk1 به DiarizedRefiner (live.py) می‌رسد؛ آنجا یک مدل زبانی املا را اصلاح و نقش کارشناس/مشتری را تعیین می‌کند
و فقط بعد از آن در چت منتشر می‌شود. بازه‌های بدون کلمه‌ی طولانی که صدا دارند «موسیقی» ثبت می‌شوند."""
from __future__ import annotations

import array
import asyncio
import logging
import os
import time
import wave

import httpx

from app.stt.base import ProviderUnavailable, Segment, Transcript
from app.stt.nonspeech import LABEL_FA, MUSIC
from app.stt.providers.openai_provider import OnSegments, _compress

log = logging.getLogger(__name__)
URL = "https://api.x.ai/v1/stt"
_RETRY = {429, 500, 502, 503, 504}


def build_turns(words: list[dict], *, gap: float = 1.2, soft_words: int = 25, max_words: int = 45) -> list[Segment]:
    """کلمه‌های دارای speaker → نوبت‌ها. نوبت با تغییر گوینده، مکث بلند، یا (بعد از حداقل soft_words) مکث کوتاه شکسته می‌شود."""
    segs: list[Segment] = []
    cur: list[dict] = []

    def flush() -> None:
        if cur:
            txt = " ".join(str(w.get("text", "")).strip() for w in cur).strip()
            if txt:
                segs.append(Segment(float(cur[0]["start"]), float(cur[-1]["end"]), txt, f"spk{cur[0].get('speaker', 0)}"))
            cur.clear()

    for w in sorted((w for w in words if str(w.get("text", "")).strip()), key=lambda w: float(w.get("start", 0))):
        if cur:
            g = float(w["start"]) - float(cur[-1]["end"])
            if w.get("speaker", 0) != cur[-1].get("speaker", 0) or g > gap or (len(cur) >= soft_words and g > 0.4) or len(cur) >= max_words:
                flush()
        cur.append(w)
    flush()
    return segs


def _levels(path: str, step: float = 0.5) -> tuple[list[float], float]:
    """میانگین دامنه‌ی هر step ثانیه (برای تشخیص صدا در بازه‌های بدون کلمه) و step."""
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            return [], step
        rate = w.getframerate()
        pcm = array.array("h")
        pcm.frombytes(w.readframes(w.getnframes()))
    n = max(1, int(step * rate))
    return [sum(abs(x) for x in pcm[i:i + n]) / max(1, len(pcm[i:i + n])) for i in range(0, len(pcm), n)], step


def music_gaps(segs: list[Segment], wav_path: str, total: float, *, min_gap: float = 6.0, ratio: float = 0.25) -> list[Segment]:
    """بازه‌های بین کلمه‌ها (≥ min_gap ثانیه) که صدا دارند (دامنه ≥ ratio × سطح معمول گفتار) → «موسیقی»؛ سکوت نادیده گرفته می‌شود."""
    lv, step = _levels(wav_path)
    if not lv:
        return []
    speech = sorted(lv)[int(len(lv) * 0.7)] or 1.0  # صدک ۷۰: سطح معمول بخش‌های پرصدا
    gaps, prev = [], 0.0
    for s in sorted(segs, key=lambda x: x.start):
        gaps.append((prev, s.start))
        prev = max(prev, s.end)
    gaps.append((prev, total))
    out = []
    for a, b in gaps:
        if b - a >= min_gap:
            win = lv[int(a / step):int(b / step)]
            if win and sum(win) / len(win) >= ratio * speech:
                out.append(Segment(a, b, LABEL_FA[MUSIC], MUSIC))
    return out


class GrokSTT:
    name = "grok"
    supports_live = True
    raw_diarization = True   # برچسب spkN خام می‌دهد؛ نقش‌ها را DiarizedRefiner تعیین می‌کند
    labels_speakers = True

    def __init__(self, api_key: str, model: str = "grok-voice-transcribe-2.0", vocab: str = "", *,
                 transport: httpx.AsyncBaseTransport | None = None, max_retries: int = 3, attempt_timeout: float = 300,
                 compress_bitrate: str = "32k", batch_turns: int = 10, sleep=asyncio.sleep):
        if not api_key:
            raise ProviderUnavailable("XAI_API_KEY تنظیم نشده است")
        self.api_key, self.model, self.transport = api_key, model, transport
        self.terms = [t.strip() for t in vocab.replace("\n", "،").split("،") if 0 < len(t.strip()) <= 50][:100]
        self.max_retries, self.attempt_timeout, self.compress_bitrate = max_retries, attempt_timeout, compress_bitrate
        self.batch_turns, self.sleep = batch_turns, sleep

    async def _post(self, path: str, language: str) -> dict:
        data: dict = {"model": self.model, "language": language, "diarize": "true"}
        if self.terms:
            data["keyterm"] = self.terms
        last: Exception | None = None
        for i in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.attempt_timeout, connect=20), transport=self.transport) as c:
                    with open(path, "rb") as f:  # فایل باید آخرین فیلد فرم باشد
                        r = await asyncio.wait_for(
                            c.post(URL, data=data, files={"file": (os.path.basename(path), f)},
                                   headers={"Authorization": f"Bearer {self.api_key}"}), self.attempt_timeout + 10)
            except (httpx.HTTPError, asyncio.TimeoutError) as e:
                last = e
                log.warning("grok stt: %s (attempt %d)", type(e).__name__, i + 1)
            else:
                if r.status_code == 200:
                    return r.json()
                if r.status_code in (401, 403):
                    raise ProviderUnavailable("کلید xAI نامعتبر است (XAI_API_KEY).")
                if r.status_code not in _RETRY:
                    log.error("grok stt http %s: %s", r.status_code, r.text[:200])
                    raise ProviderUnavailable(f"خطای Grok STT ({r.status_code}).")
                last = RuntimeError(str(r.status_code))
                log.warning("grok stt http %s (attempt %d)", r.status_code, i + 1)
            if i < self.max_retries:
                await self.sleep(min(30, 5 * 2 ** i))
        raise ProviderUnavailable("سرویس رونویسی Grok در دسترس نیست؛ کمی بعد دوباره تلاش کنید.") from last

    async def transcribe(self, wav_path: str, *, language: str = "fa", on_segments: OnSegments | None = None) -> Transcript:
        small = await asyncio.to_thread(_compress, wav_path, self.compress_bitrate) if self.compress_bitrate else None
        t0 = time.monotonic()
        try:
            j = await self._post(small or wav_path, language)
        finally:
            log.warning("stt grok: sent %d KB, done in %.1fs", os.path.getsize(small or wav_path) // 1024, time.monotonic() - t0)
            if small:
                os.unlink(small)
        words = j.get("words") or []
        segs = build_turns(words)
        if not segs and str(j.get("text", "")).strip():
            segs = [Segment(0.0, float(j.get("duration", 0) or 0), str(j["text"]).strip(), "spk0")]
        total = float(j.get("duration") or (segs[-1].end if segs else 0))
        try:
            segs = sorted(segs + music_gaps(segs, wav_path, total), key=lambda s: s.start)
        except Exception:
            log.warning("grok stt: music detection failed", exc_info=True)
        if on_segments:
            for i in range(0, len(segs), self.batch_turns):
                await on_segments(segs[i:i + self.batch_turns])
        return Transcript(segs, language, self.name, raw=None)
