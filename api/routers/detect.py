"""POST /v1/detect -- validasi payload HTTP, delegasikan ke detection_pipeline."""
from typing import Optional, Union

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Form, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, get_settings
from ..core.rate_limit import enforce_detect_rate_limit
from ..core.redis_client import get_redis_client
from ..core.validation import ensure_not_empty, validate_image
from ..db.base import get_db_session, async_session_factory
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


@router.post("/detect/stream", dependencies=[Depends(enforce_detect_rate_limit)])
async def detect_stream(
    text: Optional[str] = Form(default=None),
    company: Optional[str] = Form(default=None),
    email: Optional[str] = Form(default=None),
    phone: Optional[str] = Form(default=None),
    image: Union[UploadFile, str, None] = File(default=None),
    settings: Settings = Depends(get_settings),
    # NOTE: db is NOT injected here — the background task opens its own
    # session to prevent the GC connection-leak warning caused by the
    # session being released before the task finishes.
    redis_client: redis.Redis = Depends(get_redis_client),
):
    import asyncio
    import json
    from fastapi.responses import StreamingResponse

    if isinstance(image, str):
        image = None

    ensure_not_empty(text, company, email, phone, image=image)

    image_bytes = None
    if image is not None and image.filename:
        image_bytes = await validate_image(image, settings)

    queue = asyncio.Queue()

    async def _progress_callback(stage: str, message: str, percent: int):
        await queue.put({
            "type": "progress",
            "stage": stage,
            "message": message,
            "percent": percent,
        })

    async def _run_task():
        # Open a fresh, self-contained DB session scoped to this task.
        # This avoids the SQLAlchemy GC warning caused by the request-scoped
        # session being torn down before the background task finishes.
        async with async_session_factory() as task_db:
            try:
                ocr_text = None
                if image_bytes:
                    await _progress_callback("ocr", "Membaca teks dari gambar menggunakan RapidOCR...", 15)
                    from ..services.ocr import extract_text_from_image_bytes
                    ocr_text, _ = await asyncio.to_thread(extract_text_from_image_bytes, image_bytes)

                outcome = await run_detection_pipeline(
                    channel="web",
                    text=text,
                    ocr_text=ocr_text,
                    company=company,
                    phone=phone,
                    email=email,
                    db=task_db,
                    redis_client=redis_client,
                    settings=settings,
                    on_progress=_progress_callback,
                )
                await queue.put({
                    "type": "result",
                    "data": outcome.to_api_response(),
                })
            except Exception as e:
                await queue.put({
                    "type": "error",
                    "message": str(e) or "Terjadi kesalahan internal saat analisis.",
                })
            finally:
                await queue.put(None)  # Sentinel to finish generator

    asyncio.create_task(_run_task())

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


