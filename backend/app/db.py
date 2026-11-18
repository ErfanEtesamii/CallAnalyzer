"""لایهٔ دیتابیس (SQLite با sqlite3 استاندارد؛ قابل جایگزینی با SQLAlchemy/Postgres)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses(
 id INTEGER PRIMARY KEY AUTOINCREMENT, unique_id TEXT UNIQUE NOT NULL, filename TEXT, call_datetime TEXT,
 src_masked TEXT, dst_masked TEXT, dst_hash TEXT, seller_ext TEXT, seller_name TEXT, direction TEXT,
 panel_duration INTEGER, real_duration REAL, status TEXT NOT NULL, error_code TEXT, error_message TEXT,
 rubric_version TEXT, model TEXT, created_at REAL, updated_at REAL, audio_path TEXT, retention_until REAL);
CREATE INDEX IF NOT EXISTS ix_an_seller ON analyses(seller_ext);
CREATE INDEX IF NOT EXISTS ix_an_dst ON analyses(dst_hash);
CREATE TABLE IF NOT EXISTS transcripts(analysis_id INTEGER PRIMARY KEY, provider TEXT, segments_json TEXT, quality_metrics TEXT);
CREATE TABLE IF NOT EXISTS results(analysis_id INTEGER PRIMARY KEY, result_json TEXT, overall_score REAL, grade TEXT,
 customer_stage TEXT, interest_level REAL, schema_version TEXT, prompt_version TEXT, percentile REAL);
CREATE TABLE IF NOT EXISTS overrides(id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER, user TEXT, field TEXT,
 old TEXT, new TEXT, note TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER, user TEXT, text TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER, criterion_id TEXT,
 agrees INTEGER, manager_score REAL, reason TEXT, model_score REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS analysis_tags(analysis_id INTEGER, tag_id INTEGER, PRIMARY KEY(analysis_id, tag_id));
CREATE TABLE IF NOT EXISTS usage_log(id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER, stage TEXT, provider TEXT,
 tokens_in INTEGER, tokens_out INTEGER, audio_seconds REAL, cost_estimate REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, action TEXT, analysis_id INTEGER, created_at REAL);
"""

LIST_SORT = {"created_at": "a.created_at", "score": "r.overall_score", "call_datetime": "a.call_datetime"}


