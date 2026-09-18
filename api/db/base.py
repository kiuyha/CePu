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
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif "+asyncpg" in settings.sqlalchemy_db_url:
    _engine_kwargs["connect_args"] = {"statement_cache_size": 0}
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.sqlalchemy_db_url, **_engine_kwargs)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


async def init_models() -> None:
    """Buat semua tabel jika belum ada. TODO: ganti Alembic migration untuk production."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
