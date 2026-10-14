"""Test lapisan anti-ban: throttle, backoff, klasifikasi sinyal ban."""
import time

import pytest

from api.services import anti_ban
from api.services.anti_ban import (
    backoff_delay,
    classify_ban,
    fetch_with_browser,
    reset_throttle,
    should_retry,
    throttle,
)


def test_throttle_memberi_jeda_antar_hit():
    reset_throttle("ut-host")
    assert throttle("ut-host", min_interval=0.0) == 0.0
    t0 = time.monotonic()
    waited = throttle("ut-host", min_interval=0.15, jitter=0.0)
    elapsed = time.monotonic() - t0
    assert 0.1 <= waited <= 0.2
    assert elapsed >= 0.1
    reset_throttle("ut-host")


def test_throttle_tanpa_interval_langsung_lolos():
    assert throttle("ut-host-2", min_interval=0) == 0.0
    assert throttle("ut-host-2", min_interval=-1) == 0.0


def test_backoff_naik_per_attempt(monkeypatch):
    monkeypatch.setattr(anti_ban.random, "uniform", lambda _a, _b: 0.0)
    assert backoff_delay(0, base=0.01, cap=1.0) == pytest.approx(0.01)
    assert backoff_delay(2, base=0.01, cap=1.0) == pytest.approx(0.04)
    assert backoff_delay(10, base=1.0, cap=8.0) == pytest.approx(8.0)


def test_classify_ban():
    assert classify_ban(status_code=429) == "rate_limited"
    assert classify_ban(status_code=503) == "server_error"
    assert classify_ban(status_code=403, body_snippet="please login") == "session_expired"
    assert classify_ban(status_code=403, body_snippet="forbidden") == "blocked"
    assert classify_ban(body_snippet="Just a moment, verify you are human") == "challenge"
    assert (
        classify_ban(graphql_errors=[{"extensions": {"code": "UNSTABLE_QUERY_ERROR"}}])
        == "blocked"
    )
    assert classify_ban(graphql_errors=[{"extensions": {"code": "SOMETHING"}}]) == "server_error"
    assert classify_ban(status_code=200) == "unknown"


def test_should_retry_hanya_yang_sementara():
    assert should_retry("rate_limited")
    assert should_retry("server_error")
    assert not should_retry("blocked")
    assert not should_retry("session_expired")
    assert not should_retry("challenge")


def test_fetch_browser_graceful_tanpa_playwright(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _boom(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _boom)
    assert fetch_with_browser("https://example.com") is None


def test_scraper_entry_points_memakai_throttle(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.services.jobstreet_scraper.throttle",
        lambda host, *a, **k: calls.append(host) or 0.0,
    )
    monkeypatch.setattr(
        "api.services.jobstreet_scraper.JobStreetScraper._post_via_curl",
        lambda self, payload, curl_path: {"data": {"jobSearchV7": {"results": {"jobs": []}}}},
    )
    import shutil

    monkeypatch.setattr(shutil, "which", lambda *_a, **_k: "/usr/bin/curl")
    from api.services.jobstreet_scraper import JobStreetScraper

    JobStreetScraper().search_jobs("driver")
    assert calls == ["jobstreet"]
    assert anti_ban.throttle("other-host", min_interval=0) == 0.0


def test_impersonated_session_memakai_tls_chrome():
    from api.services.anti_ban import impersonated_session

    session = impersonated_session(
        headers={"X-Test": "1"}, cookies={"a": "b"}, timeout=5.0
    )
    try:
        assert session.headers["X-Test"] == "1"
        assert session.cookies.get("a") == "b"
    finally:
        session.close()


def test_companyhouse_memakai_transport_impersonasi():
    from api.services.validators.companyhouse_scraper import CompanyHouseScraper

    scraper = CompanyHouseScraper()
    try:
        # Bukan requests.Session polos: modul berasal dari curl_cffi.
        assert type(scraper.session).__module__.startswith("curl_cffi")
        assert "Sec-Fetch-Site" in scraper.session.headers
    finally:
        scraper.session.close()


def test_kredibel_fallback_tanpa_curl_cffi(monkeypatch):
    import builtins

    from api.services.validators import kredibel_scraper as ks

    real_import = builtins.__import__

    def _boom(name, *args, **kwargs):
        if name == "curl_cffi" or name.startswith("curl_cffi."):
            raise ImportError("no curl_cffi")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _boom)
    monkeypatch.setattr(
        ks.KredibelScraper, "_fetch_via_curl", lambda self, url, _p: {"fallback": True}
    )
    scraper = ks.KredibelScraper()
    assert scraper._fetch_via_impersonated("https://example.com") is None
    assert scraper.fetch_phone_profile("085798017153") == {"fallback": True}


