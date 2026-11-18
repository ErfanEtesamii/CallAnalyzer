#!/bin/sh
# ساخت زیپ تولیدی اکستنشن (بدون تست‌ها و فیکسچرها)
set -e
cd "$(dirname "$0")"
mkdir -p ../dist && rm -f ../dist/extension.zip
zip -r ../dist/extension.zip manifest.json src assets -x "*.map" -x "src/preset.json"
echo "dist/extension.zip"
