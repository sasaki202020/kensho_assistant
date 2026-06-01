from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import DetectedField


MAJOR_FIELDS = {
    "email",
    "email_confirm",
    "full_name",
    "last_name",
    "first_name",
    "postal_code",
    "phone",
    "address1",
}
BLOCKED_SAFETY_STATUSES = {
    "X_ACTION_REQUIRED",
    "LINE_ACTION_REQUIRED",
    "INSTAGRAM_ACTION_REQUIRED",
    "APP_REQUIRED",
    "LOGIN_REQUIRED",
    "CAPTCHA_REQUIRED",
    "AGE_RESTRICTED",
    "PURCHASE_REQUIRED",
    "RECEIPT_REQUIRED",
}
SEARCH_TERMS = {"search", "keyword", "keywords", "query", "q", "検索"}


@dataclass
class FormReadiness:
    readiness_status: str
    readiness_score: float
    readiness_reason: str
    major_fields_detected: list[str]
    search_only_detected: bool
    submit_button_detected: bool
    landing_links_detected: bool
    quiz_required: bool = False


def _field_names(fields: Iterable[DetectedField]) -> list[str]:
    return [field.field_name for field in fields]


def _search_only(fields: list[DetectedField]) -> bool:
    if not fields:
        return False
    searchable = 0
    for field in fields:
        text = " ".join([field.name, field.element_id, field.placeholder, field.label]).casefold()
        if any(term in text for term in SEARCH_TERMS):
            searchable += 1
    return searchable == len(fields)


def evaluate_form_readiness(
    *,
    fields: list[DetectedField],
    detected_forms_count: int,
    submit_button_detected: bool,
    landing_links_detected: bool,
    safety_status: str,
    quiz_required: bool = False,
) -> FormReadiness:
    detected_fields = len(fields)
    will_fill_count = sum(1 for field in fields if field.will_fill)
    max_confidence = max((field.confidence for field in fields), default=0.0)
    major_fields = sorted(set(_field_names(fields)) & MAJOR_FIELDS)
    search_only = _search_only(fields)
    unknown_count = sum(1 for field in fields if field.field_name.startswith("unknown"))
    required_age = any(field.field_name == "age" and field.required for field in fields)
    score = round(
        min(
            1.0,
            (0.10 * min(detected_fields, 5))
            + (0.15 * min(will_fill_count, 3))
            + (0.20 if major_fields else 0.0)
            + (0.15 if submit_button_detected else 0.0)
            + (0.10 if max_confidence >= 0.85 else 0.0),
        ),
        2,
    )
    if safety_status in BLOCKED_SAFETY_STATUSES:
        return FormReadiness("BLOCKED_BY_SAFETY", score, f"safety={safety_status}", major_fields, search_only, submit_button_detected, landing_links_detected, quiz_required)
    if quiz_required:
        return FormReadiness("REVIEW_ONLY", score, "クイズ回答が必要なため人間確認", major_fields, search_only, submit_button_detected, landing_links_detected, quiz_required)
    if detected_fields == 0 and landing_links_detected:
        return FormReadiness("LANDING_PAGE", score, "案内ページのみでフォームなし", major_fields, search_only, submit_button_detected, landing_links_detected, quiz_required)
    if detected_fields == 0:
        return FormReadiness("NO_FORM", score, "入力欄なし", major_fields, search_only, submit_button_detected, landing_links_detected, quiz_required)
    if search_only and will_fill_count == 0:
        return FormReadiness("SEARCH_ONLY", score, "検索欄のみ", major_fields, search_only, submit_button_detected, landing_links_detected, quiz_required)
    if max_confidence < 0.75 or unknown_count >= max(1, detected_fields // 2 + detected_fields % 2):
        return FormReadiness("LOW_CONFIDENCE", score, "confidence が低い", major_fields, search_only, submit_button_detected, landing_links_detected, quiz_required)
    if required_age:
        return FormReadiness("REVIEW_ONLY", score, "年齢必須のため自動入力しない", major_fields, search_only, submit_button_detected, landing_links_detected, quiz_required)
    if detected_fields >= 5 and will_fill_count >= 2 and max_confidence >= 0.85 and major_fields and submit_button_detected:
        return FormReadiness("READY_FOR_FILL", score, "主要項目と送信ボタンを確認", major_fields, search_only, submit_button_detected, landing_links_detected, quiz_required)
    if detected_fields and (will_fill_count <= 1 or not major_fields):
        return FormReadiness("REVIEW_ONLY", score, "主要項目または入力予定が不足", major_fields, search_only, submit_button_detected, landing_links_detected, quiz_required)
    return FormReadiness("UNKNOWN", score, "判定保留", major_fields, search_only, submit_button_detected, landing_links_detected, quiz_required)


def is_likely_entry_form(readiness: FormReadiness) -> bool:
    return readiness.readiness_status == "READY_FOR_FILL"
