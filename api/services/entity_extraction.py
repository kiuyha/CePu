"""Ekstraksi nomor telepon, email, dan nama perusahaan dari teks bebas."""
import re
from dataclasses import dataclass, field

from ..core.phone_patterns import PHONE_CANDIDATE_PATTERN, clean_phone_candidate

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_COMPANY_PREFIXES = ("PT", "CV", "UD", "Perum", "Yayasan", "Koperasi")
_COMPANY_PATTERN = re.compile(
    r"\b(" + "|".join(_COMPANY_PREFIXES) + r")\.?\s+"
    r"([A-Z][A-Za-z0-9&]*(?:\s+[A-Z][A-Za-z0-9&]*){0,4})"
)


@dataclass
class ExtractedEntities:
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    company_source: str = "heuristic_prefix"  # ganti "ner" begitu model NER terpasang


def extract_phones(text: str) -> list[str]:
    seen = set()
    result = []
    for match in PHONE_CANDIDATE_PATTERN.finditer(text):
        cleaned = clean_phone_candidate(match.group(0))
        if cleaned is not None and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def extract_emails(text: str) -> list[str]:
    seen = set()
    result = []
    for email in _EMAIL_PATTERN.findall(text):
        lowered = email.lower()
        if lowered not in seen:
            seen.add(lowered)
            result.append(email)
    return result


def extract_companies(text: str) -> list[str]:
    seen = set()
    result = []
    for match in _COMPANY_PATTERN.finditer(text):
        full_name = f"{match.group(1)} {match.group(2)}".strip()
        key = full_name.lower()
        if key not in seen:
            seen.add(key)
            result.append(full_name)
    return result


def extract_entities(text: str) -> ExtractedEntities:
    if not text:
        return ExtractedEntities()

    return ExtractedEntities(
        phones=extract_phones(text),
        emails=extract_emails(text),
        companies=extract_companies(text),
    )
