"""Pencocokan laporan pengguna untuk ditampilkan di hasil deteksi (display-only).

Tidak memengaruhi skor risiko — hanya menjawab "berapa orang melaporkan
lowongan seperti ini?" agar user melihat bukti sosial bahayanya.

Strategi pencocokan:
- phone/email: exact match setelah normalisasi (digit / lowercase).
- company: equal setelah normalize_company_name ("PT Maju Jaya" == "maju jaya").
- teks: kemiripan fuzzy (difflib ratio >= ambang) untuk tangkap copy-paste
  modus yang cuma ganti nomor/kontak. Dijaga panjang minimum agar teks
  generik pendek tidak false-positive.

Laporan berstatus false_alarm selalu dikecualikan dari hitungan.
"""
import difflib
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.company_normalize import normalize_company_name
from ..db.models import Report
from ..db.repository import ReportRepository

logger = logging.getLogger(__name__)

# Batas kandidat agar pencocokan fuzzy tetap murah.
MAX_CANDIDATES = 500
# Ambang kemiripan teks (0-1). Teks copy-paste yang cuma beda nomor
# biasanya > 0.9; 0.8 memberi toleransi edit kecil.
TEXT_SIMILARITY_THRESHOLD = 0.8
# Teks di bawah ini terlalu generik untuk dibandingkan secara fuzzy.
MIN_TEXT_LENGTH = 50

_COUNTABLE_STATUSES = ("pending", "verified_scam")


@dataclass
class ReportMatchStats:
    total: int = 0
    verified: int = 0
    matched_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "verified": self.verified,
            "matched_by": self.matched_by,
        }


def normalize_phone_digits(phone: str) -> str:
    """'+62 812-...' / '0812...' / '62812...' -> '0812...' (format nasional)."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("62"):
        digits = "0" + digits[2:]
    return digits


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_similarity(a: str, b: str) -> float:
    a, b = normalize_text(a), normalize_text(b)
    if len(a) < MIN_TEXT_LENGTH or len(b) < MIN_TEXT_LENGTH:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


async def match_report_stats(
    db: AsyncSession,
    *,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    company: Optional[str] = None,
    text: Optional[str] = None,
) -> ReportMatchStats:
    """Hitung laporan (pending + verified_scam) yang cocok dengan input deteksi."""
    want_phone = normalize_phone_digits(phone) if phone and phone.strip() else ""
    want_email = (email or "").strip().lower() or ""
    want_company = normalize_company_name(company) if company and company.strip() else ""
    want_text = normalize_text(text) if text else ""

    if not (want_phone or want_email or want_company or len(want_text) >= MIN_TEXT_LENGTH):
        return ReportMatchStats()

    repo = ReportRepository(db)
    result = await repo.session.execute(
        select(Report)
        .where(Report.status.in_(_COUNTABLE_STATUSES))
        .order_by(Report.created_at.desc())
        .limit(MAX_CANDIDATES)
    )
    candidates = list(result.scalars().all())

    matched_ids: set[str] = set()
    verified_ids: set[str] = set()
    matched_by: set[str] = set()

    for rep in candidates:
        hit: Optional[str] = None

        if want_phone and rep.suspect_phone:
            if normalize_phone_digits(rep.suspect_phone) == want_phone:
                hit = "phone"
        if hit is None and want_email and rep.suspect_email:
            if rep.suspect_email.strip().lower() == want_email:
                hit = "email"
        if hit is None and want_company and rep.suspect_company:
            if normalize_company_name(rep.suspect_company) == want_company:
                hit = "company"
        if hit is None and len(want_text) >= MIN_TEXT_LENGTH and rep.message_raw:
            if text_similarity(want_text, rep.message_raw) >= TEXT_SIMILARITY_THRESHOLD:
                hit = "similar_text"

        if hit is not None:
            matched_ids.add(rep.id)
            matched_by.add(hit)
            if rep.status == "verified_scam":
                verified_ids.add(rep.id)

    stats = ReportMatchStats(
        total=len(matched_ids),
        verified=len(verified_ids),
        matched_by=sorted(matched_by),
    )
    if stats.total:
        logger.info(
            "Report match: %d laporan (%d terverifikasi) via %s",
            stats.total, stats.verified, stats.matched_by,
        )
    return stats
