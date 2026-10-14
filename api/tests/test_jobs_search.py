"""Test GET /v1/jobs/search: DB-first, persist hasil scrape, dan WA memakai DB.

Scraper asli tidak dipanggil (monkeypatch) — yang diuji adalah alur
simpan -> sajikan dari DB tanpa fetch ulang.
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import text

from api.core.config import get_settings
from api.db.base import async_session_factory
from api.db.models import JobAlternative
from api.db.repository import JobAlternativeRepository

SETTINGS = get_settings()


@pytest.fixture(autouse=True)
async def _clean_alternatives(client):
    """Isolasi antar-test: tabel job_alternatives dipakai bersama satu file DB.

    Bergantung pada `client` agar startup (init_models) sudah membuat tabel.
    """
    async with async_session_factory() as session:
        await session.execute(text("DELETE FROM job_alternatives"))
        await session.commit()
    yield
    async with async_session_factory() as session:
        await session.execute(text("DELETE FROM job_alternatives"))
        await session.commit()

FAKE_JOBS = [
    {
        "id": "111",
        "title": "Driver Operasional",
        "company": "PT Maju Jaya",
        "location": "Jakarta",
        "salary_min": 5000000,
        "salary_max": 7000000,
        "salary_currency": "IDR",
        "salary_display": "Rp 5–7 jt",
        "work_type": "Full time",
        "listed_at": None,
        "listed_label": None,
        "url": "https://id.jobstreet.com/job/111",
    },
    {
        "id": "222",
        "title": "Driver Pribadi",
        "company": "Budi",
        "location": "Bandung",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_display": None,
        "work_type": "",
        "listed_at": None,
        "listed_label": None,
        "url": "https://id.jobstreet.com/job/222",
    },
]


@pytest.fixture()
def fake_scraper(monkeypatch):
    calls = {"n": 0}

    def _fake_search(self, role, location_text=None, page=1, page_size=10):
        calls["n"] += 1
        assert page == 1, "scrape harus selalu SATU halaman (page=1)"
        return [dict(j) for j in FAKE_JOBS]

    monkeypatch.setattr(
        "api.services.job_service.JobStreetScraper.search_jobs", _fake_search
    )
    return calls


def test_search_pertama_scrape_lalu_tersimpan(client, fake_scraper):
    resp = client.get("/v1/jobs/search", params={"role": "driver"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "live"
    assert data["count"] == 2
    urls = {j["url"] for j in data["jobs"]}
    assert urls == {
        "https://id.jobstreet.com/job/111",
        "https://id.jobstreet.com/job/222",
    }
    assert fake_scraper["n"] == 1


async def test_hasil_scrape_benar_benar_di_db(client, fake_scraper):
    client.get("/v1/jobs/search", params={"role": "driver"})
    async with async_session_factory() as session:
        repo = JobAlternativeRepository(session)
        rows = await repo.search("driver", limit=10)
    assert len(rows) == 2
    assert all(isinstance(r, JobAlternative) for r in rows)
    assert rows[0].verified_source == "jobstreet"
    assert rows[0].role == "driver"


def test_search_kedua_tanpa_fetch_ulang(client, fake_scraper, monkeypatch):
    client.get("/v1/jobs/search", params={"role": "driver"})
    assert fake_scraper["n"] == 1

    # Scraper dirusak total — kalau kode fetch ulang, request ini gagal.
    def _boom(self, *a, **k):
        raise AssertionError("tidak boleh scrape ulang kalau DB sudah ada")

    monkeypatch.setattr("api.services.job_service.JobStreetScraper.search_jobs", _boom)
    resp = client.get("/v1/jobs/search", params={"role": "driver"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "db"
    assert data["count"] == 2


def test_search_bisa_filter_lokasi_dan_judul(client, fake_scraper):
    client.get("/v1/jobs/search", params={"role": "driver"})
    resp = client.get("/v1/jobs/search", params={"role": "driver", "location": "bandung"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["jobs"][0]["title"] == "Driver Pribadi"


def test_wa_cari_kerja_memakai_db_dan_format_sederhana(client, fake_scraper, monkeypatch):
    # Seed DB dulu lewat endpoint
    client.get("/v1/jobs/search", params={"role": "driver"})
    # Matikan scraper: WA wajib jawab dari DB
    monkeypatch.setattr(
        "api.services.job_service.JobStreetScraper.search_jobs",
        lambda self, *a, **k: (_ for _ in ()).throw(AssertionError("WA tidak boleh scrape ulang")),
    )
    resp = client.post(
        "/internal/wa/inbound",
        json={"phone_hash": "wa-jobs-db-test", "msg": {"type": "text", "body": "cari kerja driver"}},
        headers={"X-Internal-Token": SETTINGS.internal_token},
    )
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    assert "Driver Operasional" in reply
    assert "https://id.jobstreet.com/job/111" in reply
    # Format sederhana: tanpa baris gaji/lokasi
    assert "💰" not in reply
    assert "📍" not in reply


async def _backdate_jobstreet(hours: int):
    # NB: pakai assignment ORM (bukan bulk update) agar tipe DateTime
    # diproses driver dengan benar.
    async with async_session_factory() as session:
        repo = JobAlternativeRepository(session)
        rows = await repo.search("driver", limit=30)
        for row in rows:
            row.captured_at = datetime.now(timezone.utc) - timedelta(hours=hours)
        await session.commit()


async def test_data_basi_melewati_ttl_memmicu_scrape_ulang(client, fake_scraper):
    client.get("/v1/jobs/search", params={"role": "driver"})
    assert fake_scraper["n"] == 1
    await _backdate_jobstreet(25)
    resp = client.get("/v1/jobs/search", params={"role": "driver"})
    assert resp.status_code == 200
    assert resp.json()["source"] == "live"
    assert fake_scraper["n"] == 2


async def test_scrape_gagal_sajikan_data_basi_daripada_kosong(
    client, fake_scraper, monkeypatch
):
    client.get("/v1/jobs/search", params={"role": "driver"})
    await _backdate_jobstreet(25)
    monkeypatch.setattr(
        "api.services.job_service.JobStreetScraper.search_jobs",
        lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("jaringan mati")),
    )
    resp = client.get("/v1/jobs/search", params={"role": "driver"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "db"
    assert data["count"] == 2


async def test_prune_hanya_menghapus_jobstreet_basi(client, fake_scraper):
    async with async_session_factory() as session:
        session.add(
            JobAlternative(
                company="PT Kurasi",
                title="Admin",
                url="https://manual/1",
                verified_source="manual",
                captured_at=datetime.now(timezone.utc) - timedelta(hours=100),
            )
        )
        await session.commit()
    client.get("/v1/jobs/search", params={"role": "driver"})
    await _backdate_jobstreet(25)
    client.get("/v1/jobs/search", params={"role": "driver"})
    async with async_session_factory() as session:
        from sqlalchemy import select

        manual_urls = (
            await session.execute(
                select(JobAlternative.url).where(JobAlternative.url == "https://manual/1")
            )
        ).all()
        assert [r[0] for r in manual_urls] == ["https://manual/1"]
        repo = JobAlternativeRepository(session)
        fresh = await repo.search("driver", limit=10)
    assert len(fresh) == 2
    now = datetime.now(timezone.utc)
    for row in fresh:
        captured = row.captured_at
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        assert (now - captured) < timedelta(hours=1)
