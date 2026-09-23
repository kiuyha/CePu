"""Mesin status bot WhatsApp: menu, parsing, format balasan."""
from typing import Optional
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings
from ..core.errors import ModelNotReadyError
from ..db.repository import EducationArticleRepository, ReportRepository, WaSessionRepository
from .detection_pipeline import DetectionOutcome, run_detection_pipeline
from .entity_extraction import extract_entities

FOOTER = "\n\n---\n_Layanan ini adalah prototipe riset, bukan produk resmi._"

STATUS_LABEL = {
    "rendah": "🟢 AMAN (Tingkat Risiko Penipuan Rendah)",
    "sedang": "🟡 WASPADA (Tingkat Risiko Penipuan Sedang)",
    "tinggi": "🔴 BAHAYA (Tingkat Risiko Penipuan Tinggi)",
}

MAIN_MENU_TEXT = (
    "Halo! 👋 Saya CePu, asisten kamu untuk mendeteksi lowongan kerja palsu. "
    "Silakan pilih menu yang ingin kamu gunakan:\n"
    "1️⃣ Edukasi – Belajar cara mengenali lowongan kerja palsu.\n"
    "2️⃣ Lapor – Laporkan lowongan kerja mencurigakan.\n"
    "3️⃣ Deteksi – Cek apakah lowongan kerja yang kamu terima palsu atau aman.\n\n"
    "Balas dengan 1, 2, atau 3 sesuai pilihanmu."
)

EDUCATION_TEXT = (
    "EDUKASI: Kenali Penipuan Lowongan Kerja\n\n"
    "Halo 👋\n"
    "Yuk pahami penipuan lowongan kerja supaya kamu tidak jadi korban!\n\n"
    "📌 Apa itu penipuan lowongan kerja?\n"
    "Penipuan ini biasanya menawarkan pekerjaan palsu untuk mengambil uang atau data pribadi. "
    "Modusnya bisa berupa biaya administrasi, training berbayar, atau meminta data sensitif."
)

REPORT_GUIDE_TEXT = (
    "📝 LAPOR LOWONGAN MENCURIGAKAN\n\n"
    "Menemukan lowongan kerja yang mencurigakan atau indikasi penipuan?\n"
    "Yuk laporkan datanya untuk membantu melindungi pencari kerja lainnya.\n\n"
    "Silakan kirimkan informasi berikut di pesan ini:\n"
    "📱 Nomor HP / Kontak Terduga\n"
    "📧 Email Terduga\n"
    "🏢 Nama Perusahaan\n"
    "📝 Kronologi / Detail Pesan Lowongan\n\n"
    "Ketik dan kirimkan informasi di atas untuk kami proses."
)

DETECTION_GUIDE_TEXT = (
    "🔎 DETEKSI LOWONGAN PEKERJAAN\n\n"
    "Curiga dengan sebuah lowongan kerja?\n"
    "Yuk kirimkan datanya untuk kami bantu cek dan analisis.\n\n"
    "Silakan lengkapi informasi berikut:\n\n"
    "📱 Nomor HP Perekrut\n"
    "Contoh: 08xxxxxxxxxx\n\n"
    "📧 Email Perekrut\n"
    "Contoh: namaperekrut@gmail.com\n\n"
    "🏢 Nama Perusahaan\n"
    "Tuliskan nama perusahaan yang tertera di lowongan\n\n"
    "📝 Teks / Pesan Lowongan\n"
    "Salin isi pesan atau deskripsi lowongan yang kamu terima\n\n"
    "📎 Screenshot Lowongan\n"
    "Kirim file dalam format PNG, JPG, atau PDF (maksimal 5MB)\n\n"
    "Setelah data lengkap, kirimkan untuk proses deteksi.\n"
    "Kami akan membantu meninjau apakah lowongan tersebut aman atau berpotensi penipuan."
)

HELP_TEXT = (
    "📖 Panduan CePu:\n"
    "1 = Edukasi mengenali penipuan loker\n"
    "2 = Laporkan lowongan kerja mencurigakan\n"
    "3 = Deteksi apakah lowongan aman atau penipuan\n"
    "'reset' = mulai ulang dari menu awal\n"
    "'bantuan' = tampilkan pesan ini lagi\n\n"
    "Tips: Kamu juga bisa langsung mengirimkan teks lowongan kerja kapan saja!"
)


def _with_footer(text: str) -> str:
    return text + FOOTER


