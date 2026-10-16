"""
Test untuk services/wa_bot.py -- mesin status bot WhatsApp.
Semua test lewat endpoint /internal/wa/inbound (integrasi penuh) supaya
sekalian jadi bukti end-to-end sesuai target fase 8.
"""
from api.core.config import get_settings
from api.db.base import async_session_factory
from api.db.repository import WaSessionRepository

SETTINGS = get_settings()
HEADERS = {"X-Internal-Token": SETTINGS.internal_token}


def _send(client, phone_hash: str, body: str, msg_type: str = "text", image_b64=None, mime_type=None):
    payload = {"phone_hash": phone_hash, "msg": {"type": msg_type, "body": body}}
    if image_b64 is not None:
        payload["msg"]["image_b64"] = image_b64
    if mime_type is not None:
        payload["msg"]["mime_type"] = mime_type
    response = client.post(
        "/internal/wa/inbound",
        json=payload,
        headers=HEADERS,
    )
    assert response.status_code == 200
    return response.json()["reply"]


def _fake_image_b64() -> str:
    import base64

    return base64.b64encode(b"fake-image-bytes-untuk-test").decode()


def _mock_ocr_text(monkeypatch, text: str):
    def _fake_ocr(_image_bytes: bytes):
        return text, 0.9

    monkeypatch.setattr("api.services.ocr.extract_text_from_image_bytes", _fake_ocr)


def test_unrecognized_input_shows_main_menu(client):
    reply = _send(client, "user1", "halo")
    assert "pilih menu" in reply.lower()


def test_menu_1_shows_education_message(client):
    reply = _send(client, "user2", "1")
    assert "edukasi" in reply.lower() or "artikel" in reply.lower()


def test_menu_2_asks_for_report_details(client):
    reply = _send(client, "user3", "2")
    assert "lapor" in reply.lower() or "detail" in reply.lower()


def test_menu_3_asks_for_detect_input(client):
    reply = _send(client, "user4", "3")
    assert "deteksi" in reply.lower() or "cek" in reply.lower()


def test_no_prototype_footer_anymore(client):
    reply = _send(client, "user5", "halo")
    assert "prototipe riset" not in reply


def test_bare_job_command_asks_clarification(client):
    reply = _send(client, "user-job-1", "/job")
    assert "/job" in reply
    assert "Mau cari kerja apa" in reply


def test_long_text_does_not_trigger_detection_image_only(client):
    """Kebijakan image-only: teks loker panjang TIDAK menjalankan pipeline."""
    reply = _send(client, "user-job-2", "PT Penipu Abadi minta transfer biaya admin 500rb ke rekening")
    assert "Rekomendasi" not in reply
    assert "Status:" not in reply
    assert "gambar" in reply.lower() or "screenshot" in reply.lower()


def test_bantuan_available_anytime(client):
    reply = _send(client, "user6", "bantuan")
    assert "Panduan" in reply


async def test_reset_clears_session(client):
    _send(client, "user7", "2")  # masuk state awaiting_report
    reply = _send(client, "user7", "reset")
    assert "direset" in reply.lower()

    async with async_session_factory() as session:
        repo = WaSessionRepository(session)
        wa_session = await repo.get("user7")

    assert wa_session is None


def test_reset_then_normal_message_shows_menu_not_report_flow(client):
    """Pastikan reset beneran keluar dari state awaiting_report."""
    _send(client, "user8", "2")
    _send(client, "user8", "reset")
    reply = _send(client, "user8", "halo lagi")
    assert "pilih menu" in reply.lower()


async def test_report_flow_creates_report_in_db(client):
    _send(client, "user9", "2")
    reply = _send(client, "user9", "PT Penipu Abadi minta transfer 500rb")

    assert "Laporan diterima" in reply

    from sqlalchemy import select
    from api.db.models import Report

    async with async_session_factory() as session:
        result = await session.execute(
            select(Report).where(Report.channel == "wa", Report.message_raw.contains("Penipu Abadi"))
        )
        report = result.scalar_one_or_none()

    assert report is not None
    assert report.status == "pending"


def test_report_flow_returns_to_idle_after_submitting(client):
    """Setelah lapor, state harus balik ke idle, bukan nyangkut di awaiting_report."""
    _send(client, "user10", "2")
    _send(client, "user10", "PT Fiktif Jaya minta transfer biaya admin 500rb ke 081299988877")
    reply = _send(client, "user10", "halo")
    assert "pilih menu" in reply.lower()


async def test_detect_flow_via_menu_3_runs_pipeline_for_image(client, monkeypatch):
    """Alur 3 + gambar -> OCR + pipeline deteksi (satu-satunya jalur deteksi)."""
    async def _fake_predict(text: str) -> float:
        return 0.8

    monkeypatch.setattr("api.services.detection_pipeline.predict_fraud_probability", _fake_predict)
    _mock_ocr_text(monkeypatch, "loker admin transfer dulu 500rb hub 081234567890")

    _send(client, "user11", "3")
    reply = _send(client, "user11", "screenshot loker", msg_type="image", image_b64=_fake_image_b64())

    assert "Status:" in reply
    assert "Alasan" in reply


