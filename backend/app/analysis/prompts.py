"""ساخت پرامپت: بخش ثابت (قابل cache) + بخش متغیر."""
from __future__ import annotations

import json
from pathlib import Path

from app.analysis.rubric_loader import Rubric

PROMPT_VERSION = "1.0.0"
_BASE = (Path(__file__).parent / "_system_prompt.txt").read_text(encoding="utf-8")


def build_system_blocks(rubric: Rubric) -> list[dict]:
    """بلوک‌های system با cache_control روی آخرین بلوک ثابت."""
    enums = {
        "call_type": rubric.ids("call_type_ids"), "customer_stage": rubric.ids("customer_stage_ids"),
        "objection_type": rubric.ids("objection_type_ids"), "seller_style": rubric.ids("seller_style_ids"),
        "sales_stages": rubric.ids("sales_stage_ids"), "criteria_ids": [c["id"] for c in rubric.criteria],
    }
    text = (f"{_BASE}\n\n<rubric>\n{rubric.rubric_md}\n</rubric>\n\n"
            f"<business_context>\n{rubric.business_md}\n</business_context>\n\n"
            f"<allowed_ids>\n{json.dumps(enums, ensure_ascii=False)}\n</allowed_ids>")
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def build_user_message(transcript_text: str, meta: dict, metrics: dict, call_type_hint: str | None,
                       diarized: bool) -> str:
    parts = [
        "<call_metadata>", json.dumps(meta, ensure_ascii=False), "</call_metadata>",
        "<computed_metrics note=\"راهنما؛ در diarization ضعیف کم‌اعتبار\">", json.dumps(metrics, ensure_ascii=False),
        "</computed_metrics>",
    ]
    if call_type_hint:
        parts.append(f"<call_type_hint>{call_type_hint}</call_type_hint>")
    if not diarized:
        parts.append("<note>ترنسکریپت برچسب گوینده ندارد؛ نقش‌ها را از محتوا حدس بزن و اطمینان را پایین بیاور.</note>")
    parts += ["<transcript>", transcript_text.replace("</transcript>", ""), "</transcript>",
              "تحلیل را فقط با ابزار submit_analysis ارسال کن."]
    return "\n".join(parts)
