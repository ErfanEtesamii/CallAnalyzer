from __future__ import annotations

import array
import asyncio
import logging
import os
import subprocess
import tempfile
import time
import wave
from collections.abc import Awaitable, Callable

import httpx

from app.stt.base import ProviderUnavailable, Segment, Transcript

log = logging.getLogger(__name__)

OnSegments = Callable[[list[Segment]], Awaitable[None]]


def _compress(wav_path: str, bitrate: str) -> str | None:
    """WAV → MP3 تک‌کاناله (سرعت آپلود سرور پایین است). در صورت هر مشکل None → همان WAV ارسال می‌شود."""
    fd, out = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", wav_path, "-vn", "-ac", "1",
                            "-ar", "16000", "-c:a", "libmp3lame", "-b:a", bitrate, out],
                           capture_output=True, timeout=120, check=False)
        if r.returncode == 0 and os.path.getsize(out) > 0:
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    os.unlink(out)
    return None


class OpenAISTT:
    """OpenAI Whisper API (و سازگارها مثل Groq). صدا به تکه‌های کوتاه شکسته می‌شود تا حباب‌های چت زنده زود برسند.

    gpt-4o-transcribe زمان‌بندی segment نمی‌دهد؛ برای timestamp از whisper-1/large-v3 استفاده می‌شود."""

    name = "openai"
    supports_live = True

    def __init__(self, api_key: str, model: str = "whisper-1", prompt: str = "", *,
                 base_url: str = "https://api.openai.com/v1", name: str = "openai", key_name: str = "OPENAI_API_KEY",
                 max_prompt_chars: int = 0, transport: httpx.AsyncBaseTransport | None = None,
                 chunk_seconds: int = 30, max_retries: int = 3, request_timeout: float = 120, sleep=asyncio.sleep,
                 compress_bitrate: str = "32k", attempt_timeout: float = 150):
        if not api_key:
            raise ProviderUnavailable(f"{key_name} تنظیم نشده است")
        self.name = name
        self.api_key, self.model, self.base_url, self.transport = api_key, model, base_url.rstrip("/"), transport
        self.max_prompt_chars = max_prompt_chars
        self.prompt = prompt[:max_prompt_chars] if max_prompt_chars else prompt  # Groq: prompt حداکثر ~۲۲۴ توکن
        self.chunk_seconds, self.max_retries, self.request_timeout, self.sleep = chunk_seconds, max_retries, request_timeout, sleep
        self.compress_bitrate, self.attempt_timeout = compress_bitrate, attempt_timeout  # bitrate خالی = بدون فشرده‌سازی

    def _prompt_for(self, tail: str) -> str:
        """واژگان دامنه + انتهای متن تکه‌ی قبل (برای پیوستگی کلمه/جمله بین تکه‌ها)."""
        if not tail:
            return self.prompt
        budget = self.max_prompt_chars or 600
        keep = max(0, budget - len(tail) - 1)
        return (self.prompt[:keep] + " " + tail).strip() if keep else tail[-budget:]

    async def transcribe(self, wav_path: str, *, language: str = "fa", on_segments: OnSegments | None = None) -> Transcript:
        segs: list[Segment] = []
        tail = ""
        for offset, chunk_path, is_tmp in _split_wav(wav_path, self.chunk_seconds):
            send_path, small = chunk_path, None
            if self.compress_bitrate:
                small = await asyncio.to_thread(_compress, chunk_path, self.compress_bitrate)
                send_path = small or chunk_path
            t0 = time.monotonic()
            try:
                j = await self._post_with_retry(send_path, language, self._prompt_for(tail))
            finally:
                log.warning("stt %s: chunk@%.0fs sent %d KB in %.1fs", self.name, offset,
                            os.path.getsize(send_path) // 1024 if os.path.exists(send_path) else -1, time.monotonic() - t0)
                if small:
                    os.unlink(small)
                if is_tmp:
                    os.unlink(chunk_path)
            part = [Segment(s["start"] + offset, s["end"] + offset, s["text"].strip()) for s in j.get("segments", [])
                    if s.get("text", "").strip()]
            if not part and j.get("text", "").strip():
                part = [Segment(offset, offset + float(j.get("duration", 0)), j["text"].strip())]
            segs.extend(part)
            if part:
                tail = " ".join(s.text for s in part)[-160:]
                if on_segments:
                    await on_segments(part)
        return Transcript(segs, language, self.name, raw=None)

    async def _post_with_retry(self, path: str, language: str, prompt: str) -> dict:
        data = {"model": self.model, "language": language, "response_format": "verbose_json",
                "timestamp_granularities[]": "segment"}
        if prompt:
            data["prompt"] = prompt
        last = "خطای ناشناخته"
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.request_timeout, transport=self.transport) as c:
                    with open(path, "rb") as f:
                        files = {"file": (os.path.basename(path), f, "audio/mpeg" if path.endswith(".mp3") else "audio/wav")}
                        r = await asyncio.wait_for(
                            c.post(f"{self.base_url}/audio/transcriptions",
                                   headers={"Authorization": f"Bearer {self.api_key}"}, data=data, files=files),
                            self.attempt_timeout)  # سقف کل هر تلاش (تایم‌اوت httpx فقط برای هر عملیات است)
            except (httpx.HTTPError, asyncio.TimeoutError) as e:  # تایم‌اوت/قطع اتصال
                last = f"اتصال به سرویس رونویسی ناموفق بود ({type(e).__name__})"
            else:
                if r.status_code == 429:
                    raise ProviderUnavailable("سهمیه‌ی رونویسی (STT) موقتاً تمام شده است؛ کمی بعد دوباره تلاش کنید.")
                if r.status_code in (401, 403):
                    raise ProviderUnavailable("کلید STT نامعتبر است.")
                if r.status_code < 400:
                    return r.json()
                if r.status_code < 500:
                    raise ProviderUnavailable(f"سرویس رونویسی درخواست را رد کرد (کد {r.status_code}).")
                last = f"سرویس رونویسی موقتاً در دسترس نیست (کد {r.status_code})"
            if attempt < self.max_retries - 1:
                await self.sleep(2 * 2 ** attempt)
        raise ProviderUnavailable(last + "؛ دوباره تلاش کنید.")


