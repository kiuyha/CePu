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

        url = f"{self.settings.kredibel_base_url.rstrip('/')}/phone/id/{clean_num}"
        logger.info("Fetching kredibel.com profile: %s", url)

        # Coba jalankan via curl --http2 jika curl tersedia
        curl_path = shutil.which("curl")
        if curl_path:
            return self._fetch_via_curl(url, curl_path)
        else:
            return self._fetch_via_httpx(url)

    def _fetch_via_curl(self, url: str, curl_path: str) -> Optional[dict[str, Any]]:
        cookie_header = self._get_cookie_header_string()
        cmd = [
            curl_path,
            "--http2",
            "-i",  # include headers
            "-s",
            url,
            "-H", f"user-agent: {self.settings.kredibel_user_agent}",
            "--compressed",
            "--max-time", str(self.settings.kredibel_timeout_seconds),
        ]
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
                return self.parse_kredibel_page(body)
            elif status_code in (301, 302, 303, 307, 308):
                # Check Location header to detect login redirect
                location = ""
                for line in all_header_lines:
                    if line.lower().startswith("location:"):
                        location = line.split(":", 1)[1].strip().lower()
                        break
                if "login" in location or "login" in body.lower():
                    logger.warning(
                        "Kredibel redirected to login: session cookie might be expired. "
                        "Update KREDIBEL_SESSION_COOKIE in your .env file."
                    )
                else:
                    logger.warning("Kredibel returned HTTP %d (redirect to: %s)", status_code, location)
                return None
            else:
                logger.warning("Kredibel returned HTTP %d", status_code)
                return None
        except Exception as exc:
            logger.warning("Kredibel curl fetch failed for %s: %s", url, exc)
            return None

    def _fetch_via_httpx(self, url: str) -> Optional[dict[str, Any]]:
        import httpx
        headers = {
            "user-agent": self.settings.kredibel_user_agent,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        cookies = dict(self._active_cookies)

        try:
            with httpx.Client(http2=True, timeout=self.settings.kredibel_timeout_seconds) as client:
                resp = client.get(url, headers=headers, cookies=cookies, follow_redirects=True)
                for k, v in resp.cookies.items():
                    self._active_cookies[k] = v
                if resp.status_code == 200:
                    return self.parse_kredibel_page(resp.text)
                return None
        except Exception as exc:
            logger.warning("Kredibel httpx fetch failed for %s: %s", url, exc)
            return None
