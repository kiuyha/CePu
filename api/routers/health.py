"""GET /healthz -- status layanan dan model."""
from fastapi import APIRouter, Depends

from ..core.config import Settings, get_settings
from ..services.bert_infer import get_load_error, is_model_loaded

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(settings: Settings = Depends(get_settings)):
    loaded = is_model_loaded()
    response = {
        "status": "ok" if loaded else "degraded",
        "model_loaded": loaded,
        "model_version": settings.model_version,
    }
    if not loaded:
        load_error = get_load_error()
        if load_error:
            response["model_load_error"] = load_error
    return response
