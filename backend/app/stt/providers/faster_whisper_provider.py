from __future__ import annotations

import asyncio

from app.stt.base import ProviderUnavailable, Segment, Transcript


class FasterWhisperSTT:
    """STT کاملاً محلی؛ نیازمند `pip install faster-whisper`."""

    name = "faster_whisper"

    def __init__(self, model_size: str = "large-v3", device: str = "auto", initial_prompt: str = ""):
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as e:
            raise ProviderUnavailable("faster-whisper نصب نیست") from e
        self.model = WhisperModel(model_size, device=device)
        self.prompt = initial_prompt

    def _run(self, wav_path: str, language: str) -> Transcript:
        segs, _ = self.model.transcribe(wav_path, language=language, vad_filter=True,
                                        initial_prompt=self.prompt or None)
        return Transcript([Segment(s.start, s.end, s.text.strip(), None, getattr(s, "avg_logprob", None))
                           for s in segs], language, self.name)

    async def transcribe(self, wav_path: str, *, language: str = "fa") -> Transcript:
        return await asyncio.to_thread(self._run, wav_path, language)
