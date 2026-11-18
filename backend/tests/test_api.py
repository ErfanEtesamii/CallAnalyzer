"""تست HTTP: مطمئن می‌شود بدنه‌ی JSON درست خوانده می‌شود (باگ 422 در batch-status)."""
import hashlib
import io
import json
import re
import zipfile

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


# ---- توزیع اکستنشن (همگام‌سازی خودکار کامپیوترها) ----


def _ext_client(tmp_path):
    ext = tmp_path / "extension"
    (ext / "src" / "lib").mkdir(parents=True)
    (ext / "tests").mkdir()
    (ext / "manifest.json").write_text(json.dumps({"manifest_version": 3, "name": "t", "version": "1.2.0"}), encoding="utf-8")
    (ext / "src" / "background.js").write_text("// bg", encoding="utf-8")
    (ext / "src" / "lib" / "a.js").write_text("// a", encoding="utf-8")
    (ext / "src" / "preset.json").write_text('{"token":"SECRET"}', encoding="utf-8")
    (ext / "src" / "x.js.map").write_text("{}", encoding="utf-8")
    (ext / "tests" / "t.test.js").write_text("// no", encoding="utf-8")
    s = Settings(api_token="test-token-0123456789", database_url=f"sqlite:///{tmp_path}/t.db", storage_dir=str(tmp_path / "st"),
                 rubric_dir="../rubric", sellers_file="../config/sellers.json", extension_dir=str(ext))
    return TestClient(create_app(s)), ext


def test_ext_endpoints_require_auth(tmp_path):
    c, _ = _ext_client(tmp_path)
    for path in ("/api/v1/ext/manifest", "/api/v1/ext/file/manifest.json", "/api/v1/ext/bundle.zip"):
        assert c.get(path).status_code == 401


def test_ext_manifest_content_and_exclusions(tmp_path):
    c, _ = _ext_client(tmp_path)
    m = c.get("/api/v1/ext/manifest", headers=H).json()
    paths = {f["path"] for f in m["files"]}
    assert paths == {"manifest.json", "src/background.js", "src/lib/a.js"}  # بدون preset (توکن)، map و تست‌ها
    assert re.fullmatch(r"1\.2\.\d{1,5}\.\d{1,5}", m["version"])
    assert all(int(x) <= 65535 for x in m["version"].split("."))
    for f in m["files"]:
        body = c.get(f"/api/v1/ext/file/{f['path']}", headers=H).content
        assert hashlib.sha256(body).hexdigest() == f["sha256"] and len(body) == f["size"]
    served = json.loads(c.get("/api/v1/ext/file/manifest.json", headers=H).text)
    assert served["version"] == m["version"] and "version_name" in served


def test_ext_no_path_traversal_and_no_secret(tmp_path):
    c, _ = _ext_client(tmp_path)
    (tmp_path / "secret.txt").write_text("x")
    for p in ("src/preset.json", "../secret.txt", "..%2Fsecret.txt", "tests/t.test.js", "src/x.js.map"):
        assert c.get(f"/api/v1/ext/file/{p}", headers=H).status_code == 404


def test_ext_version_changes_with_content_and_is_stable_otherwise(tmp_path):
    c, ext = _ext_client(tmp_path)
    a = c.get("/api/v1/ext/manifest", headers=H).json()
    assert c.get("/api/v1/ext/manifest", headers=H).json() == a
    (ext / "src" / "background.js").write_text("// bg changed", encoding="utf-8")
    b = c.get("/api/v1/ext/manifest", headers=H).json()
    assert b["build"] != a["build"] and b["version"] != a["version"]
    assert c.get("/api/v1/version", headers=H).json()["extension_build"] == b["build"]


def test_ext_bundle_zip(tmp_path):
    c, _ = _ext_client(tmp_path)
    z = zipfile.ZipFile(io.BytesIO(c.get("/api/v1/ext/bundle.zip", headers=H).content))
    assert sorted(z.namelist()) == ["manifest.json", "src/background.js", "src/lib/a.js"]
