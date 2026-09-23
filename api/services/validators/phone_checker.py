"""
Validator multi-source untuk nomor telepon:
1. Internal intel_blacklist & reports DB.
2. aduannomor.id (Kominfo) via form-data phone check.
3. Fallback ke Kredibel.com jika aduannomor bersih / 0 laporan.
"""
import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.cache import VerificationResult, mask_value
from ...db.repository import IntelBlacklistRepository, ReportRepository
from .aduannomor_client import AduanNomorClient
from .kredibel_scraper import KredibelScraper

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def check_phone_reputation(phone: str, db: Optional[AsyncSession] = None) -> VerificationResult:
    """
    Pengecekan reputasi nomor telepon dari berbagai sumber:
    1. Cek database internal (blacklist & reports) terlebih dahulu.
    2. Cek aduannomor.id (Kominfo).
       Jika reported_count > 0 atau ada rekam kejahatan -> verdict_score tinggi (0.90 - 0.95).
    3. Jika aduannomor.id kosong (reported_count == 0), fallback cek kredibel.com.
       - Rating 0 / Belum ada ulasan -> aman (0.2).
       - Rating buruk / ulasan negatif -> verdict_score (0.85).
    """
    if not phone or not phone.strip():
        return VerificationResult(
            value_masked=mask_value("phone", phone or ""),
            verdict_score=0.5,
            verdict_binary=None,
            source="not_provided",
            fetched_at=_now_iso(),
        )

    # 1. Cek internal DB jika session tersedia
    if db is not None:
        blacklist_repo = IntelBlacklistRepository(db)
        existing = await blacklist_repo.get("phone", phone)
        if existing is not None and existing.active:
            return VerificationResult(
                value_masked=existing.value_masked,
                verdict_score=0.9,
                verdict_binary=True,
                source="intel_blacklist",
                fetched_at=_now_iso(),
            )

        report_repo = ReportRepository(db)
        report_count = await report_repo.count_verified_scam_by_phone(phone)
        if report_count >= 2:
            return VerificationResult(
                value_masked=mask_value("phone", phone),
                verdict_score=0.9,
                verdict_binary=True,
                source="intel_blacklist",
                fetched_at=_now_iso(),
            )

    # 2. Cek aduannomor.id
    def _call_aduannomor():
        client = AduanNomorClient()
        return client.check_phone(phone)

    aduan_data = None
    try:
        aduan_data = await asyncio.to_thread(_call_aduannomor)
    except Exception as exc:
        logger.warning("Pengecekan aduannomor.id error: %s", exc)

    if aduan_data:
        rep_count = aduan_data.get("reported_count", 0)
        kejahatan = aduan_data.get("reported_kejahatan") or []
        if rep_count > 0 or len(kejahatan) > 0:
            # Terbukti dilaporkan di aduannomor.id
            return VerificationResult(
                value_masked=mask_value("phone", phone),
                verdict_score=0.95,
                verdict_binary=True,
                source="aduannomor.id",
                fetched_at=_now_iso(),
            )

    # 3. Fallback ke kredibel.com jika aduannomor kosong (reported_count == 0) atau gagal
    def _call_kredibel():
        scraper = KredibelScraper()
        return scraper.fetch_phone_profile(phone)

    kredibel_data = None
    try:
        kredibel_data = await asyncio.to_thread(_call_kredibel)
    except Exception as exc:
        logger.warning("Pengecekan kredibel.com error: %s", exc)

    if kredibel_data:
        if kredibel_data.get("is_fraud_flagged"):
            return VerificationResult(
                value_masked=mask_value("phone", phone),
                verdict_score=kredibel_data.get("rating_score", 0.85),
                verdict_binary=True,
                source="kredibel.com",
                fetched_at=_now_iso(),
            )
        else:
            # Rating 0 / tidak ada ulasan / ulasan baik
            return VerificationResult(
                value_masked=mask_value("phone", phone),
                verdict_score=0.2,
                verdict_binary=False,
                source="kredibel.com",
                fetched_at=_now_iso(),
            )

    # Jika aduannomor berhasil dan hasilnya 0 laporan (bersih), dan kredibel tidak memberi sinyal negatif
    if aduan_data is not None and aduan_data.get("reported_count", 0) == 0:
        return VerificationResult(
            value_masked=mask_value("phone", phone),
            verdict_score=0.2,
            verdict_binary=False,
            source="aduannomor.id",
            fetched_at=_now_iso(),
        )

    # Fallback netral jika tidak ada data dari kedua layanan
    return VerificationResult(
        value_masked=mask_value("phone", phone),
        verdict_score=0.5,
        verdict_binary=None,
        source="phone_check",
        fetched_at=_now_iso(),
    )
