"""تنظیمات برنامه از متغیرهای محیطی (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _b(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Settings:
    api_token: str = ""
    allowed_origins: list[str] = field(default_factory=list)
    anthropic_api_key: str = ""
    analysis_model: str = "claude-sonnet-5-5"
    stt_provider: str = "mock"
    openai_api_key: str = ""
    groq_api_key: str = ""
    xai_api_key: str = ""
    stt_model: str = ""
    llm_provider: str = "anthropic"     # anthropic | gemini
    gemini_api_key: str = ""
    gemini_thinking_budget: int | None = None
    hf_token: str = ""
    min_call_seconds: int = 20
    min_speech_ratio: float = 0.15
    max_upload_mb: int = 25
    retention_audio_days: int = 0
    retention_data_days: int = 180
    redact_pii: bool = True
    daily_budget_usd: float = 10.0
    database_url: str = "sqlite:///./data/app.db"
    storage_dir: str = "./data/storage"
    log_level: str = "INFO"
    rubric_dir: str = "../rubric"
    sellers_file: str = "../config/sellers.json"
    extension_dir: str = "../extension"

    @classmethod
    def from_env(cls, dotenv: str | None = ".env") -> "Settings":
        if dotenv:
            _load_dotenv(Path(dotenv))
        e = os.environ.get
        return cls(
            api_token=e("API_TOKEN", ""),
            allowed_origins=[o.strip() for o in e("ALLOWED_ORIGINS", "").split(",") if o.strip()],
            anthropic_api_key=e("ANTHROPIC_API_KEY", ""),
            analysis_model=e("ANALYSIS_MODEL") or ("gemini-2.5-flash" if e("LLM_PROVIDER", "").strip().lower() == "gemini" else "claude-sonnet-5-5"),
            stt_provider=e("STT_PROVIDER", "mock"),
            openai_api_key=e("OPENAI_API_KEY", ""),
            groq_api_key=e("GROQ_API_KEY", ""),
            xai_api_key=e("XAI_API_KEY", ""),
            stt_model=e("STT_MODEL", ""),
            llm_provider=e("LLM_PROVIDER", "anthropic").strip().lower(),
            gemini_api_key=e("GEMINI_API_KEY", ""),
            gemini_thinking_budget=(int(e("GEMINI_THINKING_BUDGET")) if (e("GEMINI_THINKING_BUDGET") or "").strip().lstrip("-").isdigit() else None),
            hf_token=e("HF_TOKEN", ""),
            min_call_seconds=int(e("MIN_CALL_SECONDS", "20")),
            min_speech_ratio=float(e("MIN_SPEECH_RATIO", "0.15")),
            max_upload_mb=int(e("MAX_UPLOAD_MB", "25")),
            retention_audio_days=int(e("RETENTION_AUDIO_DAYS", "0")),
            retention_data_days=int(e("RETENTION_DATA_DAYS", "180")),
            redact_pii=_b("REDACT_PII", True),
            daily_budget_usd=float(e("DAILY_BUDGET_USD", "10")),
            database_url=e("DATABASE_URL", "sqlite:///./data/app.db"),
            storage_dir=e("STORAGE_DIR", "./data/storage"),
            log_level=e("LOG_LEVEL", "INFO"),
            rubric_dir=e("RUBRIC_DIR", "../rubric"),
            sellers_file=e("SELLERS_FILE", "../config/sellers.json"),
            extension_dir=e("EXTENSION_DIR", "../extension"),
        )
