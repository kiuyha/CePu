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
    reply = await handle_inbound_message(
        phone_hash=payload.phone_hash,
        msg_type=payload.msg.type,
        msg_body=payload.msg.body,
        db=db,
        redis_client=redis_client,
        settings=settings,
    )
    return {"reply": reply}