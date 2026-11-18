import asyncio
import math
import struct
import wave
from pathlib import Path

import pytest

from app.analysis.analyzer import Analyzer
from app.analysis.metrics import compute_metrics
from app.analysis.redact import redact
from app.analysis.rubric_loader import load_rubric
from app.analysis.schema import build_result_model, tool_schema
from app.analysis.scoring import compute_overall, percentile_rank
from app.analysis.verify import quote_found, verify_evidence
from app.audio import preprocess as pp
from app.stt.base import Segment, Transcript
from app.util import hms_to_seconds, mask_phone, normalize_digits, parse_filename

RUBRIC = load_rubric(Path(__file__).resolve().parents[2] / "rubric")


def test_digits_and_time():
    assert normalize_digits("۰۰:۰۱:۰۹") == "00:01:09"
    assert hms_to_seconds("۰۰:۰۱:۰۹") == 69
    assert hms_to_seconds("00:00:00") == 0


def test_filename():
    p = parse_filename("out-09198255664-14-20261117-134241-1794910361.189853.wav")
    assert p and p.extension == "14" and p.unique_id == "1794910361.189853" and p.direction == "out"
    assert p.call_datetime.hour == 13
    assert parse_filename("../etc/passwd") is None
    assert parse_filename("out-1-2-99999999-000000-1.2.wav") is None


def test_mask():
    assert mask_phone("09198255664") == "0919***5664"


def test_weights_sum_and_applicability():
    assert sum(RUBRIC.weights.values()) == 100


def _crit(score, **k):
    return {"score": score, "applicable": True, **k}


def test_scoring_normalizes_na():
    cfg = RUBRIC.config
    crit = [{"id": i, **_crit(10)} for i in RUBRIC.weights]
    crit[6]["applicable"] = False  # objection_handling N/A
    r = compute_overall(crit, RUBRIC.weights, RUBRIC.applies_to, "cold_new", [], cfg)
    assert r.score == 100 and r.grade == "A"
    # followup_quality فقط برای follow_up؛ وزن ۵ در cold_new لحاظ نمی‌شود
    assert r.applicable_weight == 100 - 13 - 5


def test_scoring_penalties_and_cap():
    cfg = RUBRIC.config
    crit = [{"id": i, **_crit(9)} for i in RUBRIC.weights]
    base = compute_overall(crit, RUBRIC.weights, RUBRIC.applies_to, "follow_up", [], cfg)
    assert base.score == 90
    pen = compute_overall(crit, RUBRIC.weights, RUBRIC.applies_to, "follow_up",
                          [{"severity": "medium"}] * 5 + [{"severity": "low"}] * 9, cfg)
    assert pen.score == 90 - 10 - 6
    hi = compute_overall(crit, RUBRIC.weights, RUBRIC.applies_to, "follow_up", [{"severity": "high"}], cfg)
    assert hi.score == 50 and hi.grade == "D" and hi.capped


def test_unreliable_when_few_criteria():
    crit = [{"id": "needs_discovery", **_crit(8)}]
    r = compute_overall(crit, RUBRIC.weights, RUBRIC.applies_to, "cold_new", [], RUBRIC.config)
    assert not r.reliable and r.score == 80


def test_percentile():
    assert percentile_rank(70, [50, 60, 70, 80]) == 62.5
    assert percentile_rank(1, []) is None


def test_verify_fuzzy():
    t = "[00:05] فروشنده: سلام وقت بخیر، من از فراز هنر تماس می‌گیرم"
    assert quote_found("من از فراز هنر تماس میگیرم", t)
    assert quote_found("من از «فراز هنر» تماس می‌گیرم.", t)
    assert not quote_found("قیمت این محصول خیلی ارزان است", t)
    res = {"criteria": [{"evidence": [{"quote": "جمله‌ی ساختگی که وجود ندارد اصلاً"}]}]}
    verify_evidence(res, t)
    assert res["criteria"][0]["evidence"][0]["verified"] is False and res["warnings"]


def test_redact():
    assert "[CARD]" in redact("کارت ۶۰۳۷ ۹۹۱۱ ۲۲۳۳ ۴۴۵۵ است")
    assert "[PHONE]" in redact("شماره ۰۹۱۹۸۲۵۵۶۶۴")
    assert "[ID]" in redact("کد ملی ۰۰۱۲۳۴۵۶۷۸")


