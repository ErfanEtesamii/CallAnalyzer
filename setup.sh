#!/usr/bin/env bash
# نصب یک‌دستوری بک‌اند روی سرور لوکال:  bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"

EXT_ID="pafdcnobmnjinfeefhnleopoildeipch"          # شناسه‌ی ثابت اکستنشن (از key در manifest.json)
ENVF=backend/.env

need() { command -v "$1" >/dev/null 2>&1 || { echo "✗ $1 نصب نیست. $2"; exit 1; }; }
need docker "راهنما: https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || { echo "✗ افزونه‌ی docker compose نصب نیست."; exit 1; }
need openssl "نصب: apt install openssl"

touch "$ENVF"
getkv() { grep -E "^$1=" "$ENVF" 2>/dev/null | head -1 | cut -d= -f2- || true; }
setkv() { grep -v "^$1=" "$ENVF" > "$ENVF.tmp" || true; printf '%s=%s\n' "$1" "$2" >> "$ENVF.tmp"; mv "$ENVF.tmp" "$ENVF"; chmod 600 "$ENVF"; }

# ۱) آدرس سرور (همان که سیستم‌ها با آن وصل می‌شوند)
DEF_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}')
read -rp "آدرس IP یا نام سرور [${DEF_ADDR}]: " ADDR; ADDR=${ADDR:-$DEF_ADDR}

# ۲) توکن (فقط بار اول ساخته می‌شود)
TOKEN=$(getkv API_TOKEN); [ -n "$TOKEN" ] || TOKEN=$(openssl rand -hex 24)

# ۳) کلید Anthropic
KEY=$(getkv ANTHROPIC_API_KEY)
if [ -z "$KEY" ]; then read -rsp "ANTHROPIC_API_KEY: " KEY; echo; fi

# ۴) رونویسی صدا
echo "رونویسی صدا (STT):  1) OpenAI (نیاز به کلید)   2) محلی faster-whisper (بدون ارسال صدا به بیرون)"
read -rp "انتخاب [2]: " CH; CH=${CH:-2}
if [ "$CH" = 1 ]; then
  STT=openai; OAI=$(getkv OPENAI_API_KEY); [ -n "$OAI" ] || { read -rsp "OPENAI_API_KEY: " OAI; echo; }
  setkv OPENAI_API_KEY "$OAI"; echo "WITH_WHISPER=0" > .env
else
  STT=faster_whisper; echo "WITH_WHISPER=1" > .env
fi

setkv API_TOKEN "$TOKEN"
setkv ANTHROPIC_API_KEY "$KEY"
setkv STT_PROVIDER "$STT"
setkv ALLOWED_ORIGINS "chrome-extension://$EXT_ID"

cat > Caddyfile <<CADDY
$ADDR {
  tls internal
  reverse_proxy backend:8000
}
CADDY

echo "▶ ساخت و اجرا (بار اول چند دقیقه طول می‌کشد)…"
docker compose up -d --build

echo "▶ منتظر آماده‌شدن سرور…"
mkdir -p dist
for i in $(seq 1 60); do
  if docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt dist/caddy-root.crt >/dev/null 2>&1; then break; fi
  sleep 2
done
[ -s dist/caddy-root.crt ] || echo "⚠ گواهی Caddy هنوز ساخته نشده؛ چند ثانیه بعد دوباره bash setup.sh بزنید."

if command -v python3 >/dev/null 2>&1; then
  python3 scripts/make_client.py --url "https://$ADDR" --token "$TOKEN" --ca dist/caddy-root.crt
else
  docker run --rm -v "$PWD":/w -w /w python:3.12-slim python scripts/make_client.py --url "https://$ADDR" --token "$TOKEN" --ca dist/caddy-root.crt
fi

curl -skf "https://$ADDR/health" >/dev/null 2>&1 && echo "✓ سرور پاسخ می‌دهد" || echo "⚠ /health پاسخ نداد؛ docker compose logs backend را ببینید."
echo
echo "تمام. بسته‌ی نصب سیستم‌ها:  dist/CallAnalyzer-Client.zip"
echo "آن را روی هر سیستم باز کنید و install.bat را اجرا کنید."
