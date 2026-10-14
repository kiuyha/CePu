"""Lapisan anti-ban bersama untuk semua scraper eksternal.

Filosofi: JANGAN taruh browser (Selenium/Playwright) di jalur request —
berat (100-300MB RAM, detik startup), dan browser headless tetap gagal
pada challenge Cloudflare yang sulit. Sebagai gantinya:

1. Throttle: jeda minimum + jitter per host, thread-safe (scraper sync
   jalan via asyncio.to_thread, jadi pakai threading.Lock).
2. Klasifikasi sinyal ban: bedakan rate-limit (coba lagi) vs sesi mati
   (percuma retry) vs blokir total.
3. Playwright HANYA sebagai fallback terakhir / pemanen sesi (lihat
   scripts/refresh_browser_sessions.py), bukan untuk tiap request.
"""
import logging
import random
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Ban sementara (429/5xx/timeout) -> backoff, lalu retry masih masuk akal.
# Sesi mati / challenge -> retry langsung percuma, lebih baik degrade cepat.
RETRYABLE_KINDS = {"rate_limited", "server_error", "timeout", "network"}

_lock = threading.Lock()
_last_call: dict[str, float] = {}


def throttle(host_key: str, min_interval: float = 1.5, jitter: float = 1.0) -> float:
    """Tahan request agar antar-hit ke host yang sama ada jeda acak.

    Mengembalikan lama tidur (detik, 0 jika tidak perlu). Aman dipanggil
    dari banyak thread (scraper sync jalan via asyncio.to_thread).
    """
    if min_interval <= 0:
        with _lock:
            _last_call[host_key] = time.monotonic()
        return 0.0
    with _lock:
        now = time.monotonic()
        wait = min_interval + random.uniform(0, max(0.0, jitter)) - (now - _last_call.get(host_key, 0.0))
        if wait > 0:
            time.sleep(wait)
            _last_call[host_key] = time.monotonic()
            return wait
        _last_call[host_key] = now
        return 0.0


def reset_throttle(host_key: Optional[str] = None) -> None:
    """Reset state throttle (dipakai test)."""
    with _lock:
        if host_key is None:
            _last_call.clear()
        else:
            _last_call.pop(host_key, None)


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 8.0) -> float:
    """Jeda exponential backoff + jitter untuk percobaan ke-`attempt` (0-based)."""
    delay = min(cap, base * (2 ** max(0, attempt))) + random.uniform(0, 1.0)
    time.sleep(delay)
    return delay


def classify_ban(
    status_code: Optional[int] = None,
    body_snippet: str = "",
    graphql_errors: Optional[list] = None,
) -> str:
    """Klasifikasikan kegagalan fetch menjadi: ok | rate_limited | session_expired
    | challenge | blocked | server_error | timeout | network | unknown.
    """
    text = (body_snippet or "").lower()

    if graphql_errors:
        codes = {
            str((e or {}).get("extensions", {}).get("code", "")).upper()
            for e in graphql_errors
            if isinstance(e, dict)
        }
        if "UNSTABLE_QUERY_ERROR" in codes:
            # Backend menolak eksekusi — biasanya header/sesi tidak lengkap
            # atau query ditandai mahal. Bukan rate-limit murni.
            return "blocked"
        return "server_error"

    if status_code == 429:
        return "rate_limited"
    if status_code in (500, 502, 503, 504):
        return "server_error"
    if status_code in (401, 403):
        if any(k in text for k in ("login", "sign in", "masuk", "session", "expired")):
            return "session_expired"
        return "blocked"
    if any(k in text for k in ("captcha", "cf_challenge", "challenge-platform", "just a moment", "verify you are human")):
        return "challenge"
    if any(k in text for k in ("login", "sign in")) and status_code in (301, 302, 303, 307, 308):
        return "session_expired"
    if status_code is not None and 400 <= status_code < 500:
        return "blocked"
    return "unknown"


def should_retry(kind: str) -> bool:
    return kind in RETRYABLE_KINDS


class CircuitBreaker:
    """Pemutus sirkuit per host: setelah `threshold` gagal berturut-turut
    (challenge/blocked/rate-limited), tolak request selama `cooldown`
    agar tidak memperpanjang flag dengan menghantam sumber yang sedang
    memblokir. Sukses me-reset hitungan. Thread-safe."""

    def __init__(self, threshold: int = 3, cooldown_seconds: float = 900.0):
        self.threshold = max(1, threshold)
        self.cooldown = max(1.0, cooldown_seconds)
        self._fails = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._fails < self.threshold:
                return True
            if time.monotonic() - self._opened_at >= self.cooldown:
                self._fails = 0  # half-open: beri satu kesempatan probe
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._fails = 0

    def record_failure(self) -> None:
        with self._lock:
            self._fails += 1
            if self._fails >= self.threshold:
                self._opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self._fails = 0
            self._opened_at = 0.0


