"""
Validator AHU Online (legalitas nama perusahaan).
"""
from datetime import datetime, timezone

from ...core.cache import VerificationResult, mask_value


async def check_company_ahu(company_name: str) -> VerificationResult:
    return VerificationResult(
        value_masked=mask_value("company", company_name),
        verdict_score=0.5,
        verdict_binary=None,
        source="mock_ahu",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
