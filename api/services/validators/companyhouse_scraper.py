"""
Scraper modular untuk companyhouse.id dengan session-based HTTP workflow.
"""
import logging
import re
from typing import Any, Optional
import requests
from bs4 import BeautifulSoup

from ...core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def generate_company_slug(company_name: str) -> str:
    """
    Mengubah nama perusahaan menjadi slug URL (misal: PT. Makna Jaya Pratama -> makna-jaya-pratama).
    """
    clean = re.sub(r'^(PT|CV|Perum|UD|Firma|Yayasan)\.?\s+', '', company_name, flags=re.IGNORECASE)
    clean = re.sub(r'[\.\,\(\)\&]', ' ', clean)
    clean = re.sub(r'\s+', '-', clean).strip('-').lower()
    return clean


class CompanyHouseScraper:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.session = requests.Session()
        self._configure_session()

    def _configure_session(self) -> None:
        self.session.headers.update({
            "User-Agent": self.settings.companyhouse_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "id,en-US;q=0.9,en;q=0.8",
        })
        if self.settings.companyhouse_session_cookie:
            # Format cookie string "key=value; key2=value2"
            for part in self.settings.companyhouse_session_cookie.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    self.session.cookies.set(k.strip(), v.strip())

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

        url = f"{self.settings.companyhouse_base_url.rstrip('/')}/{slug}"
        logger.info("Fetching companyhouse.id profile: %s", url)

        try:
            resp = self.session.get(
                url,
                timeout=self.settings.companyhouse_timeout_seconds,
                allow_redirects=True,
            )
            if resp.status_code == 200:
                parsed = self.parse_company_page(resp.text, default_name=company_name)
                return parsed
            elif resp.status_code == 404:
                logger.info("Company not found on companyhouse.id (404): %s", company_name)
                return None
            else:
                logger.warning(
                    "companyhouse.id returned status %d for %s", resp.status_code, company_name
                )
                return None
        except Exception as exc:
            logger.warning("Error fetching companyhouse.id for %s: %s", company_name, exc)
            raise exc