_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(
    host_key: str, threshold: int = 3, cooldown_seconds: float = 900.0
) -> CircuitBreaker:
    with _lock:
        br = _breakers.get(host_key)
        if br is None:
            br = CircuitBreaker(threshold, cooldown_seconds)
            _breakers[host_key] = br
        return br


def reset_breaker(host_key: Optional[str] = None) -> None:
    with _lock:
        if host_key is None:
            _breakers.clear()
        else:
            _breakers.pop(host_key, None)


def proxy_map(proxy_url: str) -> Optional[dict[str, str]]:
    """Ubah URL proxy tunggal jadi mapping requests/curl_cffi/httpx.

    Contoh: "http://user:pass@rumah:8080" atau "socks5h://127.0.0.1:1080"
    (mis. hasil `ssh -D 1080 user@rumah`). Kosong -> None (langsung).
    """
    proxy_url = (proxy_url or "").strip()
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def iter_cookie_pairs(jar) -> list[tuple[str, str]]:
    """Ambil (nama, nilai) cookie dari APAPUN bentuk jar-nya.

    - curl_cffi Cookies: iterasi menghasilkan string nama saja -> pakai .items().
    - requests CookieJar: iterasi menghasilkan objek .name/.value.
    - dict biasa: .items().
    """
    if jar is None:
        return []
    try:
        items = jar.items()  # type: ignore[union-attr]
        pairs = [(str(k), str(v)) for k, v in items]
        if pairs:
            return pairs
    except Exception:
        pass
    try:
        out = []
        for c in jar:
            if isinstance(c, str):
                continue  # nama tanpa nilai (kasus iterasi curl_cffi) — sudah ditangani .items()
            out.append((str(c.name), str(c.value)))
        return out
    except Exception:
        return []


def impersonated_session(
    headers: Optional[dict[str, str]] = None,
    cookies: Optional[dict[str, str]] = None,
    timeout: float = 10.0,
    proxies: Optional[dict[str, str]] = None,
):
    """Session HTTP dengan TLS+HTTP/2 fingerprint Chrome asli (via curl_cffi).

    Ini senjata utama anti-ban level transport: JA3 handshake terlihat
    seperti Chrome sungguhan, bukan python-requests / curl sistem.
    API mirip requests.Session (get/post, .cookies, .headers).

    Butuh: pip install curl_cffi (ringan, tanpa download browser).
    Melempar ImportError jika belum terinstal — caller wajib fallback.
    """
    from curl_cffi import requests as curl_requests

    session = curl_requests.Session(impersonate="chrome")
    session.timeout = timeout
    if headers:
        session.headers.update(headers)
    if cookies:
        session.cookies.update(cookies)
    if proxies:
        session.proxies.update(proxies)
    return session


def fetch_with_browser(
    url: str,
    *,
    timeout_ms: int = 30000,
    wait_selector: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Ambil halaman memakai Chromium asli (Playwright) — fallback TERAKHIR.

    Mengembalikan {"html": ..., "cookies": {...}} atau None. Butuh:
        pip install playwright && playwright install chromium
    Kalau playwright belum terinstal, return None dengan warning jelas
    (bukan crash) — caller lanjut ke degradasi normal.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(
            "Playwright belum terinstal — lewati fetch browser. "
            "Aktifkan dengan: pip install playwright && playwright install chromium"
        )
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                locale="id-ID",
                timezone_id="Asia/Jakarta",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Beri waktu challenge JS (kalau ada) selesai.
            page.wait_for_timeout(4000)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=8000)
                except Exception:
                    pass
            html = page.content()
            cookies = {c["name"]: c["value"] for c in context.cookies()}
            browser.close()
            if classify_ban(body_snippet=html[:2000]) in ("challenge", "blocked"):
                logger.warning("Browser fetch %s masih kena challenge/blokir.", url)
                return None
            return {"html": html, "cookies": cookies}
    except Exception as exc:
        logger.warning("Browser fetch %s gagal: %s", url, exc)
        return None
