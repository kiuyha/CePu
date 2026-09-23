"""
Validator AHU / CompanyHouse (legalitas nama perusahaan).
Menggunakan companyhouse.id scraper berbasis session HTTP dan menyimpan hasil ke company_registry DB.
"""
import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.cache import VerificationResult, mask_value
from ...db.repository import CompanyRegistryRepository
from .companyhouse_scraper import CompanyHouseScraper

logger = logging.getLogger(__name__)


async def check_company_ahu(company_name: str, db: Optional[AsyncSession] = None) -> VerificationResult:
    """
    Pengecekan legalitas perusahaan:
    1. Cek database lokal `company_registry` terlebih dahulu.
    2. Jika belum ada atau belum terdaftar, scraper companyhouse.id dijalankan.
    3. Jika ditemukan di companyhouse.id, update data ke database `company_registry` dan berikan skor valid.
    """
    if not company_name or not company_name.strip():
        return VerificationResult(
            value_masked=mask_value("company", company_name or ""),
            verdict_score=0.5,
            verdict_binary=None,
            source="not_provided",
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    # 1. Cek database lokal jika session tersedia
    if db is not None:
        repo = CompanyRegistryRepository(db)
        entry = await repo.get_by_name(company_name)
        if entry is not None and entry.registered:
            return VerificationResult(
                value_masked=mask_value("company", company_name),
                verdict_score=0.2,
                verdict_binary=False,
                source="company_registry",
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
        elif entry is not None and entry.is_flagged_scam:
            return VerificationResult(
                value_masked=mask_value("company", company_name),
                verdict_score=0.9,
                verdict_binary=True,
                source="company_registry",
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )

    # 2. Coba scrape companyhouse.id
    def _scrape():
        scraper = CompanyHouseScraper()
        return scraper.fetch_company_detail(company_name)

    detail = None
    try:
        detail = await asyncio.to_thread(_scrape)
    except Exception as exc:
        logger.warning("Scraper companyhouse.id gagal untuk '%s': %s", company_name, exc)
        # Akan di-handle oleh caller retry/degraded

    if detail:
        # 3. Simpan ke database jika db session ada
        if db is not None:
            repo = CompanyRegistryRepository(db)
            legal = detail.get("company_name") or company_name
            await repo.upsert(
                legal_name=legal,
                registered=True,
                is_flagged_scam=False,
                source="companyhouse.id",
            )

        return VerificationResult(
            value_masked=mask_value("company", company_name),
            verdict_score=0.2,
            verdict_binary=False,
            source="companyhouse.id",
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    # Tidak ditemukan di companyhouse.id -> netral 0.5
    return VerificationResult(
        value_masked=mask_value("company", company_name),
        verdict_score=0.5,
        verdict_binary=None,
        source="companyhouse.id",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )

