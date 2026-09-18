"""
Orchestrator Validator Paralel
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.cache import VerificationCache
from .ahu import check_company_ahu
from .base import ValidatorUnavailable, call_with_retry
from .blacklist import check_blacklist
from .company_registry import check_company_registry
from .dns_mx import check_email_mx
from .linkedin import check_company_linkedin

NEUTRAL_SCORE = 0.5


@dataclass
class ValidatorOutput:
    v_company: float = NEUTRAL_SCORE
    v_phone: float = NEUTRAL_SCORE
    v_email: float = NEUTRAL_SCORE
    degraded_sources: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


async def _resolve(kind, value: Optional[str], check_fn, source_name: str, cache: VerificationCache):
    if not value:
        return NEUTRAL_SCORE, None, "not_provided", False

    try:
        result = await call_with_retry(lambda: check_fn(value), source=source_name)
        await cache.set(
            kind, value,
            verdict_score=result.verdict_score,
            verdict_binary=result.verdict_binary,
            source=result.source,
            cache_source_key=source_name,
        )
        return result.verdict_score, result.verdict_binary, result.source, False
    except ValidatorUnavailable:
        cached_or_neutral, is_degraded = await cache.get_or_neutral(kind, value, source_name)
        return (
            cached_or_neutral.verdict_score,
            cached_or_neutral.verdict_binary,
            cached_or_neutral.source,
            is_degraded,
        )


async def _resolve_with_db(
    kind, value: Optional[str], check_fn, source_name: str, db: AsyncSession, cache: VerificationCache
):
    if not value:
        return NEUTRAL_SCORE, None, "not_provided", False

    try:
        result = await call_with_retry(lambda: check_fn(value, db), source=source_name)
        await cache.set(
            kind, value,
            verdict_score=result.verdict_score,
            verdict_binary=result.verdict_binary,
            source=result.source,
            cache_source_key=source_name,
        )
        return result.verdict_score, result.verdict_binary, result.source, False
    except ValidatorUnavailable:
        cached_or_neutral, is_degraded = await cache.get_or_neutral(kind, value, source_name)
        return (
            cached_or_neutral.verdict_score,
            cached_or_neutral.verdict_binary,
            cached_or_neutral.source,
            is_degraded,
        )


async def _resolve_blacklist(value: Optional[str], kind, db: AsyncSession, cache: VerificationCache):
    if not value:
        return NEUTRAL_SCORE, None, "not_provided", False

    try:
        result = await call_with_retry(
            lambda: check_blacklist(kind, value, db), source="intel_blacklist"
        )
        await cache.set(
            kind, value,
            verdict_score=result.verdict_score,
            verdict_binary=result.verdict_binary,
            source=result.source,
        )
        return result.verdict_score, result.verdict_binary, result.source, False
    except ValidatorUnavailable:
        cached_or_neutral, is_degraded = await cache.get_or_neutral(kind, value)
        return (
            cached_or_neutral.verdict_score,
            cached_or_neutral.verdict_binary,
            cached_or_neutral.source,
            is_degraded,
        )


async def run_validators(
    *,
    company: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    db: AsyncSession,
    cache: VerificationCache,
) -> ValidatorOutput:
    ahu_task = _resolve("company", company, check_company_ahu, "ahu", cache)
    linkedin_task = _resolve("company", company, check_company_linkedin, "linkedin", cache)
    registry_task = _resolve_with_db(
        "company", company, check_company_registry, "company_registry", db, cache
    )
    dns_task = _resolve("email", email, check_email_mx, "dns_mx", cache)
    blacklist_task = _resolve_blacklist(phone, "phone", db, cache)

    (ahu_score, ahu_binary, ahu_source, ahu_degraded), \
        (li_score, li_binary, li_source, li_degraded), \
        (reg_score, reg_binary, reg_source, reg_degraded), \
        (email_score, email_binary, email_source, email_degraded), \
        (phone_score, phone_binary, phone_source, phone_degraded) = await asyncio.gather(
        ahu_task, linkedin_task, registry_task, dns_task, blacklist_task
    )

    v_company = (ahu_score + li_score + reg_score) / 3

    degraded_sources = []
    if ahu_degraded:
        degraded_sources.append("ahu")
    if li_degraded:
        degraded_sources.append("linkedin")
    if reg_degraded:
        degraded_sources.append("company_registry")
    if email_degraded:
        degraded_sources.append("dns_mx")
    if phone_degraded:
        degraded_sources.append("intel_blacklist")

    return ValidatorOutput(
        v_company=v_company,
        v_phone=phone_score,
        v_email=email_score,
        degraded_sources=degraded_sources,
        details={
            "ahu": {"score": ahu_score, "binary": ahu_binary, "source": ahu_source},
            "linkedin": {"score": li_score, "binary": li_binary, "source": li_source},
            "company_registry": {"score": reg_score, "binary": reg_binary, "source": reg_source},
            "dns_mx": {"score": email_score, "binary": email_binary, "source": email_source},
            "intel_blacklist": {"score": phone_score, "binary": phone_binary, "source": phone_source},
        },
    )
