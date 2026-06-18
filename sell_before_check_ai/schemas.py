from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from field_assessment_ai.schemas import SafetyNotice


class ImageRefInput(BaseModel):
    original_filename: str
    stored_filename: str
    relative_path: str
    public_url: str
    mime_type: str | None = None
    file_size_bytes: int = 0
    sort_order: int = 0
    caption: str | None = None


class ImageUploadResponse(ImageRefInput):
    check_type: str | None = None
    check_id: int | None = None


class OfficialInfoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    title: str
    summary: str | None = None
    content: str | None = None
    reference_links: list[str] = Field(default_factory=list)
    caution_level: str | None = None


class ConfidenceScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_type: str
    check_id: int
    score_value: int
    score_label: str | None = None
    reason: str | None = None
    factors: list[str] = Field(default_factory=list)
    check_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RiskJudgementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_type: str
    check_id: int
    judgement_result: str
    reason: str | None = None
    missing_info: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    official_info_ids: list[int] = Field(default_factory=list)
    reference_links: list[str] = Field(default_factory=list)
    confidence_score_id: int | None = None
    refusal_phrase: str | None = None
    caution_notes: list[str] = Field(default_factory=list)
    market_links: dict[str, str] = Field(default_factory=dict)
    check_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    confidence_score: ConfidenceScoreRead | None = None
    official_infos: list[OfficialInfoRead] = Field(default_factory=list)


class ConsumerReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_type: str
    check_id: int
    title: str
    format: str
    summary: str | None = None
    content_json: dict[str, Any] = Field(default_factory=dict)
    content_html: str | None = None
    disclaimer: str | None = None
    created_at: datetime
    updated_at: datetime


class CheckCommonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_refs: list[ImageRefInput] = Field(default_factory=list)
    market_query: str | None = None
    market_links: dict[str, str] = Field(default_factory=dict)
    caution_points: list[str] = Field(default_factory=list)
    check_points: list[str] = Field(default_factory=list)
    photo_requests: list[str] = Field(default_factory=list)
    judgement_result: str | None = None
    reason: str | None = None
    missing_info: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    official_info_ids: list[int] = Field(default_factory=list)
    reference_links: list[str] = Field(default_factory=list)
    confidence_score_value: int | None = None
    confidence_label: str | None = None
    refusal_phrase: str | None = None
    note_text: str | None = None
    latest_risk_judgement_id: int | None = None
    latest_confidence_score_id: int | None = None
    latest_report_id: int | None = None
    created_at: datetime
    updated_at: datetime
    latest_risk_judgement: RiskJudgementRead | None = None
    latest_confidence_score: ConfidenceScoreRead | None = None
    latest_report: ConsumerReportRead | None = None
    official_infos: list[OfficialInfoRead] = Field(default_factory=list)


class FlyerCheckCreate(BaseModel):
    company_name: str | None = None
    phone_number: str | None = None
    flyer_text: str | None = None
    outcall_fee_text: str | None = None
    cancellation_fee_text: str | None = None
    high_price_text: str | None = None
    same_day_cash_text: str | None = None
    inducement_text: str | None = None
    memo: str | None = None
    image_refs: list[ImageRefInput] = Field(default_factory=list)


class FlyerCheckUpdate(FlyerCheckCreate):
    company_name: str | None = None


class FlyerCheckRead(CheckCommonRead):
    company_name: str | None = None
    phone_number: str | None = None
    flyer_text: str | None = None
    outcall_fee_text: str | None = None
    cancellation_fee_text: str | None = None
    high_price_text: str | None = None
    same_day_cash_text: str | None = None
    inducement_text: str | None = None
    memo: str | None = None


class ItemCheckCreate(BaseModel):
    item_category: str | None = None
    item_name: str | None = None
    brand: str | None = None
    model_number: str | None = None
    condition_note: str | None = None
    accessories: str | None = None
    offered_price: int | None = None
    market_memo: str | None = None
    additional_photo_requests: str | None = None
    check_points: str | None = None
    memo: str | None = None
    image_refs: list[ImageRefInput] = Field(default_factory=list)


class ItemCheckUpdate(ItemCheckCreate):
    item_name: str | None = None


class ItemCheckRead(CheckCommonRead):
    item_category: str | None = None
    item_name: str | None = None
    brand: str | None = None
    model_number: str | None = None
    condition_note: str | None = None
    accessories: str | None = None
    offered_price: int | None = None
    market_memo: str | None = None
    additional_photo_requests_text: str | None = None
    check_points_text: str | None = None
    memo: str | None = None


class QuoteCheckCreate(BaseModel):
    offered_price: int | None = None
    work_fee: int | None = None
    disposal_fee: int | None = None
    outcall_fee: int | None = None
    appraisal_fee: int | None = None
    cancellation_fee: int | None = None
    home_appliance_recycling_fee: str | None = None
    additional_charge_conditions: str | None = None
    package_price: int | None = None
    same_day_extra_charge: int | None = None
    estimate_sheet_present: bool = False
    memo: str | None = None
    image_refs: list[ImageRefInput] = Field(default_factory=list)


class QuoteCheckUpdate(QuoteCheckCreate):
    offered_price: int | None = None


class QuoteCheckRead(CheckCommonRead):
    offered_price: int | None = None
    work_fee: int | None = None
    disposal_fee: int | None = None
    outcall_fee: int | None = None
    appraisal_fee: int | None = None
    cancellation_fee: int | None = None
    home_appliance_recycling_fee: str | None = None
    additional_charge_conditions: str | None = None
    package_price: int | None = None
    same_day_extra_charge: int | None = None
    estimate_sheet_present: bool = False
    memo: str | None = None


class MarketLinkGenerateRequest(BaseModel):
    check_type: str | None = None
    check_id: int | None = None
    product_name: str | None = None
    brand: str | None = None
    model_number: str | None = None
    category: str | None = None
    extra_keywords: list[str] = Field(default_factory=list)


class MarketLinkResponse(BaseModel):
    query: str
    search_links: dict[str, str]
    notes: list[str] = Field(default_factory=list)


class RiskJudgementGenerateRequest(BaseModel):
    check_type: str
    check_id: int


class RiskJudgementGenerateResponse(BaseModel):
    check_type: str
    check_id: int
    judgement: RiskJudgementRead
    check: CheckCommonRead | FlyerCheckRead | ItemCheckRead | QuoteCheckRead
    official_infos: list[OfficialInfoRead] = Field(default_factory=list)
    market_links: dict[str, str] = Field(default_factory=dict)
    hotline_notice: str | None = None


class ConsumerReportResponse(BaseModel):
    report: ConsumerReportRead
    html: str | None = None
    content_json: dict[str, Any] = Field(default_factory=dict)
    legal_notices: list[SafetyNotice] = Field(default_factory=list)


FlyerCheckRead.model_rebuild()
ItemCheckRead.model_rebuild()
QuoteCheckRead.model_rebuild()
RiskJudgementRead.model_rebuild()
CheckCommonRead.model_rebuild()