def test_metrics():
    segs = [Segment(0, 5, "سلام آقای رضایی", "A"), Segment(5, 8, "بله؟", "B"),
            Segment(8.3, 20, "شاید قیمت مناسب باشد، می‌خواید یا نه", "A")]
    m = compute_metrics(segs, "A", RUBRIC.config["lexicons"], "رضایی")
    assert m["available"] and m["hedging_word_count"] == 1 and m["invite_no_question_count"] == 1
    assert m["name_usage_count"] == 1 and m["price_first_mentioned_at"] == "00:08"
    assert not compute_metrics([Segment(0, 1, "x")], None, {})["available"]


class FakeLLM:
    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), 0

    async def call_tool(self, **kw):
        self.calls += 1
        return self.outputs.pop(0), {"tokens_in": 10, "tokens_out": 5}


def _good(quote="سلام وقت بخیر"):
    return {
        "call_validity": {"is_analyzable": True, "call_type": "cold_new", "role_assignment_confidence": 0.9},
        "summary": "x", "participants": {"seller_speaker": "S1", "customer_speaker": "S2"},
        "criteria": [{"id": i, "applicable": True, "score": 8, "confidence": 0.8, "reasoning": "r",
                      "evidence": [{"timestamp": "00:01", "quote": quote}]} for i in RUBRIC.weights if i != "followup_quality"],
        "customer_status": {"stage": "warm_followup", "interest_level": 6},
        "seller_performance": {"compliance_flags": [{"type": "x", "severity": "high", "quote": "ساختگی کاملاً نامربوط"}]},
    }


def test_analyzer_pipeline_and_retry():
    tr = Transcript([Segment(0, 3, "سلام وقت بخیر", "S1"), Segment(3, 4, "بفرمایید", "S2")], diarized=True)
    bad = _good()
    bad["customer_status"]["stage"] = "bogus"
    llm = FakeLLM([bad, _good()])
    a = Analyzer(RUBRIC, llm, "m")
    out = asyncio.run(a.analyze(tr, {}, seller_speaker="S1"))
    assert llm.calls == 2
    o = out.result["overall"]
    assert o["score"] == 80 and o["grade"] == "B"
    # تخلف بدون شاهد کنار گذاشته شد → سقف high اعمال نشد
    assert out.result["seller_performance"]["compliance_flags"] == []
    assert out.result["criteria"][0]["evidence"][0]["verified"] is True


def test_analyzer_fails_after_two_invalid():
    bad = _good(); bad["criteria"][0]["id"] = "zzz"
    a = Analyzer(RUBRIC, FakeLLM([bad, bad]), "m")
    with pytest.raises(ValueError):
        asyncio.run(a.analyze(Transcript([Segment(0, 1, "a", "S1")]), {}))


def test_not_analyzable():
    a = Analyzer(RUBRIC, FakeLLM([{"call_validity": {"is_analyzable": False, "reason": "پیغام‌گیر"}, "summary": ""}]), "m")
    out = asyncio.run(a.analyze(Transcript([Segment(0, 1, "a")]), {}))
    assert out.result["overall"]["score"] is None


def test_tool_schema_enums():
    ts = tool_schema(RUBRIC)
    ids = ts["input_schema"]["properties"]["criteria"]["items"]["properties"]["id"]["enum"]
    assert len(ids) == 12
    build_result_model(RUBRIC)


def _tone(path, secs_tone, secs_silence, sr=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        for i in range(int(sr * secs_tone)):
            w.writeframes(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 300 * i / sr) * (1 + math.sin(i / 900)) / 2)))
        w.writeframes(b"\x00\x00" * int(sr * secs_silence))


def test_vad_and_ffmpeg(tmp_path):
    src, dst = tmp_path / "a.wav", tmp_path / "b.wav"
    _tone(src, 2, 2)
    info = pp.analyze_wav(str(src))
    assert 0.35 < info.speech_ratio < 0.65 and abs(info.duration - 4) < 0.1
    assert pp.is_riff_wave(src.read_bytes()[:12])
    pp.preprocess(str(src), str(dst))
    with wave.open(str(dst)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
    silent = tmp_path / "s.wav"; _tone(silent, 0, 3)
    assert pp.analyze_wav(str(silent)).speech_ratio < 0.05
    with pytest.raises(pp.AudioError):
        (tmp_path / "bad.wav").write_bytes(b"not audio"); pp.preprocess(str(tmp_path / "bad.wav"), str(tmp_path / "o.wav"))