def _format_detection_result(outcome: DetectionOutcome) -> str:
    status_label = STATUS_LABEL.get(outcome.category, "⚪ STATUS TIDAK DIKETAHUI")

    lines = [f"Status: {status_label}", "Alasan Terindikasi:"]
    if outcome.reasons:
        for i, reason in enumerate(outcome.reasons, start=1):
            lines.append(f"  {i}. {reason}")
    else:
        lines.append("  - Tidak ditemukan indikator penipuan yang mencurigakan.")

    if outcome.alternatives:
        lines.append("Rekomendasi Lowongan yang Lebih Aman:")
        for i, alt in enumerate(outcome.alternatives, start=1):
            lines.append(f"  {i}. {alt['title']} {alt['company']}")

    if outcome.degraded_sources:
        lines.append(
            f"\n⚠️ Catatan: {len(outcome.degraded_sources)} sumber verifikasi tidak bisa "
            "diakses saat ini, hasil di atas mungkin kurang lengkap."
        )

    return "\n".join(lines)


def _is_session_expired(last_active_at: datetime, timeout_minutes: int) -> bool:
    now = datetime.now(timezone.utc)
    if last_active_at.tzinfo is None:
        last_active_at = last_active_at.replace(tzinfo=timezone.utc)
    return (now - last_active_at) > timedelta(minutes=timeout_minutes)


def _looks_like_direct_detection_input(text: str) -> bool:
    stripped = text.strip()
    if stripped in ("1", "2", "3"):
        return False
    if len(stripped) > 20:
        return True
    entities = extract_entities(stripped)
    return bool(entities.phones or entities.emails or entities.companies)


async def handle_inbound_message(
    *,
    phone_hash: str,
    msg_type: str,
    msg_body: str,
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    on_progress: Optional[any] = None,
) -> str:
    session_repo = WaSessionRepository(db)
    stripped_lower = msg_body.strip().lower()

    if stripped_lower == "reset":
        await session_repo.delete(phone_hash)
        return _with_footer("🔄 Sesi direset.\n\n" + MAIN_MENU_TEXT)

    if stripped_lower == "bantuan":
        return _with_footer(HELP_TEXT)

    if msg_type == "image":
        return _with_footer(
            "Maaf, deteksi lewat gambar via WhatsApp belum didukung saat ini. "
            "Silakan ketik ulang teks lowongannya langsung."
        )

    session = await session_repo.get(phone_hash)
    current_state = session.current_state if session else "idle"

    if session and _is_session_expired(session.last_active_at, settings.wa_session_timeout_minutes):
        current_state = "idle"

    if current_state == "awaiting_report":
        report_repo = ReportRepository(db)
        report = await report_repo.create(channel="wa", message_raw=msg_body, status="pending")
        await session_repo.upsert(phone_hash, current_state="idle")
        return _with_footer(
            f"✅ Laporan diterima (id: {report.id[:8]}...). Terima kasih sudah membantu "
            "komunitas terhindar dari penipuan lowongan kerja."
        )

    if current_state == "awaiting_detect":
        await session_repo.upsert(phone_hash, current_state="idle")
        try:
            outcome = await run_detection_pipeline(
                channel="wa", text=msg_body, company=None, phone=None, email=None,
                db=db, redis_client=redis_client, settings=settings,
                on_progress=on_progress,
            )
        except ModelNotReadyError:
            return _with_footer("⏳ Sistem deteksi sedang mempersiapkan model, coba lagi sebentar ya.")
        return _with_footer(_format_detection_result(outcome))

    if _looks_like_direct_detection_input(msg_body):
        await session_repo.upsert(phone_hash, current_state="idle")
        try:
            outcome = await run_detection_pipeline(
                channel="wa", text=msg_body, company=None, phone=None, email=None,
                db=db, redis_client=redis_client, settings=settings,
                on_progress=on_progress,
            )
        except ModelNotReadyError:
            return _with_footer("⏳ Sistem deteksi sedang mempersiapkan model, coba lagi sebentar ya.")
        return _with_footer(_format_detection_result(outcome))

    if stripped_lower == "1":
        article_repo = EducationArticleRepository(db)
        articles = await article_repo.list_published(limit=3)
        await session_repo.upsert(phone_hash, current_state="idle")
        edu_content = [EDUCATION_TEXT]
        if articles:
            edu_content.append("\n📚 Artikel & Tips Terkini:")
            for a in articles:
                edu_content.append(f"• {a.title}")
        return _with_footer("\n".join(edu_content))

    if stripped_lower == "2":
        await session_repo.upsert(phone_hash, current_state="awaiting_report")
        return _with_footer(REPORT_GUIDE_TEXT)

    if stripped_lower == "3":
        await session_repo.upsert(phone_hash, current_state="awaiting_detect")
        return _with_footer(DETECTION_GUIDE_TEXT)

    await session_repo.upsert(phone_hash, current_state="idle")
    return _with_footer(MAIN_MENU_TEXT)
