"""Validator halaman perusahaan LinkedIn"""
from datetime import datetime, timezone

from ...core.cache import VerificationResult, mask_value


async def check_company_linkedin(company_name: str) -> VerificationResult:
    return VerificationResult(
        value_masked=mask_value("company", company_name),
        verdict_score=0.5,
        verdict_binary=None,
        source="mock_linkedin",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
