"""
Scraper modular untuk Kredibel.com (pengecekan ulasan/laporan nomor telepon).
Menggunakan HTTP/2 via curl (atau fallback httpx) dengan cookie session kredibel_session.
Cookie baru dari response header set-cookie disimpan secara otomatis untuk request berikutnya.
"""
import logging
import re
import shutil
import subprocess
from typing import Any, Optional
from bs4 import BeautifulSoup

from ...core.config import Settings, get_settings

from ..anti_ban import throttle

logger = logging.getLogger(__name__)


def clean_phone_for_kredibel(phone: str) -> str:
    """
    Kredibel URL format: https://www.kredibel.com/phone/id/<phone_digits>
    Contoh: +6285798017153 -> 85798017153
            085798017153 -> 85798017153
            85798017153 -> 85798017153
    """
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("62"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]
    return digits


class KredibelScraper:
    # Simpan cookie aktif kredibel di level class agar otomatis ter-update dan digunakan kembali
    _active_cookies: dict[str, str] = {}

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._init_cookies()
        from ..anti_ban import get_breaker

        self._breaker = get_breaker(
            "kredibel",
            self.settings.scrape_circuit_threshold,
            self.settings.scrape_circuit_cooldown_seconds,
        )

    def _init_cookies(self) -> None:
        if self.settings.kredibel_session_cookie:
            raw = self.settings.kredibel_session_cookie
            if "=" in raw:
                for part in raw.split(";"):
                    if "=" in part:
                        k, v = part.strip().split("=", 1)
                        if k.strip() not in self._active_cookies:
                            self._active_cookies[k.strip()] = v.strip()
            else:
                if "kredibel_session" not in self._active_cookies:
                    self._active_cookies["kredibel_session"] = raw.strip()

    def _get_cookie_header_string(self) -> str:
        parts = []
        for k, v in self._active_cookies.items():
            parts.append(f"{k}={v}")
        return "; ".join(parts)

    def _update_cookies_from_headers(self, headers_list: list[str]) -> None:
        """Ekstraksi Set-Cookie dari header response dan update cache internal."""
        for line in headers_list:
            if line.lower().startswith("set-cookie:"):
                cookie_val = line.split(":", 1)[1].strip()
                main_part = cookie_val.split(";")[0].strip()
                if "=" in main_part:
                    k, v = main_part.split("=", 1)
                    self._active_cookies[k.strip()] = v.strip()
                    logger.debug("Kredibel cookie updated: %s", k.strip())

    def parse_kredibel_page(self, html_content: str) -> dict[str, Any]:
        """
        Parse halaman profil kredibel untuk nomor telepon.
        Mengembalikan:
        - rating_label: str (misal 'Cukup Buruk', 'Buruk', 'Sangat Buruk', 'Cukup Baik', 'Baik', atau None)
        - rating_score: float (0.0 jika tidak ada ulasan/rating 0)
        - report_count: int (jumlah laporan)
        - review_count: int (jumlah ulasan)
        - is_fraud_flagged: bool (apakah dinilai buruk / bermasalah)
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Cari Kredibel Rating
        rating_label = None
        rating_val = 0.0

        for item in soup.find_all(class_="card-stats-item"):
            label_elem = item.find(class_="card-stats-label")
            val_elem = item.find(class_="card-stats-value")
            if label_elem and val_elem:
                label_txt = label_elem.get_text(strip=True).lower()
                if "rating" in label_txt:
                    rating_label = val_elem.get_text(strip=True)

        if not rating_label:
            # Cek elemen lain seperti stars-hero atau badges
            for badge in soup.find_all(["span", "div", "p"]):
                txt = badge.get_text(strip=True)
                if txt in ["Sangat Buruk", "Buruk", "Cukup Buruk", "Cukup Baik", "Baik", "Sangat Baik"]:
                    rating_label = txt
                    break

        # Tentukan numeric score & flag dari rating label
        # Di Kredibel: 'Cukup Buruk', 'Buruk', 'Sangat Buruk' menandakan bahaya penipuan
        is_fraud = False
        if rating_label:
            lowered = rating_label.lower()
            if any(bad in lowered for bad in ["buruk", "penipu", "bahaya", "waspada"]):
                is_fraud = True
                rating_val = 0.9 if "sangat buruk" in lowered else (0.85 if "buruk" in lowered else 0.75)
            elif any(good in lowered for good in ["baik", "terpercaya", "aman"]):
                is_fraud = False
                rating_val = 0.2
        else:
            # Rating 0 / tidak ada ulasan: dianggap netral/aman
            rating_label = "Belum ada ulasan"
            rating_val = 0.0
            is_fraud = False

        # 2. Cek apakah ada laporan terdata di body teks
        full_text = soup.get_text(separator=" ", strip=True).lower()
        report_count = 0
        report_match = re.search(r'(\d+)\s+(?:laporan|keluhan)', full_text)
        if report_match:
            report_count = int(report_match.group(1))
            if report_count > 0:
                is_fraud = True

        return {
            "rating_label": rating_label,
            "rating_score": rating_val,
            "report_count": report_count,
            "is_fraud_flagged": is_fraud,
        }

    def fetch_phone_profile(self, phone: str) -> Optional[dict[str, Any]]:
        """
        Request ke https://www.kredibel.com/phone/id/<clean_phone> menggunakan HTTP/2.
        """
        clean_num = clean_phone_for_kredibel(phone)
        if not clean_num:
            return None

        if not self._breaker.allow():
            logger.info("kredibel.com di-skip (circuit terbuka).")
            return None

        throttle(
            "kredibel",
            self.settings.scrape_min_interval_seconds,
            self.settings.scrape_jitter_seconds,
        )

        # Kunjungan berurutan ala browser: homepage dulu (kalau sesi dingin),
        # lalu halaman nomor dengan Referer — bukan deep-link tiba-tiba.
        self._warm_up_homepage()

        url = f"{self.settings.kredibel_base_url.rstrip('/')}/phone/id/{clean_num}"
        logger.info("Fetching kredibel.com profile: %s", url)

        # 1. Impersonasi Chrome (JA3 asli) — paling sulit di-flag.
        try:
            result = self._fetch_via_impersonated(url)
            if result is not None:
                return result
        except ImportError:
            pass

        # 2. curl sistem via HTTP/2, lalu 3. httpx.
        curl_path = shutil.which("curl")
        if curl_path:
            return self._fetch_via_curl(url, curl_path)
        else:
            return self._fetch_via_httpx(url)

    def _fetch_via_impersonated(self, url: str) -> Optional[dict[str, Any]]:
        from ..anti_ban import classify_ban, impersonated_session, proxy_map

        try:
            session = impersonated_session(
                headers=self._browser_headers(),
                cookies=dict(self._active_cookies),
                timeout=self.settings.kredibel_timeout_seconds,
                proxies=proxy_map(self.settings.kredibel_proxy),
            )
            resp = session.get(url, allow_redirects=False)
        except Exception as exc:
            logger.warning("Kredibel impersonated fetch gagal untuk %s: %s", url, exc)
            return None

        from ..anti_ban import iter_cookie_pairs

        for name, value in iter_cookie_pairs(getattr(resp, "cookies", None)):
            self._active_cookies[name] = value

        if resp.status_code == 200:
            self._breaker.record_success()
            return self.parse_kredibel_page(resp.text)

        location = ""
        try:
            location = (resp.headers.get("location") or "").lower()
        except Exception:
            pass
        kind = classify_ban(status_code=resp.status_code, body_snippet=(resp.text or "")[:2000])
        if kind in ("challenge", "blocked", "rate_limited", "server_error"):
            self._breaker.record_failure()
        if resp.status_code in (301, 302, 303, 307, 308) and "login" in location:
            # Info saja (bukan warning): transport berikutnya akan
            # mengeluarkan warning resmi bila ikut gagal.
            logger.info("Kredibel impersonated kena redirect login untuk %s.", url)
        else:
            logger.warning("Kredibel impersonated HTTP %d [%s]", resp.status_code, kind)
        return None

    def _browser_headers(self) -> dict[str, str]:
        # Header attestasi browser (cf. kasus JobStreet): tanpa ini request
        # terlihat seperti "TLS browser tapi bisu", mudah di-flag WAF.
        # Versi diselaraskan dengan kredibel_user_agent (Chrome 153, Android).
        # Referer + sec-fetch-site: same-origin meniru navigasi dari homepage
        # (bukan deep-link tiba-tiba tanpa riwayat).
        base = self.settings.kredibel_base_url.rstrip("/")
        return {
            "user-agent": self.settings.kredibel_user_agent,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "sec-ch-ua": '"Chromium";v="153", "Not_A Brand";v="8", "Google Chrome";v="153"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "referer": base + "/",
            "upgrade-insecure-requests": "1",
        }

    def _warm_up_homepage(self) -> None:
        """Best-effort: GET homepage untuk cookie anonim + riwayat sesi
        sebelum deep-link ke halaman nomor. Hanya jalan saat jar
        benar-benar kosong (tanpa cookie .env maupun hasil request lama);
        kegagalan diabaikan dan request detail tetap jalan."""
        if self._active_cookies:
            return
        try:
            import random
            import time

            from ..anti_ban import impersonated_session, iter_cookie_pairs, proxy_map

            base = self.settings.kredibel_base_url.rstrip("/")
            # Tanpa referer: kunjungan pertama = ketik URL / buka homepage.
            headers = {
                k: v for k, v in self._browser_headers().items()
                if k.lower() != "referer"
            }
            session = impersonated_session(
                headers=headers,
                timeout=self.settings.kredibel_timeout_seconds,
                proxies=proxy_map(self.settings.kredibel_proxy),
            )
            resp = session.get(base + "/", allow_redirects=True)
            for name, value in iter_cookie_pairs(getattr(resp, "cookies", None)):
                if name not in self._active_cookies:
                    self._active_cookies[name] = value
            # Jeda baca-klik ala manusia sebelum lanjut ke halaman nomor.
            time.sleep(random.uniform(0.8, 2.0))
        except Exception as exc:
            logger.debug("Warm-up kredibel.com gagal (best-effort): %s", exc)

    def _fetch_via_curl(self, url: str, curl_path: str) -> Optional[dict[str, Any]]:
        from ..anti_ban import classify_ban

        cookie_header = self._get_cookie_header_string()
        cmd = [
            curl_path,
            "--http2",
            "-i",  # include headers
            "-s",
            url,
            "--compressed",
            "--max-time", str(self.settings.kredibel_timeout_seconds),
        ]
        proxy = (self.settings.kredibel_proxy or "").strip()
        if proxy:
            cmd.extend(["-x", proxy])
        for key, value in self._browser_headers().items():
            cmd.extend(["-H", f"{key}: {value}"])
        if cookie_header:
            cmd.extend(["-H", f"cookie: {cookie_header}"])

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=self.settings.kredibel_timeout_seconds + 2)
            raw_output = res.stdout

            # Pisahkan response headers dan body
            # Handle multiple HTTP/2 responses if redirects exist
            sections = raw_output.split("\r\n\r\n")
            if len(sections) < 2:
                sections = raw_output.split("\n\n")

            headers_raw = sections[:-1]
            body = sections[-1]

            # Kumpulkan semua headers untuk parsing Set-Cookie
            all_header_lines = []
            for h_sec in headers_raw:
                all_header_lines.extend(h_sec.splitlines())

            self._update_cookies_from_headers(all_header_lines)

            # Cek status code HTTP pada header blok terakhir
            status_code = 200
            for line in reversed(all_header_lines):
                if line.startswith("HTTP/"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        status_code = int(parts[1])
                        break

            if status_code == 200:
                self._breaker.record_success()
                return self.parse_kredibel_page(body)
            elif status_code in (301, 302, 303, 307, 308):
                # Check Location header to detect login redirect
                location = ""
                for line in all_header_lines:
                    if line.lower().startswith("location:"):
                        location = line.split(":", 1)[1].strip().lower()
                        break
                kind = classify_ban(status_code=status_code, body_snippet=body[:2000])
                if kind in ("challenge", "blocked", "rate_limited", "server_error"):
                    self._breaker.record_failure()
                if "login" in location or "login" in body.lower():
                    logger.warning(
                        "Kredibel redirected to login: session cookie might be expired. "
                        "Update KREDIBEL_SESSION_COOKIE in your .env file."
                    )
                else:
                    logger.warning("Kredibel returned HTTP %d [%s] (redirect to: %s)", status_code, kind, location)
                return None
            else:
                kind = classify_ban(status_code=status_code, body_snippet=body[:2000])
                if kind in ("challenge", "blocked", "rate_limited", "server_error"):
                    self._breaker.record_failure()
                logger.warning("Kredibel returned HTTP %d [%s]", status_code, kind)
                return None
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning("Kredibel curl fetch failed for %s: %s", url, exc)
            return None

    def _fetch_via_httpx(self, url: str) -> Optional[dict[str, Any]]:
        import httpx

        from ..anti_ban import classify_ban, proxy_map

        headers = self._browser_headers()
        cookies = dict(self._active_cookies)
        proxy = (self.settings.kredibel_proxy or "").strip() or None

        try:
            with httpx.Client(http2=True, timeout=self.settings.kredibel_timeout_seconds, proxy=proxy) as client:
                resp = client.get(url, headers=headers, cookies=cookies, follow_redirects=True)
                for k, v in resp.cookies.items():
                    self._active_cookies[k] = v
                if resp.status_code == 200:
                    self._breaker.record_success()
                    return self.parse_kredibel_page(resp.text)
                kind = classify_ban(status_code=resp.status_code, body_snippet=resp.text[:2000])
                if kind in ("challenge", "blocked", "rate_limited", "server_error"):
                    self._breaker.record_failure()
                return None
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning("Kredibel httpx fetch failed for %s: %s", url, exc)
            return None