def _quietest_frame(samples: array.array, lo: int, hi: int, frame: int, target: int) -> int:
    """ابتدای ساکت‌ترین پنجره‌ی کوتاه در بازه‌ی [lo, hi) نمونه (در تساوی، نزدیک‌تر به target) — تا برش وسط کلمه نیفتد."""
    best, best_key = target, None
    for p in range(lo, max(lo + 1, hi - frame), frame):
        win = samples[p:p + frame]
        key = (round(sum(abs(x) for x in win) / max(1, len(win))), abs(p - target))
        if best_key is None or key < best_key:
            best, best_key = p, key
    return best


def _split_wav(path: str, chunk_seconds: int):
    """(offset_sec, path, is_temp). فایل کوتاه همان‌طور ارسال می‌شود؛ فایل بلند به تکه‌های ≈chunk_seconds ثانیه‌ای
    که مرز هر کدام در نزدیک‌ترین نقطه‌ی ساکت (±۳ ثانیه) انتخاب می‌شود."""
    with wave.open(path, "rb") as w:
        rate, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        per = max(1, int(chunk_seconds * rate))
        if n <= per * 1.25:
            yield 0.0, path, False
            return
        params = w.getparams()
        pcm = array.array("h")
        can_search = sw == 2 and ch == 1
        if can_search:
            pcm.frombytes(w.readframes(n))
            w.rewind()
        slack, frame = min(int(3 * rate), per // 3), max(1, int(0.05 * rate))
        pos = 0
        while pos < n:
            end = n
            if n - pos > per * 1.25:
                end = pos + per
                if can_search:
                    end = _quietest_frame(pcm, max(pos + 1, end - slack), min(n - 1, end + slack), frame, end)
            w.setpos(pos)
            frames = w.readframes(end - pos)
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            with wave.open(tmp, "wb") as o:
                o.setparams(params)
                o.writeframes(frames)
            yield pos / rate, tmp, True
            pos = end
