"""Test report_matcher: hitungan laporan cocik untuk display hasil deteksi.

Matcher ini display-only (tidak masuk skor) — yang diuji: pencocokan
exact (phone/email/company) + fuzzy teks, dan pengecualian false_alarm.
"""
import pytest
from sqlalchemy import delete, text

from api.db.base import async_session_factory
from api.db.models import Report
from api.db.repository import ReportRepository
from api.services.report_matcher import (
    match_report_stats,
    normalize_phone_digits,
    text_similarity,
)

LONG_TEXT = (
    "Dibutuhkan segera karyawan untuk posisi admin online shop. Gaji besar "
    "5 sampai 7 juta per bulan, kerja dari rumah, tanpa pengalaman. Hubungi "
    "WA 081234567890 untuk proses lamaran cepat. Langsung diterima."
)
# Sama, kecuali nomor diganti (modus copy-paste tipikal).
LONG_TEXT_EDITED = LONG_TEXT.replace("081234567890", "089876543210")


@pytest.fixture(autouse=True)
async def _clean_reports(client):
    async with async_session_factory() as session:
        await session.execute(delete(Report))
        await session.commit()
    yield
    async with async_session_factory() as session:
        await session.execute(text("DELETE FROM reports"))
        await session.commit()


async def _seed(**fields):
    fields.setdefault("channel", "web")
    fields.setdefault("status", "pending")
    async with async_session_factory() as session:
        repo = ReportRepository(session)
        return await repo.create(**fields)


def test_normalize_phone():
    assert normalize_phone_digits("+62 812-3456-7890") == "081234567890"
    assert normalize_phone_digits("6281234567890") == "081234567890"
    assert normalize_phone_digits("081234567890") == "081234567890"


def test_text_similarity_copy_paste_tinggi():
    assert text_similarity(LONG_TEXT, LONG_TEXT_EDITED) > 0.9


def test_text_similarity_pendek_dinolkan():
    assert text_similarity("halo", "halo") == 0.0
    assert text_similarity(LONG_TEXT, "teks beda total yang tidak mirip sama sekali xyz") < 0.8


async def test_match_exact_phone_beda_format():
    await _seed(suspect_phone="081234567890", message_raw="laporan modus admin")
    stats = await _match(phone="+6281234567890")
    assert stats.total == 1
    assert stats.matched_by == ["phone"]


async def _match(**kwargs):
    async with async_session_factory() as session:
        return await match_report_stats(session, **kwargs)


async def test_match_email_case_insensitive():
    await _seed(suspect_email="Penipu@Contoh.com", message_raw="laporan email")
    stats = await _match(email="penipu@contoh.com")
    assert stats.total == 1
    assert stats.matched_by == ["email"]


async def test_match_company_ternormalisasi():
    await _seed(suspect_company="PT Maju Jaya", message_raw="laporan pt")
    stats = await _match(company="maju jaya")
    assert stats.total == 1
    assert stats.matched_by == ["company"]


async def test_match_similar_text():
    await _seed(message_raw=LONG_TEXT)
    stats = await _match(text=LONG_TEXT_EDITED)
    assert stats.total == 1
    assert stats.matched_by == ["similar_text"]


async def test_false_alarm_dikecualikan():
    await _seed(suspect_phone="081111111111", message_raw="bukan penipuan", status="false_alarm")
    stats = await _match(phone="081111111111")
    assert stats.total == 0


async def test_verified_dihitung_terpisah_dan_dedup():
    # Satu laporan cocok via phone SEKALIGUS teks mirip -> dihitung 1x.
    await _seed(
        suspect_phone="081234567890",
        message_raw=LONG_TEXT,
        status="verified_scam",
    )
    await _seed(suspect_phone="081234567890", message_raw="lain", status="pending")
    async with async_session_factory() as session:
        stats = await match_report_stats(
            session, phone="081234567890", text=LONG_TEXT_EDITED
        )
    assert stats.total == 2
    assert stats.verified == 1


async def test_tanpa_input_nol():
    stats = await _match()
    assert stats.total == 0 and stats.verified == 0


def test_detect_response_memuat_report_stats(client):
    resp = client.post("/v1/detect", data={"text": "cek report stats hadir di response"})
    assert resp.status_code == 200
    data = resp.json()
    assert "report_stats" in data
    assert data["report_stats"]["total"] == 0
    # Skor tidak boleh berubah hanya karena field display ditambah.
    assert "risk_score" in data and "category" in data
