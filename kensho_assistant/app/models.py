from __future__ import annotations

from dataclasses import dataclass, field


CAMPAIGN_HEADERS = [
    "campaign_id",
    "source",
    "campaign_name",
    "prize",
    "winner_count",
    "provider",
    "deadline",
    "knshow_url",
    "entry_url",
    "resolved_entry_url",
    "resolved_domain",
    "resolve_status",
    "resolve_reason",
    "resolved_at",
    "form_readiness_status",
    "form_readiness_score",
    "form_readiness_reason",
    "inspected_at",
    "research_keyword",
    "research_category",
    "research_source",
    "discovered_at",
    "opportunity_score",
    "opportunity_rank",
    "opportunity_reason",
    "risk_level",
    "risk_reasons",
    "recommendation_reason",
    "next_action",
    "description",
    "category",
    "entry_type_raw",
    "collected_at",
    "status",
    "notes",
    "selected_by_user",
    "selected_at",
    "selection_reason",
    "excluded_by_user",
    "excluded_reason",
]

ENTRY_HEADERS = [
    "entry_id",
    "campaign_id",
    "source",
    "campaign_name",
    "prize",
    "winner_count",
    "provider",
    "deadline",
    "knshow_url",
    "entry_url",
    "entry_type",
    "risk_level",
    "risk_reason",
    "auto_submit_allowed",
    "status",
    "submitted_at",
    "screenshot_before",
    "screenshot_after",
    "notes",
    "created_at",
    "updated_at",
]

ENTRY_HISTORY_HEADERS = [
    "campaign_id",
    "title",
    "source_site",
    "url",
    "prize",
    "deadline",
    "applied_at",
    "result_check_date",
    "status",
    "newsletter_status",
    "pii_used",
    "memo",
    "duplicate_key",
    "created_at",
    "updated_at",
]

LATER_QUEUE_HEADERS = [
    "id",
    "title",
    "site_name",
    "url",
    "normalized_url",
    "duplicate_key",
    "deadline",
    "status",
    "source_type",
    "safety_memo",
    "review_note",
    "created_at",
    "updated_at",
]


@dataclass
class ClassificationResult:
    entry_type: str
    matched_terms: list[str] = field(default_factory=list)
    confidence: str = "rule"


@dataclass
class SafetyDecision:
    status: str
    risk_level: str
    risk_reason: str
    auto_submit_allowed: bool
    notes: str = ""


@dataclass
class DetectedField:
    field_name: str
    selector: str
    label: str
    kind: str
    input_type: str = ""
    aria_label: str = ""
    placeholder: str = ""
    name: str = ""
    element_id: str = ""
    nearby_text: str = ""
    detected_from: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    required: bool = False
    will_fill: bool = False
    value_preview: str = ""
    skip_reason: str = ""


@dataclass
class FillResult:
    campaign_id: str
    filled_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    consent_fields: list[str] = field(default_factory=list)
    screenshot_before: str = ""
    screenshot_after: str = ""
    submitted: bool = False
    decision: str = ""
    notes: str = ""


@dataclass
class EntryHistoryRecord:
    campaign_id: str = ""
    title: str = ""
    source_site: str = ""
    url: str = ""
    prize: str = ""
    deadline: str = ""
    applied_at: str = ""
    result_check_date: str = ""
    status: str = ""
    newsletter_status: str = "unknown"
    pii_used: bool = False
    memo: str = ""
    duplicate_key: str = ""
    created_at: str = ""
    updated_at: str = ""
