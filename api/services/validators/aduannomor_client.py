"""
Client untuk aduannomor.id (Kominfo / Aduan Nomor Seluler).
URL endpoint: https://aduannomor.id/api/v.1/ticket/phone-check
Bypass proteksi: Header Referer: https://aduannomor.id/cek-nomor-seluler
"""
import logging
from typing import Any, Optional
import requests

from ...core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def parse_phone_number(raw_phone: str) -> tuple[str, str]:
    """
    Normalisasi nomor telepon menjadi (calling_code, phone_number).
    Contoh:
    - '08123456789' -> ('+62', '8123456789')
    - '+628123456789' -> ('+62', '8123456789')
    - '628123456789' -> ('+62', '8123456789')
    - '+12025550123' -> ('+1', '2025550123')
    """
    digits = "".join(ch for ch in raw_phone if ch.isdigit() or ch == "+")
    if digits.startswith("+62"):
        return "+62", digits[3:]
    elif digits.startswith("62"):
        return "+62", digits[2:]
    elif digits.startswith("08") or digits.startswith("0"):
        return "+62", digits[1:]
    elif digits.startswith("+"):
        return "+62", digits.lstrip("+")
    return "+62", digits


class AduanNomorClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.session = requests.Session()

    def check_phone(self, phone: str) -> Optional[dict[str, Any]]:
        """
        Request ke API aduannomor.id.
        Mengembalikan response data dict jika berhasil, None jika request gagal.
        Struktur response sukses:
        {
            "status": 200,
            "error": False,
            "data": {
                "reported_phone": "+62811111111",
                "reported_phone_status": "Blocked | Recycled | Aktif",
                "reported_count": 0,
                "reported_kejahatan": [],
                "reported_status_laporan": []
            },
            "messages": "Data Loaded"
        }
        """
        calling_code, phone_number = parse_phone_number(phone)
        url = f"{self.settings.aduannomor_base_url.rstrip('/')}/api/v.1/ticket/phone-check"

        headers = {
            "Referer": f"{self.settings.aduannomor_base_url.rstrip('/')}/cek-nomor-seluler",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "calling_code": calling_code,
            "phone_number": phone_number,
        }

        try:
            resp = self.session.post(
                url,
                data=data,
                headers=headers,
                timeout=self.settings.aduannomor_timeout_seconds,
            )
            if resp.status_code == 200:
                payload = resp.json()
                if payload.get("status") == 200 and not payload.get("error"):
                    return payload.get("data", {})
                logger.warning("aduannomor.id returned error response: %s", payload)
                return payload.get("data")
            else:
                logger.warning(
                    "aduannomor.id HTTP status %d for phone %s", resp.status_code, phone
                )
                return None
        except Exception as exc:
            logger.warning("aduannomor.id request failed for phone %s: %s", phone, exc)
            raise exc
