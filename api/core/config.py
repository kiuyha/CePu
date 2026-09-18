"""Konfigurasi aplikasi dari environment variable."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE_PATH,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    # Database & cache
    db_url: str = "sqlite:///./cepu_dev.db"
    redis_url: str = "redis://localhost:6379/0"

    @property
    def sqlalchemy_db_url(self) -> str:
        url = self.db_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("sqlite://") and "+aiosqlite" not in url:
            return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url

    # Internal auth (gateway WA -> backend)
    internal_token: str = "change-me-in-env"
    wa_session_timeout_minutes: int = 15

    # Model
    model_path: str = "./models/indobert-v1"
    model_version: str = "indobert-v1"
    hf_model_id: str = "Kiuyha/indobert-job-fraud-detection"
    bert_max_length: int = 256
    bert_max_concurrent_inference: int = 2

    # WhatsApp gateway
    wa_session_path: str = "./gateway-wa/session"

    # Rate limiting
    rate_limit_detect_per_minute: int = 10
    rate_limit_report_per_hour: int = 5

    # OCR
    ocr_lang: str = "ind+eng"

    # Upload constraints
    max_upload_size_bytes: int = 2 * 1024 * 1024
    allowed_image_content_types: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
