from __future__ import annotations

import json

import httpx

from app.stt.base import ProviderUnavailable, Segment, Transcript


class CustomHttpSTT:
    """آداپتور عمومی برای سرویس‌های STT داخلی.

    کانفیگ: url، headers، file_field، params و نگاشت پاسخ (segments_path و کلیدهای start/end/text/speaker).
    """

    name = "custom_http"

    def __init__(self, config: dict):
        if not config.get("url"):
            raise ProviderUnavailable("custom_http: url تنظیم نشده است")
        self.cfg = config

    async def transcribe(self, wav_path: str, *, language: str = "fa") -> Transcript:
        c = self.cfg
        async with httpx.AsyncClient(timeout=c.get("timeout", 300)) as cl:
            with open(wav_path, "rb") as f:
                r = await cl.post(c["url"], headers=c.get("headers", {}), params=c.get("params", {}),
                                  files={c.get("file_field", "file"): ("audio.wav", f, "audio/wav")})
        r.raise_for_status()
        j = r.json()
        for key in c.get("segments_path", "segments").split("."):
            j = j[key]
        m = {"start": "start", "end": "end", "text": "text", "speaker": "speaker"} | c.get("mapping", {})
        return Transcript([Segment(float(s[m["start"]]), float(s[m["end"]]), str(s[m["text"]]).strip(),
                                   s.get(m["speaker"])) for s in j], language, self.name,
                          diarized=any(s.get(m["speaker"]) for s in j))
