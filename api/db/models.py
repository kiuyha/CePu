"""Model ORM tabel-tabel utama, sesuai skema dokumen arsitektur."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


JsonVariant = JSON().with_variant(JSONB(), "postgresql")


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    channel: Mapped[str] = mapped_column(String(10))  # "web" | "wa"
    text_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    features: Mapped[dict | None] = mapped_column(JsonVariant, nullable=True)

    p_bert: Mapped[float | None] = mapped_column(Float, nullable=True)
    v_company: Mapped[float | None] = mapped_column(Float, nullable=True)
    v_phone: Mapped[float | None] = mapped_column(Float, nullable=True)
    v_email: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    category: Mapped[str | None] = mapped_column(String(10), nullable=True)

    reasons: Mapped[list | None] = mapped_column(JsonVariant, nullable=True)
    degraded_sources: Mapped[list | None] = mapped_column(JsonVariant, nullable=True)

    processing_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    channel: Mapped[str] = mapped_column(String(10))
    contact_optional: Mapped[str | None] = mapped_column(String(255), nullable=True)

    suspect_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    suspect_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suspect_company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    message_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending")

    reviewer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntelBlacklist(Base):
    __tablename__ = "intel_blacklist"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    kind: Mapped[str] = mapped_column(String(10))
    value_hash: Mapped[str] = mapped_column(String(64), index=True)
    value_masked: Mapped[str] = mapped_column(String(255))
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    sources: Mapped[list | None] = mapped_column(JsonVariant, nullable=True)
    active: Mapped[bool] = mapped_column(default=False)


class CompanyRegistry(Base):
    __tablename__ = "company_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    name_norm: Mapped[str] = mapped_column(String(255), index=True, unique=True)
    legal_name: Mapped[str] = mapped_column(String(255))
    ahu_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registered: Mapped[bool | None] = mapped_column(nullable=True)
    is_flagged_scam: Mapped[bool] = mapped_column(default=False)
    aliases: Mapped[list | None] = mapped_column(JsonVariant, nullable=True)
    linkedin_verified: Mapped[bool | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class JobAlternative(Base):
    __tablename__ = "job_alternatives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    company: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(500))
    verified_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    active: Mapped[bool] = mapped_column(default=True)


class WaSession(Base):
    __tablename__ = "wa_sessions"

    phone_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    current_state: Mapped[str] = mapped_column(String(30), default="idle")
    context: Mapped[dict | None] = mapped_column(JsonVariant, nullable=True)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EducationArticle(Base):
    __tablename__ = "education_articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    body_md: Mapped[str] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JsonVariant, nullable=True)
    published: Mapped[bool] = mapped_column(default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DisposableDomain(Base):
    __tablename__ = "disposable_domains"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    source: Mapped[str] = mapped_column(String(100), default="github/disposable-email-domains")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

