from api.core.company_normalize import normalize_company_name
from api.db.base import async_session_factory
from api.db.repository import CompanyRegistryRepository
from api.services.validators.company_registry import check_company_registry


# ---------- normalize_company_name ----------

def test_normalize_strips_pt_prefix():
    assert normalize_company_name("PT Sejahtera Abadi") == "sejahtera abadi"


def test_normalize_strips_cv_prefix():
    assert normalize_company_name("CV Maju Jaya") == "maju jaya"


def test_normalize_strips_tbk_suffix():
    assert normalize_company_name("PT Kimia Farma Tbk") == "kimia farma"


def test_normalize_is_case_insensitive():
    assert normalize_company_name("pt SEJAHTERA abadi") == normalize_company_name(
        "PT Sejahtera Abadi"
    )


def test_normalize_handles_dots():
    assert normalize_company_name("PT. Kimia Farma (Persero) Tbk.") == "kimia farma (persero)"


# ---------- CompanyRegistryRepository ----------

async def test_company_registry_upsert_then_get_by_name(client):
    async with async_session_factory() as session:
        repo = CompanyRegistryRepository(session)
        await repo.upsert("PT Sejahtera Abadi", registered=True, source="scraped_real_postings")

    async with async_session_factory() as session:
        repo = CompanyRegistryRepository(session)
        entry = await repo.get_by_name("PT Sejahtera Abadi")

    assert entry is not None
    assert entry.registered is True
    assert entry.source == "scraped_real_postings"


async def test_company_registry_matches_despite_different_casing_and_prefix(client):
    """Variasi penulisan (huruf besar/kecil, ada/tidaknya titik) harus tetap match."""
    async with async_session_factory() as session:
        repo = CompanyRegistryRepository(session)
        await repo.upsert("PT. Sejahtera Abadi", registered=True, source="scraped_real_postings")

    async with async_session_factory() as session:
        repo = CompanyRegistryRepository(session)
        entry = await repo.get_by_name("pt sejahtera abadi")  # beda kapitalisasi & tanpa titik

    assert entry is not None


async def test_company_registry_upsert_is_idempotent(client):
    """Upsert nama yang sama dua kali tidak boleh bikin dua baris."""
    async with async_session_factory() as session:
        repo = CompanyRegistryRepository(session)
        await repo.upsert("PT Idempoten", registered=True, source="scraped_real_postings")
        await repo.upsert("PT Idempoten", registered=True, source="scraped_real_postings")

    async with async_session_factory() as session:
        from sqlalchemy import select
        from api.db.models import CompanyRegistry

        result = await session.execute(
            select(CompanyRegistry).where(CompanyRegistry.legal_name == "PT Idempoten")
        )
        rows = result.scalars().all()

    assert len(rows) == 1


# ---------- check_company_registry validator ----------

async def test_check_company_registry_found_and_registered_returns_low_score(client):
    async with async_session_factory() as session:
        repo = CompanyRegistryRepository(session)
        await repo.upsert("PT Terdaftar Jaya", registered=True, source="scraped_real_postings")

    async with async_session_factory() as session:
        result = await check_company_registry("PT Terdaftar Jaya", session)

    assert result.verdict_binary is False
    assert result.verdict_score < 0.5


async def test_check_company_registry_not_found_returns_neutral_not_suspicious(client):
    """
    PENTING: tidak ditemukan HARUS netral, bukan mencurigakan -- data
    registry ini jauh dari lengkap, jadi banyak perusahaan asli yang sah
    pun wajar tidak ada di sini.
    """
    async with async_session_factory() as session:
        result = await check_company_registry("PT Tidak Pernah Terdaftar Sama Sekali", session)

    assert result.verdict_binary is None
    assert result.verdict_score == 0.5


async def test_check_company_registry_flagged_scam_returns_high_score(client):
    async with async_session_factory() as session:
        repo = CompanyRegistryRepository(session)
        await repo.upsert("PT Modus Penipuan", is_flagged_scam=True, source="manual_review")

    async with async_session_factory() as session:
        result = await check_company_registry("PT Modus Penipuan", session)

    assert result.verdict_binary is True
    assert result.verdict_score > 0.5
