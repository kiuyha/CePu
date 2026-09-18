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


def _send(client, phone_hash: str, body: str, msg_type: str = "text"):
    response = client.post(
        "/internal/wa/inbound",
        json={"phone_hash": phone_hash, "msg": {"type": msg_type, "body": body}},
        headers=HEADERS,
    )
    assert response.status_code == 200
    return response.json()["reply"]


def test_unrecognized_input_shows_main_menu(client):
    reply = _send(client, "user1", "halo")
    assert "Pilih menu" in reply


def test_menu_1_shows_education_message(client):
    reply = _send(client, "user2", "1")
    assert "Edukasi" in reply or "artikel" in reply.lower()


def test_menu_2_asks_for_report_details(client):
    reply = _send(client, "user3", "2")
    assert "detail" in reply.lower() or "lapor" in reply.lower()


def test_menu_3_asks_for_detect_input(client):
    reply = _send(client, "user4", "3")
    assert "cek" in reply.lower() or "kirim" in reply.lower()


def test_footer_always_present(client):
    reply = _send(client, "user5", "halo")
    assert "prototipe riset" in reply


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
    assert "Pilih menu" in reply  # bukan "laporan diterima"


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
    _send(client, "user10", "laporan pertama")
    reply = _send(client, "user10", "halo")
    assert "Pilih menu" in reply


async def test_detect_flow_via_menu_3_runs_pipeline(client, monkeypatch):
    async def _fake_predict(text: str) -> float:
        return 0.8

    monkeypatch.setattr("api.services.detection_pipeline.predict_fraud_probability", _fake_predict)

    _send(client, "user11", "3")
    reply = _send(client, "user11", "loker admin transfer dulu 500rb hub 081234567890")

    assert "HASIL DETEKSI" in reply
    assert "Status:" in reply
    assert "Alasan:" in reply


async def test_direct_detection_without_menu_when_message_long_enough(client, monkeypatch):
    """Sesuai dokumen: user bisa langsung kirim teks tanpa pilih menu dulu."""
    async def _fake_predict(text: str) -> float:
        return 0.9

    monkeypatch.setattr("api.services.detection_pipeline.predict_fraud_probability", _fake_predict)

    reply = _send(
        client,
        "user12",
        "Loker admin gaji tinggi tanpa pengalaman transfer dulu ke rekening ini segera",
    )
    assert "HASIL DETEKSI" in reply


def test_short_ambiguous_message_shows_menu_not_detection(client):
    """Pesan pendek yang ambigu -> menu, bukan deteksi."""
    reply = _send(client, "user13", "oke")
    assert "Pilih menu" in reply


def test_image_message_gets_honest_not_supported_reply(client):
    reply = _send(client, "user14", "(gambar)", msg_type="image")
    assert "belum didukung" in reply.lower()
