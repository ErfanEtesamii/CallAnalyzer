# مدل رایگان: Groq (رونویسی) + Gemini (تحلیل)

`backend\.env` را این‌طور تنظیم کنید (`.env` در گیت نیست و فقط روی سرور ویرایش می‌شود). تسک آپدیت تغییر `.env` را می‌بیند و تا ۲ دقیقه بعد سرویس را خودش ری‌استارت می‌کند؛ برای فوری: `deploy\nssm.exe restart CallAnalyzer`:

```
STT_PROVIDER=groq
GROQ_API_KEY=...          # https://console.groq.com/keys
LLM_PROVIDER=gemini
GEMINI_API_KEY=...        # https://aistudio.google.com/apikey
ANALYSIS_MODEL=gemini-2.5-flash   # نام را در AI Studio با مدل‌های رایگان فعلی تطبیق دهید
GEMINI_THINKING_BUDGET=0          # اختیاری، فقط مدل‌های 2.5
```
بررسی: `cd backend && python scripts\doctor.py`

## سقف‌ها (مرتب بررسی کنید؛ تغییر می‌کنند)
- Groq Whisper رایگان: ۲۰ درخواست در دقیقه، ۷۲۰۰ ثانیه صوت در ساعت، ۲۸٬۸۰۰ ثانیه در روز (≈ ۸ ساعت)، فایل تا ۲۵MB.
- Gemini رایگان: سهمیه‌ی درخواست/توکن در AI Studio ← Rate limits. پرامپت این پروژه بزرگ است (روبریک)، پس به سقف توکن و درخواست بیشتر می‌رسید.
- با پر شدن سهمیه، تحلیل با خطای «سهمیه تمام شده» می‌ماند و از افزونه «تلاش مجدد» می‌شود. هزینه‌ی این دو در سقف `DAILY_BUDGET_USD` حساب نمی‌شود (صفر).

## حریم خصوصی
در حالت رایگان Gemini، Google ممکن است ورودی/خروجی را برای بهبود محصولاتش استفاده کند و بازبین انسانی بخواند. شماره‌کارت/کد ملی/تلفن قبل از ارسال پنهان می‌شود (`REDACT_PII=true`) ولی محتوای مکالمه می‌رود. صوت به Groq (آمریکا) فرستاده می‌شود.
برای برگشت به Claude: `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` و `ANALYSIS_MODEL=` خالی.
