"""Validator email lewat cek DNS MX record."""
import asyncio
from datetime import datetime, timezone

import dns.asyncresolver
import dns.exception

from ...core.cache import VerificationResult, mask_value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def check_email_mx(email: str) -> VerificationResult:
    if "@" not in email:
        return VerificationResult(
            value_masked=email, verdict_score=0.9, verdict_binary=True,
            source="dns_mx", fetched_at=_now_iso(),
        )

    domain = email.rsplit("@", 1)[-1].strip()

    try:
        answers = await dns.asyncresolver.resolve(domain, "MX")
        has_mx = len(answers) > 0
    except (dns.exception.DNSException, asyncio.TimeoutError):
        has_mx = False

    return VerificationResult(
        value_masked=mask_value("email", email),
        verdict_score=0.1 if has_mx else 0.8,
        verdict_binary=not has_mx,
        source="dns_mx",
        fetched_at=_now_iso(),
    )
