"""Repository layer -- satu-satunya lapisan yang boleh menyentuh session DB langsung."""
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.cache import hash_value, mask_value
from ..core.company_normalize import normalize_company_name
from .models import (
    CompanyRegistry,
    Detection,
    EducationArticle,
    IntelBlacklist,
    JobAlternative,
    Report,
    WaSession,
)


class DetectionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields: Any) -> Detection:
        detection = Detection(**fields)
        self.session.add(detection)
        await self.session.commit()
        await self.session.refresh(detection)
        return detection

    async def get_by_id(self, detection_id: str) -> Optional[Detection]:
        result = await self.session.execute(
            select(Detection).where(Detection.id == detection_id)
        )
        return result.scalar_one_or_none()


class ReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields: Any) -> Report:
        report = Report(**fields)
        self.session.add(report)
        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def get_by_id(self, report_id: str) -> Optional[Report]:
        result = await self.session.execute(
            select(Report).where(Report.id == report_id)
        )
        return result.scalar_one_or_none()

    async def count_verified_scam_by_phone(self, phone: str) -> int:
        result = await self.session.execute(
            select(Report).where(
                Report.suspect_phone == phone,
                Report.status == "verified_scam",
            )
        )
        return len(result.scalars().all())

    async def count_verified_scam_by_email(self, email: str) -> int:
        result = await self.session.execute(
            select(Report).where(
                Report.suspect_email == email,
                Report.status == "verified_scam",
            )
        )
        return len(result.scalars().all())

    async def count_verified_scam_by_company(self, company: str) -> int:
        result = await self.session.execute(
            select(Report).where(
                Report.suspect_company == company,
                Report.status == "verified_scam",
            )
        )
        return len(result.scalars().all())


class IntelBlacklistRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, kind: str, value: str) -> Optional[IntelBlacklist]:
        value_hash = hash_value(value)
        result = await self.session.execute(
            select(IntelBlacklist).where(
                IntelBlacklist.kind == kind,
                IntelBlacklist.value_hash == value_hash,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_report_count(
        self, kind: str, value: str, *, report_count: int, source: str
    ) -> IntelBlacklist:
        existing = await self.get(kind, value)
        is_active = report_count >= 2

        if existing is not None:
            existing.report_count = report_count
            existing.active = is_active
            existing.last_reported_at = datetime.now(timezone.utc)
            sources = set(existing.sources or [])
            sources.add(source)
            existing.sources = list(sources)
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        entry = IntelBlacklist(
            kind=kind,
            value_hash=hash_value(value),
            value_masked=mask_value(kind, value),
            report_count=report_count,
            active=is_active,
            sources=[source],
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry


class CompanyRegistryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_name(self, company_name: str) -> Optional[CompanyRegistry]:
        name_norm = normalize_company_name(company_name)
        result = await self.session.execute(
            select(CompanyRegistry).where(CompanyRegistry.name_norm == name_norm)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        legal_name: str,
        *,
        registered: Optional[bool] = None,
        is_flagged_scam: bool = False,
        source: str,
    ) -> CompanyRegistry:
        name_norm = normalize_company_name(legal_name)
        existing = await self.get_by_name(legal_name)

        if existing is not None:
            if registered is not None:
                existing.registered = registered
            if is_flagged_scam:
                existing.is_flagged_scam = True
            existing.updated_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        entry = CompanyRegistry(
            name_norm=name_norm,
            legal_name=legal_name,
            registered=registered,
            is_flagged_scam=is_flagged_scam,
            source=source,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry


class JobAlternativeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active(self, limit: int = 3) -> list[JobAlternative]:
        result = await self.session.execute(
            select(JobAlternative).where(JobAlternative.active == True).limit(limit)  # noqa: E712
        )
        return list(result.scalars().all())


class WaSessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, phone_hash: str) -> Optional[WaSession]:
        result = await self.session.execute(
            select(WaSession).where(WaSession.phone_hash == phone_hash)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, phone_hash: str, *, current_state: str, context: Optional[dict] = None
    ) -> WaSession:
        existing = await self.get(phone_hash)
        now = datetime.now(timezone.utc)

        if existing is not None:
            existing.current_state = current_state
            existing.context = context
            existing.last_active_at = now
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        entry = WaSession(
            phone_hash=phone_hash,
            current_state=current_state,
            context=context,
            last_active_at=now,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def delete(self, phone_hash: str) -> None:
        existing = await self.get(phone_hash)
        if existing is not None:
            await self.session.delete(existing)
            await self.session.commit()


class EducationArticleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_published(self, limit: int = 5) -> list[EducationArticle]:
        result = await self.session.execute(
            select(EducationArticle)
            .where(EducationArticle.published == True)  # noqa: E712
            .limit(limit)
        )
        return list(result.scalars().all())
