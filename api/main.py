"""Entry point FastAPI. Jalankan: uvicorn api.main:app --reload --port 8000"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.errors import register_exception_handlers
from .db.base import async_session_factory, init_models
from .routers import admin_portal, detect, education, health, internal_wa, jobs, reports
from .services.bert_infer import load_model
from .services.disposable_sync import sync_disposable_domains_from_github
from .services.education_seed import seed_initial_education_articles

logger = logging.getLogger(__name__)


async def _sync_disposable_domains_background() -> None:
    """Sinkronisasi domain disposable di background saat startup tanpa memblokir server."""
    try:
        async with async_session_factory() as db:
            count = await sync_disposable_domains_from_github(db)
            logger.info(
                "Startup: disposable domain sync selesai, %d domain baru ditambahkan.", count
            )
    except Exception as exc:
        logger.warning("Startup: disposable domain sync gagal (non-fatal): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    # Seed artikel edukasi jika tabel masih kosong
    try:
        async with async_session_factory() as db:
            await seed_initial_education_articles(db)
    except Exception as exc:
        logger.warning("Startup: seed education articles gagal: %s", exc)

    await load_model()  # gagal load tetap lanjut; /v1/detect akan 503 sampai model siap
    # Jalankan sync disposable domains di background tanpa memblokir startup
    asyncio.create_task(_sync_disposable_domains_background())
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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(detect.router)
app.include_router(reports.router)
app.include_router(internal_wa.router)
app.include_router(education.router)
app.include_router(admin_portal.router)
app.include_router(jobs.router)
