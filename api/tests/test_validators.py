"""
Test untuk validator paralel: DNS MX (real), blacklist (real, pakai DB),
base timeout+retry, dan orchestrator (integrasi semuanya + mock AHU/LinkedIn).
"""
import asyncio

import pytest

from api.services.validators.base import ValidatorUnavailable, call_with_retry
from api.services.validators.dns_mx import check_email_mx
from api.services.validators.blacklist import check_blacklist
from api.services.validators.ahu import check_company_ahu
from api.services.validators.linkedin import check_company_linkedin
from api.services.validators.orchestrator import run_validators
from api.db.base import async_session_factory
from api.db.repository import ReportRepository
from api.core.cache import VerificationCache


# ---------- base.py: call_with_retry ----------

async def test_call_with_retry_returns_result_on_success():
    async def ok():
        return "berhasil"

    result = await call_with_retry(ok, source="test")
    assert result == "berhasil"


async def test_call_with_retry_raises_validator_unavailable_after_retry_fails():
    call_count = 0

    async def always_fails():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("simulasi gagal")

    with pytest.raises(ValidatorUnavailable):
        await call_with_retry(always_fails, source="test", retry_delay=0.01)

    # Harus dicoba 2x (percobaan pertama + 1x retry), bukan cuma sekali
    assert call_count == 2


async def test_call_with_retry_times_out_correctly():
    async def too_slow():
        await asyncio.sleep(5)
        return "harusnya tidak pernah sampai sini"

    with pytest.raises(ValidatorUnavailable):
        await call_with_retry(too_slow, source="test", timeout=0.05, retry_delay=0.01)


async def test_call_with_retry_succeeds_on_second_attempt():
    """Percobaan pertama gagal, retry-nya berhasil -- harus return hasil retry."""
    attempt = 0

    async def fails_once_then_succeeds():
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            raise RuntimeError("gagal di percobaan pertama")
        return "berhasil di retry"

    result = await call_with_retry(fails_once_then_succeeds, source="test", retry_delay=0.01)
    assert result == "berhasil di retry"
    assert attempt == 2


# ---------- dns_mx.py: validator ASLI ----------

async def test_check_email_mx_valid_domain_returns_low_score():
    """gmail.com pasti punya MX record."""
    result = await check_email_mx("siapa@gmail.com")
    assert result.verdict_binary is False  # False = tidak bermasalah
    assert result.verdict_score < 0.5


async def test_check_email_mx_invalid_domain_returns_high_score():
    result = await check_email_mx("siapa@domain-ngasal-tidak-ada-xyz123.com")
    assert result.verdict_binary is True  # True = bermasalah
    assert result.verdict_score > 0.5


async def test_check_email_mx_malformed_email_returns_high_score():
    result = await check_email_mx("bukan-email-valid")
    assert result.verdict_binary is True
    assert result.verdict_score > 0.5


async def test_check_email_disposable_domain_returns_penalty():
    result = await check_email_mx("recruitment@yopmail.com")
    assert result.verdict_binary is True
    assert result.verdict_score == 0.95


async def test_check_email_domain_similarity_impersonation_flagged():
    # Perusahaan Tokopedia, tapi email menggunakan subdomain / hyphen lookalike
    result = await check_email_mx("hrd@tokopedia-recruitment.com", company_name="PT Tokopedia")
    assert result.verdict_binary is True
    assert result.verdict_score == 0.85


async def test_check_email_corporate_entity_using_free_webmail_flagged():
    # Mengaku PT formal tapi pakai @gmail.com
    result = await check_email_mx("recruitment@gmail.com", company_name="PT Maju Makmur")
    assert result.verdict_binary is True
    assert result.verdict_score == 0.70


async def test_check_email_disposable_domain_from_database(client):
    from api.db.models import DisposableDomain
    async with async_session_factory() as session:
        session.add(DisposableDomain(domain="custom-disposable-xyz.org", source="test"))
        await session.commit()

        result = await check_email_mx("test@custom-disposable-xyz.org", db=session)
        assert result.verdict_binary is True
        assert result.verdict_score == 0.95


async def test_sync_disposable_domains_service(monkeypatch, client):
    from api.services.disposable_sync import sync_disposable_domains_from_github
    from api.db.repository import DisposableDomainRepository

    class FakeResponse:
        status_code = 200
        text = "# Sample blocklist\nfake-disposable1.com\nfake-disposable2.com\n"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    async with async_session_factory() as session:
        added = await sync_disposable_domains_from_github(session)
        assert added >= 2

        repo = DisposableDomainRepository(session)
        assert await repo.is_disposable("fake-disposable1.com") is True
        assert await repo.is_disposable("fake-disposable2.com") is True


# ---------- blacklist.py: validator ASLI (pakai DB) ----------

async def test_check_blacklist_phone_not_reported_returns_low_score(client):
    async with async_session_factory() as session:
        result = await check_blacklist("phone", "081299999999", session)
    assert result.verdict_binary is False
    assert result.verdict_score < 0.5


async def test_check_blacklist_phone_reported_twice_returns_high_score(client):
    phone = "081288888888"
    async with async_session_factory() as session:
        report_repo = ReportRepository(session)
        await report_repo.create(
            channel="web", suspect_phone=phone, message_raw="modus 1", status="verified_scam"
        )
        await report_repo.create(
            channel="web", suspect_phone=phone, message_raw="modus 2", status="verified_scam"
        )

    async with async_session_factory() as session:
        result = await check_blacklist("phone", phone, session)

    assert result.verdict_binary is True
    assert result.verdict_score > 0.5


