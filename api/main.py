"""Entry point FastAPI. Jalankan: uvicorn api.main:app --reload --port 8000"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.errors import register_exception_handlers
from .db.base import init_models
from .routers import detect, health, internal_wa, reports
from .services.bert_infer import load_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    await load_model()  # gagal load tetap lanjut; /v1/detect akan 503 sampai model siap
    yield


app = FastAPI(
    title="CePu API",
    description="Sistem Deteksi dan Edukasi Dini Risiko Penipuan Lowongan Kerja",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: kunci ke domain website saat deploy
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(detect.router)
app.include_router(reports.router)
app.include_router(internal_wa.router)