class DB:
    def __init__(self, url: str = "sqlite:///./data/app.db"):
        path = url.replace("sqlite:///", "")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def x(self, sql: str, args: tuple = ()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    # --- analyses ---
    def create_analysis(self, **f: Any) -> int:
        now = time.time()
        f.setdefault("status", "queued")
        f["created_at"] = f["updated_at"] = now
        cols = ",".join(f)
        return self.x(f"INSERT INTO analyses({cols}) VALUES({','.join('?' * len(f))})", tuple(f.values()))

    def update_analysis(self, aid: int, **f: Any) -> None:
        f["updated_at"] = time.time()
        self.x(f"UPDATE analyses SET {','.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), aid))

    def fail_interrupted(self) -> int:
        """کارهای نیمه‌کاره‌ی مانده از اجرای قبلی (ری‌استارت/خاموشی) را failed می‌کند تا ابداً گیر نکنند."""
        with self.lock:
            cur = self.conn.execute(
                "UPDATE analyses SET status='failed', error_code='interrupted', error_message=?, updated_at=? "
                "WHERE status IN ('queued','preprocessing','transcribing','analyzing')",
                ("پردازش با ری‌استارت سرویس قطع شد. دوباره تلاش کنید.", time.time()))
            self.conn.commit()
            return cur.rowcount

    def get(self, aid: int) -> dict | None:
        rows = self.q("SELECT * FROM analyses WHERE id=?", (aid,))
        return self._attach(rows[0]) if rows else None

    def get_by_uid(self, uid: str) -> dict | None:
        rows = self.q("SELECT * FROM analyses WHERE unique_id=?", (uid,))
        return self._attach(rows[0]) if rows else None

    def _attach(self, a: dict) -> dict:
        r = self.q("SELECT * FROM results WHERE analysis_id=?", (a["id"],))
        a["result"] = json.loads(r[0]["result_json"]) if r else None
        a["overall_score"] = r[0]["overall_score"] if r else None
        a["grade"] = r[0]["grade"] if r else None
        a["percentile"] = r[0]["percentile"] if r else None
        a["overrides"] = self.q("SELECT * FROM overrides WHERE analysis_id=? ORDER BY id", (a["id"],))
        a["notes"] = self.q("SELECT * FROM notes WHERE analysis_id=? ORDER BY id", (a["id"],))
        return a

    def batch_status(self, uids: list[str]) -> dict[str, dict]:
        if not uids:
            return {}
        ph = ",".join("?" * len(uids))
        rows = self.q(f"SELECT a.id,a.unique_id,a.status,a.error_message,r.overall_score,r.grade FROM analyses a "
                      f"LEFT JOIN results r ON r.analysis_id=a.id WHERE a.unique_id IN ({ph})", tuple(uids))
        return {r["unique_id"]: r for r in rows}

    def list(self, *, seller_ext=None, date_from=None, date_to=None, min_score=None, max_score=None,
             stage=None, status=None, search=None, tag=None, sort="created_at", desc=True,
             limit=50, offset=0) -> dict:
        w, a = ["1=1"], []
        for cond, val in [("a.seller_ext=?", seller_ext), ("a.call_datetime>=?", date_from), ("a.call_datetime<=?", date_to),
                          ("r.overall_score>=?", min_score), ("r.overall_score<=?", max_score),
                          ("r.customer_stage=?", stage), ("a.status=?", status)]:
            if val is not None:
                w.append(cond); a.append(val)
        if search:
            w.append("(a.dst_masked LIKE ? OR a.seller_name LIKE ? OR a.unique_id LIKE ?)")
            a += [f"%{search}%"] * 3
        if tag:
            w.append("a.id IN (SELECT at.analysis_id FROM analysis_tags at JOIN tags t ON t.id=at.tag_id WHERE t.name=?)")
            a.append(tag)
        col = LIST_SORT.get(sort, "a.created_at")
        base = f"FROM analyses a LEFT JOIN results r ON r.analysis_id=a.id WHERE {' AND '.join(w)}"
        total = self.q(f"SELECT COUNT(*) n {base}", tuple(a))[0]["n"]
        rows = self.q(f"SELECT a.*, r.overall_score, r.grade, r.customer_stage, r.interest_level, r.percentile {base} "
                      f"ORDER BY {col} {'DESC' if desc else 'ASC'} LIMIT ? OFFSET ?", (*a, limit, offset))
        return {"total": total, "items": rows}

    # --- results ---
    def save_transcript(self, aid: int, provider: str, segments: list[dict], quality: dict) -> None:
        self.x("INSERT OR REPLACE INTO transcripts VALUES(?,?,?,?)",
               (aid, provider, json.dumps(segments, ensure_ascii=False), json.dumps(quality)))

    def get_transcript(self, aid: int) -> dict | None:
        r = self.q("SELECT * FROM transcripts WHERE analysis_id=?", (aid,))
        return {"provider": r[0]["provider"], "segments": json.loads(r[0]["segments_json"]),
                "quality": json.loads(r[0]["quality_metrics"] or "{}")} if r else None

    def save_result(self, aid: int, result: dict, prompt_version: str, percentile: float | None) -> None:
        o, cs = result.get("overall", {}), result.get("customer_status") or {}
        self.x("INSERT OR REPLACE INTO results VALUES(?,?,?,?,?,?,?,?,?)",
               (aid, json.dumps(result, ensure_ascii=False), o.get("score"), o.get("grade"), cs.get("stage"),
                cs.get("interest_level"), result.get("schema_version"), prompt_version, percentile))

    def log_usage(self, aid: int, stage: str, provider: str, tin=0, tout=0, secs=0.0, cost=0.0) -> None:
        self.x("INSERT INTO usage_log(analysis_id,stage,provider,tokens_in,tokens_out,audio_seconds,cost_estimate,created_at)"
               " VALUES(?,?,?,?,?,?,?,?)", (aid, stage, provider, tin, tout, secs, cost, time.time()))

    def spend_today(self) -> float:
        start = time.time() - time.time() % 86400
        return self.q("SELECT COALESCE(SUM(cost_estimate),0) s FROM usage_log WHERE created_at>=?", (start,))[0]["s"]

    def audit(self, user: str, action: str, aid: int | None) -> None:
        self.x("INSERT INTO audit_log(user,action,analysis_id,created_at) VALUES(?,?,?,?)", (user, action, aid, time.time()))

    def delete(self, aid: int) -> str | None:
        a = self.q("SELECT audio_path FROM analyses WHERE id=?", (aid,))
        for t in ("transcripts", "results", "overrides", "notes", "feedback", "analysis_tags", "usage_log"):
            self.x(f"DELETE FROM {t} WHERE analysis_id=?", (aid,))
        self.x("DELETE FROM analyses WHERE id=?", (aid,))
        return a[0]["audio_path"] if a else None

    # --- stats ---
    def seller_stats(self, seller_ext: str | None = None) -> list[dict]:
        w, a = ("WHERE a.seller_ext=?", (seller_ext,)) if seller_ext else ("", ())
        return self.q(f"SELECT a.seller_ext, a.seller_name, COUNT(*) calls, AVG(r.overall_score) avg_score, "
                      f"MIN(r.overall_score) min_score, MAX(r.overall_score) max_score FROM analyses a JOIN results r "
                      f"ON r.analysis_id=a.id {w} {'AND' if w else 'WHERE'} r.overall_score IS NOT NULL "
                      f"GROUP BY a.seller_ext ORDER BY avg_score DESC", a)

    def scores_population(self, seller_ext: str | None = None) -> list[float]:
        w, a = ("AND a.seller_ext=?", (seller_ext,)) if seller_ext else ("", ())
        return [r["overall_score"] for r in self.q(
            f"SELECT r.overall_score FROM results r JOIN analyses a ON a.id=r.analysis_id "
            f"WHERE r.overall_score IS NOT NULL {w}", a)]
