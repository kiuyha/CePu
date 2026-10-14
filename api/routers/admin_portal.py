"""Router khusus untuk Portal Admin CePu (Dashboard, Laporan, Deteksi, Perusahaan, Intel Blacklist)."""
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, get_settings
from ..db.base import get_db_session
from ..db.models import (
    CompanyRegistry,
    Detection,
    EducationArticle,
    IntelBlacklist,
    JobAlternative,
    Report,
    WaSession,
)

router = APIRouter(prefix="/v1/admin", tags=["admin-portal"])


class AdminLoginPayload(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    username: str
    message: str


# Helper dependency untuk memvalidasi token sesi admin
def _verify_admin_auth(
    authorization: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header Authorization dibutuhkan untuk mengakses portal admin.",
        )

    # Format bearer token: 'Bearer <expected_secret>'
    token = authorization.replace("Bearer ", "").strip()
    expected_token = f"cepu-admin-{settings.admin_username}-{settings.admin_password}"

    if token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token admin tidak valid atau sudah kadaluarsa.",
        )
    return settings.admin_username


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(
    payload: AdminLoginPayload,
    settings: Settings = Depends(get_settings),
):
    """Autentikasi admin berdasarkan konfigurasi environment variable."""
    if payload.username != settings.admin_username or payload.password != settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password admin salah.",
        )

    token = f"cepu-admin-{settings.admin_username}-{settings.admin_password}"
    return AdminLoginResponse(
        token=token,
        username=settings.admin_username,
        message="Login admin berhasil.",
    )


@router.get("/overview", dependencies=[Depends(_verify_admin_auth)])
async def get_admin_overview(
    db: AsyncSession = Depends(get_db_session),
):
    """Statistik agregat ringkas untuk dashboard admin."""
    detection_count = (await db.execute(select(func.count(Detection.id)))).scalar() or 0
    report_count = (await db.execute(select(func.count(Report.id)))).scalar() or 0
    pending_reports = (
        await db.execute(select(func.count(Report.id)).where(Report.status == "pending"))
    ).scalar() or 0
    company_count = (await db.execute(select(func.count(CompanyRegistry.id)))).scalar() or 0
    blacklist_count = (await db.execute(select(func.count(IntelBlacklist.id)))).scalar() or 0
    article_count = (await db.execute(select(func.count(EducationArticle.id)))).scalar() or 0

    return {
        "detections": detection_count,
        "reports": report_count,
        "pending_reports": pending_reports,
        "companies": company_count,
        "blacklists": blacklist_count,
        "articles": article_count,
    }


@router.get("/detections", dependencies=[Depends(_verify_admin_auth)])
async def get_admin_detections(
    limit: int = 50,
    offset: int = 0,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Melihat catatan deteksi lowongan kerja (log riwayat sistem)."""
    stmt = select(Detection).order_by(Detection.created_at.desc()).limit(limit).offset(offset)
    if category:
        stmt = stmt.where(Detection.category == category)

    res = await db.execute(stmt)
    records = res.scalars().all()
    return records


@router.get("/reports", dependencies=[Depends(_verify_admin_auth)])
async def get_admin_reports(
    limit: int = 50,
    offset: int = 0,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Melihat daftar laporan penipuan masuk dari pengguna."""
    stmt = select(Report).order_by(Report.created_at.desc()).limit(limit).offset(offset)
    if status_filter:
        stmt = stmt.where(Report.status == status_filter)

    res = await db.execute(stmt)
    return res.scalars().all()


class UpdateReportStatusPayload(BaseModel):
    status: str  # "verified_scam" | "false_alarm" | "pending"
    note: Optional[str] = None
    reviewer: Optional[str] = None


@router.put("/reports/{report_id}", dependencies=[Depends(_verify_admin_auth)])
async def update_report_status(
    report_id: str,
    payload: UpdateReportStatusPayload,
    db: AsyncSession = Depends(get_db_session),
):
    """Memperbarui status peninjauan laporan (misal: verifikasi scam)."""
    res = await db.execute(select(Report).where(Report.id == report_id))
    report = res.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan.")

    report.status = payload.status
    if payload.note is not None:
        report.note = payload.note
    if payload.reviewer is not None:
        report.reviewer = payload.reviewer

    await db.commit()
    await db.refresh(report)
    return report


@router.get("/companies", dependencies=[Depends(_verify_admin_auth)])
async def get_admin_companies(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Melihat data registri perusahaan yang tersimpan."""
    stmt = select(CompanyRegistry).order_by(CompanyRegistry.updated_at.desc()).limit(limit).offset(offset)
    if search:
        stmt = stmt.where(CompanyRegistry.legal_name.ilike(f"%{search}%"))

    res = await db.execute(stmt)
    return res.scalars().all()


class ToggleCompanyFlagPayload(BaseModel):
    is_flagged_scam: bool


@router.put("/companies/{company_id}/flag", dependencies=[Depends(_verify_admin_auth)])
async def toggle_company_flag(
    company_id: str,
    payload: ToggleCompanyFlagPayload,
    db: AsyncSession = Depends(get_db_session),
):
    """Menandai perusahaan sebagai scam / terverifikasi."""
    res = await db.execute(select(CompanyRegistry).where(CompanyRegistry.id == company_id))
    company = res.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Perusahaan tidak ditemukan.")

    company.is_flagged_scam = payload.is_flagged_scam
    await db.commit()
    await db.refresh(company)
    return company


@router.get("/blacklists", dependencies=[Depends(_verify_admin_auth)])
async def get_admin_blacklists(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
):
    """Melihat catatan intel blacklist kontak (telepon / email)."""
    stmt = select(IntelBlacklist).order_by(IntelBlacklist.last_reported_at.desc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/wa-sessions", dependencies=[Depends(_verify_admin_auth)])
async def get_admin_wa_sessions(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
):
    """Melihat state machine bot percakapan WhatsApp."""
    stmt = select(WaSession).order_by(WaSession.last_active_at.desc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    return res.scalars().all()
