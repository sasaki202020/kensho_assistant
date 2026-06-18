from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SafetyNotice(BaseModel):
    code: str
    severity: Literal["info", "warning", "critical"] = "warning"
    title: str
    message: str
    category: str | None = None
    legal_hint: str | None = None


class PriceRange(BaseModel):
    minimum: int
    median: int
    maximum: int


class AnalysisCandidate(BaseModel):
    name: str
    category: str | None = None
    condition: str | None = None
    rank_candidates: list[str] = Field(default_factory=list)
    estimated_value_range: PriceRange
    check_points: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reasoning: str | None = None


class AnalysisRequest(BaseModel):
    item_id: int | None = None
    name: str | None = None
    category: str | None = None
    brand: str | None = None
    model_number: str | None = None
    condition_note: str | None = None
    quantity: int | None = 1
    image_ids: list[int] = Field(default_factory=list)
    memo: str | None = None


class AnalysisResponse(BaseModel):
    source: str
    input_summary: str
    suggested_category: str | None = None
    suggested_condition: str | None = None
    rank_candidates: list[str] = Field(default_factory=list)
    estimated_value_range: PriceRange
    check_points: list[str] = Field(default_factory=list)
    candidate_items: list[AnalysisCandidate] = Field(default_factory=list)
    legal_notices: list[SafetyNotice] = Field(default_factory=list)
    analysis_notes: list[str] = Field(default_factory=list)
    mock_mode: bool = True


class SearchLinkRequest(BaseModel):
    item_id: int | None = None
    product_name: str | None = None
    brand: str | None = None
    model_number: str | None = None
    category: str | None = None
    extra_keywords: list[str] = Field(default_factory=list)


class SearchLinkResponse(BaseModel):
    query: str
    search_links: dict[str, str]
    notes: list[str] = Field(default_factory=list)


class MarketMemoUpsertRequest(BaseModel):
    lowest_price: int | None = None
    median_price: int | None = None
    highest_price: int | None = None
    sold_count: int | None = None
    purchase_price: int | None = None
    shipping_fee: int | None = None
    marketplace_fee: int | None = None
    packing_fee: int | None = None
    disposal_fee_memo: str | None = None
    internal_memo: str | None = None
    search_keyword: str | None = None
    source_urls: list[str] = Field(default_factory=list)


class MarketMemoRead(MarketMemoUpsertRequest):
    model_config = ConfigDict(from_attributes=True)

    item_id: int
    id: int
    created_at: datetime
    updated_at: datetime


class JobCreate(BaseModel):
    title: str
    customer_name: str | None = None
    address: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    status: str = "draft"
    memo: str | None = None
    safety_notes: str | None = None


class JobUpdate(BaseModel):
    title: str | None = None
    customer_name: str | None = None
    address: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    status: str | None = None
    memo: str | None = None
    safety_notes: str | None = None


class ItemCreate(BaseModel):
    job_id: int | None = None
    name: str
    category: str | None = None
    brand: str | None = None
    model_number: str | None = None
    condition_note: str | None = None
    quantity: int = 1
    location_note: str | None = None
    memo: str | None = None
    status: str = "active"
    safety_flags: list[str] = Field(default_factory=list)


class ItemUpdate(BaseModel):
    job_id: int | None = None
    name: str | None = None
    category: str | None = None
    brand: str | None = None
    model_number: str | None = None
    condition_note: str | None = None
    quantity: int | None = None
    location_note: str | None = None
    memo: str | None = None
    status: str | None = None
    safety_flags: list[str] | None = None


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int | None
    name: str
    category: str | None
    brand: str | None
    model_number: str | None
    condition_note: str | None
    quantity: int
    location_note: str | None
    memo: str | None
    status: str
    safety_flags: list[str] = Field(default_factory=list)
    image_count: int = 0
    created_at: datetime
    updated_at: datetime


class ImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    original_filename: str
    stored_filename: str
    relative_path: str
    public_url: str
    thumbnail_url: str | None = None
    mime_type: str | None = None
    file_size_bytes: int
    sort_order: int
    caption: str | None = None
    created_at: datetime


class ItemDetailRead(ItemRead):
    images: list[ImageRead] = Field(default_factory=list)
    market_memo: MarketMemoRead | None = None
    analysis: AnalysisResponse | None = None
    latest_estimate: EstimateRead | None = None
    safety_notices: list[SafetyNotice] = Field(default_factory=list)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    customer_name: str | None
    address: str | None
    contact_name: str | None
    contact_phone: str | None
    status: str
    memo: str | None
    safety_notes: str | None
    item_count: int = 0
    created_at: datetime
    updated_at: datetime


class JobDetailRead(JobRead):
    items: list[ItemRead] = Field(default_factory=list)
    latest_estimate: EstimateRead | None = None
    report_count: int = 0
    safety_notices: list[SafetyNotice] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class CalculationOptions(BaseModel):
    discount_ratio: float = Field(default=0.2, ge=0.0, le=1.0)
    work_fee_override: int | None = None
    disposal_fee_override: int | None = None
    purchase_override: int | None = None


class EstimateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope_type: str
    job_id: int | None
    item_id: int | None
    resale_estimate_min: int | None
    resale_estimate_max: int | None
    purchase_estimate: int | None
    disposal_fee_estimate: int | None
    work_fee_estimate: int | None
    discount_possible_amount: int | None
    final_estimate_guide: int | None
    sale_value_score: int | None
    rank_candidate: str | None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class EstimateResponse(BaseModel):
    estimate: EstimateRead
    analysis: AnalysisResponse | None = None
    market_memo: MarketMemoRead | None = None
    legal_notices: list[SafetyNotice] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class ReportDraftRequest(BaseModel):
    job_id: int
    title: str | None = None
    format: Literal["json", "html"] = "json"


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    title: str
    format: str
    summary: str | None
    content_json: dict[str, Any]
    content_html: str | None
    disclaimer: str | None
    created_at: datetime
    updated_at: datetime


class ReportResponse(BaseModel):
    report: ReportRead
    html: str | None = None
    content_json: dict[str, Any]
    legal_notices: list[SafetyNotice] = Field(default_factory=list)


class JobEstimateResponse(EstimateResponse):
    job: JobRead | JobDetailRead | None = None


class ItemEstimateResponse(EstimateResponse):
    item: ItemRead | ItemDetailRead | None = None


EstimateRead.model_rebuild()
ItemDetailRead.model_rebuild()
JobDetailRead.model_rebuild()
