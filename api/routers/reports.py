"""POST /v1/reports -- laporan lowongan mencurigakan dari pengguna."""
from typing import Optional, Union

from fastapi import APIRouter, Depends, Form, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, get_settings
from ..core.rate_limit import enforce_report_rate_limit
from ..core.validation import ensure_not_empty, validate_image
from ..db.base import get_db_session
from ..db.repository import ReportRepository

router = APIRouter(prefix="/v1", tags=["reports"])


@router.post("/reports", dependencies=[Depends(enforce_report_rate_limit)])
async def create_report(
    contact_optional: Optional[str] = Form(default=None),
    suspect_phone: Optional[str] = Form(default=None),
    suspect_email: Optional[str] = Form(default=None),
    suspect_company: Optional[str] = Form(default=None),
    message_raw: Optional[str] = Form(default=None),
    screenshot: Union[UploadFile, str, None] = File(default=None),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db_session),
):
    if isinstance(screenshot, str):
        screenshot = None

    ensure_not_empty(suspect_phone, suspect_email, suspect_company, message_raw, image=screenshot)

    screenshot_path = None
    if screenshot is not None and screenshot.filename:
        await validate_image(screenshot, settings)
        # TODO: upload ke storage sungguhan
        screenshot_path = f"pending-upload/{screenshot.filename}"

    repo = ReportRepository(db)
    report = await repo.create(
        channel="web",
        contact_optional=contact_optional,
        suspect_phone=suspect_phone,
        suspect_email=suspect_email,
        suspect_company=suspect_company,
        message_raw=message_raw,
        screenshot_path=screenshot_path,
        status="pending",
    )

    return {"id": report.id, "status": report.status}
