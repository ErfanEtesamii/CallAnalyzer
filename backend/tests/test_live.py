"""چت زنده: برچسب گوینده، انتشار تدریجی حباب‌ها، endpoint /live."""
import asyncio
from pathlib import Path

import pytest

from app.analysis.analyzer import Analyzer
from app.analysis.rubric_loader import load_rubric
from app.config import Settings
from app.db import DB
from app.jobs import Pipeline
from app.live import CUSTOMER, SELLER, DiarizedRefiner, LiveStore, SpeakerLabeler, heuristic_labels
from app.stt.base import Segment, Transcript
from tests.test_core import _good, _tone

RUBRIC = load_rubric(Path(__file__).resolve().parents[2] / "rubric")


def run(c):
    return asyncio.run(c)


class RouterLLM:
    """هم برچسب‌زنی (label_speakers) و هم تحلیل را جواب می‌دهد."""
    def __init__(self, labeler_out=None, boom=False):
        self.labeler_out, self.boom, self.label_calls = labeler_out, boom, 0

    async def call_tool(self, *, system, user, tool, model, temperature):
        if tool["name"] == "label_speakers":
            self.label_calls += 1
            if self.boom:
                raise RuntimeError("x")
            n = user.count("\n") and sum(1 for ln in user.split("<قطعه‌های_جدید>")[1].splitlines() if ln[:1].isdigit())
            return (self.labeler_out(n) if self.labeler_out else {"labels": [SELLER, CUSTOMER] * n}), {}
        if tool["name"] == "refine_turns":  # ویرایش‌گر: نقش‌ها مثل برچسب‌زن، متن بدون تغییر
            self.label_calls += 1
            if self.boom:
                raise RuntimeError("x")
            lines = [ln.split("] ", 1)[1] for ln in user.split("<نوبت‌های_جدید>")[1].splitlines() if ln[:1].isdigit() and "] " in ln]
            labels = (self.labeler_out(len(lines)) if self.labeler_out else {"labels": [SELLER, CUSTOMER] * len(lines)})["labels"]
            return {"turns": [{"speaker": sp, "text": lines[i % len(lines)]} for i, sp in enumerate(labels)]}, {}  # طول نامتناسب → heuristic
        return _good(), {"tokens_in": 1, "tokens_out": 1}


def test_heuristic_alternates_on_gap_and_question():
    segs = [Segment(0, 2, "سلام وقت بخیر"), Segment(2.1, 4, "از فراز هنر تماس می‌گیرم"),
            Segment(5.5, 6, "بفرمایید"), Segment(6.1, 8, "شما هدیه می‌خرید؟"), Segment(8.1, 9, "بله")]
    assert heuristic_labels(segs, None, None) == [SELLER, SELLER, CUSTOMER, CUSTOMER, SELLER]


def test_labeler_uses_llm_and_keeps_context():
    llm = RouterLLM(lambda n: {"labels": [SELLER] + [CUSTOMER] * (n - 1)})
    lb = SpeakerLabeler(llm, "m")
    a = run(lb.label([Segment(0, 1, "سلام"), Segment(1, 2, "بفرمایید")]))
    assert [s.speaker for s in a] == [SELLER, CUSTOMER] and lb.llm_batches == 1
    run(lb.label([Segment(3, 4, "ممنون")]))
    assert len(lb.history) == 3


@pytest.mark.parametrize("llm", [RouterLLM(boom=True), RouterLLM(lambda n: {"labels": ["seller"]}),
                                 RouterLLM(lambda n: {"labels": ["x"] * n}), None])
def test_labeler_falls_back_without_breaking(llm):
    lb = SpeakerLabeler(llm, "m")
    out = run(lb.label([Segment(0, 1, "سلام"), Segment(3, 4, "بله")]))
    assert all(s.speaker in (SELLER, CUSTOMER) for s in out) and lb.llm_batches == 0


