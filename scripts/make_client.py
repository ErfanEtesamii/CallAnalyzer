"""ساخت بسته‌ی نصب کلاینت (برای کاربران عادی، بدون ادمین).

بسته فقط نصب‌کننده + آدرس/توکن است؛ خود اکستنشن را نصب‌کننده از بک‌اند دانلود می‌کند و بعد خودکار همگام نگه می‌دارد
(client/sync.ps1)، پس این بسته را فقط یک‌بار می‌سازید و با تغییر کد اکستنشن نیازی به ساخت دوباره‌اش نیست.

اجرا: python3 scripts/make_client.py --url http://192.168.10.5:8000 --token XXXX [--ca dist/caddy-root.crt]
"""
import argparse, json, re, shutil, zipfile
from pathlib import Path
from urllib.parse import urlparse

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True)
ap.add_argument("--token", required=True)
ap.add_argument("--ca", default="")
a = ap.parse_args()

root = Path(__file__).resolve().parent.parent
u = urlparse(a.url)
LAN = re.compile(r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)")
if u.scheme not in ("http", "https") or not u.hostname:
    raise SystemExit("URL must look like https://192.168.1.10 or http://192.168.1.10:8000")
if u.scheme == "http" and not LAN.match(u.hostname):
    raise SystemExit("plain http is only allowed for local-network addresses")

# آدرس بک‌اند باید در host_permissions اکستنشن باشد، وگرنه fetch اکستنشن به سرور رد می‌شود.
manifest = json.loads((root / "extension" / "manifest.json").read_text(encoding="utf-8"))
covered = any(urlparse(p.replace("*", "x", 1) if p.endswith("/*") else p).hostname == u.hostname
              and p.startswith(u.scheme + "://") for p in manifest.get("host_permissions", []))
if not covered:
    print(f"WARNING: {u.scheme}://{u.hostname}/* is not in extension/manifest.json host_permissions. "
          "Add it there (and commit) or the extension cannot reach the backend.")

build = root / "dist" / "client"
shutil.rmtree(build, ignore_errors=True)
build.mkdir(parents=True)
for name in ("install-client.bat", "install.ps1", "sync.ps1", "sync.vbs"):
    shutil.copy(root / "client" / name, build / name)
(build / "preset.json").write_text(
    json.dumps({"backendUrl": f"{u.scheme}://{u.netloc}", "token": a.token}, indent=2) + "\n", encoding="utf-8")

ca = Path(a.ca) if a.ca else None
if ca and ca.exists() and ca.stat().st_size:
    shutil.copy(ca, build / "caddy-root.crt")

out = root / "dist" / "CallAnalyzer-Client.zip"
out.unlink(missing_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(build.rglob("*")):
        if p.is_file():
            z.write(p, p.relative_to(build))
print("OK", out)
print("Give users this zip: extract, double-click install-client.bat (no admin needed). It contains the token - share it only inside the company.")