async def test_image_detection_reply_tanpa_rekomendasi_otomatis(client, monkeypatch):
    async def _fake_predict(text: str) -> float:
        return 0.8

    monkeypatch.setattr("api.services.detection_pipeline.predict_fraud_probability", _fake_predict)
    _mock_ocr_text(monkeypatch, "PT Penipu Abadi minta transfer biaya admin 500rb")

    reply = _send(client, "user-job-3", "caption", msg_type="image", image_b64=_fake_image_b64())
    assert "Rekomendasi" not in reply
    assert "Status:" in reply


def test_direct_long_text_gets_image_only_nudge_not_detection(client):
    """User kirim teks loker langsung tanpa menu -> diminta kirim gambar, bukan dideteksi."""
    reply = _send(
        client,
        "user12",
        "Loker admin gaji tinggi tanpa pengalaman transfer dulu ke rekening ini segera",
    )
    assert "Status:" not in reply
    assert "gambar" in reply.lower() or "screenshot" in reply.lower()


def test_short_ambiguous_message_shows_menu_not_detection(client):
    """Pesan pendek yang ambigu -> menu, bukan deteksi."""
    reply = _send(client, "user13", "oke")
    assert "pilih menu" in reply.lower()


def test_image_without_bytes_gets_readable_error(client):
    """Gambar tanpa image_b64 (gagal download di gateway) -> minta kirim ulang, bukan crash."""
    reply = _send(client, "user14", "(gambar)", msg_type="image")
    assert "tidak bisa dibaca" in reply.lower() or "kirim ulang" in reply.lower()


def test_image_with_unreadable_ocr_gets_resend_hint(client, monkeypatch):
    _mock_ocr_text(monkeypatch, "")
    reply = _send(client, "user14b", "", msg_type="image", image_b64=_fake_image_b64())
    assert "tidak ada teks" in reply.lower() or "kirim ulang" in reply.lower()


def test_unsupported_msg_type_gets_image_only_nudge(client):
    for weird in ("audio", "video", "sticker", "document", "location", "reaction"):
        reply = _send(client, f"user-weird-{weird}", "x", msg_type=weird)
        assert "gambar" in reply.lower() or "screenshot" in reply.lower()
        assert "Status:" not in reply


def test_oversized_image_rejected_gracefully(client):
    import base64

    big = base64.b64encode(b"x" * (6 * 1024 * 1024)).decode()
    reply = _send(client, "user-big", "besar", msg_type="image", image_b64=big)
    assert "kebesaran" in reply.lower() or "5mb" in reply.lower()


def test_menu_command_wins_over_report_flow(client):
    """Reproduksi transkrip: 2 lalu 3 -> pindah ke Deteksi, bukan filing '3'."""
    _send(client, "user-menu-wins", "2")
    reply = _send(client, "user-menu-wins", "3")
    assert "Laporan diterima" not in reply
    assert "deteksi" in reply.lower() or "cek" in reply.lower()


async def test_menu_switch_files_no_junk_report(client):
    _send(client, "user-menu-wins-2", "2")
    _send(client, "user-menu-wins-2", "3")

    from sqlalchemy import select
    from api.db.models import Report

    async with async_session_factory() as session:
        result = await session.execute(
            select(Report).where(Report.message_raw == "3")
        )
        assert result.scalar_one_or_none() is None


def test_junk_not_filed_stays_in_report_flow(client):
    _send(client, "user-junk", "2")
    reply = _send(client, "user-junk", "ok")
    assert "Laporan diterima" not in reply
    assert "belum lengkap" in reply
    # State bertahan: laporan beneran sesudahnya tetap difiling.
    reply2 = _send(
        client, "user-junk", "PT Penipu Abadi minta transfer 500rb ke 081234567890"
    )
    assert "Laporan diterima" in reply2


def test_junk_in_detect_flow_gets_image_nudge(client):
    _send(client, "user-djunk", "3")
    reply = _send(client, "user-djunk", "ok")
    assert "gambar" in reply.lower() or "screenshot" in reply.lower()
    assert "Status:" not in reply


async def test_text_in_detect_flow_stays_in_detect_state(client):
    """Teks di state awaiting_detect tidak me-reset ke idle; gambar berikutnya tetap dideteksi."""
    _send(client, "user-dstay", "3")
    _send(client, "user-dstay", "ini teks panjang loker admin transfer 500rb")
    async with async_session_factory() as session:
        repo = WaSessionRepository(session)
        wa_session = await repo.get("user-dstay")
    assert wa_session is not None
    assert wa_session.current_state == "awaiting_detect"
