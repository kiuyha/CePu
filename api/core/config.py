"""Konfigurasi aplikasi dari environment variable."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_API_DIR = Path(__file__).resolve().parent.parent

_ENV_FILE_PATHS = [
    _ROOT_DIR / ".env",
    _API_DIR / ".env",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE_PATHS,
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

    # Admin Portal Credentials (hardcoded default or from .env)
    admin_username: str = "admin"
    admin_password: str = "cepu123"

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

    # Phone Checking Configuration (aduannomor.id & kredibel.com)
    aduannomor_base_url: str = "https://aduannomor.id"
    aduannomor_timeout_seconds: float = 5.0
    kredibel_base_url: str = "https://www.kredibel.com"
    kredibel_session_cookie: str = ""
    kredibel_user_agent: str = (
        "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/153.0.0.0 Mobile Safari/537.36"
    )
    kredibel_timeout_seconds: float = 6.0

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

    # JobStreet Job Search (on-demand, via GraphQL JobSearchV7)
    # Tanpa cookie browser: cukup session id (otomatis dibuat acak kalau kosong).
    jobstreet_base_url: str = "https://id.jobstreet.com"
    jobstreet_session_id: str = ""
    jobstreet_visitor_id: str = ""
    jobstreet_sol_visitor_id: str = ""
    jobstreet_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
    )
    jobstreet_timeout_seconds: float = 10.0
    jobstreet_default_page_size: int = 10
    # Umur maksimal data jobstreet tersimpan (jam). Lewat dari ini dianggap
    # basi -> scrape ulang 1 halaman saat berikutnya dicari.
    jobstreet_cache_ttl_hours: int = 24

    # Anti-ban global untuk semua scraper eksternal (lihat services/anti_ban.py).
    # Jeda minimum + jitter acak antar request ke host yang sama (detik).
    scrape_min_interval_seconds: float = 1.5
    scrape_jitter_seconds: float = 1.0
    # Circuit breaker: berhenti memukul host setelah N gagal berturut-turut
    # (challenge/blocked/rate-limit) selama cooldown detik. Mencegah flag
    # makin panjang akibat dihantam terus saat sedang memblokir.
    scrape_circuit_threshold: int = 3
    scrape_circuit_cooldown_seconds: float = 900.0
    # Proxy egress per sumber (opsional). IP datacenter gampang di-flag;
    # arahkan lewat IP rumahan tepercaya bila ada, mis:
    #   "http://user:pass@ip-rumah:8080" atau "socks5h://127.0.0.1:1080"
    companyhouse_proxy: str = ""
    kredibel_proxy: str = ""
    jobstreet_proxy: str = ""

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
