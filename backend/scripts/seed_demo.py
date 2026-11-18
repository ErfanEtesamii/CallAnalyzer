"""پر کردن دیتابیس با داده‌ی نمایشی برای بازبینی UI بدون تماس واقعی."""
import json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.analysis.rubric_loader import load_rubric
from app.analysis.scoring import compute_overall
from app.config import Settings
from app.db import DB

s = Settings.from_env(); db = DB(s.database_url); r = load_rubric(s.rubric_dir)
random.seed(7)
for i in range(12):
    ext = random.choice(["14", "15", "16"])
    crit = [{"id": c["id"], "score": random.randint(3, 10), "applicable": c["id"] != "followup_quality", "confidence": .8,
             "name": c["name"], "reasoning": "نمونه‌ی نمایشی", "evidence": []} for c in r.criteria]
    ov = compute_overall(crit, r.weights, r.applies_to, "cold_new", [], r.config)
    res = {"schema_version": "1.0", "rubric_version": r.version, "call_validity": {"is_analyzable": True, "call_type": "cold_new"},
           "summary": "تماس نمایشی", "overall": {"score": ov.score, "grade": ov.grade, "rank_label": ov.rank_label, "headline": "نمونه‌ی نمایشی", "confidence": .8},
           "criteria": crit, "customer_status": {"stage": random.choice(r.ids("customer_stage_ids")), "interest_level": random.randint(0, 10)}, "warnings": []}
    aid = db.create_analysis(unique_id=f"demo.{i}", filename=f"demo{i}.wav", seller_ext=ext, seller_name=f"فروشنده {ext}",
                             call_datetime=f"2026-11-{10 + i % 8:02d}T10:00:00", dst_masked="0919***5664", direction="out", status="done")
    db.save_result(aid, res, "demo", None)
print("۱۲ تحلیل نمایشی ساخته شد")
