"""Pola & helper nomor telepon Indonesia, dipakai bareng oleh anonymize.py dan entity_extraction.py."""
import re

PHONE_CANDIDATE_PATTERN = re.compile(r"(?:\+62|62|0)8[\d\s-]{7,13}")


def clean_phone_candidate(raw: str) -> str | None:
    """Bersihkan separator, validasi panjang digit (10-14). Return None kalau tidak valid."""
    has_plus = raw.strip().startswith("+")
    digits_only = re.sub(r"\D", "", raw)

    if not (10 <= len(digits_only) <= 14):
        return None

    return ("+" if has_plus else "") + digits_only
