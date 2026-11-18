from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None
    confidence: float | None = None


@dataclass
class Transcript:
    segments: list[Segment]
    language: str = "fa"
    provider: str = ""
    raw: Any = None
    diarized: bool = False

    def to_json(self) -> list[dict]:
        return [s.__dict__.copy() for s in self.segments]

    @classmethod
    def from_json(cls, data: list[dict], provider: str = "") -> "Transcript":
        segs = [Segment(**d) for d in data]
        return cls(segs, provider=provider, diarized=any(s.speaker for s in segs))


class STTProvider(Protocol):
    name: str

    async def transcribe(self, wav_path: str, *, language: str = "fa") -> Transcript: ...


class ProviderUnavailable(RuntimeError):
    """کلید/وابستگی ارائه‌دهنده موجود نیست."""
