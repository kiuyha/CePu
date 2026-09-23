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

    # NER Model
    ner_model_id: str = "fahmisyaifudin/indobert_ner_p1"
    ner_max_length: int = 512

    # WhatsApp gateway
    wa_session_path: str = "./gateway-wa/session"

    # Rate limiting
    rate_limit_detect_per_minute: int = 10
    rate_limit_report_per_hour: int = 5

    # OCR
    ocr_lang: str = "ind+eng"

    # CompanyHouse.id Scraper Configuration
    companyhouse_base_url: str = "https://companyhouse.id"
    companyhouse_session_cookie: str = ""
    companyhouse_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    companyhouse_timeout_seconds: float = 5.0

    # Email Verifier Settings
    disposable_domains_sync_url: str = (
        "https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf"
    )
    disposable_email_domains: str = (
        "yopmail.com,mailinator.com,tempmail.com,guerrillamail.com,10minutemail.com,trashmail.com,sharklasers.com,dispostable.com"
    )
    free_email_domains: str = (
        "gmail.com,yahoo.com,hotmail.com,outlook.com,icloud.com,aol.com,zoho.com"
    )

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