async def test_check_blacklist_caches_result_in_intel_blacklist_table(client):
    """Panggilan kedua harus lebih cepat karena sudah ada di intel_blacklist."""
    from api.db.repository import IntelBlacklistRepository

    phone = "081277777777"
    async with async_session_factory() as session:
        await check_blacklist("phone", phone, session)

    async with async_session_factory() as session:
        repo = IntelBlacklistRepository(session)
        entry = await repo.get("phone", phone)

    assert entry is not None


# ---------- ahu.py & linkedin.py: mock, selalu netral ----------

async def test_mock_ahu_always_returns_neutral():
    result = await check_company_ahu("PT Apapun Saja")
    assert result.verdict_score == 0.5
    assert result.verdict_binary is None
    assert result.source == "companyhouse.id"



async def test_mock_linkedin_always_returns_neutral():
    result = await check_company_linkedin("PT Apapun Saja")
    assert result.verdict_score == 0.5
    assert result.source == "mock_linkedin"


# ---------- orchestrator.py: integrasi penuh ----------

async def test_run_validators_with_all_fields_provided(client, fake_redis):
    cache = VerificationCache(fake_redis)
    async with async_session_factory() as session:
        output = await run_validators(
            company="PT Sejahtera Abadi",
            phone="081266666666",
            email="test@gmail.com",
            db=session,
            cache=cache,
        )

    assert 0.0 <= output.v_company <= 1.0
    assert 0.0 <= output.v_phone <= 1.0
    assert 0.0 <= output.v_email <= 1.0
    # gmail.com valid -> tidak ada di degraded_sources untuk dns_mx
    assert "dns_mx" not in output.degraded_sources


async def test_run_validators_with_no_fields_returns_neutral_and_not_degraded(client, fake_redis):
    """Kalau tidak ada company/phone/email sama sekali, semua netral, TIDAK degraded."""
    cache = VerificationCache(fake_redis)
    async with async_session_factory() as session:
        output = await run_validators(
            company=None, phone=None, email=None, db=session, cache=cache
        )

    assert output.v_company == 0.5
    assert output.v_phone == 0.5
    assert output.v_email == 0.5
    assert output.degraded_sources == []


async def test_run_validators_combines_ahu_linkedin_and_registry_for_v_company(client, fake_redis):
    """
    Karena AHU dan LinkedIn mock netral (0.5), dan company_registry juga
    netral untuk perusahaan yang belum pernah di-seed (0.5), V_company
    harus tetap 0.5 (rata-rata dari tiga angka 0.5).
    """
    cache = VerificationCache(fake_redis)
    async with async_session_factory() as session:
        output = await run_validators(
            company="PT Belum Pernah Terdaftar", phone=None, email=None, db=session, cache=cache
        )

    assert output.v_company == 0.5


async def test_run_validators_v_company_lower_when_company_registered(client, fake_redis):
    """
    Kalau perusahaan ADA di company_registry (registered=True), V_company
    harus lebih rendah dari 0.5 (lebih dipercaya) dibanding yang tidak
    ditemukan sama sekali -- walau AHU+LinkedIn masih netral.
    """
    from api.db.repository import CompanyRegistryRepository

    async with async_session_factory() as session:
        repo = CompanyRegistryRepository(session)
        await repo.upsert("PT Sudah Terverifikasi", registered=True, source="scraped_real_postings")

    cache = VerificationCache(fake_redis)
    async with async_session_factory() as session:
        output = await run_validators(
            company="PT Sudah Terverifikasi", phone=None, email=None, db=session, cache=cache
        )

    assert output.v_company < 0.5


async def test_run_validators_uses_cache_when_source_fails(client, fake_redis, monkeypatch):
    """
    Simulasi: sumber eksternal gagal total, tapi cache SUDAH punya data
    dari panggilan sebelumnya -- harus pakai cache, BUKAN degraded.
    """
    cache = VerificationCache(fake_redis)
    await cache.set(
        "email",
        "cached@example.com",
        verdict_score=0.2,
        verdict_binary=False,
        source="dns_mx",
        cache_source_key="dns_mx",  # cocok sama cara orchestrator simpan cache untuk kind="email"
    )

    async def always_fail(email):
        raise RuntimeError("simulasi DNS server down")

    monkeypatch.setattr(
        "api.services.validators.orchestrator.check_email_mx", always_fail
    )

    async with async_session_factory() as session:
        output = await run_validators(
            company=None, phone=None, email="cached@example.com", db=session, cache=cache
        )

    assert output.v_email == 0.2
    assert "dns_mx" not in output.degraded_sources  # pakai cache, bukan degraded


async def test_run_validators_marks_degraded_when_source_fails_and_cache_empty(
    client, fake_redis, monkeypatch
):
    """Sumber gagal DAN cache kosong -> harus masuk degraded_sources."""
    cache = VerificationCache(fake_redis)

    async def always_fail(email):
        raise RuntimeError("simulasi DNS server down")

    monkeypatch.setattr(
        "api.services.validators.orchestrator.check_email_mx", always_fail
    )

    async with async_session_factory() as session:
        output = await run_validators(
            company=None,
            phone=None,
            email="belumadadicache@example.com",
            db=session,
            cache=cache,
        )

    assert output.v_email == 0.5  # nilai netral
    assert "dns_mx" in output.degraded_sources
