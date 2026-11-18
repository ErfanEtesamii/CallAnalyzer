"""Gemini (تحلیل) و Groq (STT رایگان): آداپترها با سرور ساختگی؛ بدون شبکه."""
import asyncio
import json
import wave

import httpx
import pytest

from app.analysis.errors import LLMError
from app.analysis.gemini import GeminiLLM, _extract_json
from app.config import Settings
from app.stt.base import ProviderUnavailable
from app.stt.providers.openai_provider import OpenAISTT
from app.stt.registry import build_provider

TOOL = {"name": "submit_analysis", "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}}}
SYSTEM = [{"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}]


def _resp(text, status=200, tin=100, tout=20):
    body = {"candidates": [{"content": {"parts": [{"text": text}]}}], "usageMetadata": {"promptTokenCount": tin, "candidatesTokenCount": tout, "thoughtsTokenCount": 5}}
    return httpx.Response(status, json=body)


def _llm(handler, **kw):
    async def nosleep(_):
        return None
    return GeminiLLM("KEY", transport=httpx.MockTransport(handler), sleep=nosleep, **kw)


def run(coro):
    return asyncio.run(coro)


def test_extract_json_variants():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": {"b": 2}}\n```') == {"a": {"b": 2}}
    assert _extract_json('متن قبل {"a": 1} بعد') == {"a": 1}
    for bad in ("", "[1,2]", "no json", '{"a": '):
        with pytest.raises(ValueError):
            _extract_json(bad)


def test_gemini_request_shape_and_usage():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers.get("x-goog-api-key"), json.loads(req.content)
        return _resp('{"summary": "ok"}')
    out, usage = run(_llm(handler).call_tool(system=SYSTEM, user="U", tool=TOOL, model="gemini-2.5-flash", temperature=0.1))
    assert out == {"summary": "ok"}
    assert usage == {"tokens_in": 100, "tokens_out": 25, "cache_read": 0, "cache_write": 0}
    assert seen["url"].endswith("/models/gemini-2.5-flash:generateContent") and seen["key"] == "KEY"
    b = seen["body"]
    assert b["systemInstruction"]["parts"][0]["text"] == "SYS" and "cache_control" not in json.dumps(b)
    assert b["generationConfig"]["responseMimeType"] == "application/json"
    assert "json_schema" in b["contents"][0]["parts"][0]["text"] and '"summary"' in b["contents"][0]["parts"][0]["text"]
    assert "thinkingConfig" not in b["generationConfig"]


def test_gemini_thinking_budget_optional():
    seen = {}

    def handler(req):
        seen["g"] = json.loads(req.content)["generationConfig"]
        return _resp("{}")
    run(_llm(handler, thinking_budget=0).call_tool(system=SYSTEM, user="U", tool=TOOL, model="m", temperature=0))
    assert seen["g"]["thinkingConfig"] == {"thinkingBudget": 0}


def test_gemini_retries_rate_limit_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, text="quota") if len(calls) < 3 else _resp("{}")
    run(_llm(handler).call_tool(system=SYSTEM, user="U", tool=TOOL, model="m", temperature=0))
    assert len(calls) == 3


def test_gemini_rate_limit_gives_clear_error():
    with pytest.raises(LLMError) as e:
        run(_llm(lambda r: httpx.Response(429, text="quota")).call_tool(system=SYSTEM, user="U", tool=TOOL, model="m", temperature=0))
    assert e.value.code == "llm_rate_limit" and "Gemini" in e.value.message


def test_gemini_errors_do_not_leak_body():
    with pytest.raises(LLMError) as e:
        run(_llm(lambda r: httpx.Response(400, text="SECRET TRANSCRIPT")).call_tool(system=SYSTEM, user="U", tool=TOOL, model="m", temperature=0))
    assert "SECRET" not in e.value.message
    with pytest.raises(LLMError) as e2:
        run(_llm(lambda r: httpx.Response(404, text="nf")).call_tool(system=SYSTEM, user="U", tool=TOOL, model="bad", temperature=0))
    assert e2.value.code == "llm_model" and "bad" in e2.value.message


def test_gemini_bad_json_retried_once_then_error():
    n = []

    def handler(req):
        n.append(1)
        return _resp("not json")
    with pytest.raises(LLMError) as e:
        run(_llm(handler).call_tool(system=SYSTEM, user="U", tool=TOOL, model="m", temperature=0))
    assert e.value.code == "llm_bad_output" and len(n) == 2


def test_gemini_blocked_prompt():
    h = lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(LLMError) as e:
        run(_llm(h).call_tool(system=SYSTEM, user="U", tool=TOOL, model="m", temperature=0))
    assert e.value.code == "llm_blocked"


def test_gemini_requires_key():
    with pytest.raises(RuntimeError):
        GeminiLLM("")


# ---- Groq STT ----
def _wav(path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0\0" * 1600)


def test_groq_stt_uses_groq_endpoint_and_truncates_prompt(tmp_path):
    wav = tmp_path / "a.wav"; _wav(wav)
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], req.content
        return httpx.Response(200, json={"text": "سلام", "duration": 1.0, "segments": [{"start": 0, "end": 1, "text": " سلام "}]})
    s = Settings(stt_provider="groq", groq_api_key="gk")
    p = build_provider(s, vocab_prompt="و" * 5000)
    assert p.name == "groq" and p.base_url == "https://api.groq.com/openai/v1" and p.model == "whisper-large-v3" and len(p.prompt) == 600
    p.transport = httpx.MockTransport(handler)
    tr = run(p.transcribe(str(wav)))
    assert seen["url"] == "https://api.groq.com/openai/v1/audio/transcriptions" and seen["auth"] == "Bearer gk"
    assert tr.provider == "groq" and tr.segments[0].text == "سلام"


def test_groq_stt_errors_and_key(tmp_path):
    wav = tmp_path / "a.wav"; _wav(wav)
    with pytest.raises(ProviderUnavailable) as e:
        build_provider(Settings(stt_provider="groq"))
    assert "GROQ_API_KEY" in str(e.value)
    p = OpenAISTT("k", base_url="http://x/v1", transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    with pytest.raises(ProviderUnavailable) as e2:
        run(p.transcribe(str(wav)))
    assert "سهمیه" in str(e2.value)


def test_openai_default_unchanged():
    p = build_provider(Settings(stt_provider="openai", openai_api_key="k"))
    assert p.base_url == "https://api.openai.com/v1" and p.model == "whisper-1" and p.name == "openai"


def test_settings_from_env(monkeypatch):
    for k, v in {"LLM_PROVIDER": "Gemini", "GEMINI_API_KEY": "g", "GEMINI_THINKING_BUDGET": "0", "STT_PROVIDER": "groq", "GROQ_API_KEY": "q"}.items():
        monkeypatch.setenv(k, v)
    s = Settings.from_env(None)
    assert (s.llm_provider, s.gemini_api_key, s.gemini_thinking_budget, s.groq_api_key) == ("gemini", "g", 0, "q")
    monkeypatch.delenv("GEMINI_THINKING_BUDGET")
    assert Settings.from_env(None).gemini_thinking_budget is None


def test_full_pipeline_with_gemini_adapter_and_zero_cost(tmp_path):
    """کل مسیر: STT ساختگی ← Analyzer واقعی ← GeminiLLM (سرور ساختگی) ← اعتبارسنجی schema ← امتیاز؛ هزینه‌ی رایگان = ۰."""
    from pathlib import Path

    from app.analysis.analyzer import Analyzer
    from app.analysis.rubric_loader import load_rubric
    from app.db import DB
    from app.jobs import Pipeline
    from app.stt.providers.mock import MockSTT
    from tests.test_core import _good, _tone

    rubric = load_rubric(Path(__file__).resolve().parents[2] / "rubric")
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return _resp(json.dumps(_good(), ensure_ascii=False), tin=30000, tout=2000)
    s = Settings(storage_dir=str(tmp_path), min_speech_ratio=0.15, llm_provider="gemini", gemini_api_key="k")
    db = DB(":memory:")
    p = Pipeline(s, db, lambda: MockSTT(), Analyzer(rubric, _llm(handler), "gemini-2.5-flash"))
    wav = tmp_path / "a.wav"; _tone(wav, 3, 0.5)
    aid = db.create_analysis(unique_id="9.9", filename="f.wav", seller_ext="14", seller_name="x", direction="out",
                             call_datetime="2026-11-17T13:42:41")
    run(p.run(aid, str(wav)))
    a = db.get(aid)
    assert a["status"] == "done", a
    assert a["overall_score"] == 80
    assert db.q("SELECT SUM(cost_estimate) c FROM usage_log WHERE stage='analysis'")[0]["c"] == 0
    sys_text = seen["body"]["systemInstruction"]["parts"][0]["text"]
    assert "<rubric>" in sys_text and "<allowed_ids>" in sys_text


def test_pipeline_surfaces_quota_error_to_user(tmp_path):
    from pathlib import Path

    from app.analysis.analyzer import Analyzer
    from app.analysis.rubric_loader import load_rubric
    from app.db import DB
    from app.jobs import Pipeline
    from app.stt.providers.mock import MockSTT
    from tests.test_core import _tone

    rubric = load_rubric(Path(__file__).resolve().parents[2] / "rubric")
    s = Settings(storage_dir=str(tmp_path), min_speech_ratio=0.15, llm_provider="gemini", gemini_api_key="k")
    db = DB(":memory:")
    p = Pipeline(s, db, lambda: MockSTT(), Analyzer(rubric, _llm(lambda r: httpx.Response(429, text="q")), "m"))
    wav = tmp_path / "a.wav"; _tone(wav, 3, 0.5)
    aid = db.create_analysis(unique_id="8.8", filename="f.wav", seller_ext="14", seller_name="x", direction="out",
                             call_datetime="2026-11-17T13:42:41")
    run(p.run(aid, str(wav)))
    a = db.get(aid)
    assert a["status"] == "failed" and a["error_code"] == "llm_rate_limit" and "Gemini" in a["error_message"]


def _make_wav(path, seconds, rate=16000):
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)


def test_stt_chunks_long_audio_and_offsets(tmp_path):
    import asyncio, httpx
    wav = tmp_path / "a.wav"; _make_wav(wav, 25)
    calls = []
    def handler(req):
        calls.append(1)
        return httpx.Response(200, json={"segments": [{"start": 0, "end": 1, "text": "سلام"}]})
    p = OpenAISTT("k", chunk_seconds=10, transport=httpx.MockTransport(handler))
    tr = asyncio.run(p.transcribe(str(wav)))
    assert len(calls) == 3 and [s.start for s in tr.segments] == [0, 10, 20]


def test_stt_retries_5xx_then_succeeds(tmp_path):
    import asyncio, httpx
    wav = tmp_path / "a.wav"; _make_wav(wav, 3)
    n = {"c": 0}
    def handler(req):
        n["c"] += 1
        return httpx.Response(524) if n["c"] < 3 else httpx.Response(200, json={"text": "ok", "duration": 3})
    async def nosleep(_): pass
    p = OpenAISTT("k", transport=httpx.MockTransport(handler), sleep=nosleep)
    assert asyncio.run(p.transcribe(str(wav))).segments[0].text == "ok" and n["c"] == 3


def test_stt_persistent_5xx_is_friendly_error(tmp_path):
    import asyncio, httpx, pytest
    from app.stt.base import ProviderUnavailable
    wav = tmp_path / "a.wav"; _make_wav(wav, 3)
    async def nosleep(_): pass
    p = OpenAISTT("k", transport=httpx.MockTransport(lambda r: httpx.Response(524)), sleep=nosleep)
    with pytest.raises(ProviderUnavailable, match="524"):
        asyncio.run(p.transcribe(str(wav)))

def test_interrupted_jobs_failed_on_startup(tmp_path):
    from app.db import DB
    d = DB(str(tmp_path / "t.db"))
    a = d.create_analysis(unique_id="u1", status="transcribing")
    b = d.create_analysis(unique_id="u2", status="done")
    assert d.fail_interrupted() == 1
    assert d.get(a)["status"] == "failed" and d.get(a)["error_code"] == "interrupted"
    assert d.get(b)["status"] == "done"