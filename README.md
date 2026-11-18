# تحلیل هوشمند مکالمات فروشندگان — فراز هنر

اکستنشن کروم (MV3) + بک‌اند FastAPI که مکالمات ضبط‌شده‌ی پنل Issabel را دانلود، رونویسی و با Claude طبق روبریک (`rubric/`) تحلیل می‌کند.

## راه‌اندازی بک‌اند
```bash
cd backend && cp .env.example .env   # API_TOKEN و ANTHROPIC_API_KEY را پر کنید
pip install -r requirements.txt       # ffmpeg هم لازم است
python3 scripts/doctor.py             # بررسی محیط
uvicorn app.main:app --port 8000
```
Docker: `docker compose up -d` (Caddy با HTTPS). تست‌ها: `make test`، `make ext-test`.

## نصب اکستنشن
برای کاربران عادی (بدون ادمین) و به‌روزرسانی خودکار: `docs/auto-update.md` و `INSTALL.md`. نصب دستی برای توسعه:
`chrome://extensions` ← Developer mode ← Load unpacked ← پوشه‌ی `extension/`. سپس تنظیمات: آدرس بک‌اند و توکن. حداقل Chrome 114.
مقدار `ALLOWED_ORIGINS` را `chrome-extension://<ID>` بگذارید.

## پیش‌نمایش رابط (بدون نصب اکستنشن)
`make preview` سپس `extension/dev/preview.html` را در Chrome باز کنید (با داده‌ی نمونه). پارامترها: `?tab=queue|history|compare`، `?theme=dark`، `?empty=1`.

## فونت
برای ظاهر بهتر فایل `Vazirmatn.woff2` را در `extension/assets/fonts/` بگذارید. بدون آن، Segoe UI یا Tahoma استفاده می‌شود.

## حریم خصوصی
ضبط و پردازش مکالمات نیازمند اطلاع‌رسانی به مشتری است؛ متن پیشنهادی ابتدای تماس: «این تماس جهت بهبود کیفیت خدمات ضبط می‌شود.» به‌طور پیش‌فرض صوت پس از پردازش حذف و PII پیش از ارسال به Claude پنهان می‌شود. حالت محلی: `STT_PROVIDER=faster_whisper`.

## ویرایش روبریک
فایل‌های `rubric/` را ویرایش، `make rubric` را اجرا و `POST /api/v1/rubric/reload` را بزنید. وزن‌ها در `rubric.config.json`.

## وضعیت پیاده‌سازی و محدودیت‌ها
در `docs/` و پیام تحویل شرح داده شده است.
