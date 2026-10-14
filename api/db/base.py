"""Setup koneksi database SQLAlchemy async (SQLite dev, Postgres production)."""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from ..core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

_engine_kwargs = {"echo": False}

if settings.sqlalchemy_db_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30.0}
elif "+asyncpg" in settings.sqlalchemy_db_url:
    _engine_kwargs["connect_args"] = {"statement_cache_size": 0}
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.sqlalchemy_db_url, **_engine_kwargs)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


async def init_models() -> None:
    """Buat semua tabel jika belum ada. Aktifkan WAL mode untuk SQLite agar mendukung konkurensi."""
    async with engine.begin() as conn:
        if settings.sqlalchemy_db_url.startswith("sqlite"):
            from sqlalchemy import text
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;"))
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_job_alternatives_columns(conn)


async def _ensure_job_alternatives_columns(conn) -> None:
    """Migrasi ringan: create_all tidak menambah kolom ke tabel lama.

    Tambahkan kolom hasil scraper (role/location/salary_display) jika belum ada,
    agar database lama tetap kompatibel tanpa alembic.
    """
    from sqlalchemy import text

    wanted = {
        "role": "VARCHAR(100)",
        "location": "VARCHAR(255)",
        "salary_display": "VARCHAR(255)",
    }
    is_sqlite = settings.sqlalchemy_db_url.startswith("sqlite")

    if is_sqlite:
        existing = {
            row[1]
            for row in (await conn.execute(text("PRAGMA table_info(job_alternatives)"))).all()
        }
    else:
        existing = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'job_alternatives'"
                    )
                )
            ).all()
        }

    for col, ddl in wanted.items():
        if col in existing:
            continue
        if is_sqlite:
            await conn.execute(text(f"ALTER TABLE job_alternatives ADD COLUMN {col} {ddl}"))
        else:
            await conn.execute(
                text(f"ALTER TABLE job_alternatives ADD COLUMN IF NOT EXISTS {col} {ddl}")
            )
