"""مدل تحلیل با Google Gemini (API رایگان AI Studio) به‌جای Anthropic.

چرا JSON mode و نه tool use: schema این پروژه بزرگ است و Gemini فقط زیرمجموعه‌ای از JSON Schema را در function calling می‌پذیرد.
پس schema ابزار به‌صورت متن در پیام می‌آید، خروجی JSON (responseMimeType) گرفته می‌شود و مثل Claude با pydantic اعتبارسنجی می‌شود
(Analyzer در صورت نامعتبر بودن یک بار دوباره می‌پرسد).
هشدار حریم خصوصی: در حالت رایگان Google ممکن است ورودی/خروجی را برای بهبود محصولاتش استفاده کند.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time

import httpx

from app.analysis.errors import LLMError

log = logging.getLogger(__name__)
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _extract_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no json object")
    return json.loads(t[a:b + 1])  # از { تا } همیشه شیء است؛ خطای سینتکس = ValueError


class GeminiLLM:
    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 thinking_budget: int | None = None, max_retries: int = 3, sleep=asyncio.sleep):
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY تنظیم نشده است")
        self.api_key, self.transport, self.thinking_budget = api_key, transport, thinking_budget
        self.max_retries, self._sleep = max_retries, sleep

    async def _post(self, model: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=300, transport=self.transport) as c:
            for i in range(self.max_retries + 1):
                t0 = time.monotonic()
                r = await c.post(URL.format(model=model), json=body, headers={"x-goog-api-key": self.api_key})
                log.warning("gemini %s: http %s in %.1fs (attempt %d)", model, r.status_code, time.monotonic() - t0, i + 1)
                if r.status_code == 200:
                    return r.json()
                if r.status_code in _RETRY_STATUS and i < self.max_retries:
                    await self._sleep(min(60, 15 * 2 ** i))
                    continue
                if r.status_code == 429:
                    raise LLMError("llm_rate_limit", "سهمیه‌ی رایگان Gemini موقتاً تمام شده است؛ کمی بعد دوباره تلاش کنید.")
                if r.status_code in (400, 403) and "API key" in r.text:
                    raise LLMError("llm_auth", "کلید Gemini نامعتبر است (GEMINI_API_KEY).")
                if r.status_code == 404:
                    raise LLMError("llm_model", f"مدل «{model}» پیدا نشد؛ ANALYSIS_MODEL را بررسی کنید.")
                log.error("gemini http %s", r.status_code)  # بدون بدنه (ممکن است محتوا داشته باشد)
                raise LLMError("llm_http", f"خطای Gemini ({r.status_code}).")
        raise LLMError("llm_http", "خطای Gemini.")

    async def call_tool(self, *, system, user, tool, model, temperature):
        schema = json.dumps(tool["input_schema"], ensure_ascii=False)
        sys_text = "\n\n".join(b["text"] for b in system)
        prompt = (f"{user}\n\nبه‌جای فراخوانی ابزار، خروجی را مستقیماً فقط به‌صورت «یک شیء JSON» برگردان که دقیقاً مطابق JSON Schema زیر باشد "
                  f"(همان آرگومان‌های {tool['name']}؛ بدون هیچ متن، توضیح یا کد-بلاک اضافه).\n<json_schema>\n{schema}\n</json_schema>")
        gen: dict = {"temperature": temperature, "responseMimeType": "application/json", "maxOutputTokens": 32768}
        if self.thinking_budget is not None:
            gen["thinkingConfig"] = {"thinkingBudget": self.thinking_budget}
        body = {"systemInstruction": {"parts": [{"text": sys_text}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": gen}
        tin = tout = 0
        for attempt in range(2):  # یک بار دوباره اگر JSON خراب یا نیمه‌کاره بود
            j = await self._post(model, body)
            um = j.get("usageMetadata", {})
            tin += um.get("promptTokenCount", 0)
            tout += um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0)
            cands = j.get("candidates") or []
            if not cands:
                reason = (j.get("promptFeedback") or {}).get("blockReason", "unknown")
                raise LLMError("llm_blocked", f"Gemini پاسخی نداد ({reason}).")
            text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
            try:
                usage = {"tokens_in": tin, "tokens_out": tout, "cache_read": 0, "cache_write": 0}
                return _extract_json(text), usage
            except ValueError:
                log.warning("gemini returned non-json (attempt %d)", attempt + 1)
        raise LLMError("llm_bad_output", "خروجی Gemini JSON معتبر نبود؛ دوباره تلاش کنید.")
