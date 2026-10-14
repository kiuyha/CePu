"""
Orchestrator Validator Paralel
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.cache import VerificationCache
from ...db.base import async_session_factory
from .companyhouse import check_company_legalitas
from .base import ValidatorUnavailable, call_with_retry
from .blacklist import check_blacklist
from .company_registry import check_company_registry
from .dns_mx import check_email_mx
from .phone_checker import check_phone_reputation

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
    """Versi DB dengan session milik sendiri per cabang paralel.

    PENTING: AsyncSession TIDAK boleh dipakai konkurensi (asyncio.gather).
    Setiap cabang membuka session sendiri agar tidak rebutan state dengan
    cabang lain — inilah penyebab IllegalStateChangeError di production.
    Session `db` milik caller tidak dipakai untuk query validator, hanya
    dipertahankan di signature agar kompatibel.
    """
    if not value:
        return NEUTRAL_SCORE, None, "not_provided", False

    async with async_session_factory() as session:
        try:
            result = await call_with_retry(lambda: check_fn(value, session), source=source_name)
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
    companyhouse_task = _resolve_with_db(
        "company", company, check_company_legalitas, "companyhouse", db, cache
    )
    registry_task = _resolve_with_db(
        "company", company, check_company_registry, "company_registry", db, cache
    )
    dns_task = _resolve_with_db(
        "email", email, lambda em, s: check_email_mx(em, company_name=company, db=s), "dns_mx", db, cache
    )
    phone_task = _resolve_with_db("phone", phone, check_phone_reputation, "phone_check", db, cache)

    (
        (ch_score, ch_binary, ch_source, ch_degraded),
        (reg_score, reg_binary, reg_source, reg_degraded),
        (email_score, email_binary, email_source, email_degraded),
        (phone_score, phone_binary, phone_source, phone_degraded),
    ) = await asyncio.gather(companyhouse_task, registry_task, dns_task, phone_task)

    # v_company: rata-rata 2 sumber aktif (companyhouse.id + company_registry)
    # LinkedIn dihapus karena hanya mock 0.5 yang tidak memberikan sinyal nyata
    v_company = (ch_score + reg_score) / 2

    degraded_sources = []
    if ch_degraded:
        degraded_sources.append("companyhouse")
    if reg_degraded:
        degraded_sources.append("company_registry")
    if email_degraded:
        degraded_sources.append("dns_mx")
    if phone_degraded:
        degraded_sources.append("phone_check")

    return ValidatorOutput(
        v_company=v_company,
        v_phone=phone_score,
        v_email=email_score,
        degraded_sources=degraded_sources,
        details={
            "companyhouse": {"score": ch_score, "binary": ch_binary, "source": ch_source},
            "company_registry": {"score": reg_score, "binary": reg_binary, "source": reg_source},
            "dns_mx": {"score": email_score, "binary": email_binary, "source": email_source},
            "intel_blacklist": {"score": phone_score, "binary": phone_binary, "source": phone_source},
            "phone_check": {"score": phone_score, "binary": phone_binary, "source": phone_source},
        },
    )
