"""
Test fase 2: memastikan data BENAR-BENAR tersimpan di database, bukan
cuma "kelihatan berhasil" di response API. Ini beda dengan test di
test_detect.py/test_reports.py yang cuma cek response HTTP -- di sini
kita buka session DB baru dan query langsung, meniru cara verifikasi
independen (tidak percaya begitu saja pada apa yang endpoint klaim).
"""
from api.db.base import async_session_factory
from api.db.repository import DetectionRepository, ReportRepository


async def test_detect_response_id_actually_exists_in_db(client):
    response = client.post("/v1/detect", data={"text": "cek persistensi ke DB"})
    assert response.status_code == 200
    request_id = response.json()["request_id"]

    # Buka session BARU (bukan session yang dipakai endpoint tadi) untuk
    # membuktikan datanya sungguh committed ke DB, bukan cuma "terlihat
    # tersimpan" di dalam transaksi yang sama.
    async with async_session_factory() as session:
        repo = DetectionRepository(session)
        record = await repo.get_by_id(request_id)

    assert record is not None, "Detection tidak ditemukan di DB padahal API bilang berhasil"
    assert record.text_input == "cek persistensi ke DB"
    assert record.channel == "web"


async def test_report_response_id_actually_exists_in_db(client):
    response = client.post("/v1/reports", data={"message_raw": "laporan untuk cek persistensi"})
    assert response.status_code == 200
    report_id = response.json()["id"]

    async with async_session_factory() as session:
        repo = ReportRepository(session)
        record = await repo.get_by_id(report_id)

    assert record is not None, "Report tidak ditemukan di DB padahal API bilang berhasil"
    assert record.message_raw == "laporan untuk cek persistensi"
    assert record.status == "pending"


async def test_report_count_verified_scam_by_phone_helper(client):
    """
    Sanity check untuk helper yang akan dipakai fase Validator nanti:
    hitung laporan berstatus verified_scam untuk nomor tertentu.
    """
    async with async_session_factory() as session:
        repo = ReportRepository(session)
        # Buat 2 laporan verified_scam untuk nomor yang sama secara langsung
        # (skip lewat API karena endpoint belum punya cara set status manual)
        await repo.create(
            channel="web",
            suspect_phone="081200000000",
            message_raw="modus 1",
            status="verified_scam",
        )
        await repo.create(
            channel="web",
            suspect_phone="081200000000",
            message_raw="modus 2",
            status="verified_scam",
        )
        # Satu laporan lain dengan nomor sama tapi status pending -- tidak boleh ikut terhitung
        await repo.create(
            channel="web",
            suspect_phone="081200000000",
            message_raw="belum diverifikasi",
            status="pending",
        )

        count = await repo.count_verified_scam_by_phone("081200000000")

    assert count == 2


async def test_detect_stores_anonymized_text_not_raw_pii(client):
    """
    Fase 4: pastikan data yang BENAR-BENAR tersimpan di DB sudah
    dianonimkan -- NIK dan nomor telepon asli TIDAK boleh muncul mentah
    di kolom text_input, walau user mengirimkannya di field 'text'.
    """
    raw_text = "NIK saya 3201234567890123, hub 081234567890 untuk info lowongan"
    response = client.post("/v1/detect", data={"text": raw_text})
    assert response.status_code == 200
    request_id = response.json()["request_id"]

    async with async_session_factory() as session:
        repo = DetectionRepository(session)
        record = await repo.get_by_id(request_id)

    assert record is not None
    # Data mentah TIDAK BOLEH ada sama sekali di DB
    assert "3201234567890123" not in record.text_input
    assert "081234567890" not in record.text_input
    # Tapi harus tetap ada jejak bahwa itu pernah terdeteksi (di features)
    assert record.features["nik_found_count"] == 1


async def test_detect_stores_extracted_entities_in_features(client):
    """
    Fase 4: entitas (telepon/email/perusahaan) yang disebut di teks bebas
    harus ikut tersimpan di kolom `features`, untuk dipakai fase Validator
    nanti -- bukan cuma hilang begitu saja setelah anonimisasi.
    """
    text = "Lowongan dari PT Sejahtera Abadi, hub 081234567890 atau hr@sejahtera.com"
    response = client.post("/v1/detect", data={"text": text})
    assert response.status_code == 200
    request_id = response.json()["request_id"]

    async with async_session_factory() as session:
        repo = DetectionRepository(session)
        record = await repo.get_by_id(request_id)

    assert record.features["extracted_companies"] == ["PT Sejahtera Abadi"]
    assert record.features["extracted_emails"] == ["hr@sejahtera.com"]
    assert record.features["extracted_phones"] == ["081234567890"]


async def test_detect_stores_validator_scores_from_extracted_email(client):
    """
    Fase 5: email yang diekstrak dari teks bebas (bukan diisi eksplisit di
    field 'email') harus tetap divalidasi lewat DNS MX, dan hasilnya
    (v_email) tersimpan ke DB.
    """
    # Email dengan domain korporasi mandiri yang valid (memiliki MX)
    text = "Lowongan dari PT Contoh, hub hr@sejahtera.com untuk info"
    response = client.post("/v1/detect", data={"text": text})
    assert response.status_code == 200
    request_id = response.json()["request_id"]

    async with async_session_factory() as session:
        repo = DetectionRepository(session)
        record = await repo.get_by_id(request_id)

    # sejahtera.com punya MX record valid dan bukan free/disposable webmail -> v_email rendah
    assert record.v_email is not None
    assert record.v_email < 0.5


async def test_detect_with_explicit_phone_field_gets_validated(client):
    """Field 'phone' yang diisi eksplisit (bukan dari ekstraksi teks) juga harus divalidasi."""
    response = client.post("/v1/detect", data={"phone": "081255555555"})
    assert response.status_code == 200
    request_id = response.json()["request_id"]

    async with async_session_factory() as session:
        repo = DetectionRepository(session)
        record = await repo.get_by_id(request_id)

    assert record.v_phone is not None
