"""محاسبه‌ی قطعی امتیاز کل، درجه و جریمه‌ها (در کد، نه توسط مدل)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScoreResult:
    score: int
    raw_score: float
    grade: str
    rank_label: str
    reliable: bool
    applicable_weight: float
    penalties_applied: list[dict] = field(default_factory=list)
    capped: bool = False


def is_applicable_type(applies_to, call_type: str | None) -> bool:
    return applies_to == "all" or (call_type in applies_to if isinstance(applies_to, list) else True)


def grade_for(score: float, grades: list[dict]) -> tuple[str, str]:
    for g in sorted(grades, key=lambda g: -g["min"]):
        if score >= g["min"]:
            return g["grade"], g["label"]
    return grades[-1]["grade"], grades[-1]["label"]


def compute_overall(criteria: list[dict], weights: dict[str, float], applies_to: dict, call_type: str | None,
                    flags: list[dict], cfg: dict) -> ScoreResult:
    """criteria: [{id, score, applicable}]؛ flags: [{type, severity}]."""
    sc = cfg["scoring"]
    num = den = 0.0
    for c in criteria:
        cid = c["id"]
        if cid not in weights or not c.get("applicable", True) or c.get("score") is None:
            continue
        if not is_applicable_type(applies_to.get(cid, "all"), call_type):
            continue
        s = min(10.0, max(0.0, float(c["score"])))
        num += weights[cid] * s / 10
        den += weights[cid]
    if den == 0:
        return ScoreResult(0, 0.0, "F", "بسیار ضعیف", False, 0.0)
    raw = num / den * 100
    score = raw
    applied: list[dict] = []
    med = [f for f in flags if f.get("severity") == "medium"]
    low = [f for f in flags if f.get("severity") == "low"]
    high = [f for f in flags if f.get("severity") == "high"]
    med_pen = min(10, 5 * len(med))
    low_pen = min(6, 2 * len(low))
    if med_pen:
        score -= med_pen
        applied.append({"severity": "medium", "count": len(med), "points": -med_pen})
    if low_pen:
        score -= low_pen
        applied.append({"severity": "low", "count": len(low), "points": -low_pen})
    capped = False
    if high:
        if score > 50:
            score, capped = 50, True
        applied.append({"severity": "high", "count": len(high), "cap": 50})
    score = max(0.0, min(100.0, score))
    rounded = int(round(score))
    grade, label = grade_for(rounded, sc["grades"])
    if high and grade in {"A", "B", "C"}:  # سقف ۵۰ حداکثر D را تضمین می‌کند
        grade, label = "D", next(g["label"] for g in sc["grades"] if g["grade"] == "D")
    reliable = den >= sc["min_applicable_weight_for_reliable_score"]
    return ScoreResult(rounded, round(raw, 2), grade, label, reliable, den, applied, capped)


def percentile_rank(value: float, population: list[float]) -> float | None:
    if not population:
        return None
    below = sum(1 for p in population if p < value)
    equal = sum(1 for p in population if p == value)
    return round((below + 0.5 * equal) / len(population) * 100, 1)
