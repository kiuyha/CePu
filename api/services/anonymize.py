"""Anonimisasi teks: hapus NIK, mask nomor telepon, netralkan nama."""
import re
from dataclasses import dataclass, field

from ..core.cache import mask_value
from ..core.phone_patterns import PHONE_CANDIDATE_PATTERN, clean_phone_candidate

_NIK_PATTERN = re.compile(r"(?<!\d)\d{16}(?!\d)")

# Placeholder sampai NER dari tim ML tersedia: redact nama setelah honorifik umum.
_HONORIFIC_NAME_PATTERN = re.compile(
    r"\b(Bapak|Ibu|Bpk\.?|Sdr\.?|Sdri\.?)\s+"
    r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})"
)


@dataclass
class AnonymizeResult:
    anonymized_text: str
    nik_found_count: int = 0
    phones_masked: list[str] = field(default_factory=list)
    names_neutralized_count: int = 0


def remove_nik(text: str) -> tuple[str, int]:
    count = len(_NIK_PATTERN.findall(text))
    cleaned = _NIK_PATTERN.sub("[NIK_DIHAPUS]", text)
    return cleaned, count


def mask_phones_in_text(text: str) -> tuple[str, list[str]]:
    masked_versions: list[str] = []

    def _replace(match: re.Match) -> str:
        cleaned = clean_phone_candidate(match.group(0))
        if cleaned is None:
            return match.group(0)
        masked = mask_value("phone", cleaned.lstrip("+"))
        masked_versions.append(masked)
        return masked

    result_text = PHONE_CANDIDATE_PATTERN.sub(_replace, text)
    return result_text, masked_versions


def _neutralize_names_placeholder(text: str) -> tuple[str, int]:
    count = len(_HONORIFIC_NAME_PATTERN.findall(text))

    def _replace(match: re.Match) -> str:
        return f"{match.group(1)} [NAMA]"

    result_text = _HONORIFIC_NAME_PATTERN.sub(_replace, text)
    return result_text, count


def anonymize_text(text: str) -> AnonymizeResult:
    if not text:
        return AnonymizeResult(anonymized_text=text or "")

    step1_text, nik_count = remove_nik(text)
    step2_text, masked_phones = mask_phones_in_text(step1_text)
    step3_text, names_count = _neutralize_names_placeholder(step2_text)

    return AnonymizeResult(
        anonymized_text=step3_text,
        nik_found_count=nik_count,
        phones_masked=masked_phones,
        names_neutralized_count=names_count,
    )
