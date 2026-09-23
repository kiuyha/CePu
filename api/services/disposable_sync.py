"""
Layanan sinkronisasi berkala disposable email domains dari repositori GitHub
open-source (disposable-email-domains) ke tabel disposable_domains di database.
"""
import logging
from typing import Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, get_settings
from ..db.repository import DisposableDomainRepository

logger = logging.getLogger(__name__)


async def sync_disposable_domains_from_github(
    db: AsyncSession,
    settings: Optional[Settings] = None,
) -> int:
    """
    Mengunduh daftar domain sekali pakai terbaru dari GitHub
    dan menyimpannya ke tabel `disposable_domains` secara batch.
    """
    settings = settings or get_settings()
    url = settings.disposable_domains_sync_url

    logger.info("Starting synchronization of disposable domains from: %s", url)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(
                    "Failed to fetch disposable domains from GitHub, status code: %d",
                    resp.status_code,
                )
                return 0

            content = resp.text

        # File berformat plain text dengan 1 domain per baris
        lines = [line.strip().lower() for line in content.splitlines() if line.strip() and not line.startswith("#")]
        if not lines:
            return 0

        repo = DisposableDomainRepository(db)
        added_count = await repo.bulk_upsert(lines, source="github/disposable-email-domains")
        logger.info(
            "Disposable domains sync completed. Parsed %d domains, newly added %d to database.",
            len(lines),
            added_count,
        )
        return added_count
    except Exception as exc:
        logger.error("Error synchronizing disposable domains from GitHub: %s", exc)
        return 0
