"""Pipeline deteksi end-to-end, dipakai bareng oleh /v1/detect dan endpoint internal WA."""
import time
from dataclasses import dataclass, field
from typing import Optional

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.cache import VerificationCache
from ..core.config import Settings
from ..core.errors import ModelNotReadyError
from ..db.repository import DetectionRepository, JobAlternativeRepository
from .anonymize import anonymize_text
from .bert_infer import is_model_loaded, predict_fraud_probability, run_ner
from .entity_extraction import extract_entities, extract_entities_and_features, process_job_text
from .risk_scorer import build_reasons, compute_risk
from .validators.orchestrator import run_validators

NEUTRAL_P_BERT = 0.5


@dataclass
class DetectionOutcome:
    request_id: str
    risk_score: Optional[float]
    category: Optional[str]
    reasons: list = field(default_factory=list)
    alternatives: list = field(default_factory=list)
    degraded_sources: list = field(default_factory=list)
    processing_ms: int = 0
    model_version: str = ""

    def to_api_response(self) -> dict:
        return {
            "request_id": self.request_id,
            "risk_score": self.risk_score,
            "category": self.category,
            "reasons": self.reasons,
            "alternatives": self.alternatives,
            "degraded_sources": self.degraded_sources,
            "processing_ms": self.processing_ms,
            "model_version": self.model_version,
        }


async def run_detection_pipeline(
    *,
    channel: str,
    text: Optional[str],
    ocr_text: Optional[str] = None,
    company: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    on_progress: Optional[any] = None,
) -> DetectionOutcome:
    start = time.perf_counter()

    async def _notify_progress(stage: str, message: str, percent: int = 0):
        if on_progress:
            try:
                res = on_progress(stage, message, percent)
                import inspect
                if inspect.isawaitable(res):
                    await res
            except Exception:
                pass

    await _notify_progress("init", "Memulai inisialisasi analisis lowongan...", 10)

    effective_text = text or ocr_text

    if effective_text and not is_model_loaded():
        raise ModelNotReadyError("Model klasifikasi belum siap dimuat. Coba lagi sesaat lagi.")

    ner_results = []
    if effective_text:
        await _notify_progress("ner", "Mengekstraksi entitas teks menggunakan IndoBERT NER...", 25)
        ner_results = await run_ner(effective_text)

    processed_data = process_job_text(effective_text, ner_entities=ner_results) if effective_text else None
    text_clean_no_contact = processed_data["text_clean_no_contact"] if processed_data else ""
    text_clean_with_contact = processed_data["text_clean_with_contact"] if processed_data else (effective_text or "")


    # Anonimisasi NIK dan nama untuk teks yang akan disimpan di DB
    anonymized = anonymize_text(text_clean_with_contact) if text_clean_with_contact else None
    text_to_store = anonymized.anonymized_text if anonymized else text_clean_with_contact

    feature_reasons = []
    features = None
    if processed_data is not None:
        extracted_feats = extract_entities_and_features(
            text_clean_no_contact,
            emails=processed_data["extracted_emails"],
            phones=processed_data["extracted_phones"],
            urls=processed_data["extracted_urls"],
            companies=processed_data["extracted_companies"],
        )
        feature_reasons = extracted_feats["reasons"]
        features = {
            "extracted_phones": processed_data["extracted_phones"],
            "extracted_emails": processed_data["extracted_emails"],
            "extracted_companies": processed_data["extracted_companies"],
            "extracted_urls": processed_data["extracted_urls"],
            "company_source": "ner_and_heuristic" if ner_results else "heuristic_prefix",
            "digit_count": extracted_feats["digit_count"],
            "special_char_ratio": extracted_feats["special_char_ratio"],
            "suspicious_keyword_count": extracted_feats["suspicious_keyword_count"],
            "nik_found_count": anonymized.nik_found_count if anonymized else 0,
            "names_neutralized_count": anonymized.names_neutralized_count if anonymized else 0,
        }

    # Model inference: selalu pakai text_clean_no_contact (tanpa kontak / sudah di-mask)
    await _notify_progress("bert", "Menganalisis probabilitas penipuan dengan model IndoBERT...", 45)
    if text_clean_no_contact:
        p_bert = await predict_fraud_probability(text_clean_no_contact)
    elif text_to_store:
        p_bert = await predict_fraud_probability(text_to_store)
    else:
        p_bert = NEUTRAL_P_BERT

    extracted_companies = processed_data["extracted_companies"] if processed_data else []
    extracted_phones = processed_data["extracted_phones"] if processed_data else []
    extracted_emails = processed_data["extracted_emails"] if processed_data else []

    company_to_validate = company or (extracted_companies[0] if extracted_companies else None)
    phone_to_validate = phone or (extracted_phones[0] if extracted_phones else None)
    email_to_validate = email or (extracted_emails[0] if extracted_emails else None)

    await _notify_progress("validation", "Memverifikasi legalitas perusahaan, nomor kontak, & email...", 70)
    cache = VerificationCache(redis_client)
    validator_output = await run_validators(
        company=company_to_validate,
        phone=phone_to_validate,
        email=email_to_validate,
        db=db,
        cache=cache,
    )

    await _notify_progress("scoring", "Menghitung skor risiko & rekomendasi alternatif...", 88)
    risk = compute_risk(
        p_bert=p_bert,
        v_company=validator_output.v_company,
        v_phone=validator_output.v_phone,
        v_email=validator_output.v_email,
    )
    reasons = build_reasons(
        p_bert=p_bert,
        validator_details=validator_output.details,
        category=risk.category,
        feature_reasons=feature_reasons,
    )

    alternatives = []
    if risk.category in ("sedang", "tinggi"):
        alt_repo = JobAlternativeRepository(db)
        alt_records = await alt_repo.get_active(limit=3)
        alternatives = [
            {"company": alt.company, "title": alt.title, "url": alt.url}
            for alt in alt_records
        ]

    processing_ms = int((time.perf_counter() - start) * 1000)

    await _notify_progress("complete", "Analisis selesai.", 100)
    repo = DetectionRepository(db)
    record = await repo.create(
        channel=channel,
        text_input=text_to_store,
        ocr_text=ocr_text,
        features=features,
        p_bert=p_bert,
        v_company=validator_output.v_company,
        v_phone=validator_output.v_phone,
        v_email=validator_output.v_email,
        risk_score=risk.risk_score,
        category=risk.category,
        reasons=reasons,
        degraded_sources=validator_output.degraded_sources,
        processing_ms=processing_ms,
        model_version=settings.model_version,
    )

    return DetectionOutcome(
        request_id=record.id,
        risk_score=record.risk_score,
        category=record.category,
        reasons=record.reasons,
        alternatives=alternatives,
        degraded_sources=record.degraded_sources,
        processing_ms=record.processing_ms,
        model_version=record.model_version,
    )
