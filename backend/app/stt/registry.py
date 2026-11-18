from __future__ import annotations

from app.config import Settings
from app.stt.base import ProviderUnavailable, STTProvider


def build_provider(settings: Settings, name: str | None = None, vocab_prompt: str = "") -> STTProvider:
    name = (name or settings.stt_provider).lower()
    if name == "mock":
        from app.stt.providers.mock import MockSTT
        return MockSTT()
    if name == "openai":
        from app.stt.providers.openai_provider import OpenAISTT
        return OpenAISTT(settings.openai_api_key, prompt=vocab_prompt)
    if name in {"faster_whisper", "faster-whisper"}:
        from app.stt.providers.faster_whisper_provider import FasterWhisperSTT
        return FasterWhisperSTT(initial_prompt=vocab_prompt)
    if name == "custom_http":
        import json
        import os
        from app.stt.providers.custom_http import CustomHttpSTT
        return CustomHttpSTT(json.loads(os.environ.get("CUSTOM_STT_CONFIG", "{}")))
    raise ProviderUnavailable(f"ارائه‌دهنده‌ی STT ناشناخته: {name}")
