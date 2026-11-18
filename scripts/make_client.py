"""ساخت بسته‌ی نصب سیستم‌ها: اکستنشن با آدرس/توکن از پیش تنظیم‌شده + install.bat + گواهی Caddy.
اجرا: python3 scripts/make_client.py --url https://192.168.1.10 --token XXXX [--ca dist/caddy-root.crt]
"""
import argparse, json, shutil, zipfile
from pathlib import Path
from urllib.parse import urlparse

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True)
ap.add_argument("--token", required=True)
ap.add_argument("--ca", default="")
a = ap.parse_args()

root = Path(__file__).resolve().parent.parent
u = urlparse(a.url)
import re
LAN = re.compile(r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)")
if u.scheme not in ("http", "https") or not u.hostname:
    raise SystemExit("URL must look like https://192.168.1.10 or http://192.168.1.10:8000")
if u.scheme == "http" and not LAN.match(u.hostname):
    raise SystemExit("plain http is only allowed for local-network addresses")

build = root / "dist" / "client"
shutil.rmtree(build, ignore_errors=True)
ext = build / "extension"
ext.mkdir(parents=True)
shutil.copy(root / "extension" / "manifest.json", ext / "manifest.json")
shutil.copytree(root / "extension" / "src", ext / "src")
if (root / "extension" / "assets").exists():
    shutil.copytree(root / "extension" / "assets", ext / "assets")

m = json.loads((ext / "manifest.json").read_text(encoding="utf-8"))
pattern = f"{u.scheme}://{u.hostname}/*"
if pattern not in m["host_permissions"]:
    m["host_permissions"].append(pattern)
(ext / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(ext / "src" / "preset.json").write_text(
    json.dumps({"backendUrl": f"{u.scheme}://{u.netloc}", "token": a.token}, indent=2) + "\n", encoding="utf-8")

ca = Path(a.ca) if a.ca else None
if ca and ca.exists() and ca.stat().st_size:
    shutil.copy(ca, build / "caddy-root.crt")

bat = r"""@echo off
set "DEST=%LOCALAPPDATA%\CallAnalyzer\extension"
echo [1/3] Copying extension...
if exist "%DEST%" rmdir /s /q "%DEST%"
xcopy /e /i /y "%~dp0extension" "%DEST%" >nul
if exist "%~dp0caddy-root.crt" (
  echo [2/3] Trusting server certificate - click Yes in the Windows prompt...
  certutil -user -addstore Root "%~dp0caddy-root.crt" >nul
)
echo %DEST%| clip
echo [3/3] Extension path copied to clipboard. Chrome will open now.
echo.
echo   1) Turn ON "Developer mode" (top right)
echo   2) Click "Load unpacked"
echo   3) Press Ctrl+V in the path box, then "Select Folder"
echo.
start "" chrome "chrome://extensions"
pause
"""
(build / "install.bat").write_text(bat.replace("\n", "\r\n"), encoding="ascii")

out = root / "dist" / "CallAnalyzer-Client.zip"
out.unlink(missing_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in build.rglob("*"):
        if p.is_file():
            z.write(p, p.relative_to(build))
print("✓", out)
