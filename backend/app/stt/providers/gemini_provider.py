"""رونویسی و تفکیک گوینده با Gemini روی خود صدا (به‌جای Whisper + حدس از روی متن).

Whisper روی تماس تلفنی ۸kHz فارسی غلط املایی زیاد دارد و گوینده نمی‌شناسد؛ Gemini صدا را مستقیم می‌شنود و برای هر نوبت
گوینده (کارشناس/مشتری)، موسیقی و تلفن گویا را همراه متن برمی‌گرداند. هر تکه با چند نوبت آخر تکه‌ی قبل شروع می‌شود تا نقش‌ها ثابت بمانند.
اگر Gemini برای یک تکه جواب ندهد (سهمیه/۵۰۳) و fallback (مثلاً Groq) داده شده باشد همان تکه با آن رونویسی می‌شود
و گوینده‌اش بعداً توسط SpeakerLabeler تعیین می‌شود."""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
import wave

import httpx

from app.analysis.errors import LLMError
from app.analysis.gemini import GeminiLLM, _extract_json
from app.stt.base import ProviderUnavailable, Segment, Transcript
from app.stt.nonspeech import IVR, LABEL_FA, MUSIC
from app.stt.providers.openai_provider import OnSegments, _compress, _split_wav

log = logging.getLogger(__name__)
SELLER, CUSTOMER = "seller", "customer"
_ROLES = {SELLER: "کارشناس", CUSTOMER: "مشتری", IVR: "(تلفن گویا)", MUSIC: "(موسیقی)"}
_SPEAKERS = {SELLER, CUSTOMER, IVR, MUSIC}

SYSTEM = """تو رونویس‌کننده‌ی حرفه‌ای تماس‌های تلفنی فارسی هستی. یک تماس فروش بین «کارشناس فروش» (کسی که تماس می‌گیرد، خودش و شرکتش را معرفی می‌کند و محصول/خدمت پیشنهاد می‌دهد)
و «مشتری» (کسی که پاسخ می‌دهد) است. فقط همین تکه‌ی صوتی را رونویسی کن.
قواعد:
- متن را به فارسی معیار و با املای درست بنویس؛ چیزی اضافه یا حدس‌زده ننویس. کلمه‌ی نامفهوم را «[نامفهوم]» بگذار.
- هر بار که گوینده عوض می‌شود نوبت جدید بساز، حتی برای جواب کوتاه مثل «بله». حرف هر دو نفر هرگز در یک نوبت نیاید.
- speaker: seller (کارشناس) | customer (مشتری) | ivr (پیام ضبط‌شده/تلفن گویا/صندوق صوتی/منوی صوتی) | music (موسیقی بدون گفتار).
- نقش‌ها را با کمک «زمینه‌ی قبلی» ثابت نگه دار؛ اگر زمینه‌ای نیست، کسی که خود و شرکت را معرفی می‌کند و پیشنهاد می‌دهد کارشناس است.
- start و end (ثانیه، نسبت به ابتدای همین تکه) را تقریبی ولی صعودی بده. برای موسیقی متن خالی بگذار.
خروجی: فقط یک شیء JSON به شکل {"turns":[{"speaker":"seller","start":0.0,"end":3.2,"text":"..."}]}"""


