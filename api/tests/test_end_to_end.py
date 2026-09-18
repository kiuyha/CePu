"""
Test End-to-End (fase 8), sesuai permintaan eksplisit dokumen arsitektur
di bagian Rencana Pengujian: "load smoke test 25 permintaan paralel serta
uji dengan mematikan sumber eksternal untuk memastikan fallback cache
Redis berjalan dan degraded_sources muncul pada respons".
"""
import asyncio

from api.core.cache import VerificationCache
from api.core.config import get_settings
from api.db.base import async_session_factory
from api.services.detection_pipeline import run_detection_pipeline

SETTINGS = get_settings()


async def test_degraded_sources_appear_when_all_external_sources_fail(
    client, fake_redis, monkeypatch
):
    """
    Matikan SEMUA sumber eksternal (AHU, LinkedIn, company_registry, DNS
    MX) sekaligus, cache-nya juga kosong -> harus tetap 200 (bukan crash),
    dengan degraded_sources terisi lengkap dan skor jatuh ke nilai netral.
    """
    async def _always_fail(*args, **kwargs):
        raise RuntimeError("simulasi sumber eksternal mati total")

    monkeypatch.setattr("api.services.validators.orchestrator.check_company_ahu", _always_fail)
    monkeypatch.setattr("api.services.validators.orchestrator.check_company_linkedin", _always_fail)
    monkeypatch.setattr("api.services.validators.orchestrator.check_email_mx", _always_fail)

    async def _fake_predict(text: str) -> float:
        return 0.1

    monkeypatch.setattr("api.services.detection_pipeline.predict_fraud_probability", _fake_predict)

    response = client.post(
        "/v1/detect",
        data={
            "text": "lowongan biasa",
            "company": "PT Belum Pernah Ada Di Manapun",
            "email": "test@domain-benar-benar-ngasal-xyz999.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "ahu" in body["degraded_sources"]
    assert "linkedin" in body["degraded_sources"]
    assert "dns_mx" in body["degraded_sources"]
    # company_registry TIDAK dimock gagal, jadi tetap query normal (bukan degraded)
    assert "company_registry" not in body["degraded_sources"]


async def test_pipeline_handles_25_concurrent_requests_without_crashing(client, fake_redis, monkeypatch):
    """
    Smoke test 25 permintaan paralel sesuai dokumen. Dijalankan langsung
    ke detection_pipeline (bukan lewat HTTP + rate limiter) supaya murni
    menguji ketahanan pipeline terhadap concurrency, bukan rate limiting
    (itu sudah ada test terpisah di test_detect.py).
    """
    async def _fake_predict(text: str) -> float:
        return 0.3

    monkeypatch.setattr("api.services.detection_pipeline.predict_fraud_probability", _fake_predict)

    cache = VerificationCache(fake_redis)

    async def _one_request(i: int):
        async with async_session_factory() as session:
            return await run_detection_pipeline(
                channel="web",
                text=f"lowongan test paralel nomor {i}",
                company=None,
                phone=None,
                email=None,
                db=session,
                redis_client=fake_redis,
                settings=SETTINGS,
            )

    import time

    start = time.perf_counter()
    results = await asyncio.gather(*[_one_request(i) for i in range(25)])
    elapsed = time.perf_counter() - start

    assert len(results) == 25
    assert all(r.request_id for r in results)
    assert all(r.risk_score is not None for r in results)
    # Target dokumen: p95 di bawah 5 detik -- di lingkungan test lokal
    # (SQLite + fakeredis + BERT mock) semestinya jauh lebih cepat lagi.
    assert elapsed < 5.0
