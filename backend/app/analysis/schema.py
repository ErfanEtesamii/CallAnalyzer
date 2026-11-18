"""طرح خروجی تحلیل: JSON Schema ابزار + اعتبارسنجی Pydantic پویا از روی روبریک."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, create_model, field_validator

from app.analysis.rubric_loader import Rubric

SCHEMA_VERSION = "1.0"


class Evidence(BaseModel):
    timestamp: str = ""
    speaker: str = ""
    quote: str = ""
    verified: Optional[bool] = None


class Criterion(BaseModel):
    id: str
    name: str = ""
    score: Optional[float] = Field(None, ge=0, le=10)
    max_score: int = 10
    applicable: bool = True
    confidence: float = Field(0.5, ge=0, le=1)
    reasoning: str = ""
    evidence: list[Evidence] = []
    improvement: str = ""
    better_phrase_example: str = ""


class CompatDict(BaseModel):
    model_config = {"extra": "allow"}


def build_result_model(r: Rubric) -> type[BaseModel]:
    """مدل خروجی با Enumهای گرفته‌شده از روبریک (چیزی hard-code نیست)."""
    call_types, stages = set(r.ids("call_type_ids")), set(r.ids("customer_stage_ids"))
    crit_ids = {c["id"] for c in r.criteria}

    class Validity(CompatDict):
        is_analyzable: bool
        reason: Optional[str] = None
        call_type: Optional[str] = None
        conversation_type: str = "sales_call"
        transcript_quality: str = "fair"
        role_assignment_confidence: float = Field(0.5, ge=0, le=1)

        @field_validator("call_type")
        @classmethod
        def _ct(cls, v):
            if v is not None and v not in call_types:
                raise ValueError(f"call_type نامعتبر: {v}")
            return v

    class CustomerStatus(CompatDict):
        stage: str
        interest_level: float = Field(0, ge=0, le=10)
        buying_signals: list[dict] = []
        objections: list[dict] = []
        decision_maker: str = "unknown"
        sentiment_trajectory: str = "stable"

        @field_validator("stage")
        @classmethod
        def _st(cls, v):
            if v not in stages:
                raise ValueError(f"stage نامعتبر: {v}")
            return v

    class Overall(CompatDict):
        confidence: float = Field(0.5, ge=0, le=1)
        headline: str = ""

    class Result(CompatDict):
        call_validity: Validity
        summary: str = ""
        participants: dict = {}
        sales_process: dict = {}
        overall: Overall = Overall()
        criteria: list[Criterion] = []
        customer_status: Optional[CustomerStatus] = None
        lead_info: dict = {}
        seller_performance: dict = {}
        next_best_action: dict = {}
        coaching: dict = {}
        warnings: list[str] = []

        @field_validator("criteria")
        @classmethod
        def _crit(cls, v):
            bad = [c.id for c in v if c.id not in crit_ids]
            if bad:
                raise ValueError(f"شناسه‌ی معیار نامعتبر: {bad}")
            if len({c.id for c in v}) != len(v):
                raise ValueError("معیار تکراری")
            return v

    return Result


def tool_schema(r: Rubric) -> dict[str, Any]:
    """JSON Schema ابزار submit_analysis برای tool use."""
    ev = {"type": "object", "properties": {"timestamp": {"type": "string"}, "speaker": {"type": "string"},
                                            "quote": {"type": "string"}}, "required": ["timestamp", "quote"]}
    crit = {"type": "object", "required": ["id", "applicable", "reasoning"], "properties": {
        "id": {"type": "string", "enum": [c["id"] for c in r.criteria]},
        "name": {"type": "string"}, "score": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
        "applicable": {"type": "boolean"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string"}, "evidence": {"type": "array", "items": ev},
        "improvement": {"type": "string"}, "better_phrase_example": {"type": "string"}}}
    obj = {"type": "object"}
    return {
        "name": "submit_analysis",
        "description": "ارسال تحلیل ساختاریافته‌ی مکالمه مطابق روبریک.",
        "input_schema": {"type": "object", "required": ["call_validity", "summary", "criteria"], "properties": {
            "call_validity": {"type": "object", "required": ["is_analyzable"], "properties": {
                "is_analyzable": {"type": "boolean"}, "reason": {"type": ["string", "null"]},
                "call_type": {"type": ["string", "null"], "enum": r.ids("call_type_ids") + [None]},
                "conversation_type": {"type": "string"}, "transcript_quality": {"type": "string"},
                "role_assignment_confidence": {"type": "number", "minimum": 0, "maximum": 1}}},
            "summary": {"type": "string"}, "participants": obj, "sales_process": obj,
            "overall": {"type": "object", "properties": {"confidence": {"type": "number"}, "headline": {"type": "string"}}},
            "criteria": {"type": "array", "items": crit},
            "customer_status": {"type": "object", "required": ["stage"], "properties": {
                "stage": {"type": "string", "enum": r.ids("customer_stage_ids")},
                "interest_level": {"type": "number", "minimum": 0, "maximum": 10},
                "buying_signals": {"type": "array", "items": obj}, "objections": {"type": "array", "items": obj},
                "decision_maker": {"type": "string"}, "sentiment_trajectory": {"type": "string"}}},
            "lead_info": obj, "seller_performance": obj, "next_best_action": obj, "coaching": obj,
            "warnings": {"type": "array", "items": {"type": "string"}}}},
    }