def _dur(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _ctx(tail: list[Segment]) -> str:
    return "\n".join(f"{_ROLES.get(s.speaker or '', 'مشتری')}: {s.text}" for s in tail) or "(شروع تماس)"


def turns_to_segments(turns: list[dict], offset: float, length: float) -> list[Segment]:
    """نوبت‌های JSON مدل → Segment؛ زمان‌ها به بازه‌ی تکه کشیده و صعودی می‌شوند، نوبت‌های نامعتبر حذف."""
    clean = []
    for t in turns:
        sp = str(t.get("speaker", "")).strip().lower()
        txt = str(t.get("text", "")).strip()
        if sp not in _SPEAKERS or (not txt and sp != MUSIC):
            continue
        try:
            a, b = float(t.get("start", 0)), float(t.get("end", 0))
        except (TypeError, ValueError):
            a = b = 0.0
        clean.append([sp, txt, a, b])
    out, cur = [], 0.0
    n = len(clean)
    for i, (sp, txt, a, b) in enumerate(clean):
        a = min(max(a, cur), length)
        if b <= a:  # زمان گم‌شده: به‌نسبت طول متن از باقی‌مانده‌ی تکه
            b = a + (length - a) / max(1, n - i) if i == n - 1 else a + max(0.5, len(txt) / 14)
        b = min(max(b, a + 0.1), max(length, a + 0.1))
        cur = b
        if sp == MUSIC:
            txt = LABEL_FA[MUSIC]
        out.append(Segment(offset + a, offset + b, txt, sp))
    return out


class GeminiSTT:
    name = "gemini"
    supports_live = True
    labels_speakers = True  # گوینده را خودش تعیین می‌کند

    def __init__(self, api_key: str, model: str = "gemini-3.8-flash", vocab: str = "", *, fallback=None,
                 transport: httpx.AsyncBaseTransport | None = None, chunk_seconds: int = 45,
                 compress_bitrate: str = "32k", attempt_timeout: float = 170, sleep=asyncio.sleep):
        if not api_key:
            raise ProviderUnavailable("GEMINI_API_KEY تنظیم نشده است")
        self.model, self.vocab, self.fallback = model, vocab, fallback
        self.chunk_seconds, self.compress_bitrate, self.attempt_timeout = chunk_seconds, compress_bitrate, attempt_timeout
        self.llm = GeminiLLM(api_key, transport=transport, thinking_budget=0, sleep=sleep)

    def _body(self, audio: bytes, mime: str, tail: list[Segment]) -> dict:
        text = f"<context>\n{_ctx(tail)}\n</context>\n"
        if self.vocab:
            text += f"<vocabulary>{self.vocab}</vocabulary>\n"
        text += "این تکه‌ی صوتی ادامه‌ی همان تماس است؛ رونویسی کن."
        return {"systemInstruction": {"parts": [{"text": SYSTEM}]},
                "contents": [{"role": "user", "parts": [{"inlineData": {"mimeType": mime, "data": base64.b64encode(audio).decode()}},
                                                        {"text": text}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 8192,
                                     "thinkingConfig": {"thinkingBudget": 0}}}

    async def _ask(self, path: str, mime: str, tail: list[Segment]) -> list[dict]:
        with open(path, "rb") as f:
            body = self._body(f.read(), mime, tail)
        for attempt in range(2):  # یک بار دوباره اگر JSON خراب بود
            j = await asyncio.wait_for(self.llm._post_with_fallback(self.model, body), self.attempt_timeout)
            cands = j.get("candidates") or []
            if not cands:
                raise LLMError("llm_blocked", "Gemini پاسخی نداد.")
            text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
            try:
                turns = _extract_json(text).get("turns", [])
                if isinstance(turns, list):
                    return turns
            except ValueError:
                log.warning("gemini stt: non-json (attempt %d)", attempt + 1)
        raise LLMError("llm_bad_output", "خروجی Gemini معتبر نبود.")

    async def transcribe(self, wav_path: str, *, language: str = "fa", on_segments: OnSegments | None = None) -> Transcript:
        segs: list[Segment] = []
        for offset, chunk_path, is_tmp in _split_wav(wav_path, self.chunk_seconds):
            small = await asyncio.to_thread(_compress, chunk_path, self.compress_bitrate) if self.compress_bitrate else None
            send, mime = (small, "audio/mp3") if small else (chunk_path, "audio/wav")
            t0 = time.monotonic()
            try:
                length = _dur(chunk_path)
                try:
                    part = turns_to_segments(await self._ask(send, mime, segs[-6:]), offset, length)
                    if not part:
                        log.warning("gemini stt: chunk@%.0fs returned no turns", offset)
                except (LLMError, asyncio.TimeoutError, httpx.HTTPError) as e:
                    if self.fallback is None:
                        raise ProviderUnavailable("رونویسی با Gemini انجام نشد؛ کمی بعد دوباره تلاش کنید.") from e
                    log.warning("gemini stt failed at %.0fs (%s); using fallback", offset, type(e).__name__)
                    fb = await self.fallback.transcribe(chunk_path, language=language)
                    part = [Segment(s.start + offset, s.end + offset, s.text, s.speaker) for s in fb.segments]
            finally:
                log.warning("stt gemini: chunk@%.0fs in %.1fs", offset, time.monotonic() - t0)
                if small:
                    os.unlink(small)
                if is_tmp:
                    os.unlink(chunk_path)
            segs.extend(part)
            if part and on_segments:
                await on_segments(part)
        return Transcript(segs, language, self.name, raw=None)
