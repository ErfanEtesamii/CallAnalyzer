"""بنچمارک STT: python scripts/benchmark_stt.py <پوشه> --providers openai faster_whisper
در پوشه: x.wav و (اختیاری) x.txt ترنسکریپت مرجع. خروجی: جدول Markdown و docs/stt-benchmark.md"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.audio.preprocess import analyze_wav, preprocess  # noqa: E402
from app.config import Settings  # noqa: E402
from app.stt.registry import build_provider  # noqa: E402
from app.util import normalize_fa_text  # noqa: E402


def edit_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def wer(ref: str, hyp: str) -> float:
    r, h = normalize_fa_text(ref).split(), normalize_fa_text(hyp).split()
    return edit_distance(r, h) / max(1, len(r))


def cer(ref: str, hyp: str) -> float:
    r, h = list(normalize_fa_text(ref).replace(" ", "")), list(normalize_fa_text(hyp).replace(" ", ""))
    return edit_distance(r, h) / max(1, len(r))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder"); ap.add_argument("--providers", nargs="+", default=["mock"])
    ap.add_argument("--price-per-min", type=float, default=0.006)
    a = ap.parse_args()
    s = Settings.from_env()
    rows = ["| فایل | ارائه‌دهنده | WER | CER | زمان (ث) | هزینه‌ی تقریبی ($) |", "|---|---|---|---|---|---|"]
    for wav in sorted(Path(a.folder).glob("*.wav")):
        proc = wav.with_suffix(".bench.wav"); preprocess(str(wav), str(proc))
        dur = analyze_wav(str(proc)).duration
        ref_p = wav.with_suffix(".txt"); ref = ref_p.read_text(encoding="utf-8") if ref_p.exists() else None
        for name in a.providers:
            try:
                p = build_provider(s, name); t0 = time.time()
                tr = await p.transcribe(str(proc)); el = time.time() - t0
                hyp = " ".join(x.text for x in tr.segments)
                rows.append(f"| {wav.name} | {name} | {wer(ref, hyp):.2%} | {cer(ref, hyp):.2%} | {el:.1f} | {dur / 60 * a.price_per_min:.4f} |"
                            if ref else f"| {wav.name} | {name} | - | - | {el:.1f} | {dur / 60 * a.price_per_min:.4f} |")
            except Exception as e:  # noqa: BLE001
                rows.append(f"| {wav.name} | {name} | خطا: {type(e).__name__} | | | |")
        proc.unlink(missing_ok=True)
    out = "\n".join(rows); print(out)
    Path("../docs").mkdir(exist_ok=True); Path("../docs/stt-benchmark.md").write_text("# بنچمارک STT\n\n" + out + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