class ChunkedSTT:
    """مثل OpenAISTT: بعد از هر تکه on_segments را صدا می‌زند."""
    name = "fake"
    supports_live = True

    def __init__(self):
        self.seen_counts = []

    async def transcribe(self, wav_path, *, language="fa", on_segments=None):
        segs = []
        for i, text in enumerate(["سلام وقت بخیر از فراز هنر", "سلام بفرمایید", "برای هدیه‌ی سازمانی تماس گرفتم"]):
            part = [Segment(i * 4, i * 4 + 3, text)]
            segs.extend(part)
            if on_segments:
                await on_segments(part)
        return Transcript(segs, language, "fake")


def test_pipeline_publishes_bubbles_incrementally_then_analyzes(tmp_path):
    s = Settings(storage_dir=str(tmp_path), min_speech_ratio=0.15)
    db = DB(":memory:")
    stt, llm = ChunkedSTT(), RouterLLM()
    p = Pipeline(s, db, lambda: stt, Analyzer(RUBRIC, llm, "m"))
    snapshots = []
    orig = p.live.append
    p.live.append = lambda aid, segs: (orig(aid, segs), snapshots.append(p.live.count(aid)))
    wav = tmp_path / "a.wav"
    _tone(wav, 3, 0.5)
    aid = db.create_analysis(unique_id="1.1", filename="f.wav", seller_ext="14", seller_name="x", direction="out",
                             call_datetime="2026-11-17T13:42:41")
    run(p.run(aid, str(wav)))
    a = db.get(aid)
    assert a["status"] == "done", a
    assert snapshots == [1, 2, 3]  # حباب‌ها یکی‌یکی رسیدند
    rows = p.live.get(aid)
    assert [r["speaker"] for r in rows] == [SELLER, CUSTOMER, SELLER]
    tr = db.get_transcript(aid)
    assert [x["speaker"] for x in tr["segments"]] == [SELLER, CUSTOMER, SELLER]
    assert llm.label_calls == 3
    r = db.get_result(aid) if hasattr(db, "get_result") else None
    part = (r or db.get(aid).get("result") or {}).get("participants", {})
    assert part.get("seller_speaker") == SELLER and part.get("customer_speaker") == CUSTOMER


def test_live_store_append_get_after_and_reset():
    db = DB(":memory:")
    st = LiveStore(db)
    st.append(1, [Segment(0, 1, "الف", SELLER), Segment(1, 2, "ب", CUSTOMER)])
    st.append(1, [Segment(2, 3, "ج", SELLER)])
    assert [r["i"] for r in st.get(1)] == [0, 1, 2] and [r["text"] for r in st.get(1, 2)] == ["ج"]
    st.reset(1)
    assert st.get(1) == []


