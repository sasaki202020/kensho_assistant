from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Iterable, Mapping

from .campaign_classifier import _normalize
from .models import ClassificationResult, SafetyDecision


BLOCK_STATUS_MAP = {
    "X_CAMPAIGN": "X_ACTION_REQUIRED",
    "INSTAGRAM_CAMPAIGN": "INSTAGRAM_ACTION_REQUIRED",
    "LINE_CAMPAIGN": "LINE_ACTION_REQUIRED",
    "FACEBOOK_CAMPAIGN": "FACEBOOK_ACTION_REQUIRED",
    "APP_REQUIRED": "APP_REQUIRED",
    "LOGIN_REQUIRED": "LOGIN_REQUIRED",
    "MEMBER_REGISTRATION": "MEMBER_REGISTRATION_REQUIRED",
    "AGE_RESTRICTED": "AGE_RESTRICTED",
    "PURCHASE_REQUIRED": "PURCHASE_REQUIRED",
    "RECEIPT_REQUIRED": "RECEIPT_REQUIRED",
    "BARCODE_REQUIRED": "BARCODE_REQUIRED",
    "CAPTCHA_REQUIRED": "CAPTCHA_REQUIRED",
    "REGION_LIMITED": "REGION_LIMITED",
    "CLOSED_CAMPAIGN": "BLOCKED",
}

SAFE_ENTRY_TYPES = {"WEB_FORM", "EASY_ENTRY", "SURVEY", "QUIZ", "SAMPLE"}


def _is_duplicate(campaign: Mapping[str, str], existing_entries: Iterable[Mapping[str, str]]) -> bool:
    target_name = _normalize(campaign.get("campaign_name", ""))
    target_provider = _normalize(campaign.get("provider", ""))
    target_deadline = _normalize(campaign.get("deadline", ""))
    target_campaign_id = _normalize(campaign.get("campaign_id", ""))
    target_entry_url = _normalize(campaign.get("entry_url", ""))
    for row in existing_entries:
        if target_campaign_id and target_campaign_id == _normalize(row.get("campaign_id", "")):
            return True
        if target_entry_url and target_entry_url == _normalize(row.get("entry_url", "")):
            return True
        if (
            target_name
            and target_provider
            and target_deadline
            and target_name == _normalize(row.get("campaign_name", ""))
            and target_provider == _normalize(row.get("provider", ""))
            and target_deadline == _normalize(row.get("deadline", ""))
        ):
            return True
    return False


def _deadline_is_past(deadline: str, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    text = deadline or ""
    if not text:
        return False
    if "本日締切" in text:
        return False
    match = re.search(r"(?:(\d{4})[/-])?(\d{1,2})[/-](\d{1,2})", text)
    if match:
        year = int(match.group(1) or now.year)
        month = int(match.group(2))
        day = int(match.group(3))
        try:
            return datetime(year, month, day) < now.replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            return False
    return False


def evaluate_safety(
    campaign: Mapping[str, str],
    classification: ClassificationResult,
    existing_entries: Iterable[Mapping[str, str]] | None = None,
    now: datetime | None = None,
) -> SafetyDecision:
    existing_entries = list(existing_entries or [])
    if _is_duplicate(campaign, existing_entries):
        return SafetyDecision(
            status="DUPLICATE_ENTRY",
            risk_level="low",
            risk_reason="duplicate entry detected",
            auto_submit_allowed=False,
        )

    if classification.entry_type in BLOCK_STATUS_MAP:
        status = BLOCK_STATUS_MAP[classification.entry_type]
        return SafetyDecision(
            status=status,
            risk_level="high",
            risk_reason=classification.entry_type.lower(),
            auto_submit_allowed=False,
        )

    text = _normalize(" ".join(
        [
            campaign.get("campaign_name", ""),
            campaign.get("prize", ""),
            campaign.get("description", ""),
            campaign.get("entry_type_raw", ""),
            campaign.get("category", ""),
        ]
    ))
    if "自動応募禁止" in text or "bot禁止" in text:
        return SafetyDecision(
            status="AUTO_ENTRY_FORBIDDEN",
            risk_level="high",
            risk_reason="auto entry forbidden by campaign rules",
            auto_submit_allowed=False,
        )
    if _deadline_is_past(campaign.get("deadline", ""), now=now):
        return SafetyDecision(
            status="BLOCKED",
            risk_level="high",
            risk_reason="deadline passed",
            auto_submit_allowed=False,
        )
    if classification.entry_type == "UNKNOWN":
        return SafetyDecision(
            status="RULES_UNCLEAR",
            risk_level="medium",
            risk_reason="entry type could not be determined",
            auto_submit_allowed=False,
        )
    if classification.entry_type not in SAFE_ENTRY_TYPES:
        return SafetyDecision(
            status="NEEDS_HUMAN_REVIEW",
            risk_level="medium",
            risk_reason=f"review needed for {classification.entry_type}",
            auto_submit_allowed=False,
        )
    return SafetyDecision(
        status="SAFE_TO_FILL",
        risk_level="low",
        risk_reason="safe web form candidate",
        auto_submit_allowed=True,
    )

