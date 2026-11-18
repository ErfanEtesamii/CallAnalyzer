"""بارگذاری روبریک، پیکربندی و زمینه‌ی کسب‌وکار از پوشه‌ی rubric/."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Rubric:
    version: str
    schema: dict
    config: dict
    rubric_md: str
    business_md: str

    @property
    def criteria(self) -> list[dict]:
        return self.schema["criteria"]

    @property
    def weights(self) -> dict[str, float]:
        return {c["id"]: c["weight"] for c in self.criteria}

    @property
    def applies_to(self) -> dict[str, object]:
        return {c["id"]: c["applies_to"] for c in self.criteria}

    def ids(self, key: str) -> list[str]:
        return self.config[key]


def load_rubric(rubric_dir: str | Path) -> Rubric:
    d = Path(rubric_dir)
    cfg = json.loads((d / "rubric.config.json").read_text(encoding="utf-8"))
    schema = json.loads((d / "rubric.schema.json").read_text(encoding="utf-8"))
    if cfg["rubric_version"] != schema["rubric_version"]:
        raise ValueError("نسخه‌ی config و schema روبریک یکسان نیست")
    return Rubric(cfg["rubric_version"], schema, cfg,
                  (d / "rubric.md").read_text(encoding="utf-8"),
                  (d / "business_context.md").read_text(encoding="utf-8"))
