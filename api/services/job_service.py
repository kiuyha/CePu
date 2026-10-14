"""Lapisan pencarian kerja DB-first dengan TTL, dipakai endpoint web & bot WA.

Alur: cari di `job_alternatives` dulu -> kalau kosong, basi (> TTL), atau
refresh=True, scrape SATU halaman JobStreet lalu simpan ke DB. Pencarian
berulang untuk role yang sama tidak pernah menyentuh JobStreet lagi
selama datanya masih segar.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, get_settings
from ..db.models import JobAlternative
from ..db.repository import JobAlternativeRepository
from .jobstreet_scraper import JobStreetScraper

logger = logging.getLogger(__name__)

# Satu halaman scrape saja — hemat request & waktu.
SCRAPE_PAGE_SIZE = 10


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite mengembalikan DateTime(timezone=True) sebagai naive — anggap UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_fresh(rows: list[JobAlternative], cutoff: datetime) -> bool:
    if not rows:
        return False
    newest = max((_as_aware(r.captured_at) for r in rows), default=None)
    return newest is not None and newest >= cutoff


def _to_dict(row: JobAlternative) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "company": row.company,
        "location": row.location,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_display": row.salary_display,
        "work_type": None,
        "listed_at": row.captured_at.isoformat() if row.captured_at else None,
        "listed_label": None,
        "url": row.url,
    }


async def get_or_fetch_jobs(
    *,
    role: str,
    location: Optional[str] = None,
    limit: int = 10,
    refresh: bool = False,
    db: AsyncSession,
    settings: Optional[Settings] = None,
) -> tuple[list[dict[str, Any]], str]:
    """Kembalikan (jobs, source) dengan source 'db' | 'live' | 'empty'.

    - 'db': hasil dari database dan masih segar (< TTL, tanpa fetch).
    - 'live': baru saja di-scrape 1 halaman lalu disimpan ke database.
    - 'empty': DB kosong dan scrape gagal/kosong.
    """
    settings = settings or get_settings()
    ttl_hours = max(1, settings.jobstreet_cache_ttl_hours)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)

    role = (role or "").strip()
    location = (location or "").strip() or None
    if not role:
        return [], "empty"

    repo = JobAlternativeRepository(db)

    if not refresh:
        rows = await repo.search(role, location, limit)
        if _is_fresh(rows, cutoff):
            logger.info("JobStreet: %d hasil untuk %r dari DB (segar, tanpa fetch).", len(rows), role)
            return [_to_dict(r) for r in rows], "db"
        if rows:
            logger.info("JobStreet: %d hasil untuk %r basi (> %dh), scrape ulang.", len(rows), role, ttl_hours)

    # Scrape SATU halaman saja, lalu simpan.
    try:
        scraper = JobStreetScraper(settings)
        scraped = await asyncio.to_thread(
            scraper.search_jobs, role, location, 1, SCRAPE_PAGE_SIZE
        )
    except Exception as exc:
        logger.warning("JobStreet scrape gagal untuk %r: %s", role, exc)
        scraped = []

    if scraped:
        try:
            # Prune dulu (termasuk baris basi role ini), baru simpan yang segar.
            # Hanya baris jobstreet yang dihapus — data kurasi manual aman.
            await repo.delete_expired_jobstreet(cutoff)
            await repo.upsert_scraped(scraped, role)
        except Exception as exc:
            logger.warning("Gagal menyimpan hasil JobStreet ke DB: %s", exc)
        rows = await repo.search(role, location, limit)
        if rows:
            return [_to_dict(r) for r in rows], "live"
        return scraped[:limit], "live"

    # Scrape gagal/kosong: sajikan sisa DB walau basi, daripada kosong.
    rows = await repo.search(role, location, limit)
    return ([_to_dict(r) for r in rows], "db") if rows else ([], "empty")
