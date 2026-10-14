"""GET /v1/jobs/search -- pencarian kerja on-demand (DB-first).

Hanya dipanggil saat user eksplisit meminta (mis. tombol "cari pekerjaan
yang mirip" di web atau perintah "cari kerja ..." di WhatsApp).
TIDAK dipanggil otomatis oleh pipeline deteksi.

Hasil scrape JobStreet (selalu SATU halaman) disimpan ke `job_alternatives`,
jadi pencarian berulang untuk role yang sama disajikan dari DB tanpa fetch.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, get_settings
from ..db.base import get_db_session
from ..services.job_service import get_or_fetch_jobs

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("/search")
async def search_jobs(
    role: str = Query(..., min_length=2, max_length=100, description="Posisi/pekerjaan, mis. 'driver'"),
    location: str | None = Query(default=None, max_length=100, description="Lokasi opsional, mis. 'Jakarta'"),
    limit: int = Query(default=10, ge=1, le=30, description="Maksimal hasil dari data tersimpan"),
    refresh: bool = Query(default=False, description="True = scrape ulang 1 halaman lalu simpan"),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        jobs, source = await get_or_fetch_jobs(
            role=role.strip(),
            location=location.strip() if location else None,
            limit=limit,
            refresh=refresh,
            db=db,
            settings=settings,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pencarian lowongan gagal: {exc}.")
    return {
        "role": role.strip(),
        "location": location.strip() if location else None,
        "count": len(jobs),
        "source": source,  # 'db' | 'live' | 'empty'
        "jobs": jobs,
    }
