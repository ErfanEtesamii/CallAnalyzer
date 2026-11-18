"""تولید rubric/rubric.schema.json از روی rubric.md و rubric.config.json."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "rubric"


def parse_criteria(md: str) -> list[dict]:
    out = []
    pat = re.compile(r"^### ۴\.(\d+) (.+?) — `(\w+)` — وزن (\d+)\s*$", re.M)
    ms = list(pat.finditer(md))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else md.index("\n## ۵.", m.end())
        body = md[m.end():end]

        def section(title: str) -> str:
            mm = re.search(rf"\*\*{title}[^\n]*\*\*:?\s*\n(.*?)(?=\n\*\*|\n\*منابع|\Z)", body, re.S)
            return mm.group(1) if mm else ""

        def bullets(s: str) -> list[str]:
            return [x[2:].strip() for x in s.splitlines() if x.startswith("- ")]

        goal = re.search(r"\*\*هدف:\*\*\s*(.+)", body)
        scale = {}
        for r in re.finditer(r"- \*\*(\d+)-(\d+):\*\*\s*(.+)", body):
            scale[f"{r.group(1)}-{r.group(2)}"] = r.group(3).strip()
        src = re.search(r"\*منابع:\*\s*(.+)", body)
        out.append({
            "id": m.group(3), "name": m.group(2).strip(), "weight": int(m.group(4)),
            "goal": goal.group(1).strip() if goal else "",
            "positive_signs": bullets(section("نشانه‌های مثبت")),
            "negative_signs": bullets(section("نشانه‌های منفی")),
            "scale": scale,
            "notes": bullets(section("نکات")),
            "sources": src.group(1).strip() if src else "",
        })
    return out


def main() -> int:
    md = (ROOT / "rubric.md").read_text(encoding="utf-8")
    cfg = json.loads((ROOT / "rubric.config.json").read_text(encoding="utf-8"))
    crit = parse_criteria(md)
    errors = []
    cw = cfg["criteria_weights"]
    if {c["id"] for c in crit} != set(cw):
        errors.append("شناسه‌ی معیارها در rubric.md و config یکسان نیست")
    for c in crit:
        if c["id"] in cw:
            if cw[c["id"]]["weight"] != c["weight"]:
                errors.append(f"وزن {c['id']} ناهماهنگ است")
            c["applies_to"] = cw[c["id"]]["applies_to"]
        if len(c["scale"]) != 5:
            errors.append(f"مقیاس {c['id']} کامل نیست")
        if not c["positive_signs"] or not c["negative_signs"]:
            errors.append(f"نشانه‌های {c['id']} خالی است")
    if sum(c["weight"] for c in crit) != 100:
        errors.append("جمع وزن‌ها ۱۰۰ نیست")
    schema = {
        "rubric_version": cfg["rubric_version"],
        "criteria": crit,
        "scoring": cfg["scoring"],
        "call_type_ids": cfg["call_type_ids"],
        "sales_stage_ids": cfg["sales_stage_ids"],
        "customer_stage_ids": cfg["customer_stage_ids"],
        "objection_type_ids": cfg["objection_type_ids"],
        "seller_style_ids": cfg["seller_style_ids"],
        "lead_info_fields": cfg["lead_info_fields"],
        "min_analyzable_seller_speech_seconds": cfg["min_analyzable_seller_speech_seconds"],
    }
    (ROOT / "rubric.schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    for e in errors:
        print("ناهماهنگی:", e)
    print(f"{len(crit)} معیار، جمع وزن {sum(c['weight'] for c in crit)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
