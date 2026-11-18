"""بررسی سلامت محیط: ffmpeg، دیتابیس، فضای دیسک، کلیدها."""
import os, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import Settings
from app.db import DB

s = Settings.from_env()
ok = True
def line(name, good, detail=""):
    global ok
    ok &= bool(good)
    print(("✓" if good else "✗"), name, detail)
line("ffmpeg", shutil.which("ffmpeg"))
if s.llm_provider == "gemini":
    line("GEMINI_API_KEY", s.gemini_api_key, f"(مدل {s.analysis_model})")
else:
    line("ANTHROPIC_API_KEY", s.anthropic_api_key)
line("API_TOKEN", len(s.api_token) >= 16, "(حداقل ۱۶ نویسه)")
line("STT", {"openai": s.openai_api_key, "groq": s.groq_api_key}.get(s.stt_provider, True), s.stt_provider)
try:
    DB(s.database_url); line("database", True)
except Exception as e:
    line("database", False, str(e))
free = shutil.disk_usage(".").free / 1e9
line("disk", free > 1, f"{free:.1f}GB آزاد")
sys.exit(0 if ok else 1)
