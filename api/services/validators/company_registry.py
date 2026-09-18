"""
Validator company_registry -- cek internal berbasis data lowongan REAL
yang berhasil dikumpulkan tim Data Scraping (scraper AHU/LinkedIn asli
tidak tersedia). "Tidak ditemukan" dianggap netral, BUKAN mencurigakan,
karena data registry ini jauh dari lengkap.
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.cache import VerificationResult, mask_value
from ...db.repository import CompanyRegistryRepository


async def check_company_registry(company_name: str, db: AsyncSession) -> VerificationResult:
    repo = CompanyRegistryRepository(db)
    entry = await repo.get_by_name(company_name)

    if entry is None:
        return VerificationResult(
            value_masked=mask_value("company", company_name),
            verdict_score=0.5,
            verdict_binary=None,
            source="company_registry",
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    if entry.is_flagged_scam:
        score, binary = 0.9, True
    elif entry.registered:
        score, binary = 0.2, False
    else:
        score, binary = 0.5, None

    return VerificationResult(
        value_masked=mask_value("company", company_name),
        verdict_score=score,
        verdict_binary=binary,
        source="company_registry",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
