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
from .bert_infer import is_model_loaded, predict_fraud_probability
from .entity_extraction import extract_entities
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
    company: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
) -> DetectionOutcome:
    start = time.perf_counter()

    if text and not is_model_loaded():
        raise ModelNotReadyError("Model klasifikasi belum siap dimuat. Coba lagi sesaat lagi.")

    entities = extract_entities(text) if text else None

    anonymized = anonymize_text(text) if text else None
    text_to_store = anonymized.anonymized_text if anonymized else text

    features = None
    if entities is not None:
        features = {
            "extracted_phones": entities.phones,
            "extracted_emails": entities.emails,
            "extracted_companies": entities.companies,
            "company_source": entities.company_source,
            "nik_found_count": anonymized.nik_found_count if anonymized else 0,
            "names_neutralized_count": anonymized.names_neutralized_count if anonymized else 0,
        }

    if text_to_store:
        p_bert = await predict_fraud_probability(text_to_store)
    else:
        p_bert = NEUTRAL_P_BERT

    company_to_validate = company or (entities.companies[0] if entities and entities.companies else None)
    phone_to_validate = phone or (entities.phones[0] if entities and entities.phones else None)
    email_to_validate = email or (entities.emails[0] if entities and entities.emails else None)

    cache = VerificationCache(redis_client)
    validator_output = await run_validators(
        company=company_to_validate,
        phone=phone_to_validate,
        email=email_to_validate,
        db=db,
        cache=cache,
    )

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

    repo = DetectionRepository(db)
    record = await repo.create(
        channel=channel,
        text_input=text_to_store,
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