def test_live_endpoint(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.main import create_app
    url = f"sqlite:///{tmp_path}/l.db"
    s = Settings(api_token="t" * 20, database_url=url, storage_dir=str(tmp_path / "st"), rubric_dir="../rubric")
    c = TestClient(create_app(s, llm=object(), stt_factory=lambda: None))
    h = {"Authorization": "Bearer " + "t" * 20}
    assert c.get("/api/v1/analyses/1/live").status_code == 401
    assert c.get("/api/v1/analyses/99/live", headers=h).status_code == 404
    d = DB(url)
    aid = d.create_analysis(unique_id="z", status="transcribing")
    LiveStore(d).append(aid, [Segment(0, 1, "سلام", SELLER), Segment(1, 2, "بله", CUSTOMER)])
    j = c.get(f"/api/v1/analyses/{aid}/live", headers=h).json()
    assert j["status"] == "transcribing" and j["next"] == 2 and [x["speaker"] for x in j["segments"]] == [SELLER, CUSTOMER]
    assert c.get(f"/api/v1/analyses/{aid}/live?after=2", headers=h).json()["segments"] == []


# ---- موسیقی و تلفن گویا ----
def test_nonspeech_detection():
    from app.stt.nonspeech import is_music, looks_ivr
    assert is_music({"text": "♪♪"}) and is_music({"text": "موسیقی"}) and is_music({"text": "ترجمه و زیرنویس توسط علی"})
    assert is_music({"text": "ممنون", "no_speech_prob": 0.9, "avg_logprob": -1.2})
    assert not is_music({"text": "سلام وقت بخیر", "no_speech_prob": 0.05, "avg_logprob": -0.2})
    assert not is_music({"text": "ممنون", "no_speech_prob": 0.9, "avg_logprob": -0.3})  # گفتار واقعی با احتمال سکوت بالا ولی مطمئن
    assert looks_ivr("برای ارتباط با فروش عدد یک را فشار دهید") and looks_ivr("مشترک مورد نظر در دسترس نیست")
    assert not looks_ivr("سلام وقت بخیر از فراز هنر تماس می‌گیرم")


def test_provider_marks_music_segments(tmp_path):
    import httpx

    from app.stt.providers.openai_provider import OpenAISTT
    wav = tmp_path / "a.wav"
    _tone(wav, 3, 0.5)
    segs = [{"start": 0, "end": 3, "text": "♪", "no_speech_prob": 0.1, "avg_logprob": -0.2},
            {"start": 3, "end": 5, "text": "سلام", "no_speech_prob": 0.01, "avg_logprob": -0.1}]
    p = OpenAISTT("k", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"segments": segs})), compress_bitrate="")
    tr = run(p.transcribe(str(wav)))
    assert [(s.speaker, s.text) for s in tr.segments] == [("music", "موسیقی"), (None, "سلام")]


def test_labeler_keeps_specials_and_ivr_regex_without_llm():
    segs = [Segment(0, 3, "موسیقی", "music"), Segment(3, 8, "برای ارتباط با فروش عدد ۱ را فشار دهید"),
            Segment(9, 11, "سلام وقت بخیر از فراز هنر"), Segment(12, 13, "بله بفرمایید")]
    out = run(SpeakerLabeler(None, "m").label(segs))
    assert [s.speaker for s in out] == ["music", "ivr", SELLER, CUSTOMER]


def test_metrics_ignore_specials_and_transcript_shows_parentheses():
    from app.analysis.metrics import compute_metrics, format_transcript
    segs = [Segment(0, 30, "موسیقی", "music"), Segment(30, 34, "سلام", SELLER), Segment(34, 36, "بله", CUSTOMER),
            Segment(36, 40, "برای فروش عدد ۱", "ivr")]
    m = compute_metrics(segs, SELLER, {})
    assert m.get("available", True) is not False
    txt = format_transcript(segs)
    assert "(موسیقی)" in txt and "(تلفن گویا: برای فروش عدد ۱)" in txt
    only_music = compute_metrics([Segment(0, 30, "موسیقی", "music")], SELLER, {})
    assert only_music.get("available") is False


# ---- Gemini STT (رونویسی + گوینده از روی صدا) ----
def _gem_resp(turns):
    import json
    return {"candidates": [{"content": {"parts": [{"text": json.dumps({"turns": turns}, ensure_ascii=False)}]}}]}


def test_turns_to_segments_clamps_and_orders():
    from app.stt.providers.gemini_provider import turns_to_segments
    out = turns_to_segments([{"speaker": "seller", "start": 0, "end": 3, "text": "سلام"},
                             {"speaker": "customer", "start": 2, "end": 0, "text": "بله"},  # شروع قبل از پایان قبلی، پایان نامعتبر
                             {"speaker": "robot", "start": 5, "end": 6, "text": "x"},  # گوینده نامعتبر حذف
                             {"speaker": "music", "start": 6, "end": 9, "text": ""}], 100.0, 10.0)
    assert [(s.speaker, s.text) for s in out] == [("seller", "سلام"), ("customer", "بله"), ("music", "موسیقی")]
    assert all(b.start >= a.end - 1e-9 for a, b in zip(out, out[1:])) and out[0].start == 100.0 and out[-1].end <= 110.5


