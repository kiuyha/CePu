"""Endpoints publik & admin untuk modul artikel edukasi anti-scam."""
from datetime import datetime, timezone
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.base import get_db_session
from ..db.repository import EducationArticleRepository

router = APIRouter(prefix="/v1/education", tags=["education"])


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "-", cleaned).strip("-")
    return slug or "artikel"


class ArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    title: str
    body_md: str
    tags: Optional[list[str]] = None
    published: bool
    published_at: Optional[datetime] = None


class ArticleCreateUpdatePayload(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    body_md: str = Field(..., min_length=10)
    slug: Optional[str] = Field(default=None, max_length=255)
    tags: Optional[list[str]] = Field(default_factory=list)
    published: bool = True


@router.get("/articles", response_model=list[ArticleResponse])
async def list_published_articles(
    db: AsyncSession = Depends(get_db_session),
):
    """Endpoint publik untuk membaca artikel edukasi yang terbit."""
    repo = EducationArticleRepository(db)
    articles = await repo.list_published(limit=50)
    return articles


@router.get("/articles/{slug_or_id}", response_model=ArticleResponse)
async def get_single_article(
    slug_or_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Membaca detail 1 artikel berdasarkan slug atau ID."""
    repo = EducationArticleRepository(db)
    article = await repo.get_by_slug(slug_or_id)
    if not article:
        article = await repo.get_by_id(slug_or_id)

    if not article:
        raise HTTPException(status_code=404, detail="Artikel tidak ditemukan.")
    return article


# ==============================================================================
# ADMIN ENDPOINTS (Bisa dipanggil oleh interface /admin)
# ==============================================================================

@router.get("/admin/articles", response_model=list[ArticleResponse])
async def admin_list_articles(
    db: AsyncSession = Depends(get_db_session),
):
    """Daftar seluruh artikel (termasuk draft/unpublished) untuk halaman admin."""
    repo = EducationArticleRepository(db)
    return await repo.list_all()


@router.post("/admin/articles", response_model=ArticleResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_article(
    payload: ArticleCreateUpdatePayload,
    db: AsyncSession = Depends(get_db_session),
):
    """Membuat artikel edukasi baru."""
    repo = EducationArticleRepository(db)
    slug = (payload.slug or "").strip() or _slugify(payload.title)

    existing = await repo.get_by_slug(slug)
    if existing:
        slug = f"{slug}-{int(datetime.now(timezone.utc).timestamp())}"

    article = await repo.upsert_by_slug(
        slug=slug,
        title=payload.title.strip(),
        body_md=payload.body_md,
        tags=payload.tags or [],
        published=payload.published,
    )
    return article


@router.put("/admin/articles/{article_id}", response_model=ArticleResponse)
async def admin_update_article(
    article_id: str,
    payload: ArticleCreateUpdatePayload,
    db: AsyncSession = Depends(get_db_session),
):
    """Memperbarui artikel yang ada."""
    repo = EducationArticleRepository(db)
    slug = (payload.slug or "").strip() or _slugify(payload.title)

    article = await repo.update(
        article_id=article_id,
        title=payload.title.strip(),
        slug=slug,
        body_md=payload.body_md,
        tags=payload.tags or [],
        published=payload.published,
    )
    if not article:
        raise HTTPException(status_code=404, detail="Artikel tidak ditemukan.")
    return article


@router.delete("/admin/articles/{article_id}")
async def admin_delete_article(
    article_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Menghapus artikel edukasi."""
    repo = EducationArticleRepository(db)
    deleted = await repo.delete(article_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Artikel tidak ditemukan.")
    return {"message": "Artikel berhasil dihapus.", "id": article_id}
