"""موتور تحلیل: Claude با tool use + اعتبارسنجی + امتیازدهی در کد."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.analysis import prompts
from app.analysis.metrics import compute_metrics, format_transcript
from app.analysis.redact import redact
from app.analysis.rubric_loader import Rubric
from app.analysis.schema import SCHEMA_VERSION, build_result_model, tool_schema
from app.analysis.scoring import compute_overall, percentile_rank  # noqa: F401
from app.analysis.verify import drop_unverified_compliance, verify_evidence
from app.stt.base import Transcript

log = logging.getLogger(__name__)


class LLMClient(Protocol):
    async def call_tool(self, *, system: list[dict], user: str, tool: dict, model: str,
                        temperature: float) -> tuple[dict, dict]:
        """(ورودی ابزار، usage)"""


class AnthropicLLM:
    def __init__(self, api_key: str):
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY تنظیم نشده است")
        import anthropic  # type: ignore
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def call_tool(self, *, system, user, tool, model, temperature):
        r = await self.client.messages.create(
            model=model, max_tokens=8000, temperature=temperature, system=system,
            tools=[tool], tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": user}])
        block = next((b for b in r.content if getattr(b, "type", "") == "tool_use"), None)
        if block is None:
            raise ValueError("پاسخ مدل شامل ابزار نبود")
        u = r.usage
        usage = {"tokens_in": u.input_tokens, "tokens_out": u.output_tokens,
                 "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}
        return dict(block.input), usage


@dataclass
class AnalysisOutput:
    result: dict
    usage: dict
    prompt_version: str


def resolve_roles(result: dict) -> tuple[str | None, str | None]:
    p = result.get("participants") or {}
    return p.get("seller_speaker"), p.get("customer_speaker")


class Analyzer:
    def __init__(self, rubric: Rubric, llm: LLMClient, model: str, redact_pii: bool = True):
        self.rubric, self.llm, self.model, self.redact_pii = rubric, llm, model, redact_pii
        self.Result = build_result_model(rubric)
        self.tool = tool_schema(rubric)
        self.system = prompts.build_system_blocks(rubric)

    async def analyze(self, transcript: Transcript, meta: dict, *, seller_speaker: str | None = None,
                      call_type_hint: str | None = None) -> AnalysisOutput:
        lex = self.rubric.config.get("lexicons", {})
        metrics = compute_metrics(transcript.segments, seller_speaker, lex)
        text = format_transcript(transcript.segments)
        plain_for_verify = text
        if self.redact_pii:
            text = redact(text)
        user = prompts.build_user_message(text, meta, metrics, call_type_hint, transcript.diarized)
        usage_total = {"tokens_in": 0, "tokens_out": 0, "cache_read": 0, "cache_write": 0}
        raw: dict = {}
        err: str | None = None
        model_obj = None
        for attempt in range(2):  # یک بار retry با پیام خطا
            msg = user if err is None else f"{user}\n\n<validation_error>خروجی قبلی نامعتبر بود: {err}\nاصلاح کن.</validation_error>"
            raw, usage = await self.llm.call_tool(system=self.system, user=msg, tool=self.tool,
                                                  model=self.model, temperature=0.1)
            for k in usage_total:
                usage_total[k] += usage.get(k, 0)
            try:
                model_obj = self.Result.model_validate(raw)
                break
            except ValidationError as e:
                err = str(e)[:600]
                log.warning("schema validation failed (attempt %d)", attempt + 1)
        if model_obj is None:
            raise ValueError("خروجی تحلیل معتبر نبود")
        result = model_obj.model_dump(mode="json")
        return AnalysisOutput(self.finalize(result, plain_for_verify, metrics), usage_total, prompts.PROMPT_VERSION)

    def finalize(self, result: dict, transcript_text: str, metrics: dict | None = None) -> dict:
        r = self.rubric
        result["schema_version"], result["rubric_version"] = SCHEMA_VERSION, r.version
        result["computed_metrics"] = metrics or {}
        cv = result["call_validity"]
        if not cv["is_analyzable"]:
            result["overall"] = {**result.get("overall", {}), "score": None, "grade": None,
                                 "rank_label": "قابل‌تحلیل نیست", "penalties_applied": []}
            return result
        verify_evidence(result, transcript_text)
        drop_unverified_compliance(result)
        # criteria: نام فارسی را از روبریک پر کن
        names = {c["id"]: c["name"] for c in r.criteria}
        for c in result["criteria"]:
            c["name"] = c.get("name") or names.get(c["id"], c["id"])
            c["max_score"] = 10
            if c["applicable"] and c["score"] is None:
                c["applicable"] = False
        flags = result.get("seller_performance", {}).get("compliance_flags", [])
        s = compute_overall(result["criteria"], r.weights, r.applies_to, cv.get("call_type"), flags, r.config)
        conf = float(result.get("overall", {}).get("confidence", 0.5))
        result["overall"].update({"score": s.score, "raw_score": s.raw_score, "grade": s.grade,
                                  "rank_label": s.rank_label,
                                  "penalties_applied": s.penalties_applied, "reliable": s.reliable,
                                  "applicable_weight": s.applicable_weight, "confidence": conf})
        warns = result.setdefault("warnings", [])
        if not s.reliable:
            warns.append("امتیاز کل کم‌اعتبار است (وزن معیارهای قابل‌اعمال کم است).")
        th = r.config["scoring"]["role_confidence_threshold"]
        if cv.get("role_assignment_confidence", 1) < th:
            warns.append("تفکیک گوینده‌ها نامطمئن است؛ معیارهای وابسته به نقش را با احتیاط تفسیر کنید.")
            for c in result["criteria"]:
                if c["id"] in {"active_listening", "questioning_technique", "rapport_trust"}:
                    c["confidence"] = min(c["confidence"], 0.4)
        return result
