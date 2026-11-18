# معماری
اکستنشن ← (دانلود WAV با نشست کاربر) ← آپلود به FastAPI ← ffmpeg (mono 16k) ← VAD ← STT (قابل تعویض) ← Claude (tool use با schema) ← verify شواهد ← امتیاز در کد ← SQLite.
- روبریک: `rubric/` منبع حقیقت (config + schema + md)؛ `POST /api/v1/rubric/reload` برای بازخوانی.
- امتیاز کل/درجه/جریمه: `backend/app/analysis/scoring.py` (قطعی، تست‌شده).
- صوت پس از پردازش حذف می‌شود (مگر `RETENTION_AUDIO_DAYS>0`).
- نقاط توسعه: `IngestSource` (حالت خودکار)، webhook، گزارش PDF (هنوز پیاده نشده؛ در README ذکر شده).
