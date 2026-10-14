"""Test untuk modul router & repositori edukasi."""
import pytest
from httpx import AsyncClient

from api.db.base import async_session_factory
from api.db.repository import EducationArticleRepository


@pytest.mark.asyncio
async def test_education_articles_endpoints(client):
    # 1. Pastikan endpoint publik menghasilkan list artikel (sudah ter-seed saat startup)
    resp = client.get("/v1/education/articles")
    assert resp.status_code == 200
    articles = resp.json()
    assert isinstance(articles, list)
    assert len(articles) >= 3

    # 2. Ambil salah satu artikel berdasarkan slug
    first_slug = articles[0]["slug"]
    resp_detail = client.get(f"/v1/education/articles/{first_slug}")
    assert resp_detail.status_code == 200
    assert resp_detail.json()["slug"] == first_slug

    # 3. Admin list
    resp_admin = client.get("/v1/education/admin/articles")
    assert resp_admin.status_code == 200
    admin_list = resp_admin.json()
    assert len(admin_list) >= 3

    # 4. Admin create article baru
    new_payload = {
        "title": "Waspada Modus Kerja Paruh Waktu Freelance",
        "slug": "waspada-freelance-scam",
        "body_md": "## Modus Freelance\n\nJangan pernah mentransfer uang deposit.",
        "tags": ["freelance", "deposit"],
        "published": True,
    }
    resp_create = client.post("/v1/education/admin/articles", json=new_payload)
    assert resp_create.status_code == 201
    created_art = resp_create.json()
    assert created_art["slug"] == "waspada-freelance-scam"
    created_id = created_art["id"]

    # 5. Admin update article
    update_payload = {
        "title": "Waspada Modus Kerja Paruh Waktu Freelance (Revisi)",
        "slug": "waspada-freelance-scam",
        "body_md": "## Modus Freelance Update\n\nIsi artikel telah diperbarui.",
        "tags": ["freelance", "updated"],
        "published": True,
    }
    resp_update = client.put(f"/v1/education/admin/articles/{created_id}", json=update_payload)
    assert resp_update.status_code == 200
    assert resp_update.json()["title"] == "Waspada Modus Kerja Paruh Waktu Freelance (Revisi)"

    # 6. Admin delete article
    resp_delete = client.delete(f"/v1/education/admin/articles/{created_id}")
    assert resp_delete.status_code == 200

    # 7. Verifikasi artikel terhapus
    resp_not_found = client.get(f"/v1/education/articles/{created_id}")
    assert resp_not_found.status_code == 404
