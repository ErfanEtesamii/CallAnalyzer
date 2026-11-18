from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import time
import wave

import httpx

from app.stt.base import ProviderUnavailable, Segment, Transcript


log = logging.getLogger(__name__)


def _compress(wav_path: str, bitrate: str) -> str | None:
    """WAV → MP3 تک‌کاناله (سرعت آپلود سرور پایین است). در صورت هر مشکل None → همان WAV ارسال می‌شود."""
    fd, out = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", wav_path, "-vn", "-ac", "1",
                            "-ar", "16000", "-c:a", "libmp3lame", "-b:a", bitrate, out],
                           capture_output=True, timeout=120)
        if r.returncode == 0 and os.path.getsize(out) > 0:
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    os.unlink(out)
    return None


class OpenAISTT:
    """OpenAI Whisper API. gpt-4o-transcribe زمان‌بندی segment نمی‌دهد؛ برای timestamp از whisper-1 استفاده می‌شود."""

    name = "openai"

    def __init__(self, api_key: str, model: str = "whisper-1", prompt: str = "", *,
                 base_url: str = "https://api.openai.com/v1", name: str = "openai", key_name: str = "OPENAI_API_KEY",
                 max_prompt_chars: int = 0, transport: httpx.AsyncBaseTransport | None = None,
                 chunk_seconds: int = 240, max_retries: int = 3, request_timeout: float = 120, sleep=asyncio.sleep,
                 compress_bitrate: str = "32k", attempt_timeout: float = 150):
        if not api_key:
            raise ProviderUnavailable(f"{key_name} تنظیم نشده است")
        self.name = name
        self.api_key, self.model, self.base_url, self.transport = api_key, model, base_url.rstrip("/"), transport
        self.chunk_seconds, self.max_retries, self.request_timeout, self.sleep = chunk_seconds, max_retries, request_timeout, sleep
        self.compress_bitrate, self.attempt_timeout = compress_bitrate, attempt_timeout  # bitrate خالی = بدون فشرده‌سازی
        self.prompt = prompt[:max_prompt_chars] if max_prompt_chars else prompt  # Groq: prompt حداکثر ~۲۲۴ توکن

    async def transcribe(self, wav_path: str, *, language: str = "fa") -> Transcript:
        segs: list[Segment] = []
        for offset, chunk_path, is_tmp in _split_wav(wav_path, self.chunk_seconds):
            send_path, small = chunk_path, None
            if self.compress_bitrate:
                small = await asyncio.to_thread(_compress, chunk_path, self.compress_bitrate)
                send_path = small or chunk_path
            t0 = time.monotonic()
            try:
                j = await self._post_with_retry(send_path, language)
            finally:
                log.warning("stt %s: chunk@%.0fs sent %d KB in %.1fs", self.name, offset,
                            os.path.getsize(send_path) // 1024 if os.path.exists(send_path) else -1, time.monotonic() - t0)
                if small:
                    os.unlink(small)
                if is_tmp:
                    os.unlink(chunk_path)
            part = [Segment(s["start"] + offset, s["end"] + offset, s["text"].strip()) for s in j.get("segments", [])]
            if not part and j.get("text"):
                part = [Segment(offset, offset + float(j.get("duration", 0)), j["text"].strip())]
            segs.extend(part)
        return Transcript(segs, language, self.name, raw=None)

    async def _post_with_retry(self, path: str, language: str) -> dict:
        data = {"model": self.model, "language": language, "response_format": "verbose_json",
                "timestamp_granularities[]": "segment"}
        if self.prompt:
            data["prompt"] = self.prompt
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


def _split_wav(path: str, chunk_seconds: int):
    """(offset_sec, path, is_temp) — فایل کوتاه همان‌طور ارسال می‌شود؛ فایل بلند به تکه‌های chunk_seconds ثانیه‌ای."""
    with wave.open(path, "rb") as w:
        rate, n = w.getframerate(), w.getnframes()
        per = max(1, int(chunk_seconds * rate))
        if n <= per:
            yield 0.0, path, False
            return
        params = w.getparams()
        pos = 0
        while pos < n:
            frames = w.readframes(min(per, n - pos))
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            with wave.open(tmp, "wb") as o:
                o.setparams(params)
                o.writeframes(frames)
            yield pos / rate, tmp, True
            pos += per
