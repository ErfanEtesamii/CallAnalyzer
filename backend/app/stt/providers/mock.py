from __future__ import annotations

from app.stt.base import Segment, Transcript


class MockSTT:
    name = "mock"

    def __init__(self, segments: list[Segment] | None = None):
        self._segments = segments

    async def transcribe(self, wav_path: str, *, language: str = "fa") -> Transcript:
        segs = self._segments or [
            Segment(0, 4, "سلام وقت بخیر، از مجموعه‌ی فراز هنر تماس می‌گیرم", "SPEAKER_1"),
            Segment(4, 6, "سلام بفرمایید", "SPEAKER_2"),
        ]
        return Transcript(segs, language, self.name, diarized=True)
