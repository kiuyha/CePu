"""
Validator email:
1. MX & DNS Active Records: Memastikan domain email aktif menerima email.
2. Disposable & Free Webmail Flag: Deteksi email sekali pakai atau email publik gratis untuk entitas korporasi.
3. Domain Mismatch / Similarity: Deteksi typosquatting / domain lookalike via Levenshtein distance.
"""
import asyncio
from datetime import datetime, timezone
import re
from typing import Optional

import dns.asyncresolver
import dns.exception
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.cache import VerificationResult, mask_value
from ...core.config import Settings, get_settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def levenshtein_distance(s1: str, s2: str) -> int:
    """Menghitung jarak Levenshtein antara dua string."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def extract_base_domain(domain: str) -> str:
    """Mengambil nama utama domain (misal: 'hrd-tokopedia.co.id' -> 'hrd-tokopedia')."""
    domain = domain.lower().strip()
    parts = domain.split(".")
    if len(parts) >= 2:
        return parts[0]
    return domain


def check_domain_similarity_suspicious(email_domain: str, company_name: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Mengecek apakah domain email menyerupai nama perusahaan (lookalike/typosquatting)
    namun memiliki perbedaan mencurigakan (misal: tokopedia -> hrd-tokopedia.com).
    """
    if not company_name:
        return False, None

    # Bersihkan nama perusahaan
    clean_company = re.sub(r'^(PT|CV|Perum|UD|Firma|Yayasan)\.?\s+', '', company_name, flags=re.IGNORECASE)
    clean_company = re.sub(r'[^a-zA-Z0-9]', '', clean_company).lower()

    if not clean_company or len(clean_company) < 4:
        return False, None

    email_base = extract_base_domain(email_domain)
    clean_email_base = re.sub(r'[^a-zA-Z0-9]', '', email_base).lower()

    # Domain persis sama -> bukan impersonasi, tapi email domain resmi
    if clean_company == clean_email_base:
        return False, "official_match"

    # Jika nama perusahaan terkandung di domain email dengan imbuhan (misal: hrd-tokopedia, tokopedia-jobs)
    if clean_company in email_base and len(email_base) > len(clean_company):
        return True, "subdomain_or_hyphen_impersonation"

    # Jarak Levenshtein kecil (1-2 karakter typo) untuk nama yang cukup panjang
    dist = levenshtein_distance(clean_company, clean_email_base)
    if dist in (1, 2) and len(clean_company) >= 5:
        return True, "typosquatting"

    return False, None


async def check_email_mx(
    email: str,
    company_name: Optional[str] = None,
    db: Optional[AsyncSession] = None,
    settings: Optional[Settings] = None,
) -> VerificationResult:
    if "@" not in email:
        return VerificationResult(
            value_masked=email,
            verdict_score=0.9,
            verdict_binary=True,
            source="dns_mx",
            fetched_at=_now_iso(),
        )

    settings = settings or get_settings()
    domain = email.rsplit("@", 1)[-1].strip().lower()

    # 1. Cek Disposable Email: Cek DB (tabel disposable_domains) terlebih dahulu jika session DB tersedia
    is_disposable = False
    if db is not None:
        from ...db.repository import DisposableDomainRepository

        repo = DisposableDomainRepository(db)
        is_disposable = await repo.is_disposable(domain)

    # Fallback ke daftar env jika belum ada di DB
    if not is_disposable:
        disposable_list = [d.strip().lower() for d in settings.disposable_email_domains.split(",") if d.strip()]
        if domain in disposable_list:
            is_disposable = True

    if is_disposable:
        return VerificationResult(
            value_masked=mask_value("email", email),
            verdict_score=0.95,
            verdict_binary=True,
            source="dns_mx",
            fetched_at=_now_iso(),
        )

    free_list = [d.strip().lower() for d in settings.free_email_domains.split(",") if d.strip()]


    # 2. Cek Domain Impersonasi / Lookalike (sebelum MX karena domain palsu mungkin belum punya MX atau punya MX palsu)
    is_impersonation, pattern_type = check_domain_similarity_suspicious(domain, company_name)
    if is_impersonation:
        return VerificationResult(
            value_masked=mask_value("email", email),
            verdict_score=0.85,
            verdict_binary=True,
            source="dns_mx",
            fetched_at=_now_iso(),
        )

    # 3. Cek Free Webmail untuk klaim perusahaan formal
    has_company_claim = bool(company_name and re.search(r'\b(PT|CV|Perum|UD|Firma|Yayasan)\b', company_name, re.I))
    if domain in free_list and has_company_claim:
        return VerificationResult(
            value_masked=mask_value("email", email),
            verdict_score=0.7,
            verdict_binary=True,
            source="dns_mx",
            fetched_at=_now_iso(),
        )

    # 4. Cek MX Records
    try:
        answers = await dns.asyncresolver.resolve(domain, "MX")
        has_mx = len(answers) > 0
    except (dns.exception.DNSException, asyncio.TimeoutError):
        has_mx = False

    if not has_mx:
        return VerificationResult(
            value_masked=mask_value("email", email),
            verdict_score=0.8,
            verdict_binary=True,
            source="dns_mx",
            fetched_at=_now_iso(),
        )

    # Email domain valid, memiliki MX, dan tidak mencurigakan
    return VerificationResult(
        value_masked=mask_value("email", email),
        verdict_score=0.1,
        verdict_binary=False,
        source="dns_mx",
        fetched_at=_now_iso(),
    )

