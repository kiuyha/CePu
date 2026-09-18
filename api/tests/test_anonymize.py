from api.services.anonymize import (
    anonymize_text,
    mask_phones_in_text,
    remove_nik,
)


# ---------- remove_nik ----------

def test_remove_nik_removes_16_digit_sequence():
    text = "NIK saya 3201234567890123 mohon diproses"
    cleaned, count = remove_nik(text)
    assert count == 1
    assert "3201234567890123" not in cleaned
    assert "[NIK_DIHAPUS]" in cleaned


def test_remove_nik_does_not_touch_shorter_numbers():
    """15 digit (bukan NIK) tidak boleh ikut terhapus."""
    text = "nomor rekening 123456789012345"
    cleaned, count = remove_nik(text)
    assert count == 0
    assert cleaned == text


def test_remove_nik_handles_multiple_niks():
    text = "NIK1: 1111111111111111 NIK2: 2222222222222222"
    cleaned, count = remove_nik(text)
    assert count == 2
    assert "1111111111111111" not in cleaned
    assert "2222222222222222" not in cleaned


# ---------- mask_phones_in_text ----------

def test_mask_phones_masks_plain_number():
    text = "hub 081234567890 segera"
    masked_text, masked_list = mask_phones_in_text(text)
    assert "081234567890" not in masked_text
    assert len(masked_list) == 1


def test_mask_phones_handles_dashes_and_spaces():
    text = "hub 0812-3456-7890 atau 0813 4567 8901"
    masked_text, masked_list = mask_phones_in_text(text)
    assert "0812-3456-7890" not in masked_text
    assert "0813 4567 8901" not in masked_text
    assert len(masked_list) == 2


def test_mask_phones_no_phone_in_text_returns_unchanged():
    text = "tidak ada nomor di sini"
    masked_text, masked_list = mask_phones_in_text(text)
    assert masked_text == text
    assert masked_list == []


# ---------- anonymize_text (pipeline penuh) ----------

def test_anonymize_text_removes_nik_and_masks_phone_together():
    text = "NIK 3201234567890123, hub Bapak Andi Wijaya di 081234567890"
    result = anonymize_text(text)

    assert "3201234567890123" not in result.anonymized_text
    assert "081234567890" not in result.anonymized_text
    assert "Andi Wijaya" not in result.anonymized_text
    assert result.nik_found_count == 1
    assert len(result.phones_masked) == 1
    assert result.names_neutralized_count == 1


def test_anonymize_text_empty_string_returns_empty():
    result = anonymize_text("")
    assert result.anonymized_text == ""
    assert result.nik_found_count == 0


def test_anonymize_text_plain_text_without_pii_unchanged():
    text = "Lowongan kerja untuk posisi admin di kantor pusat"
    result = anonymize_text(text)
    assert result.anonymized_text == text
    assert result.nik_found_count == 0
    assert result.phones_masked == []
