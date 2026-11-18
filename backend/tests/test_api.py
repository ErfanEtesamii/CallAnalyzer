"""تست HTTP: مطمئن می‌شود بدنه‌ی JSON درست خوانده می‌شود (باگ 422 در batch-status)."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

H = {"Authorization": "Bearer test-token-0123456789"}


def _client(tmp_path):
    s = Settings(api_token="test-token-0123456789", database_url=f"sqlite:///{tmp_path}/t.db",
                 storage_dir=str(tmp_path / "st"), rubric_dir="../rubric", sellers_file="../config/sellers.json")
    return TestClient(create_app(s))


def test_health_and_auth(tmp_path):
    c = _client(tmp_path)
    assert c.get("/health").json()["ok"] is True
    assert c.get("/api/v1/version").status_code == 401
    assert c.get("/api/v1/version", headers=H).status_code == 200


def test_batch_status_accepts_json_body(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/v1/analyses/batch-status", json={"unique_ids": ["1.1", "2.2"]}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json() == {}


def test_json_body_endpoints_not_422(tmp_path):
    c = _client(tmp_path)
    for path, body in [("/api/v1/analyses/999/notes", {"text": "x"}),
                       ("/api/v1/analyses/999/override", {"field": "overall_score", "new": 50}),
                       ("/api/v1/analyses/999/feedback", {"criterion_id": "c", "agrees": True}),
                       ("/api/v1/analyses/999/reanalyze", {})]:
        r = c.post(path, json=body, headers=H)
        assert r.status_code != 422, (path, r.text)
