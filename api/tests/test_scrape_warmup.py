"""
Test untuk navigasi berurutan ala browser (warm-up + Referer) dan
konfigurasi panen sesi Cloudflare.

Prinsip yang diuji:
1. companyhouse: jar dingin -> GET homepage dulu, lalu detail dengan
   header Referer. Jar hangat -> langsung detail (tanpa request ganda).
2. kredibel: header detail membawa referer + sec-fetch-site same-origin;
   warm-up homepage mengisi cookie anonim saat jar kosong.
3. harvester: site kredibel ikut memanen cf_clearance/__cf_bm.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.core.config import Settings
from api.services.anti_ban import reset_breaker
from api.services.validators.companyhouse_scraper import CompanyHouseScraper
from api.services.validators.kredibel_scraper import KredibelScraper


@pytest.fixture()
def clean_scrape_state():
    """Isolasi state class-level antar-test (cookie + circuit breaker)."""
    saved_ch = dict(CompanyHouseScraper._active_cookies)
    saved_kr = dict(KredibelScraper._active_cookies)
    CompanyHouseScraper._active_cookies.clear()
    KredibelScraper._active_cookies.clear()
    yield
    CompanyHouseScraper._active_cookies.clear()
    CompanyHouseScraper._active_cookies.update(saved_ch)
    KredibelScraper._active_cookies.clear()
    KredibelScraper._active_cookies.update(saved_kr)
    reset_breaker("companyhouse")
    reset_breaker("kredibel")


@pytest.fixture()
def no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *args, **kwargs: None)


def _cold_companyhouse_settings() -> Settings:
    # "" eksplisit menimpa .env (kalau ada cookie asli di root .env).
    return Settings(companyhouse_session_cookie="")


def _fake_ok_page(html: str = "<html><h1>PT Tes</h1></html>"):
    return SimpleNamespace(status_code=200, text=html, cookies={})


# ---------- companyhouse ----------

def test_companyhouse_cold_jar_hits_homepage_first(clean_scrape_state, no_sleep, monkeypatch):
    monkeypatch.setattr(
        "api.services.validators.companyhouse_scraper.throttle",
        lambda *args, **kwargs: 0.0,
    )
    scraper = CompanyHouseScraper(settings=_cold_companyhouse_settings())
    calls = []

    def _fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _fake_ok_page()

    monkeypatch.setattr(scraper.session, "get", _fake_get)

    result = scraper.fetch_company_detail("PT Tes Sejahtera")

    assert result is not None
    assert len(calls) == 2
    home_url, _ = calls[0]
    detail_url, detail_kwargs = calls[1]
    assert home_url.rstrip("/") == scraper.settings.companyhouse_base_url.rstrip("/")
    assert "tes-sejahtera" in detail_url
    assert detail_kwargs.get("headers", {}).get("Referer") == home_url.rstrip("/") + "/"


def test_companyhouse_warm_jar_skips_homepage(clean_scrape_state, no_sleep, monkeypatch):
    monkeypatch.setattr(
        "api.services.validators.companyhouse_scraper.throttle",
        lambda *args, **kwargs: 0.0,
    )
    # Seed sesi agar jar hangat (meniru cookie .env / hasil request lama).
    CompanyHouseScraper._active_cookies["companyhouse_session"] = "seed-abc"
    scraper = CompanyHouseScraper(settings=_cold_companyhouse_settings())
    calls = []

    def _fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _fake_ok_page()

    monkeypatch.setattr(scraper.session, "get", _fake_get)

    scraper.fetch_company_detail("PT Tes Sejahtera")

    assert len(calls) == 1
    assert "tes-sejahtera" in calls[0][0]


# ---------- kredibel ----------

def test_kredibel_detail_headers_look_like_homepage_navigation(clean_scrape_state):
    scraper = KredibelScraper(settings=Settings(kredibel_session_cookie=""))
    headers = scraper._browser_headers()
    lowered = {k.lower(): v for k, v in headers.items()}
    assert lowered.get("referer") == scraper.settings.kredibel_base_url.rstrip("/") + "/"
    assert lowered.get("sec-fetch-site") == "same-origin"


def test_kredibel_cold_warmup_fills_anon_cookies(clean_scrape_state, no_sleep, monkeypatch):
    scraper = KredibelScraper(settings=Settings(kredibel_session_cookie=""))
    seen = {}

    class _FakeSession:
        def get(self, url, **kwargs):
            seen["url"] = url
            return SimpleNamespace(cookies={"cf_clearance": "clr-123", "kredibel_session": "anon"})

    monkeypatch.setattr(
        "api.services.anti_ban.impersonated_session",
        lambda **kwargs: _FakeSession(),
    )

    scraper._warm_up_homepage()

    assert KredibelScraper._active_cookies.get("cf_clearance") == "clr-123"
    assert seen["url"].rstrip("/") == scraper.settings.kredibel_base_url.rstrip("/")


def test_kredibel_warm_jar_skips_warmup_request(clean_scrape_state, no_sleep, monkeypatch):
    KredibelScraper._active_cookies["kredibel_session"] = "dari-env"
    scraper = KredibelScraper(settings=Settings(kredibel_session_cookie=""))

    def _boom(**kwargs):
        raise AssertionError("warm-up tidak boleh jalan saat jar hangat")

    monkeypatch.setattr("api.services.anti_ban.impersonated_session", _boom)
    scraper._warm_up_homepage()  # harus no-op tanpa error


# ---------- harvester ----------

def _load_harvester_sites():
    path = Path(__file__).resolve().parent.parent.parent / "scripts" / "refresh_browser_sessions.py"
    spec = importlib.util.spec_from_file_location("refresh_browser_sessions", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SITES


def test_harvester_keeps_cf_clearance_for_kredibel():
    sites = _load_harvester_sites()
    names = sites["kredibel"]["cookie_names"]
    assert "kredibel_session" in names
    assert "cf_clearance" in names
