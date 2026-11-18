"""پیش‌پردازش صوت با ffmpeg + VAD انرژی‌محور (بدون وابستگی خارجی)."""
from __future__ import annotations

import array
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path


class AudioError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class AudioInfo:
    duration: float
    speech_ratio: float
    rms: float
    looks_like_voicemail: bool = False


def is_riff_wave(head: bytes) -> bool:
    return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"


def build_ffmpeg_args(src: str, dst: str, *, normalize: bool = True, trim_silence: bool = True,
                      denoise: bool = False) -> list[str]:
    filters = ["highpass=f=60"]  # حذف DC offset و رامبل
    if denoise:
        filters.append("afftdn=nf=-25")
    if trim_silence:
        filters.append("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.3")
        filters.append("areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.3,areverse")
    if normalize:
        filters.append("dynaudnorm")
    return ["ffmpeg", "-nostdin", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
            "-af", ",".join(filters), "-c:a", "pcm_s16le", dst]


def preprocess(src: str, dst: str, **opts) -> None:
    try:
        r = subprocess.run(build_ffmpeg_args(src, dst, **opts), capture_output=True, timeout=180)
    except FileNotFoundError as e:
        raise AudioError("ffmpeg_missing", "ffmpeg نصب نیست") from e
    except subprocess.TimeoutExpired as e:
        raise AudioError("ffmpeg_timeout", "پیش‌پردازش صوت بیش از حد طول کشید") from e
    if r.returncode != 0 or not Path(dst).exists():
        raise AudioError("ffmpeg_failed", "فایل صوتی قابل‌پردازش نیست")


def analyze_wav(path: str, frame_ms: int = 30, rel_threshold: float = 0.1) -> AudioInfo:
    """VAD ساده: فریم‌هایی که انرژی‌شان از نسبتی از انرژی بالاترین‌ها بیشتر است گفتار حساب می‌شوند."""
    with wave.open(path, "rb") as w:
        n, sr, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw != 2:
        raise AudioError("bad_format", "فقط PCM16 پشتیبانی می‌شود")
    samples = array.array("h")
    samples.frombytes(raw)
    if ch > 1:
        samples = samples[::ch]
    duration = len(samples) / sr if sr else 0.0
    if not samples:
        return AudioInfo(0.0, 0.0, 0.0)
    fl = max(1, int(sr * frame_ms / 1000))
    energies = []
    for i in range(0, len(samples) - fl + 1, fl):
        fr = samples[i:i + fl]
        energies.append((sum(x * x for x in fr) / fl) ** 0.5)
    rms = (sum(x * x for x in samples) / len(samples)) ** 0.5
    if not energies:
        return AudioInfo(duration, 0.0, rms)
    peak = sorted(energies)[int(len(energies) * 0.95) - 1 if len(energies) > 20 else -1]
    thr = max(peak * rel_threshold, 30.0)
    speech = sum(1 for e in energies if e > thr)
    return AudioInfo(duration, speech / len(energies), rms)


def looks_like_voicemail(duration: float, distinct_speakers: int, text: str) -> bool:
    keys = ("پیغام‌گیر", "پیام‌گیر", "صندوق صوتی", "پس از صدای بوق", "پس از شنیدن بوق", "در دسترس نیست",
            "خاموش می‌باشد", "مشترک مورد نظر")
    return any(k in text for k in keys) or (duration < 25 and distinct_speakers <= 1 and len(text) < 120 and
                                            any(k in text for k in ("بوق", "پیام")))
