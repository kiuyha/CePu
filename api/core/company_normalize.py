"""Normalisasi nama perusahaan untuk pencocokan di company_registry."""
import re

_PREFIX_PATTERN = re.compile(r"^(pt|cv|ud|perum|yayasan|koperasi)\.?\s+", re.IGNORECASE)
_SUFFIX_PATTERN = re.compile(r",?\s*(tbk|persero)\.?\s*$", re.IGNORECASE)
_PUNCTUATION_PATTERN = re.compile(r"[.,]")


def normalize_company_name(name: str) -> str:
    normalized = name.strip().lower()
    normalized = _PREFIX_PATTERN.sub("", normalized)
    normalized = _SUFFIX_PATTERN.sub("", normalized)
    normalized = _PUNCTUATION_PATTERN.sub("", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized
