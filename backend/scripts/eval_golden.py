"""اجرای مجموعه‌ی طلایی: backend/golden/*.json شامل {transcript: [...segments], expected: {overall, criteria}}.
هر مورد چند بار اجرا می‌شود؛ ثبات (انحراف معیار) و انحراف از امتیاز مدیر گزارش می‌شود. نیازمند ANTHROPIC_API_KEY."""
import asyncio, json, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.analysis.analyzer import Analyzer, AnthropicLLM
from app.analysis.rubric_loader import load_rubric
from app.config import Settings
from app.stt.base import Segment, Transcript

RUNS = 3

async def main():
    s = Settings.from_env(); files = sorted(Path("golden").glob("*.json"))
    if not files:
        print("مجموعه‌ی طلایی خالی است: فایل‌های golden/*.json را از تماس‌های برچسب‌خورده بسازید."); return
    an = Analyzer(load_rubric(s.rubric_dir), AnthropicLLM(s.anthropic_api_key), s.analysis_model, s.redact_pii)
    for f in files:
        g = json.loads(f.read_text(encoding="utf-8"))
        tr = Transcript([Segment(**x) for x in g["transcript"]], diarized=True)
        scores = [(await an.analyze(tr, {}, seller_speaker=g.get("seller_speaker"))).result["overall"]["score"] for _ in range(RUNS)]
        exp = g["expected"]["overall"]
        print(f"{f.name}: میانگین={statistics.mean(scores):.1f} انحراف‌معیار={statistics.pstdev(scores):.1f} مدیر={exp} اختلاف={statistics.mean(scores) - exp:+.1f}")

asyncio.run(main())
