"""FastAPI app. اجرا: uvicorn app.main:app"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.analysis.analyzer import Analyzer, AnthropicLLM
from app.analysis.rubric_loader import load_rubric
from app.audio.preprocess import is_riff_wave
from app.auth import RateLimiter, make_auth
from app.config import Settings
from app.db import DB
from app.jobs import Pipeline
from app.stt.registry import build_provider
from app.util import hash_phone, hms_to_seconds, mask_phone, parse_filename

VERSION = "1.0.0"


class BatchIn(BaseModel):
    unique_ids: list[str]


class ReIn(BaseModel):
    seller_speaker: str | None = None


class OverrideIn(BaseModel):
    field: str
    new: float | str
    note: str = ""


class NoteIn(BaseModel):
    text: str


class FeedbackIn(BaseModel):
    criterion_id: str
    agrees: bool
    manager_score: float | None = None
    reason: str = ""


def create_app(settings: Settings | None = None, llm=None, stt_factory=None) -> FastAPI:
    s = settings or Settings.from_env()
    db = DB(s.database_url)
    rubric = load_rubric(s.rubric_dir)
    sellers = json.loads(Path(s.sellers_file).read_text(encoding="utf-8")) if Path(s.sellers_file).exists() else {}
    vocab = Path("domain_vocab.txt").read_text(encoding="utf-8").replace("\n", "، ") if Path("domain_vocab.txt").exists() else ""
    llm = llm or (AnthropicLLM(s.anthropic_api_key) if s.anthropic_api_key else None)
    pipe = Pipeline(s, db, stt_factory or (lambda: build_provider(s, vocab_prompt=vocab)),
                    Analyzer(rubric, llm, s.analysis_model, s.redact_pii) if llm else None, sellers)  # type: ignore[arg-type]
    state = {"rubric": rubric}
    storage = Path(s.storage_dir); storage.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Call Analyzer", version=VERSION)
    app.add_middleware(CORSMiddleware, allow_origins=s.allowed_origins, allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])
    auth = make_auth([s.api_token], RateLimiter())

    @app.get("/health")
    def health():
        return {"ok": True, "llm": llm is not None, "stt": s.stt_provider}

    @app.get("/api/v1/version")
    def version(_: str = Depends(auth)):
        return {"backend": VERSION, "rubric": state["rubric"].version, "model": s.analysis_model}

    @app.post("/api/v1/analyses", status_code=202)
    async def create(bg: BackgroundTasks, file: UploadFile = File(...), unique_id: str = Form(...),
                     namefile: str = Form(""), call_date: str = Form(""), call_time: str = Form(""),
                     src: str = Form(""), dst: str = Form(""), panel_duration: str = Form("0"), talk_seconds: str = Form(""),
                     seller_ext: str = Form(""), direction: str = Form("out"), force: bool = Form(False),
                     user: str = Depends(auth)):
        if pipe.analyzer is None:
            raise HTTPException(503, "کلید Anthropic روی سرور تنظیم نشده است.")
        ex = db.get_by_uid(unique_id)
        if ex and not force and ex["status"] != "failed":
            return {"id": ex["id"], "status": ex["status"], "existing": True}
        if unique_id in pipe.inflight and not pipe.inflight[unique_id].done():
            return {"id": ex["id"] if ex else None, "status": "queued", "existing": True}
        dur = hms_to_seconds(panel_duration)
        talk = int(talk_seconds) if talk_seconds.strip().isdigit() else dur
        if talk and talk < s.min_call_seconds:
            raise HTTPException(422, f"مدت تماس کمتر از {s.min_call_seconds} ثانیه است.")
        parsed = parse_filename(namefile) if namefile else None
        ext = seller_ext or (parsed.extension if parsed else "")
        raw = storage / f"{uuid.uuid4().hex}.wav"
        size = 0
        with raw.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > s.max_upload_mb << 20:
                    out.close(); raw.unlink(missing_ok=True)
                    raise HTTPException(413, "حجم فایل بیش از حد مجاز است.")
                out.write(chunk)
        if not is_riff_wave(raw.read_bytes()[:12]):
            raw.unlink(missing_ok=True)
            raise HTTPException(422, "فایل WAV معتبر نیست (شاید نشست پنل منقضی شده).")
        fields = dict(unique_id=unique_id, filename=namefile, call_datetime=(parsed.call_datetime.isoformat() if parsed else f"{call_date} {call_time}"),
                      src_masked=mask_phone(src), dst_masked=mask_phone(dst or (parsed.number if parsed else "")),
                      dst_hash=hash_phone(dst or (parsed.number if parsed else ""), s.api_token), seller_ext=ext,
                      seller_name=sellers.get(ext, {}).get("name") if isinstance(sellers.get(ext), dict) else sellers.get(ext),
                      direction=(parsed.direction if parsed else direction), panel_duration=dur, status="queued")
        if ex:
            db.update_analysis(ex["id"], **{k: v for k, v in fields.items() if k != "unique_id"})
            aid = ex["id"]
        else:
            aid = db.create_analysis(**fields)
        db.audit(user, "create", aid)
        pipe.inflight[unique_id] = asyncio.create_task(pipe.run(aid, str(raw)))
        return {"id": aid, "status": "queued"}

    def _owned(aid: int) -> dict:
        a = db.get(aid)
        if not a:
            raise HTTPException(404, "تحلیل یافت نشد.")
        return a

    @app.get("/api/v1/analyses/by-unique-id/{uid}")
    def by_uid(uid: str, _: str = Depends(auth)):
        a = db.get_by_uid(uid)
        if not a:
            raise HTTPException(404, "یافت نشد.")
        return a


    @app.post("/api/v1/analyses/batch-status")
    def batch(b: BatchIn, _: str = Depends(auth)):
        return db.batch_status(b.unique_ids[:500])

    @app.get("/api/v1/analyses")
    def list_(seller_ext: str | None = None, date_from: str | None = None, date_to: str | None = None,
              min_score: float | None = None, max_score: float | None = None, stage: str | None = None,
              status: str | None = None, search: str | None = None, tag: str | None = None,
              sort: str = "created_at", desc: bool = True, limit: int = 50, offset: int = 0, _: str = Depends(auth)):
        return db.list(seller_ext=seller_ext, date_from=date_from, date_to=date_to, min_score=min_score,
                       max_score=max_score, stage=stage, status=status, search=search, tag=tag, sort=sort,
                       desc=desc, limit=min(limit, 200), offset=offset)

    @app.get("/api/v1/analyses/{aid}")
    def get(aid: int, user: str = Depends(auth)):
        a = _owned(aid); db.audit(user, "view", aid)
        a["transcript"] = db.get_transcript(aid)
        return a

    @app.get("/api/v1/analyses/{aid}/events")
    async def events(aid: int, _: str = Depends(auth)):
        _owned(aid)

        async def gen():
            last = None
            for _i in range(600):
                st = db.get(aid)["status"]
                if st != last:
                    yield f"data: {json.dumps({'status': st})}\n\n"; last = st
                if st in {"done", "failed"}:
                    return
                await asyncio.sleep(1)
        return StreamingResponse(gen(), media_type="text/event-stream")


    @app.post("/api/v1/analyses/{aid}/reanalyze", status_code=202)
    async def reanalyze(aid: int, b: ReIn | None = None, user: str = Depends(auth)):
        _owned(aid); db.audit(user, "reanalyze", aid)
        asyncio.create_task(pipe.reanalyze(aid, b.seller_speaker if b else None))
        return {"id": aid, "status": "analyzing"}


    @app.post("/api/v1/analyses/{aid}/override")
    def override(aid: int, b: OverrideIn, user: str = Depends(auth)):
        a = _owned(aid)
        old = (a["result"] or {}).get("overall", {}).get(b.field) if a["result"] else None
        db.x("INSERT INTO overrides(analysis_id,user,field,old,new,note,created_at) VALUES(?,?,?,?,?,?,strftime('%s','now'))",
             (aid, user, b.field, str(old), str(b.new), b.note))
        db.audit(user, "override", aid)
        return {"ok": True}


    @app.post("/api/v1/analyses/{aid}/notes")
    def note(aid: int, b: NoteIn, user: str = Depends(auth)):
        _owned(aid)
        db.x("INSERT INTO notes(analysis_id,user,text,created_at) VALUES(?,?,?,strftime('%s','now'))", (aid, user, b.text))
        return {"ok": True}


    @app.post("/api/v1/analyses/{aid}/feedback")
    def feedback(aid: int, b: FeedbackIn, _: str = Depends(auth)):
        a = _owned(aid)
        ms = next((c["score"] for c in (a["result"] or {}).get("criteria", []) if c["id"] == b.criterion_id), None)
        db.x("INSERT INTO feedback(analysis_id,criterion_id,agrees,manager_score,reason,model_score,created_at) VALUES(?,?,?,?,?,?,strftime('%s','now'))",
             (aid, b.criterion_id, int(b.agrees), b.manager_score, b.reason, ms))
        return {"ok": True}

    @app.delete("/api/v1/analyses/{aid}")
    def delete(aid: int, user: str = Depends(auth)):
        _owned(aid)
        p = db.delete(aid); db.audit(user, "delete", aid)
        if p:
            Path(p).unlink(missing_ok=True)
        return {"ok": True}

    @app.get("/api/v1/analyses/{aid}/audio")
    def audio(aid: int, _: str = Depends(auth)):
        a = _owned(aid)
        if not a.get("audio_path") or not Path(a["audio_path"]).exists():
            raise HTTPException(404, "فایل صوتی نگهداری نشده است.")
        return FileResponse(a["audio_path"], media_type="audio/wav")

    @app.get("/api/v1/sellers/stats")
    def sellers_stats(_: str = Depends(auth)):
        return db.seller_stats()

    @app.get("/api/v1/sellers/{ext}/stats")
    def seller_stats(ext: str, _: str = Depends(auth)):
        return db.seller_stats(ext)

    @app.get("/api/v1/rubric")
    def rubric_get(_: str = Depends(auth)):
        r = state["rubric"]
        return {"version": r.version, "criteria": r.criteria, "scoring": r.schema["scoring"], "markdown": r.rubric_md}

    @app.post("/api/v1/rubric/reload")
    def rubric_reload(user: str = Depends(auth)):
        r = load_rubric(s.rubric_dir)
        state["rubric"] = r
        if pipe.analyzer:
            pipe.analyzer = Analyzer(r, pipe.analyzer.llm, s.analysis_model, s.redact_pii)
        db.audit(user, "rubric_reload", None)
        return {"version": r.version}

    return app


def _lazy_app():
    return create_app()


app = create_app()