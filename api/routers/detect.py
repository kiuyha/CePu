"""POST /v1/detect -- validasi payload HTTP, delegasikan ke detection_pipeline."""
from typing import Optional, Union

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Form, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, get_settings
from ..core.rate_limit import enforce_detect_rate_limit
from ..core.redis_client import get_redis_client
from ..core.validation import ensure_not_empty, validate_image
from ..db.base import get_db_session
from ..services.detection_pipeline import run_detection_pipeline

router = APIRouter(prefix="/v1", tags=["detect"])


@router.post("/detect", dependencies=[Depends(enforce_detect_rate_limit)])
async def detect(
    text: Optional[str] = Form(default=None),
    company: Optional[str] = Form(default=None),
    email: Optional[str] = Form(default=None),
    phone: Optional[str] = Form(default=None),
    # Union[UploadFile, str, None]: Swagger UI mengirim "" saat file kosong,
    # bukan benar-benar tidak ada field-nya.
    image: Union[UploadFile, str, None] = File(default=None),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db_session),
    redis_client: redis.Redis = Depends(get_redis_client),
):
    if isinstance(image, str):
        image = None

    ensure_not_empty(text, company, email, phone, image=image)

    image_bytes = None
    ocr_text = None
    if image is not None and image.filename:
        image_bytes = await validate_image(image, settings)
        try:
            import asyncio
            from ..services.ocr import extract_text_from_image_bytes

            ocr_text, _ = await asyncio.to_thread(extract_text_from_image_bytes, image_bytes)
        except Exception:
            ocr_text = None

    outcome = await run_detection_pipeline(
        channel="web",
        text=text,
        ocr_text=ocr_text,
        company=company,
        phone=phone,
        email=email,
        db=db,
        redis_client=redis_client,
        settings=settings,
    )

    return outcome.to_api_response()