def test_gemini_stt_chunks_context_and_labels(tmp_path):
    import json

    import httpx

    from app.stt.providers.gemini_provider import GeminiSTT
    wav = tmp_path / "a.wav"
    _tone(wav, 100, 0.5)
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        n = len(bodies)
        return httpx.Response(200, json=_gem_resp([{"speaker": "seller", "start": 0, "end": 4, "text": f"سلام {n}"},
                                                   {"speaker": "customer", "start": 4, "end": 6, "text": f"بله {n}"}]))

    got = []

    async def cb(part):
        got.append(part)

    p = GeminiSTT("k", transport=httpx.MockTransport(handler), chunk_seconds=45, compress_bitrate="")
    tr = run(p.transcribe(str(wav), on_segments=cb))
    assert len(bodies) >= 2 and len(got) == len(bodies) and tr.provider == "gemini"
    assert "(شروع تماس)" in bodies[0]["contents"][0]["parts"][1]["text"]
    assert "مشتری: بله 1" in bodies[1]["contents"][0]["parts"][1]["text"]  # زمینه‌ی تکه‌ی قبل
    assert tr.segments[2].start >= 40 and tr.segments[0].speaker == "seller"


def test_gemini_stt_fallback_and_labeler_preserves_labels(tmp_path):
    import httpx

    from app.stt.base import Transcript
    from app.stt.providers.gemini_provider import GeminiSTT
    wav = tmp_path / "a.wav"
    _tone(wav, 30, 0.5)

    class FB:
        async def transcribe(self, path, language="fa"):
            return Transcript([Segment(0, 2, "سلام")], "fa", "groq")

    p = GeminiSTT("k", transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad")), fallback=FB(), compress_bitrate="")
    tr = run(p.transcribe(str(wav)))
    assert [(s.text, s.speaker) for s in tr.segments] == [("سلام", None)]  # بعداً SpeakerLabeler برچسب می‌زند
    segs = [Segment(0, 2, "سلام", CUSTOMER), Segment(3, 4, "بله")]
    out = run(SpeakerLabeler(None, "m").label(segs))
    assert out[0].speaker == CUSTOMER  # برچسب ارائه‌دهنده بازنویسی نمی‌شود


def test_gemini_400_shows_api_reason():
    import httpx
    import pytest

    from app.analysis.errors import LLMError
    from app.analysis.gemini import GeminiLLM
    t = httpx.MockTransport(lambda r: httpx.Response(400, json={"error": {"message": "Unsupported thinking config"}}))
    with pytest.raises(LLMError) as ei:
        run(GeminiLLM("k", transport=t, fallback_models=[])._post("m", {}))
    assert "Unsupported thinking config" in str(ei.value)


# ---- Grok STT + DiarizedRefiner ----
def test_build_turns_by_speaker_gap_and_length():
    from app.stt.providers.grok_provider import build_turns
    w = lambda t, a, b, sp: {"text": t, "start": a, "end": b, "speaker": sp}  # noqa: E731
    segs = build_turns([w("سلام", 0, .5, 0), w("وقت", .6, .9, 0), w("بخیر", 1, 1.4, 0), w("بله", 1.6, 1.9, 1),
                        w("بفرمایید", 2, 2.5, 1), w("ممنون", 6, 6.5, 1)])
    assert [(s.speaker, s.text) for s in segs] == [("spk0", "سلام وقت بخیر"), ("spk1", "بله بفرمایید"), ("spk1", "ممنون")]
    assert segs[0].start == 0 and segs[0].end == 1.4


def test_grok_stt_request_and_batches(tmp_path):
    import httpx

    from app.stt.providers.grok_provider import GrokSTT
    wav = tmp_path / "a.wav"
    _tone(wav, 30, 0.5)
    seen = {}

    def handler(req):
        seen["auth"], seen["body"] = req.headers["authorization"], req.content
        words = [{"text": f"w{i}", "start": i * 2.0, "end": i * 2.0 + 1, "speaker": i % 2} for i in range(25)]
        return httpx.Response(200, json={"words": words, "duration": 30, "text": "x"})

    got = []

    async def cb(part):
        got.append(len(part))

    tr = run(GrokSTT("xk", vocab="فراز هنر، شب یلدا", transport=httpx.MockTransport(handler), compress_bitrate="", batch_turns=10).transcribe(str(wav), on_segments=cb))
    assert seen["auth"] == "Bearer xk" and b'name="diarize"' in seen["body"] and b'name="keyterm"' in seen["body"]
    assert seen["body"].rfind(b'name="file"') > seen["body"].rfind(b'name="keyterm"')  # فایل آخرین فیلد
    assert sum(got) == len(tr.segments) and got[0] == 10 and tr.segments[0].speaker == "spk0"


def test_grok_music_gap_detected_only_when_loud(tmp_path):
    from app.stt.providers.grok_provider import music_gaps
    wav = tmp_path / "a.wav"
    _tone(wav, 30, 0.5)  # کل فایل «صدا» دارد
    segs = [Segment(0, 5, "a", "spk0"), Segment(15, 20, "b", "spk1")]
    out = music_gaps(segs, str(wav), 30)
    assert [(m.speaker, round(m.start), round(m.end)) for m in out] == [("music", 5, 15), ("music", 20, 30)]
    quiet = tmp_path / "q.wav"
    _tone(quiet, 0, 30)
    assert music_gaps(segs, str(quiet), 30) == []


class _FakeLLM:
    def __init__(self, turns):
        self.turns, self.calls = turns, 0

    async def call_tool(self, **kw):
        self.calls += 1
        return {"turns": self.turns(kw["user"])}, {}


def test_refiner_roles_spelling_and_stable_mapping():
    segs = [Segment(0, 3, "سلام آقای پسندیده", "spk1"), Segment(3, 5, "سلام وندیگه", "spk0"), Segment(5, 9, "من از فراز خانر", "spk1")]
    llm = _FakeLLM(lambda u: [{"speaker": "seller", "text": "سلام، آقای پسندیده."}, {"speaker": "customer", "text": "سلام و درود."},
                              {"speaker": "seller", "text": "من از فراز هنر هستم."}])
    r = DiarizedRefiner(llm, "m")
    out = run(r.label(segs))
    assert [s.speaker for s in out] == [SELLER, CUSTOMER, SELLER] and out[2].text == "من از فراز هنر هستم."
    # دسته‌ی بعد: مدل اشتباهاً نقش را برعکس بدهد؛ نگاشت ثابت اعمال می‌شود. ivr حفظ می‌شود
    llm.turns = lambda u: [{"speaker": "customer", "text": "بله"}, {"speaker": "ivr", "text": "پیام ضبط شده"}]
    out2 = run(r.label([Segment(10, 11, "بله", "spk1"), Segment(12, 14, "پیام ضبط شده", "spk0")]))
    assert [s.speaker for s in out2] == [SELLER, "ivr"]


def test_refiner_guards_bad_text_and_falls_back_on_error():
    seg = Segment(0, 3, "سلام وقت بخیر", "spk0")
    llm = _FakeLLM(lambda u: [{"speaker": "seller", "text": "x" * 200}])  # طول غیرعادی → متن اصلی
    assert run(DiarizedRefiner(llm, "m").label([seg]))[0].text == "سلام وقت بخیر"

    class Boom:
        async def call_tool(self, **kw):
            raise RuntimeError("down")

    r = DiarizedRefiner(Boom(), "m")
    out = run(r.label([Segment(0, 2, "سلام", "spk5"), Segment(2, 4, "بله", "spk9"), Segment(4, 6, "خب", "spk5")]))
    assert [s.speaker for s in out] == [SELLER, CUSTOMER, SELLER] and out[1].text == "بله"


def test_openai_compat_llm_json_and_errors():
    import json

    import httpx

    from app.analysis.errors import LLMError
    from app.analysis.openai_compat import OpenAICompatLLM
    seen = {}

    def ok(req):
        seen["b"] = json.loads(req.content)
        seen["auth"] = req.headers["authorization"]
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 5, "completion_tokens": 2}})

    llm = OpenAICompatLLM("k", transport=httpx.MockTransport(ok))
    out, usage = run(llm.call_tool(system=[{"type": "text", "text": "s"}], user="u", tool={"name": "t", "input_schema": {"type": "object"}},
                                   model="deepseek-chat", temperature=0))
    assert out == {"a": 1} and usage["tokens_in"] == 5 and seen["auth"] == "Bearer k"
    assert seen["b"]["response_format"] == {"type": "json_object"} and "JSON" in seen["b"]["messages"][1]["content"]
    for code, expect in [(401, "llm_auth"), (402, "llm_balance")]:
        bad = OpenAICompatLLM("k", transport=httpx.MockTransport(lambda r, c=code: httpx.Response(c, json={"error": {"message": "x"}})))
        with pytest.raises(LLMError) as ei:
            run(bad.call_tool(system=[{"type": "text", "text": "s"}], user="u", tool={"name": "t", "input_schema": {}}, model="m", temperature=0))
        assert ei.value.code == expect
    trunc = OpenAICompatLLM("k", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": '{"a":'}, "finish_reason": "length"}]})))
    with pytest.raises(LLMError) as ei:
        run(trunc.call_tool(system=[{"type": "text", "text": "s"}], user="u", tool={"name": "t", "input_schema": {}}, model="m", temperature=0))
    assert ei.value.code == "llm_bad_output"


def test_refiner_without_diarization_uses_llm_role_and_fixes_text():
    llm = _FakeLLM(lambda u: [{"speaker": "seller", "text": "سلام، آقای پسندیده."}, {"speaker": "customer", "text": "سلام و درود."}])
    out = run(DiarizedRefiner(llm, "m").label([Segment(0, 2, "سلام آقای پسندیده"), Segment(2, 4, "سلام و ندیگه")]))
    assert [(s.speaker, s.text) for s in out] == [(SELLER, "سلام، آقای پسندیده."), (CUSTOMER, "سلام و درود.")]


def test_openai_compat_retries_without_json_mode_and_daily_limit():
    import json

    import httpx
    import pytest

    from app.analysis.errors import LLMError
    from app.analysis.openai_compat import OpenAICompatLLM
    bodies = []

    def h(req):
        b = json.loads(req.content)
        bodies.append("response_format" in b)
        if "response_format" in b:
            return httpx.Response(400, json={"error": {"message": "response_format json_object is not supported"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]})

    llm = OpenAICompatLLM("k", transport=httpx.MockTransport(h), key_name="OPENROUTER_API_KEY")
    out, _ = run(llm.call_tool(system=[{"type": "text", "text": "s"}], user="u", tool={"name": "t", "input_schema": {}}, model="m:free", temperature=0))
    assert out == {"ok": True} and bodies == [True, False]
    day = OpenAICompatLLM("k", transport=httpx.MockTransport(lambda r: httpx.Response(429, text="Rate limit exceeded: free-models-per-day")), sleep=lambda s: asyncio.sleep(0))
    with pytest.raises(LLMError) as ei:
        run(day.call_tool(system=[{"type": "text", "text": "s"}], user="u", tool={"name": "t", "input_schema": {}}, model="m", temperature=0))
    assert ei.value.code in {"llm_rate_limit", "llm_http"}
