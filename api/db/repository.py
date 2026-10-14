"""Repository layer -- satu-satunya lapisan yang boleh menyentuh session DB langsung."""
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, or_, select, text
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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

    async def search(
        self, role: str, location: Optional[str] = None, limit: int = 10
    ) -> list[JobAlternative]:
        """Cari lowongan tersimpan: cocokkan role ke kolom role/judul/perusahaan.

        Dipakai endpoint & WA agar pencarian berulang tidak scraping ulang.
        """
        role = (role or "").strip()
        if not role:
            return []
        like = f"%{role}%"
        stmt = select(JobAlternative).where(
            JobAlternative.active == True,  # noqa: E712
            or_(
                JobAlternative.role.ilike(like),
                JobAlternative.title.ilike(like),
                JobAlternative.company.ilike(like),
            ),
        )
        if location and location.strip():
            stmt = stmt.where(JobAlternative.location.ilike(f"%{location.strip()}%"))
        stmt = stmt.order_by(JobAlternative.captured_at.desc()).limit(max(1, min(limit, 30)))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_scraped(self, jobs: list[dict], role: str) -> int:
        """Simpan hasil scrape; lewati URL yang sudah ada. Kembalikan jumlah baris baru."""
        role = (role or "").strip().lower() or None
        fresh = [j for j in jobs if isinstance(j, dict) and j.get("url")]
        if not fresh:
            return 0
        existing_urls = {
            row[0]
            for row in (
                await self.session.execute(
                    select(JobAlternative.url).where(
                        JobAlternative.url.in_([j["url"] for j in fresh])
                    )
                )
            ).all()
        }
        inserted = 0
        for job in fresh:
            if job["url"] in existing_urls:
                continue
            self.session.add(
                JobAlternative(
                    company=(job.get("company") or "")[:255],
                    title=(job.get("title") or "")[:255],
                    url=job["url"][:500],
                    verified_source="jobstreet",
                    role=role,
                    location=(job.get("location") or None),
                    salary_display=(job.get("salary_display") or None),
                )
            )
            inserted += 1
        if inserted:
            await self.session.commit()
        return inserted

    async def delete_expired_jobstreet(self, cutoff: datetime) -> int:
        """Hapus baris jobstreet yang lebih tua dari cutoff (TTL cache).

        Hanya menyentuh verified_source='jobstreet' — baris manual/legacy
        (alternatif kurasi deteksi) tidak pernah dihapus.
        """
        res = await self.session.execute(
            delete(JobAlternative)
            .where(
                JobAlternative.verified_source == "jobstreet",
                JobAlternative.captured_at < cutoff,
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        return res.rowcount or 0


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

    async def list_published(self, limit: int = 50) -> list[EducationArticle]:
        result = await self.session.execute(
            select(EducationArticle)
            .where(EducationArticle.published == True)  # noqa: E712
            .order_by(EducationArticle.published_at.desc(), EducationArticle.title.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[EducationArticle]:
        result = await self.session.execute(
            select(EducationArticle).order_by(EducationArticle.title.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, article_id: str) -> EducationArticle | None:
        result = await self.session.execute(
            select(EducationArticle).where(EducationArticle.id == article_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> EducationArticle | None:
        result = await self.session.execute(
            select(EducationArticle).where(EducationArticle.slug == slug)
        )
        return result.scalar_one_or_none()

    async def upsert_by_slug(
        self,
        slug: str,
        title: str,
        body_md: str,
        tags: list | None = None,
        published: bool = True,
        published_at: datetime | None = None,
    ) -> EducationArticle:
        existing = await self.get_by_slug(slug)
        if existing:
            existing.title = title
            existing.body_md = body_md
            existing.tags = tags
            existing.published = published
            if published and not existing.published_at:
                existing.published_at = published_at or _utcnow()
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        article = EducationArticle(
            slug=slug,
            title=title,
            body_md=body_md,
            tags=tags or [],
            published=published,
            published_at=published_at or (_utcnow() if published else None),
        )
        self.session.add(article)
        await self.session.commit()
        await self.session.refresh(article)
        return article

    async def update(
        self,
        article_id: str,
        title: str | None = None,
        slug: str | None = None,
        body_md: str | None = None,
        tags: list | None = None,
        published: bool | None = None,
    ) -> EducationArticle | None:
        article = await self.get_by_id(article_id)
        if not article:
            return None
        if title is not None:
            article.title = title
        if slug is not None:
            article.slug = slug
        if body_md is not None:
            article.body_md = body_md
        if tags is not None:
            article.tags = tags
        if published is not None:
            article.published = published
            if published and not article.published_at:
                article.published_at = _utcnow()
        await self.session.commit()
        await self.session.refresh(article)
        return article

    async def delete(self, article_id: str) -> bool:
        article = await self.get_by_id(article_id)
        if not article:
            return False
        await self.session.delete(article)
        await self.session.commit()
        return True


class DisposableDomainRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def is_disposable(self, domain: str) -> bool:
        norm = domain.strip().lower()
        from .models import DisposableDomain
        result = await self.session.execute(
            select(DisposableDomain).where(DisposableDomain.domain == norm)
        )
        return result.scalar_one_or_none() is not None

    async def bulk_upsert(self, domains: list[str], source: str = "github/disposable-email-domains") -> int:
        """
        Menyimpan banyak domain disposable sekaligus menggunakan INSERT ... ON CONFLICT DO NOTHING.
        Jauh lebih efisien daripada N×SELECT+INSERT yang digunakan sebelumnya.
        Commit dilakukan per 500 baris agar transaksi tidak terlalu besar.
        """
        from .models import DisposableDomain

        # Normalisasi dan de-duplikasi
        unique_domains = list(dict.fromkeys(
            d.strip().lower() for d in domains if d and d.strip()
        ))

        if not unique_domains:
            return 0

        CHUNK_SIZE = 500
        total_inserted = 0
        # Deteksi dialect dari settings URL (session.bind bisa None di async SQLAlchemy)
        from ..core.config import get_settings as _gs
        _db_url = _gs().sqlalchemy_db_url
        dialect_name = "postgresql" if "postgresql" in _db_url else "sqlite"

        for i in range(0, len(unique_domains), CHUNK_SIZE):
            chunk = unique_domains[i: i + CHUNK_SIZE]
            if dialect_name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                stmt = (
                    pg_insert(DisposableDomain)
                    .values([{"domain": d, "source": source} for d in chunk])
                    .on_conflict_do_nothing(index_elements=["domain"])
                )
                result = await self.session.execute(stmt)
                total_inserted += result.rowcount if result.rowcount and result.rowcount > 0 else 0
            else:
                # SQLite / fallback: check-and-insert
                for d in chunk:
                    existing = await self.session.execute(
                        select(DisposableDomain).where(DisposableDomain.domain == d)
                    )
                    if existing.scalar_one_or_none() is None:
                        self.session.add(DisposableDomain(domain=d, source=source))
                        total_inserted += 1
            await self.session.commit()

        return total_inserted
