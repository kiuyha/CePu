"""
Scraper modular untuk companyhouse.id dengan session-based HTTP workflow.
"""
import logging
import random
import re
import time
from typing import Any, Optional
from bs4 import BeautifulSoup

from ...core.config import Settings, get_settings

from ..anti_ban import throttle

logger = logging.getLogger(__name__)


def generate_company_slug(company_name: str) -> str:
    """
    Mengubah nama perusahaan menjadi slug URL (misal: PT. Makna Jaya Pratama -> makna-jaya-pratama).
    Baris pertama saja yang dipakai jika company_name mengandung newline (misalnya hasil ekstraksi
    regex yang tidak dibatasi per-baris).
    """
    # Ambil hanya baris pertama — amankan dari hasil regex yang menelan newline
    company_name = company_name.split('\n')[0].strip()
    clean = re.sub(r'^(PT|CV|Perum|UD|Firma|Yayasan)\.?\s+', '', company_name, flags=re.IGNORECASE)
    clean = re.sub(r'[\.\,\(\)\&\/\\]', ' ', clean)
    clean = re.sub(r'\s+', '-', clean).strip('-').lower()
    return clean


class CompanyHouseScraper:
    # Simpan cookie aktif di level class agar request berikutnya otomatis memakai cookie ter-update
    _active_cookies: dict[str, str] = {}

    # Jeda baca-klik ala manusia antara warm-up homepage dan request detail.
    WARMUP_CLICK_DELAY = (0.8, 2.0)

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        # Transport impersonasi Chrome (JA3 asli) — jauh lebih sulit di-flag
        # daripada python-requests. Fallback ke requests bila curl_cffi
        # belum terinstal (pip install curl_cffi).
        from ..anti_ban import proxy_map

        proxies = proxy_map(self.settings.companyhouse_proxy)
        try:
            from ..anti_ban import impersonated_session

            self.session = impersonated_session(proxies=proxies)
        except ImportError:
            import requests

            logger.warning("curl_cffi tidak ada — pakai requests (mudah di-flag WAF).")
            self.session = requests.Session()
            if proxies:
                self.session.proxies.update(proxies)
        self._configure_session()

    def _configure_session(self) -> None:
        # Meniru header browser desktop: tanpa sec-fetch-*/sec-ch-ua*,
        # WAF gampang menandai request sebagai script (cf. kasus JobStreet
        # yang menjawab UNSTABLE_QUERY_ERROR). Tidak ada secret di sini.
        self.session.headers.update({
            "User-Agent": self.settings.companyhouse_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "id,en-US;q=0.9,en;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not_A Brand";v="8", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Upgrade-Insecure-Requests": "1",
        })
        # 1. Pasang cookie dari environment variable jika ada
        if self.settings.companyhouse_session_cookie:
            for part in self.settings.companyhouse_session_cookie.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    self.session.cookies.set(k.strip(), v.strip())
                elif part.strip():
                    self.session.cookies.set("companyhouse_session", part.strip())

        # 2. Timpa dengan cookie aktif yang sudah diperbarui server
        for k, v in self._active_cookies.items():
            self.session.cookies.set(k, v)

    def _update_cookies_from_response(self, resp) -> None:
        """Menyimpan cookie baru yang dikirim server via set-cookie."""
        from ..anti_ban import iter_cookie_pairs

        for name, value in iter_cookie_pairs(getattr(resp, "cookies", None)):
            self._active_cookies[name] = value
            try:
                self.session.cookies.set(name, value)
            except Exception:
                pass

    def _is_jar_cold(self) -> bool:
        """True jika cookie jar kosong (belum ada sesi sama sekali)."""
        from ..anti_ban import iter_cookie_pairs

        return not iter_cookie_pairs(self.session.cookies)

    def _warm_up_homepage(self) -> None:
        """Best-effort: kunjungi homepage dulu sebelum deep-link.

        Memberi session riwayat navigasi + cookie segar layaknya kunjungan
        browser (homepage -> klik -> halaman detail). Hanya jalan saat jar
        benar-benar dingin (tanpa cookie .env maupun hasil request lama);
        kegagalan diabaikan dan request detail tetap jalan.
        """
        if not self._is_jar_cold():
            return
        base = self.settings.companyhouse_base_url.rstrip("/")
        try:
            resp = self.session.get(
                base + "/",
                timeout=self.settings.companyhouse_timeout_seconds,
                allow_redirects=True,
            )
            self._update_cookies_from_response(resp)
            # Jeda baca-klik ala manusia sebelum lanjut ke halaman detail.
            time.sleep(random.uniform(*self.WARMUP_CLICK_DELAY))
        except Exception as exc:
            logger.debug("Warm-up companyhouse.id gagal (best-effort): %s", exc)

    def parse_company_page(self, html_content: str, default_name: str = "") -> dict[str, Any]:
        """
        Ekstraksi informasi perusahaan dari HTML halaman detail.
        Mengembalikan dictionary dengan 8 field wajib:
        - company_name: string
        - legal_entity_type: string
        - business_number: string
        - sk_number: string or None
        - city: string
        - country: string
        - phone: string or None
        - registered_address: string
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # Fallback values
        company_name = default_name
        legal_entity_type = "Limited Liability Company (PT)"
        business_number = ""
        sk_number = None
        city = ""
        country = "Indonesia"
        phone = None
        registered_address = ""

        # Cari judul / nama perusahaan
        h1 = soup.find("h1")
        if h1 and h1.text.strip():
            company_name = h1.text.strip()

        # Ekstraksi berbasis key-value atau tabel/list pada halaman
        # Periksa text elements atau dl / dt / dd atau table rows
        for row in soup.find_all(["tr", "div", "li"]):
            text = row.text.strip()
            lowered = text.lower()

            if "entity type" in lowered or "bentuk badan" in lowered or "jenis perseroan" in lowered:
                val = self._extract_value_after_colon_or_tag(row)
                if val:
                    legal_entity_type = val

            elif "business number" in lowered or "nomor pendaftaran" in lowered or "nomor ah" in lowered or "nomor nib" in lowered:
                val = self._extract_value_after_colon_or_tag(row)
                if val:
                    business_number = val

            elif "sk number" in lowered or "nomor sk" in lowered or "sk menteri" in lowered:
                val = self._extract_value_after_colon_or_tag(row)
                if val:
                    sk_number = val

            elif "city" in lowered or "kota" in lowered or "kabupaten" in lowered:
                val = self._extract_value_after_colon_or_tag(row)
                if val:
                    city = val

            elif "phone" in lowered or "telepon" in lowered:
                val = self._extract_value_after_colon_or_tag(row)
                if val:
                    phone = val

            elif "address" in lowered or "alamat" in lowered:
                val = self._extract_value_after_colon_or_tag(row)
                if val:
                    registered_address = val

        # Jika registered_address belum ditemukan, cek paragraph deskripsi atau itemprop address
        if not registered_address:
            addr_elem = soup.find(attrs={"itemprop": "address"}) or soup.find(class_=re.compile(r"address", re.I))
            if addr_elem and addr_elem.text.strip():
                registered_address = addr_elem.text.strip()

        # Ekstraksi city dari address jika city kosong
        if not city and registered_address:
            city_match = re.search(r'\b(KOTA\s+[A-Z\s]+|KABUPATEN\s+[A-Z\s]+)\b', registered_address, re.IGNORECASE)
            if city_match:
                city = city_match.group(1).strip()

        return {
            "company_name": company_name,
            "legal_entity_type": legal_entity_type,
            "business_number": business_number,
            "sk_number": sk_number,
            "city": city,
            "country": country,
            "phone": phone,
            "registered_address": registered_address,
        }

    def _extract_value_after_colon_or_tag(self, element: Any) -> Optional[str]:
        text = element.text.strip()
        if ":" in text:
            parts = text.split(":", 1)
            val = parts[1].strip()
            return val if val else None
        # Cek apakah ada child element bernilai
        children = list(element.find_all(recursive=False))
        if len(children) >= 2:
            return children[1].text.strip()
        return None

    def fetch_company_detail(self, company_name: str) -> Optional[dict[str, Any]]:
        """
        Request ke target profile page di companyhouse.id.
        """
        slug = generate_company_slug(company_name)
        if not slug:
            return None

        from ..anti_ban import classify_ban, get_breaker

        breaker = get_breaker(
            "companyhouse",
            self.settings.scrape_circuit_threshold,
            self.settings.scrape_circuit_cooldown_seconds,
        )
        if not breaker.allow():
            # Jangan hantam sumber yang sedang memblokir — biarkan flag reda,
            # caller turun ke jalur degraded (cache/netral).
            logger.info("companyhouse.id di-skip (circuit terbuka).")
            return None

        throttle(
            "companyhouse",
            self.settings.scrape_min_interval_seconds,
            self.settings.scrape_jitter_seconds,
        )

        # Kunjungan berurutan ala browser: homepage dulu (kalau sesi dingin),
        # lalu detail dengan Referer — bukan deep-link tiba-tiba.
        self._warm_up_homepage()

        base = self.settings.companyhouse_base_url.rstrip("/")
        url = f"{base}/{slug}"
        logger.info("Fetching companyhouse.id profile: %s", url)

        try:
            resp = self.session.get(
                url,
                timeout=self.settings.companyhouse_timeout_seconds,
                allow_redirects=True,
                headers={"Referer": base + "/"},
            )
            self._update_cookies_from_response(resp)
            if resp.status_code == 200:
                breaker.record_success()
                parsed = self.parse_company_page(resp.text, default_name=company_name)
                return parsed
            elif resp.status_code == 404:
                breaker.record_success()
                logger.info("Company not found on companyhouse.id (404): %s", company_name)
                return None
            else:
                kind = classify_ban(
                    status_code=resp.status_code, body_snippet=resp.text[:2000]
                )
                if kind in ("challenge", "blocked", "rate_limited", "server_error"):
                    breaker.record_failure()
                if kind == "challenge":
                    logger.warning(
                        "companyhouse.id menampilkan Cloudflare challenge "
                        "(tidak bisa dilewati HTTP client). Panen clearance baru: "
                        ".venv/bin/python scripts/refresh_browser_sessions.py "
                        "--site companyhouse --headed --profile-dir ./sessions/chrome"
                    )
                else:
                    logger.warning(
                        "companyhouse.id returned status %d [%s] for %s",
                        resp.status_code, kind, company_name,
                    )
                return None
        except Exception as exc:
            breaker.record_failure()
            logger.warning("Error fetching companyhouse.id for %s: %s", company_name, exc)
            # Jangan re-raise: caller (companyhouse.py) sudah menangkap Exception.
            # Re-raise menyebabkan double-log dan melempar exception melewati asyncio.to_thread.
            return None
