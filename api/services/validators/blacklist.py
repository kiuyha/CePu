"""Validator blacklist internal, berbasis tabel reports/intel_blacklist."""
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.cache import VerificationResult, mask_value
from ...db.repository import IntelBlacklistRepository, ReportRepository

Kind = Literal["phone", "email", "company"]

_COUNT_METHOD_BY_KIND = {
    "phone": "count_verified_scam_by_phone",
    "email": "count_verified_scam_by_email",
    "company": "count_verified_scam_by_company",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def check_blacklist(kind: Kind, value: str, db: AsyncSession) -> VerificationResult:
    blacklist_repo = IntelBlacklistRepository(db)
    existing = await blacklist_repo.get(kind, value)

    if existing is not None:
        return VerificationResult(
            value_masked=existing.value_masked,
            verdict_score=0.9 if existing.active else 0.2,
            verdict_binary=existing.active,
            source="intel_blacklist",
            fetched_at=_now_iso(),
        )

    report_repo = ReportRepository(db)
    count_method = getattr(report_repo, _COUNT_METHOD_BY_KIND[kind])
    report_count = await count_method(value)

    await blacklist_repo.upsert_report_count(
        kind, value, report_count=report_count, source="reports_table"
    )

    is_active = report_count >= 2
    return VerificationResult(
        value_masked=mask_value(kind, value),
        verdict_score=0.9 if is_active else 0.2,
        verdict_binary=is_active,
        source="intel_blacklist",
        fetched_at=_now_iso(),
    )