def test_iter_cookie_pairs_semua_bentuk_jar():
    from http.cookiejar import CookieJar, Cookie

    from api.services.anti_ban import iter_cookie_pairs
    from curl_cffi.requests.cookies import Cookies

    assert iter_cookie_pairs(None) == []
    assert sorted(iter_cookie_pairs({"a": "1"})) == [("a", "1")]
    assert sorted(iter_cookie_pairs(Cookies({"x": "9", "y": "8"}))) == [
        ("x", "9"),
        ("y", "8"),
    ]

    jar = CookieJar()
    jar.set_cookie(
        Cookie(
            version=0, name="s", value="v", port=None, port_specified=False,
            domain="example.com", domain_specified=True, domain_initial_dot=False,
            path="/", path_specified=True, secure=False, expires=None,
            discard=False, comment=None, comment_url=None, rest={},
        )
    )
    assert iter_cookie_pairs(jar) == [("s", "v")]


def test_companyhouse_update_cookies_dari_curl_cffi_tidak_crash():
    from curl_cffi.requests.cookies import Cookies

    from api.services.validators.companyhouse_scraper import CompanyHouseScraper

    scraper = CompanyHouseScraper()
    try:
        fake_resp = type("R", (), {"cookies": Cookies({"sess": "abc"})})()
        scraper._update_cookies_from_response(fake_resp)
        assert scraper._active_cookies.get("sess") == "abc"
    finally:
        scraper.session.close()


def test_kredibel_impersonated_simpan_cookie_tanpa_crash(monkeypatch):
    from curl_cffi.requests.cookies import Cookies

    from api.services.validators import kredibel_scraper as ks

    class FakeResp:
        status_code = 200
        text = "<html></html>"
        headers = {}
        cookies = Cookies({"kredibel_session": "xyz"})

    class FakeSession:
        def get(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(
        "api.services.anti_ban.impersonated_session",
        lambda **k: FakeSession(),
    )
    scraper = ks.KredibelScraper()
    out = scraper._fetch_via_impersonated("https://www.kredibel.com/phone/id/123")
    assert scraper._active_cookies.get("kredibel_session") == "xyz"
    assert isinstance(out, dict)


def test_circuit_breaker_buka_tutup():
    from api.services.anti_ban import CircuitBreaker

    br = CircuitBreaker(threshold=2, cooldown_seconds=1.0)
    assert br.allow()
    br.record_failure()
    assert br.allow()  # 1 < 2
    br.record_failure()
    assert not br.allow()  # terbuka
    import time as _t

    _t.sleep(1.05)
    assert br.allow()  # half-open setelah cooldown
    br.record_success()
    br.record_failure()
    assert br.allow()  # sukses me-reset hitungan


def test_get_breaker_registry_dan_reset():
    from api.services.anti_ban import get_breaker, reset_breaker

    a = get_breaker("ut-cb", threshold=1, cooldown_seconds=60)
    assert get_breaker("ut-cb") is a
    a.record_failure()
    assert not a.allow()
    reset_breaker("ut-cb")
    assert get_breaker("ut-cb").allow()


def test_proxy_map():
    from api.services.anti_ban import proxy_map

    assert proxy_map("") is None
    assert proxy_map("  ") is None
    assert proxy_map("http://rumah:8080") == {
        "http": "http://rumah:8080",
        "https": "http://rumah:8080",
    }


def test_companyhouse_skip_saat_circuit_terbuka(monkeypatch):
    from api.services.anti_ban import get_breaker
    from api.services.validators.companyhouse_scraper import CompanyHouseScraper

    scraper = CompanyHouseScraper()
    try:
        get_breaker("companyhouse").record_failure()
        get_breaker("companyhouse").record_failure()
        get_breaker("companyhouse").record_failure()

        def _boom(*a, **k):
            raise AssertionError("tidak boleh request saat circuit terbuka")

        monkeypatch.setattr(scraper.session, "get", _boom)
        assert scraper.fetch_company_detail("PT Apa Saja") is None
    finally:
        scraper.session.close()
