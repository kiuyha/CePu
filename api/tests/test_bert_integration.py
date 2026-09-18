"""
Test fase 7: endpoint /v1/detect dengan BERT + risk scorer tersambung
penuh. P_BERT dikontrol lewat monkeypatch (bukan model asli) supaya
hasilnya deterministik dan tidak butuh torch/download model.
"""
from api.db.base import async_session_factory
from api.db.repository import DetectionRepository


def _mock_predict(monkeypatch, value: float):
    """Ganti predict_fraud_probability supaya selalu return nilai tertentu."""

    async def _fake(text: str) -> float:
        return value

    monkeypatch.setattr("api.services.detection_pipeline.predict_fraud_probability", _fake)


async def test_detect_high_p_bert_and_no_signals_gives_moderate_risk(client, monkeypatch):
    """
    P_BERT tinggi (0.9) sendirian, tanpa sinyal validator apapun (semua
    netral 0.5), harus tetap menghasilkan skor & kategori yang masuk akal
    sesuai formula: 0.4*0.9 + 0.25*0.5 + 0.25*0.5 + 0.10*0.5 = 0.66
    """
    _mock_predict(monkeypatch, 0.9)

    response = client.post("/v1/detect", data={"text": "lowongan kerja apa saja"})
    assert response.status_code == 200

    body = response.json()
    assert body["risk_score"] is not None
    assert abs(body["risk_score"] - 0.66) < 1e-6
    assert body["category"] == "tinggi"
    assert len(body["reasons"]) >= 1


async def test_detect_low_p_bert_gives_moderate_risk_due_to_neutral_validators(client, monkeypatch):
    """
    P_BERT rendah (0.05) sendirian, tapi validator netral (0.5 masing-masing)
    tetap menyumbang 0.3 ke skor akhir -- formula: 0.4*0.05 + 0.3 = 0.32,
    yang jatuh ke kategori 'sedang' (bukan 'rendah'), karena batas 'rendah'
    cuma sampai 0.3. Ini nunjukkin validator netral BUKAN berarti tidak
    berkontribusi ke skor.
    """
    _mock_predict(monkeypatch, 0.05)

    response = client.post("/v1/detect", data={"text": "lowongan kerja normal"})
    assert response.status_code == 200

    body = response.json()
    assert abs(body["risk_score"] - 0.32) < 1e-6
    assert body["category"] == "sedang"


async def test_detect_very_low_p_bert_with_verified_company_gives_low_risk(client, monkeypatch):
    """
    Supaya beneran dapat kategori 'rendah', butuh P_BERT rendah DAN
    sinyal validator yang juga rendah (bukan netral) -- misal perusahaan
    yang sudah terverifikasi di company_registry (skor 0.2, bukan 0.5).
    """
    from api.db.repository import CompanyRegistryRepository

    async with async_session_factory() as session:
        repo = CompanyRegistryRepository(session)
        await repo.upsert("PT Sudah Diverifikasi", registered=True, source="scraped_real_postings")

    _mock_predict(monkeypatch, 0.05)

    response = client.post(
        "/v1/detect", data={"text": "lowongan biasa", "company": "PT Sudah Diverifikasi"}
    )
    assert response.status_code == 200

    body = response.json()
    assert body["category"] == "rendah"


async def test_detect_without_text_uses_neutral_p_bert_no_model_needed(client):
    """
    Kalau tidak ada teks bebas sama sekali (cuma phone/email/company),
    tidak perlu model BERT sama sekali -- P_BERT default netral (0.5).
    """
    response = client.post("/v1/detect", data={"phone": "081234567890"})
    assert response.status_code == 200

    body = response.json()
    assert body["risk_score"] is not None  # tetap terhitung, cuma p_bert-nya netral


async def test_detect_stores_p_bert_and_risk_score_to_db(client, monkeypatch):
    _mock_predict(monkeypatch, 0.7)

    response = client.post("/v1/detect", data={"text": "contoh teks lowongan"})
    request_id = response.json()["request_id"]

    async with async_session_factory() as session:
        repo = DetectionRepository(session)
        record = await repo.get_by_id(request_id)

    assert record.p_bert == 0.7
    assert record.risk_score is not None
    assert record.category is not None
    assert isinstance(record.reasons, list)
    assert len(record.reasons) >= 1


async def test_detect_high_category_includes_alternatives_key(client, monkeypatch):
    _mock_predict(monkeypatch, 0.95)

    response = client.post("/v1/detect", data={"text": "lowongan sangat mencurigakan"})
    body = response.json()

    assert body["category"] == "tinggi"
    assert "alternatives" in body
    assert isinstance(body["alternatives"], list)  # boleh kosong (belum ada data alternatif)


async def test_detect_returns_503_when_model_not_loaded(client, monkeypatch):
    """
    Simulasi model belum siap (misal masih proses download saat startup).
    Endpoint HARUS menolak dengan 503, BUKAN crash 500, ketika ada teks
    yang perlu diklasifikasi.
    """
    monkeypatch.setattr("api.services.detection_pipeline.is_model_loaded", lambda: False)

    response = client.post("/v1/detect", data={"text": "butuh model untuk ini"})
    assert response.status_code == 503


async def test_detect_without_text_works_even_if_model_not_loaded(client, monkeypatch):
    """Kalau tidak ada teks, model tidak dibutuhkan -- 503 TIDAK boleh muncul."""
    monkeypatch.setattr("api.services.detection_pipeline.is_model_loaded", lambda: False)

    response = client.post("/v1/detect", data={"company": "PT Contoh"})
    assert response.status_code == 200
