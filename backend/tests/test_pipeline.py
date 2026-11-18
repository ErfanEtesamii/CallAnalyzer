import asyncio, math, struct, wave
from pathlib import Path

from app.analysis.analyzer import Analyzer
from app.analysis.rubric_loader import load_rubric
from app.config import Settings
from app.db import DB
from app.jobs import Pipeline
from app.stt.providers.mock import MockSTT
from tests.test_core import FakeLLM, _good, _tone

RUBRIC = load_rubric(Path(__file__).resolve().parents[2] / "rubric")


def make(tmp_path, llm=None):
    s = Settings(storage_dir=str(tmp_path), min_speech_ratio=0.15)
    db = DB(":memory:")
    p = Pipeline(s, db, lambda: MockSTT(), Analyzer(RUBRIC, llm or FakeLLM([_good()]), "m"))
    return s, db, p


def new(db, uid="1.1"):
    return db.create_analysis(unique_id=uid, filename="f.wav", seller_ext="14", seller_name="x", direction="out",
                              call_datetime="2026-11-17T13:42:41")


def test_full_pipeline(tmp_path):
    s, db, p = make(tmp_path)
    wav = tmp_path / "a.wav"; _tone(wav, 3, 0.5)
    aid = new(db)
    asyncio.run(p.run(aid, str(wav)))
    a = db.get(aid)
    assert a["status"] == "done", a
    assert a["overall_score"] == 80 and a["percentile"] is not None
    assert db.get_transcript(aid)["segments"]
    assert not wav.exists()  # صوت پس از STT حذف می‌شود
    # reanalyze بدون STT
    p.analyzer.llm = FakeLLM([_good()])
    asyncio.run(p.reanalyze(aid))
    assert db.get(aid)["status"] == "done"


def test_silent_call_costs_nothing(tmp_path):
    s, db, p = make(tmp_path)
    wav = tmp_path / "s.wav"; _tone(wav, 0, 5)
    aid = new(db)
    asyncio.run(p.run(aid, str(wav)))
    a = db.get(aid)
    assert a["status"] == "done" and a["result"]["call_validity"]["is_analyzable"] is False
    assert db.q("SELECT COUNT(*) n FROM usage_log")[0]["n"] == 0


def test_bad_audio_fails_gracefully(tmp_path):
    s, db, p = make(tmp_path)
    wav = tmp_path / "b.wav"; wav.write_bytes(b"garbage")
    aid = new(db)
    asyncio.run(p.run(aid, str(wav)))
    a = db.get(aid)
    assert a["status"] == "failed" and a["error_code"] == "ffmpeg_failed"


def test_budget_stop(tmp_path):
    s, db, p = make(tmp_path)
    s.daily_budget_usd = 0.0
    wav = tmp_path / "a.wav"; _tone(wav, 3, 0.5)
    aid = new(db)
    asyncio.run(p.run(aid, str(wav)))
    assert db.get(aid)["error_code"] == "budget_exceeded"


def test_db_list_filters_delete(tmp_path):
    s, db, p = make(tmp_path)
    for i in range(3):
        a = new(db, f"{i}.0")
        db.save_result(a, {"overall": {"score": 50 + 10 * i, "grade": "C"}, "customer_status": {"stage": "hot_ready"}}, "v", None)
        db.update_analysis(a, status="done")
    assert db.list(min_score=60)["total"] == 2
    assert db.list(sort="score", desc=False)["items"][0]["overall_score"] == 50
    assert db.batch_status(["0.0", "9.9"]).keys() == {"0.0"}
    assert db.seller_stats()[0]["calls"] == 3
    db.delete(1)
    assert db.get(1) is None
