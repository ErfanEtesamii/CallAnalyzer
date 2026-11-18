"""چت زنده: برچسب گوینده، انتشار تدریجی حباب‌ها، endpoint /live."""
import asyncio
from pathlib import Path

import pytest

from app.analysis.analyzer import Analyzer
from app.analysis.rubric_loader import load_rubric
from app.config import Settings
from app.db import DB
from app.jobs import Pipeline
from app.live import CUSTOMER, SELLER, LiveStore, SpeakerLabeler, heuristic_labels
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
