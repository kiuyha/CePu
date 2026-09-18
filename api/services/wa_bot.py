"""Mesin status bot WhatsApp: menu, parsing, format balasan."""
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings
from ..core.errors import ModelNotReadyError
from ..db.repository import EducationArticleRepository, ReportRepository, WaSessionRepository
from .detection_pipeline import DetectionOutcome, run_detection_pipeline
from .entity_extraction import extract_entities

FOOTER = "\n\n---\n_Layanan ini adalah prototipe riset, bukan produk resmi._"

STATUS_LABEL = {"rendah": "AMAN", "sedang": "WASPADA", "tinggi": "BAHAYA"}

MAIN_MENU_TEXT = (
    "👋 Selamat datang di CePu -- Deteksi Penipuan Lowongan Kerja!\n\n"
    "Pilih menu:\n"
    "1. Edukasi\n"
    "2. Lapor lowongan mencurigakan\n"
    "3. Cek lowongan/kontak\n\n"
    "Atau langsung kirim teks lowongan/nomor/email untuk langsung dicek.\n"
    "Ketik 'bantuan' kapan saja untuk panduan, 'reset' untuk mulai ulang."
)

HELP_TEXT = (
    "📖 Panduan CePu:\n"
    "1 = lihat artikel edukasi\n"
    "2 = lapor lowongan mencurigakan (kirim detailnya di pesan berikutnya)\n"
    "3 = cek lowongan/kontak (kirim teksnya di pesan berikutnya)\n"
    "'reset' = mulai ulang dari menu awal\n"
    "'bantuan' = tampilkan pesan ini lagi\n\n"
    "Tips: kamu juga bisa langsung kirim teks lowongan tanpa pilih menu dulu."
)


def _with_footer(text: str) -> str:
    return text + FOOTER


def _format_detection_result(outcome: DetectionOutcome) -> str:
    status_label = STATUS_LABEL.get(outcome.category, "TIDAK DIKETAHUI")
    score_display = f"{outcome.risk_score:.2f}" if outcome.risk_score is not None else "-"

    lines = ["🚩 HASIL DETEKSI", f"Status: {status_label} (skor {score_display})", "Alasan:"]
    for i, reason in enumerate(outcome.reasons, start=1):
        lines.append(f"{i}. {reason}")

    if outcome.alternatives:
        alt_lines = [f"- {alt['title']} ({alt['company']})" for alt in outcome.alternatives]
        lines.append("Lowongan alternatif:\n" + "\n".join(alt_lines))
    else:
        lines.append("Lowongan alternatif: -")

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
            )
        except ModelNotReadyError:
            return _with_footer("⏳ Sistem deteksi sedang mempersiapkan model, coba lagi sebentar ya.")
        return _with_footer(_format_detection_result(outcome))

    if stripped_lower == "1":
        article_repo = EducationArticleRepository(db)
        articles = await article_repo.list_published(limit=5)
        await session_repo.upsert(phone_hash, current_state="idle")
        if not articles:
            return _with_footer("Belum ada artikel edukasi tersedia saat ini.")
        lines = ["📚 Artikel Edukasi:"] + [f"- {a.title}" for a in articles]
        return _with_footer("\n".join(lines))

    if stripped_lower == "2":
        await session_repo.upsert(phone_hash, current_state="awaiting_report")
        return _with_footer(
            "📝 Silakan kirim detail lowongan yang mencurigakan (nomor/email/nama "
            "perusahaan, atau ceritakan kejadiannya) di pesan berikutnya."
        )

    if stripped_lower == "3":
        await session_repo.upsert(phone_hash, current_state="awaiting_detect")
        return _with_footer(
            "🔍 Silakan kirim teks lowongan, nomor telepon, email, atau nama "
            "perusahaan yang ingin dicek di pesan berikutnya."
        )

    await session_repo.upsert(phone_hash, current_state="idle")
    return _with_footer(MAIN_MENU_TEXT)
