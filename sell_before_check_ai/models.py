from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from field_assessment_ai.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ResultCacheMixin:
    market_query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    market_links_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    caution_points_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    check_points_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    photo_requests_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    judgement_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_info_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    next_actions_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    official_info_ids_json: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    reference_links_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    confidence_score_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    refusal_phrase: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_risk_judgement_id: Mapped[int | None] = mapped_column(ForeignKey("risk_judgements.id"), nullable=True)
    latest_confidence_score_id: Mapped[int | None] = mapped_column(ForeignKey("confidence_scores.id"), nullable=True)
    latest_report_id: Mapped[int | None] = mapped_column(ForeignKey("consumer_reports.id"), nullable=True)


class FlyerCheck(Base, TimestampMixin, ResultCacheMixin):
    __tablename__ = "flyer_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    image_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    flyer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcall_fee_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_fee_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    high_price_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    same_day_cash_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    inducement_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConsumerItemCheck(Base, TimestampMixin, ResultCacheMixin):
    __tablename__ = "consumer_item_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    image_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    item_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    condition_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    accessories: Mapped[str | None] = mapped_column(Text, nullable=True)
    offered_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    market_memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_photo_requests_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    check_points_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)


class QuoteCheck(Base, TimestampMixin, ResultCacheMixin):
    __tablename__ = "quote_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    image_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    offered_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disposal_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcall_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    appraisal_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancellation_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_appliance_recycling_fee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    additional_charge_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    package_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    same_day_extra_charge: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimate_sheet_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)


class OfficialInfo(Base, TimestampMixin):
    __tablename__ = "official_infos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_links_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    caution_level: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ConfidenceScore(Base):
    __tablename__ = "confidence_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    check_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    check_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    score_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    factors_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    check_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RiskJudgement(Base):
    __tablename__ = "risk_judgements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    check_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    check_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    judgement_result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_info_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    next_actions_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    official_info_ids_json: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    reference_links_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    confidence_score_id: Mapped[int | None] = mapped_column(ForeignKey("confidence_scores.id"), nullable=True)
    refusal_phrase: Mapped[str | None] = mapped_column(Text, nullable=True)
    caution_notes_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    market_links_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    check_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RefusalPhrase(Base):
    __tablename__ = "refusal_phrases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    phrase: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ConsumerReport(Base, TimestampMixin):
    __tablename__ = "consumer_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    check_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    check_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="json")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    disclaimer: Mapped[str | None] = mapped_column(Text, nullable=True)

