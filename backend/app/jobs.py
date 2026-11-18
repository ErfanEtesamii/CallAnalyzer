"""پایپ‌لاین پردازش: queued → preprocessing → transcribing → analyzing → done|failed."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from app.analysis.analyzer import Analyzer
from app.analysis.errors import LLMError
from app.analysis.scoring import percentile_rank
from app.audio import preprocess as pp
from app.config import Settings
from app.db import DB
from app.stt.base import ProviderUnavailable, Segment, Transcript
from app.util import normalize_fa_text

log = logging.getLogger(__name__)

STAGE_TIMEOUT = {"preprocessing": 180, "transcribing": 1200, "analyzing": 900}


class PipelineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


# هزینه‌ی تقریبی (دلار)؛ قابل‌ویرایش
COST = {"stt_per_min": 0.006, "llm_in_per_m": 3.0, "llm_out_per_m": 15.0}


def estimate_llm_cost(tin: int, tout: int) -> float:
    return tin / 1e6 * COST["llm_in_per_m"] + tout / 1e6 * COST["llm_out_per_m"]


def guess_roles(segments: list[Segment]) -> str | None:
    """گوینده‌ی اول را فروشنده فرض می‌کنیم (تماس خروجی)؛ نهایی‌سازی با Claude/اصلاح دستی."""
    for s in segments:
        if s.speaker:
            return s.speaker
    return None


@dataclass
class Pipeline:
    settings: Settings
    db: DB
    stt_factory: Callable[[], object]
    analyzer: Analyzer
    sellers: dict = field(default_factory=dict)
    events: dict[int, list[Callable[[str], None]]] = field(default_factory=dict)
    inflight: dict[str, asyncio.Task] = field(default_factory=dict)

    def emit(self, aid: int, status: str) -> None:
        for cb in self.events.get(aid, []):
            cb(status)

    def set_status(self, aid: int, status: str, **kw) -> None:
        self.db.update_analysis(aid, status=status, **kw)
        self.emit(aid, status)

    async def run(self, aid: int, raw_path: str) -> None:
        """اجرای کامل؛ هیچ استثنایی به بیرون نشت نمی‌کند."""
        try:
            if self.db.spend_today() >= self.settings.daily_budget_usd:
                raise PipelineError("budget_exceeded", "سقف بودجه‌ی روزانه پر شده است")
            a = self.db.get(aid)
            self.set_status(aid, "preprocessing")
            proc = str(Path(raw_path).with_suffix(".proc.wav"))
            await asyncio.wait_for(asyncio.to_thread(pp.preprocess, raw_path, proc), STAGE_TIMEOUT["preprocessing"])
            info = await asyncio.to_thread(pp.analyze_wav, proc)
            self.db.update_analysis(aid, real_duration=info.duration)
            if info.speech_ratio < self.settings.min_speech_ratio or info.duration < 3:
                self.db.save_transcript(aid, "none", [], {"speech_ratio": info.speech_ratio})
                self._close_no_conversation(aid, "نسبت گفتار بسیار کم است (احتمالاً بوق/سکوت/پیغام‌گیر).")
                return
            self.set_status(aid, "transcribing")
            tr = await asyncio.wait_for(self.stt_factory().transcribe(proc, language="fa"), STAGE_TIMEOUT["transcribing"])
            for s in tr.segments:
                s.text = normalize_fa_text(s.text)
            tr.segments = [s for s in tr.segments if s.text]
            self.db.save_transcript(aid, tr.provider, tr.to_json(), {"speech_ratio": info.speech_ratio, "rms": info.rms})
            self.db.log_usage(aid, "stt", tr.provider, secs=info.duration, cost=0.0 if self.settings.stt_provider == "groq" else info.duration / 60 * COST["stt_per_min"])
            text = " ".join(s.text for s in tr.segments)
            if pp.looks_like_voicemail(info.duration, len({s.speaker for s in tr.segments if s.speaker}), text):
                self._close_no_conversation(aid, "پیغام‌گیر/صندوق صوتی تشخیص داده شد.")
                return
            await self.analyze_transcript(aid, tr)
        except PipelineError as e:
            self.set_status(aid, "failed", error_code=e.code, error_message=e.message)
        except asyncio.TimeoutError:
            self.set_status(aid, "failed", error_code="timeout", error_message="پردازش بیش از حد طول کشید؛ دوباره تلاش کنید.")
        except pp.AudioError as e:
            self.set_status(aid, "failed", error_code=e.code, error_message=e.message)
        except LLMError as e:
            self.set_status(aid, "failed", error_code=e.code, error_message=e.message)
        except ProviderUnavailable as e:
            self.set_status(aid, "failed", error_code="stt_unavailable", error_message=str(e))
        except Exception:  # noqa: BLE001
            log.exception("pipeline failed for analysis %s", aid)  # بدون محتوای مکالمه
            self.set_status(aid, "failed", error_code="internal", error_message="خطای داخلی در پردازش. دوباره تلاش کنید.")
        finally:
            self._cleanup_audio(aid, raw_path)

    def _close_no_conversation(self, aid: int, reason: str) -> None:
        res = {"schema_version": "1.0", "rubric_version": self.analyzer.rubric.version,
               "call_validity": {"is_analyzable": False, "reason": reason, "conversation_type": "no_conversation"},
               "overall": {"score": None, "grade": None, "rank_label": "قابل‌تحلیل نیست"},
               "customer_status": {"stage": "no_conversation", "interest_level": 0}, "warnings": [reason]}
        self.db.save_result(aid, res, "none", None)
        self.set_status(aid, "done")

    async def analyze_transcript(self, aid: int, tr: Transcript, seller_speaker: str | None = None) -> None:
        a = self.db.get(aid)
        self.set_status(aid, "analyzing")
        seller = seller_speaker or guess_roles(tr.segments)
        meta = {"call_datetime": a["call_datetime"], "duration_seconds": a["real_duration"], "direction": a["direction"],
                "seller_name": a["seller_name"]}
        out = await asyncio.wait_for(self.analyzer.analyze(tr, meta, seller_speaker=seller), STAGE_TIMEOUT["analyzing"])
        u = out.usage
        self.db.log_usage(aid, "analysis", self.analyzer.model, u["tokens_in"], u["tokens_out"],
                          cost=0.0 if self.settings.llm_provider != "anthropic" else estimate_llm_cost(u["tokens_in"], u["tokens_out"]))
        score = out.result["overall"].get("score")
        pct = percentile_rank(score, self.db.scores_population(a["seller_ext"]) + [score]) if score is not None else None
        self.db.save_result(aid, out.result, out.prompt_version, pct)
        self.db.update_analysis(aid, rubric_version=self.analyzer.rubric.version, model=self.analyzer.model)
        self.set_status(aid, "done", error_code=None, error_message=None)

    async def reanalyze(self, aid: int, seller_speaker: str | None = None) -> None:
        t = self.db.get_transcript(aid)
        if not t:
            raise PipelineError("no_transcript", "ترنسکریپت موجود نیست؛ تحلیل از ابتدا لازم است.")
        try:
            await self.analyze_transcript(aid, Transcript.from_json(t["segments"], t["provider"]), seller_speaker)
        except LLMError as e:
            self.set_status(aid, "failed", error_code=e.code, error_message=e.message)
        except Exception:  # noqa: BLE001
            log.exception("reanalyze failed %s", aid)
            self.set_status(aid, "failed", error_code="internal", error_message="تحلیل مجدد ناموفق بود.")

    def _cleanup_audio(self, aid: int, raw_path: str) -> None:
        keep = self.settings.retention_audio_days > 0
        for p in (raw_path, str(Path(raw_path).with_suffix(".proc.wav"))):
            if keep and p == raw_path:
                self.db.update_analysis(aid, audio_path=p)
                continue
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
