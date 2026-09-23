from api.services.entity_extraction import (
    extract_companies,
    extract_emails,
    extract_entities,
    extract_phones,
)


# ---------- extract_phones ----------

def test_extract_phones_finds_plain_number():
    assert extract_phones("hub 081234567890 ya") == ["081234567890"]


def test_extract_phones_normalizes_dashes_and_spaces():
    result = extract_phones("hub 0812-3456-7890")
    assert result == ["081234567890"]


def test_extract_phones_finds_country_code_format():
    result = extract_phones("call +6281234567890 now")
    assert result == ["+6281234567890"]


def test_extract_phones_dedups_repeated_number():
    text = "hub 081234567890 atau 081234567890 juga bisa"
    assert extract_phones(text) == ["081234567890"]


def test_extract_phones_no_phone_returns_empty_list():
    assert extract_phones("tidak ada nomor") == []


# ---------- extract_emails ----------

def test_extract_emails_finds_valid_email():
    assert extract_emails("kirim ke hr@contoh.com ya") == ["hr@contoh.com"]


def test_extract_emails_dedups_case_insensitive():
    text = "kirim ke HR@Contoh.com atau hr@contoh.com"
    result = extract_emails(text)
    assert len(result) == 1


def test_extract_emails_no_email_returns_empty_list():
    assert extract_emails("tidak ada email di sini") == []


# ---------- extract_companies ----------

def test_extract_companies_finds_pt_prefix():
    result = extract_companies("Lowongan dari PT Sejahtera Abadi untuk posisi admin")
    assert result == ["PT Sejahtera Abadi"]


def test_extract_companies_finds_cv_prefix():
    result = extract_companies("bekerja sama dengan CV Maju Jaya")
    assert result == ["CV Maju Jaya"]


def test_extract_companies_no_prefix_returns_empty():
    """Tanpa prefix formal, heuristik ini TIDAK menangkap -- ini keterbatasan
    yang memang didokumentasikan, ditutup nanti oleh NER."""
    result = extract_companies("bekerja di Sejahtera Abadi Group")
    assert result == []


def test_extract_companies_dedups_same_company():
    text = "PT Sejahtera Abadi membuka lowongan. Hub PT Sejahtera Abadi segera."
    result = extract_companies(text)
    assert len(result) == 1


# ---------- extract_entities (gabungan) ----------

def test_extract_entities_combines_all_three():
    text = "Lowongan dari PT Sejahtera Abadi, hub 081234567890 atau email hr@sejahtera.com"
    result = extract_entities(text)

    assert result.phones == ["081234567890"]
    assert result.emails == ["hr@sejahtera.com"]
    assert result.companies == ["PT Sejahtera Abadi"]
    assert result.company_source == "heuristic_prefix"


def test_extract_entities_empty_text_returns_all_empty():
    result = extract_entities("")
    assert result.phones == []
    assert result.emails == []
    assert result.companies == []


# ---------- notebook specific: artifacts stripping & process_job_text ----------

def test_strip_source_artifacts_cleans_hoax_narratives_and_emojis():
    from api.services.entity_extraction import strip_source_artifacts

    raw = "🔥 Cek fakta turnbackhoax! 💼 Lowongan kerja #loker2024"
    cleaned = strip_source_artifacts(raw)
    assert "turnbackhoax" not in cleaned.lower()
    assert "cek fakta" not in cleaned.lower()
    assert "🔥" not in cleaned
    assert "💼" not in cleaned


def test_process_job_text_masks_contacts_and_companies():
    from api.services.entity_extraction import process_job_text

    raw = (
        "Lowongan PT Sejahtera Abadi posisi staff. "
        "Hubungi 081234567890 atau email hr@sejahtera.com atau https://sejahtera.com"
    )
    processed = process_job_text(raw)

    assert "[PERUSAHAAN]" in processed["text_clean_no_contact"]
    assert "[NOMOR_HP]" in processed["text_clean_no_contact"]
    assert "[EMAIL]" in processed["text_clean_no_contact"]
    assert "[URL]" in processed["text_clean_no_contact"]
    assert "PT Sejahtera Abadi" in processed["extracted_companies"]
    assert "081234567890" in processed["extracted_phones"]
    assert "hr@sejahtera.com" in processed["extracted_emails"]


def test_extract_entities_and_features_computes_keyword_and_stats():
    from api.services.entity_extraction import extract_entities_and_features

    text = "Mohon transfer biaya pendaftaran administrasi sebesar 50000000000000000"
    feats = extract_entities_and_features(text)

    assert feats["suspicious_keyword_count"] >= 2
    assert any("kata kunci mencurigakan" in r for r in feats["reasons"])
    assert any("Frekuensi karakter angka tinggi" in r for r in feats["reasons"])

