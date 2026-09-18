from api.services.risk_scorer import (
    build_reasons,
    compute_risk,
    compute_risk_score,
    determine_category,
)


# ---------- compute_risk_score: formula ----------

def test_compute_risk_score_matches_formula_exactly():
    """0.4*P_BERT + 0.25*V_company + 0.25*V_phone + 0.10*V_email"""
    score = compute_risk_score(p_bert=1.0, v_company=1.0, v_phone=1.0, v_email=1.0)
    assert score == 1.0  # 0.4+0.25+0.25+0.10 = 1.0


def test_compute_risk_score_all_zero_is_zero():
    assert compute_risk_score(0.0, 0.0, 0.0, 0.0) == 0.0


def test_compute_risk_score_weights_bert_highest():
    """P_BERT tinggi sendirian (bobot 0.4) harus menghasilkan skor lebih
    besar dibanding V_email tinggi sendirian (bobot 0.10)."""
    score_bert_high = compute_risk_score(p_bert=1.0, v_company=0, v_phone=0, v_email=0)
    score_email_high = compute_risk_score(p_bert=0, v_company=0, v_phone=0, v_email=1.0)
    assert score_bert_high > score_email_high


def test_compute_risk_score_example_from_document():
    """Contoh nilai wajar, pastikan hasilnya sesuai perhitungan manual."""
    # 0.4*0.9 + 0.25*0.8 + 0.25*0.7 + 0.10*0.3 = 0.36+0.2+0.175+0.03 = 0.765
    score = compute_risk_score(p_bert=0.9, v_company=0.8, v_phone=0.7, v_email=0.3)
    assert abs(score - 0.765) < 1e-9


def test_compute_risk_score_clamped_to_valid_range():
    """Jaga-jaga floating point drift tidak menghasilkan angka di luar [0,1]."""
    score = compute_risk_score(p_bert=1.0, v_company=1.0, v_phone=1.0, v_email=1.0)
    assert 0.0 <= score <= 1.0


# ---------- determine_category: batas kategori ----------

def test_category_boundary_rendah_inclusive_at_0_3():
    assert determine_category(0.3) == "rendah"


def test_category_boundary_sedang_starts_just_above_0_3():
    assert determine_category(0.31) == "sedang"


def test_category_boundary_sedang_inclusive_at_0_6():
    assert determine_category(0.6) == "sedang"


def test_category_boundary_tinggi_starts_just_above_0_6():
    assert determine_category(0.61) == "tinggi"


def test_category_zero_is_rendah():
    assert determine_category(0.0) == "rendah"


def test_category_one_is_tinggi():
    assert determine_category(1.0) == "tinggi"


# ---------- compute_risk: gabungan ----------

def test_compute_risk_returns_score_and_matching_category():
    result = compute_risk(p_bert=0.9, v_company=0.8, v_phone=0.9, v_email=0.8)
    assert result.risk_score > 0.6
    assert result.category == "tinggi"


def test_compute_risk_low_everything_is_rendah():
    result = compute_risk(p_bert=0.05, v_company=0.1, v_phone=0.1, v_email=0.1)
    assert result.category == "rendah"


# ---------- build_reasons ----------

def test_build_reasons_high_p_bert_included():
    reasons = build_reasons(p_bert=0.85, validator_details={}, category="tinggi")
    assert any("modus penipuan" in r for r in reasons)


def test_build_reasons_moderate_p_bert_different_wording():
    reasons = build_reasons(p_bert=0.5, validator_details={}, category="sedang")
    assert any("indikator mencurigakan" in r for r in reasons)


def test_build_reasons_low_p_bert_not_mentioned():
    reasons = build_reasons(p_bert=0.1, validator_details={}, category="rendah")
    p_bert_specific_phrases = (
        "sangat mirip modus penipuan",
        "beberapa indikator mencurigakan",
    )
    assert not any(phrase in r for r in reasons for phrase in p_bert_specific_phrases)


def test_build_reasons_company_registry_flagged():
    details = {"company_registry": {"binary": True, "score": 0.9, "source": "company_registry"}}
    reasons = build_reasons(p_bert=0.1, validator_details=details, category="tinggi")
    assert any("perusahaan bermasalah" in r for r in reasons)


def test_build_reasons_company_registry_verified_legit():
    details = {"company_registry": {"binary": False, "score": 0.2, "source": "company_registry"}}
    reasons = build_reasons(p_bert=0.1, validator_details=details, category="rendah")
    assert any("terverifikasi pada lowongan asli" in r for r in reasons)


def test_build_reasons_phone_blacklisted():
    details = {"intel_blacklist": {"binary": True, "score": 0.9, "source": "intel_blacklist"}}
    reasons = build_reasons(p_bert=0.1, validator_details=details, category="tinggi")
    assert any("dilaporkan sebagai indikasi penipuan" in r for r in reasons)


def test_build_reasons_email_no_mx():
    details = {"dns_mx": {"binary": True, "score": 0.8, "source": "dns_mx"}}
    reasons = build_reasons(p_bert=0.1, validator_details=details, category="sedang")
    assert any("tidak memiliki rekaman MX" in r for r in reasons)


def test_build_reasons_neutral_signals_not_included():
    """Sinyal netral (binary=None, misal 'not_provided') tidak boleh jadi alasan."""
    details = {
        "dns_mx": {"binary": None, "score": 0.5, "source": "not_provided"},
        "intel_blacklist": {"binary": None, "score": 0.5, "source": "not_provided"},
    }
    reasons = build_reasons(p_bert=0.1, validator_details=details, category="rendah")
    assert not any("MX" in r or "dilaporkan" in r for r in reasons)


def test_build_reasons_never_empty_even_with_no_signals():
    """Selalu ada minimal 1 alasan, jangan sampai reasons[] kosong total."""
    reasons = build_reasons(p_bert=0.1, validator_details={}, category="rendah")
    assert len(reasons) >= 1


def test_build_reasons_multiple_signals_all_included():
    details = {
        "company_registry": {"binary": True, "score": 0.9, "source": "company_registry"},
        "intel_blacklist": {"binary": True, "score": 0.9, "source": "intel_blacklist"},
        "dns_mx": {"binary": True, "score": 0.8, "source": "dns_mx"},
    }
    reasons = build_reasons(p_bert=0.9, validator_details=details, category="tinggi")
    # 4 sinyal aktif: BERT tinggi, company flagged, phone blacklisted, email no MX
    assert len(reasons) == 4
