"""توزیع اکستنشن از خود بک‌اند: فهرست فایل‌ها + هش + نسخه‌ی خودکار.

چرا: اکستنشن روی کامپیوتر کاربران (بدون ادمین) به‌صورت unpacked نصب می‌شود و Chrome برای آن به‌روزرسانی خودکار ندارد.
بک‌اند پوشه‌ی `extension/` را همان لحظه از دیسک می‌خواند و نسخه‌ای می‌سازد که با هر تغییر فایل عوض می‌شود؛
اسکریپت همگام‌ساز روی هر کامپیوتر (client/sync.ps1) فایل‌های تغییرکرده را می‌گیرد و خود اکستنشن
با chrome.runtime.reload() نسخه‌ی جدید را برمی‌دارد. پس تغییر اکستنشن = فقط commit روی سرور؛ نه ری‌استارت، نه نصب مجدد.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

# فقط این‌ها توزیع می‌شوند (تست‌ها، fixtureها و dev هرگز).
_ROOTS = ("src", "assets")
# preset.json آدرس سرور و توکن همان کامپیوتر است و فقط محلی نگه داشته می‌شود.
_NEVER = {"src/preset.json", "src/preset.example.json"}
_SKIP_SUFFIX = (".map", ".pyc")


@dataclass(frozen=True)
class Bundle:
    build: str          # هش کوتاه از محتوای همه‌ی فایل‌ها
    version: str        # نسخه‌ی معتبر Chrome (a.b.c.d) که در manifest.json توزیع‌شده می‌نشیند
    files: dict[str, bytes]

    def index(self) -> dict:
        return {
            "build": self.build,
            "version": self.version,
            "files": [{"path": p, "sha256": hashlib.sha256(b).hexdigest(), "size": len(b)}
                      for p, b in sorted(self.files.items())],
        }


def _walk(ext_dir: Path):
    for root in _ROOTS:
        base = ext_dir / root
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(ext_dir).as_posix()
            if rel in _NEVER or rel.endswith(_SKIP_SUFFIX) or any(part.startswith(".") for part in p.relative_to(ext_dir).parts):
                continue
            yield rel, p


def _chrome_version(base: str, digest: str) -> str:
    """۲ بخش اول از manifest + دو بخش ۱۶بیتی از هش (هر بخش Chrome حداکثر ۶۵۵۳۵)."""
    parts = (base.split(".") + ["0", "0"])[:2]
    major_minor = ".".join(str(int(x)) if x.isdigit() else "0" for x in parts)
    return f"{major_minor}.{int(digest[:4], 16)}.{int(digest[4:8], 16)}"


def load_bundle(ext_dir: str | Path) -> Bundle:
    ext = Path(ext_dir)
    mpath = ext / "manifest.json"
    if not mpath.is_file():
        raise FileNotFoundError(f"manifest.json not found in {ext}")
    base_manifest = mpath.read_bytes()
    files: dict[str, bytes] = {rel: p.read_bytes() for rel, p in _walk(ext)}

    h = hashlib.sha256(base_manifest)
    for rel in sorted(files):
        h.update(rel.encode()); h.update(b"\0"); h.update(hashlib.sha256(files[rel]).digest())
    digest = h.hexdigest()

    m = json.loads(base_manifest.decode("utf-8"))
    base_version = str(m.get("version", "0.0")).strip()
    version = _chrome_version(base_version, digest)
    m["version"] = version
    m["version_name"] = f"{base_version} ({digest[:8]})"
    files["manifest.json"] = (json.dumps(m, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return Bundle(build=digest[:16], version=version, files=files)


class BundleCache:
    """هر بار فقط mtime/size فایل‌ها را می‌سنجد و فقط اگر چیزی عوض شده باشد دوباره هش می‌گیرد."""

    def __init__(self, ext_dir: str | Path):
        self.ext_dir = Path(ext_dir)
        self._sig: tuple | None = None
        self._bundle: Bundle | None = None

    def _signature(self) -> tuple:
        sig = []
        for rel, p in [("manifest.json", self.ext_dir / "manifest.json"), *_walk(self.ext_dir)]:
            try:
                st = p.stat()
            except OSError:
                continue
            sig.append((rel, st.st_mtime_ns, st.st_size))
        return tuple(sig)

    def get(self) -> Bundle:
        sig = self._signature()
        if self._bundle is None or sig != self._sig:
            self._bundle, self._sig = load_bundle(self.ext_dir), sig
        return self._bundle


def make_zip(bundle: Bundle) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p, b in sorted(bundle.files.items()):
            z.writestr(p, b)
    return buf.getvalue()
