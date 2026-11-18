"""مدل تحلیل با هر API سازگار با OpenAI (پیش‌فرض DeepSeek). خروجی JSON (response_format=json_object) و schema ابزار به‌صورت متن در پیام،
مثل GeminiLLM؛ Analyzer در صورت نامعتبر بودن خروجی یک بار دوباره می‌پرسد."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import httpx

from app.analysis.errors import LLMError
from app.analysis.gemini import _extract_json

log = logging.getLogger(__name__)
_RETRY = {429, 500, 502, 503, 504}


class OpenAICompatLLM:
    def __init__(self, api_key: str, *, base_url: str = "https://api.deepseek.com", key_name: str = "DEEPSEEK_API_KEY",
                 max_tokens: int | None = None, transport: httpx.AsyncBaseTransport | None = None, max_retries: int = 3,
                 sleep=asyncio.sleep, timeout: float = 240):
        if not api_key:
            raise RuntimeError(f"{key_name} تنظیم نشده است")
        self.api_key, self.base_url, self.transport = api_key, base_url.rstrip("/"), transport
        self.max_tokens = max_tokens or int(os.environ.get("LLM_MAX_TOKENS", "8192"))
        self.max_retries, self._sleep, self.timeout = max_retries, sleep, timeout

    async def _post(self, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as c:
            for i in range(self.max_retries + 1):
                t0 = time.monotonic()
                r = await c.post(f"{self.base_url}/chat/completions", json=body, headers={"Authorization": f"Bearer {self.api_key}"})
                log.warning("llm %s: http %s in %.1fs (attempt %d)", body["model"], r.status_code, time.monotonic() - t0, i + 1)
                if r.status_code == 200:
                    return r.json()
                if r.status_code in _RETRY and i < self.max_retries:
                    await self._sleep(min(30, 5 * 2 ** i))
                    continue
                if r.status_code == 401:
                    raise LLMError("llm_auth", "کلید مدل زبانی نامعتبر است (DEEPSEEK_API_KEY).")
                if r.status_code == 402:
                    raise LLMError("llm_balance", "اعتبار حساب مدل زبانی تمام شده است.")
                if r.status_code == 404 or (r.status_code == 400 and "model" in r.text.lower() and "exist" in r.text.lower()):
                    raise LLMError("llm_model", f"مدل «{body['model']}» پیدا نشد؛ ANALYSIS_MODEL را بررسی کنید.")
                why = ""
                try:
                    why = str((r.json().get("error") or {}).get("message", ""))[:300]
                except ValueError:
                    pass
                log.error("llm http %s: %s", r.status_code, why)
                raise LLMError("llm_http", f"خطای مدل زبانی ({r.status_code})" + (f": {why}" if r.status_code == 400 and why else "."))
        raise LLMError("llm_http", "خطای مدل زبانی.")

    async def call_tool(self, *, system, user, tool, model, temperature):
        schema = json.dumps(tool["input_schema"], ensure_ascii=False)
        sys_text = "\n\n".join(b["text"] for b in system)
        prompt = (f"{user}\n\nخروجی را مستقیماً فقط به‌صورت «یک شیء JSON» برگردان که دقیقاً مطابق JSON Schema زیر باشد "
                  f"(همان آرگومان‌های {tool['name']}؛ بدون هیچ متن، توضیح یا کد-بلاک اضافه). فقط JSON.\n<json_schema>\n{schema}\n</json_schema>")
        body = {"model": model, "temperature": temperature, "max_tokens": self.max_tokens, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": sys_text}, {"role": "user", "content": prompt}]}
        tin = tout = 0
        for attempt in range(2):
            j = await self._post(body)
            u = j.get("usage") or {}
            tin += u.get("prompt_tokens", 0)
            tout += u.get("completion_tokens", 0)
            ch = (j.get("choices") or [{}])[0]
            text = (ch.get("message") or {}).get("content") or ""
            try:
                if ch.get("finish_reason") == "length":
                    raise ValueError("truncated")
                return _extract_json(text), {"tokens_in": tin, "tokens_out": tout, "cache_read": 0, "cache_write": 0}
            except ValueError:
                log.warning("llm returned bad/truncated json (attempt %d, finish=%s)", attempt + 1, ch.get("finish_reason"))
        raise LLMError("llm_bad_output", "خروجی مدل زبانی JSON معتبر یا کامل نبود؛ دوباره تلاش کنید.")
