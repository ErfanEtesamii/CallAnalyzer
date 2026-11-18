from __future__ import annotations

import httpx

from app.stt.base import ProviderUnavailable, Segment, Transcript


class OpenAISTT:
    """OpenAI Whisper API. gpt-4o-transcribe زمان‌بندی segment نمی‌دهد؛ برای timestamp از whisper-1 استفاده می‌شود."""

    name = "openai"

    def __init__(self, api_key: str, model: str = "whisper-1", prompt: str = ""):
        if not api_key:
            raise ProviderUnavailable("OPENAI_API_KEY تنظیم نشده است")
        self.api_key, self.model, self.prompt = api_key, model, prompt

    async def transcribe(self, wav_path: str, *, language: str = "fa") -> Transcript:
        data = {"model": self.model, "language": language, "response_format": "verbose_json",
                "timestamp_granularities[]": "segment"}
        if self.prompt:
            data["prompt"] = self.prompt
        async with httpx.AsyncClient(timeout=300) as c:
            with open(wav_path, "rb") as f:
                r = await c.post("https://api.openai.com/v1/audio/transcriptions",
                                 headers={"Authorization": f"Bearer {self.api_key}"},
                                 data=data, files={"file": ("audio.wav", f, "audio/wav")})
        r.raise_for_status()
        j = r.json()
        segs = [Segment(s["start"], s["end"], s["text"].strip()) for s in j.get("segments", [])]
        if not segs and j.get("text"):
            segs = [Segment(0, float(j.get("duration", 0)), j["text"].strip())]
        return Transcript(segs, language, self.name, raw=None)
