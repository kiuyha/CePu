"""
Test untuk modul pengecekan nomor telepon:
1. AduanNomorClient (aduannomor.id parsing & calling_code normalization)
2. KredibelScraper (kredibel.com parsing, rating analysis, dan auto-cookie update)
3. check_phone_reputation (integrasi fallback aduannomor -> kredibel -> blacklist)
"""
import pytest
from unittest.mock import MagicMock

from api.services.validators.aduannomor_client import (
    AduanNomorClient,
    parse_phone_number,
)
from api.services.validators.kredibel_scraper import (
    KredibelScraper,
    clean_phone_for_kredibel,
)
from api.services.validators.phone_checker import check_phone_reputation
from api.core.config import get_settings


# ---------- 1. AduanNomor Tests ----------

def test_parse_phone_number_formats():
    assert parse_phone_number("08123456789") == ("+62", "8123456789")
    assert parse_phone_number("+628123456789") == ("+62", "8123456789")
    assert parse_phone_number("628123456789") == ("+62", "8123456789")
    assert parse_phone_number("+62-812-345-6789") == ("+62", "8123456789")


def test_aduannomor_client_parses_success_response(monkeypatch):
    client = AduanNomorClient()

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "status": 200,
        "error": False,
        "data": {
            "reported_phone": "+62811111111",
            "reported_phone_status": "Aktif",
            "reported_count": 0,
            "reported_kejahatan": [],
            "reported_status_laporan": [],
        },
        "messages": "Data Loaded",
    }

    monkeypatch.setattr(client.session, "post", lambda *args, **kwargs: fake_response)

    res = client.check_phone("0811111111")
    assert res is not None
    assert res["reported_count"] == 0
    assert res["reported_phone"] == "+62811111111"


# ---------- 2. KredibelScraper Tests ----------

def test_clean_phone_for_kredibel():
    assert clean_phone_for_kredibel("+6285798017153") == "85798017153"
    assert clean_phone_for_kredibel("085798017153") == "85798017153"
    assert clean_phone_for_kredibel("85798017153") == "85798017153"


def test_kredibel_scraper_parse_bad_rating():
    html_sample = """
    <html>
      <body>
        <div class="card card-stats">
          <div class="card-stats-item">
            <div class="card-stats-label">Kredibel Rating</div>
            <div class="card-stats-value">Cukup Buruk</div>
          </div>
        </div>
      </body>
    </html>
    """
    scraper = KredibelScraper()
    parsed = scraper.parse_kredibel_page(html_sample)

    assert parsed["rating_label"] == "Cukup Buruk"
    assert parsed["is_fraud_flagged"] is True
    assert parsed["rating_score"] >= 0.7


def test_kredibel_scraper_parse_zero_or_clean_rating():
    html_sample = """
    <html>
      <body>
        <div class="card card-stats">
          <div>Tidak ada ulasan ditemukan</div>
        </div>
      </body>
    </html>
    """
    scraper = KredibelScraper()
    parsed = scraper.parse_kredibel_page(html_sample)

    assert parsed["rating_label"] == "Belum ada ulasan"
    assert parsed["is_fraud_flagged"] is False
    assert parsed["rating_score"] == 0.0


def test_kredibel_scraper_auto_updates_session_cookie():
    scraper = KredibelScraper()
    header_sample = [
        "HTTP/2 200",
        "set-cookie: kredibel_session=new_fresh_token_12345; expires=Wed, 23 Sep 2026 20:39:59 GMT; Max-Age=7200; path=/; secure; httponly; samesite=lax",
        "set-cookie: XSRF-TOKEN=xsrf_token_abc; path=/",
    ]
    scraper._update_cookies_from_headers(header_sample)

    assert KredibelScraper._active_cookies.get("kredibel_session") == "new_fresh_token_12345"
    assert KredibelScraper._active_cookies.get("XSRF-TOKEN") == "xsrf_token_abc"
    cookie_str = scraper._get_cookie_header_string()
    assert "kredibel_session=new_fresh_token_12345" in cookie_str


# ---------- 3. check_phone_reputation Tests ----------

async def test_check_phone_reputation_aduannomor_reported(monkeypatch):
    """Jika aduannomor.id memiliki reported_count > 0, skor penipuan harus tinggi (0.95)."""
    fake_aduan = {
        "reported_phone": "+628129999999",
        "reported_count": 3,
        "reported_kejahatan": ["Penipuan Lowongan Kerja"],
    }
    monkeypatch.setattr(
        "api.services.validators.phone_checker.AduanNomorClient.check_phone",
        lambda self, p: fake_aduan,
    )

    res = await check_phone_reputation("08129999999")
    assert res.verdict_score == 0.95
    assert res.verdict_binary is True
    assert res.source == "aduannomor.id"


async def test_check_phone_reputation_fallback_to_kredibel_when_aduan_zero(monkeypatch):
    """
    Jika aduannomor.id reported_count == 0, fallback ke Kredibel.com.
    Jika Kredibel menemukan rating Cukup Buruk, skor penipuan harus tinggi.
    """
    clean_aduan = {
        "reported_phone": "+6285798017153",
        "reported_count": 0,
        "reported_kejahatan": [],
    }
    kredibel_result = {
        "rating_label": "Cukup Buruk",
        "rating_score": 0.85,
        "report_count": 2,
        "is_fraud_flagged": True,
    }

    monkeypatch.setattr(
        "api.services.validators.phone_checker.AduanNomorClient.check_phone",
        lambda self, p: clean_aduan,
    )
    monkeypatch.setattr(
        "api.services.validators.phone_checker.KredibelScraper.fetch_phone_profile",
        lambda self, p: kredibel_result,
    )

    res = await check_phone_reputation("085798017153")
    assert res.verdict_score == 0.85
    assert res.verdict_binary is True
    assert res.source == "kredibel.com"


async def test_check_phone_reputation_safe_when_both_clean(monkeypatch):
    """Jika aduannomor.id reported_count == 0 dan kredibel tidak memiliki ulasan negatif, skor aman (0.2)."""
    clean_aduan = {
        "reported_phone": "+62811111111",
        "reported_count": 0,
        "reported_kejahatan": [],
    }
    kredibel_clean = {
        "rating_label": "Belum ada ulasan",
        "rating_score": 0.0,
        "report_count": 0,
        "is_fraud_flagged": False,
    }

    monkeypatch.setattr(
        "api.services.validators.phone_checker.AduanNomorClient.check_phone",
        lambda self, p: clean_aduan,
    )
    monkeypatch.setattr(
        "api.services.validators.phone_checker.KredibelScraper.fetch_phone_profile",
        lambda self, p: kredibel_clean,
    )

    res = await check_phone_reputation("0811111111")
    assert res.verdict_score == 0.2
    assert res.verdict_binary is False
