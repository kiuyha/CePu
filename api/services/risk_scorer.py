"""Formula risk score, kategori, dan penyusunan reasons[]."""
from dataclasses import dataclass

W_BERT = 0.4
W_COMPANY = 0.25
W_PHONE = 0.25
W_EMAIL = 0.10

Category = str  # "rendah" | "sedang" | "tinggi"


@dataclass
class RiskResult:
    risk_score: float
    category: Category


def compute_risk_score(p_bert: float, v_company: float, v_phone: float, v_email: float) -> float:
    score = W_BERT * p_bert + W_COMPANY * v_company + W_PHONE * v_phone + W_EMAIL * v_email
    return max(0.0, min(1.0, score))


def determine_category(risk_score: float) -> Category:
    if risk_score <= 0.3:
        return "rendah"
    if risk_score <= 0.6:
        return "sedang"
    return "tinggi"


def compute_risk(p_bert: float, v_company: float, v_phone: float, v_email: float) -> RiskResult:
    score = compute_risk_score(p_bert, v_company, v_phone, v_email)
    return RiskResult(risk_score=score, category=determine_category(score))


def build_reasons(
    *,
    p_bert: float,
    validator_details: dict,
    category: Category,
    feature_reasons: list[str] | None = None,
) -> list[str]:
    reasons: list[str] = []

    if p_bert >= 0.7:
        reasons.append("Teks lowongan menunjukkan pola bahasa yang sangat mirip modus penipuan")
    elif p_bert >= 0.4:
        reasons.append("Teks lowongan memiliki beberapa indikator mencurigakan")

    # Tambahkan alasan linguistik/fitur yang terdeteksi (kata kunci, digit berlebih, dsb)
    if feature_reasons:
        for r in feature_reasons:
            if r not in reasons:
                reasons.append(r)

    company = validator_details.get("company_registry", {})
    if company.get("binary") is True:
        reasons.append("Nama perusahaan tercatat sebagai perusahaan bermasalah")
    elif company.get("binary") is False:
        reasons.append("Nama perusahaan pernah terverifikasi pada lowongan asli")

    ahu = validator_details.get("ahu", {})
    if ahu.get("binary") is True:
        reasons.append("Nama perusahaan tidak ditemukan di data AHU")

    phone = validator_details.get("intel_blacklist", {})
    if phone.get("binary") is True:
        reasons.append("Nomor telah dilaporkan sebagai indikasi penipuan oleh pengguna lain")

    email = validator_details.get("dns_mx", {})
    if email.get("binary") is True:
        email_score = email.get("score", 0.8)
        if email_score >= 0.95:
            reasons.append("Menggunakan domain email sementara (disposable/fake email)")
        elif email_score >= 0.85:
            reasons.append("Indikasi domain email mencurigakan (menyerupai/impersonasi nama perusahaan)")
        elif email_score >= 0.75:
            reasons.append("Domain email tidak memiliki rekaman MX aktif (kemungkinan tidak aktif/palsu)")
        elif email_score >= 0.65:
            reasons.append("Klaim entitas korporasi resmi menggunakan alamat email publik gratis")
        else:
            reasons.append("Domain email mencurigakan atau tidak memiliki rekaman MX yang valid")


    if not reasons:
        if category == "rendah":
            reasons.append("Tidak ditemukan indikator mencurigakan yang signifikan")
        else:
            reasons.append("Skor risiko dipengaruhi kombinasi beberapa sinyal minor")

    return reasons

