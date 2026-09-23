"""POST /internal/wa/inbound -- satu-satunya endpoint yang diakses gateway WhatsApp."""
from typing import Optional

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, get_settings
from ..core.errors import InvalidInternalTokenError
from ..core.redis_client import get_redis_client
from ..db.base import get_db_session
from ..services.wa_bot import handle_inbound_message

router = APIRouter(prefix="/internal/wa", tags=["internal-wa"])


class WaMessage(BaseModel):
    type: str  # "text" | "image"
    body: str


class WaInboundPayload(BaseModel):
    phone_hash: str
    msg: WaMessage
    stream: bool = False


def _verify_internal_token(
    x_internal_token: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if x_internal_token != settings.internal_token:
        raise InvalidInternalTokenError("Header X-Internal-Token tidak valid atau tidak ada.")


@router.post("/inbound", dependencies=[Depends(_verify_internal_token)])
async def wa_inbound(
    payload: WaInboundPayload,
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db_session),
    redis_client: redis.Redis = Depends(get_redis_client),
):
    if not payload.stream:
        reply = await handle_inbound_message(
            phone_hash=payload.phone_hash,
            msg_type=payload.msg.type,
            msg_body=payload.msg.body,
            db=db,
            redis_client=redis_client,
            settings=settings,
        )
        return {"reply": reply}

    # Streaming mode for WhatsApp gateway
    import asyncio
    import json
    from fastapi.responses import StreamingResponse

    queue = asyncio.Queue()

    async def _progress_callback(stage: str, message: str, percent: int):
        await queue.put({
            "type": "progress",
            "stage": stage,
            "message": message,
            "percent": percent,
        })

    async def _worker():
        try:
            reply = await handle_inbound_message(
                phone_hash=payload.phone_hash,
                msg_type=payload.msg.type,
                msg_body=payload.msg.body,
                db=db,
                redis_client=redis_client,
                settings=settings,
                on_progress=_progress_callback,
            )
            await queue.put({"type": "result", "reply": reply})
        except Exception as e:
            await queue.put({"type": "error", "message": str(e)})
        finally:
            await queue.put(None)

    asyncio.create_task(_worker())

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