from __future__ import annotations

import httpx

from app.stt.base import ProviderUnavailable, Segment, Transcript


class OpenAISTT:
    """OpenAI Whisper API. gpt-4o-transcribe زمان‌بندی segment نمی‌دهد؛ برای timestamp از whisper-1 استفاده می‌شود."""

    name = "openai"

    def __init__(self, api_key: str, model: str = "whisper-1", prompt: str = "", *,
                 base_url: str = "https://api.openai.com/v1", name: str = "openai", key_name: str = "OPENAI_API_KEY",
                 max_prompt_chars: int = 0, transport: httpx.AsyncBaseTransport | None = None):
        if not api_key:
            raise ProviderUnavailable(f"{key_name} تنظیم نشده است")
        self.name = name
        self.api_key, self.model, self.base_url, self.transport = api_key, model, base_url.rstrip("/"), transport
        self.prompt = prompt[:max_prompt_chars] if max_prompt_chars else prompt  # Groq: prompt حداکثر ~۲۲۴ توکن

    async def transcribe(self, wav_path: str, *, language: str = "fa") -> Transcript:
        data = {"model": self.model, "language": language, "response_format": "verbose_json",
                "timestamp_granularities[]": "segment"}
        if self.prompt:
            data["prompt"] = self.prompt
        async with httpx.AsyncClient(timeout=300, transport=self.transport) as c:
            with open(wav_path, "rb") as f:
                r = await c.post(f"{self.base_url}/audio/transcriptions",
                                 headers={"Authorization": f"Bearer {self.api_key}"},
                                 data=data, files={"file": ("audio.wav", f, "audio/wav")})
        if r.status_code == 429:
            raise ProviderUnavailable("سهمیه‌ی رونویسی (STT) موقتاً تمام شده است؛ کمی بعد دوباره تلاش کنید.")
        if r.status_code in (401, 403):
            raise ProviderUnavailable("کلید STT نامعتبر است.")
        r.raise_for_status()
        j = r.json()
        segs = [Segment(s["start"], s["end"], s["text"].strip()) for s in j.get("segments", [])]
        if not segs and j.get("text"):
            segs = [Segment(0, float(j.get("duration", 0)), j["text"].strip())]
        return Transcript(segs, language, self.name, raw=None)
