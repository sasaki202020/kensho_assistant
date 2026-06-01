from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Mapping

import yaml

from .models import ClassificationResult
from .paths import RULES_YAML
from .product_guardrails import DEFAULT_RULES


def _normalize(value: str) -> str:
    return re.sub(r"[\s\u3000]+", "", (value or "").casefold())


@lru_cache(maxsize=1)
def load_rules(path: str | Path | None = None) -> dict:
    rules_path = Path(path) if path else RULES_YAML
    if rules_path.exists():
        with rules_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        merged = dict(DEFAULT_RULES)
        merged.update(loaded)
        if "entry_type_keywords" in loaded:
            merged["entry_type_keywords"] = {**DEFAULT_RULES["entry_type_keywords"], **loaded["entry_type_keywords"]}
        if "blocked_terms" in loaded:
            merged["blocked_terms"] = {**DEFAULT_RULES["blocked_terms"], **loaded["blocked_terms"]}
        return merged
    return dict(DEFAULT_RULES)


def _contains_any(text: str, keywords: list[str]) -> list[str]:
    hits = []
    for keyword in keywords:
        if _normalize(keyword) in text:
            hits.append(keyword)
    return hits


def classify_campaign(campaign: Mapping[str, str], rules: dict | None = None) -> ClassificationResult:
    rules = rules or load_rules()
    fields = [
        campaign.get("entry_type_raw", ""),
        campaign.get("campaign_name", ""),
        campaign.get("prize", ""),
        campaign.get("description", ""),
        campaign.get("category", ""),
        campaign.get("provider", ""),
        campaign.get("entry_url", ""),
        campaign.get("knshow_url", ""),
    ]
    text = _normalize(" ".join(fields))
    raw_type = _normalize(campaign.get("entry_type_raw", ""))

    order = [
        "X_CAMPAIGN",
        "INSTAGRAM_CAMPAIGN",
        "LINE_CAMPAIGN",
        "FACEBOOK_CAMPAIGN",
        "APP_REQUIRED",
        "LOGIN_REQUIRED",
        "MEMBER_REGISTRATION",
        "BARCODE_REQUIRED",
        "RECEIPT_REQUIRED",
        "PURCHASE_REQUIRED",
        "AGE_RESTRICTED",
        "CAPTCHA_REQUIRED",
        "REGION_LIMITED",
        "CLOSED_CAMPAIGN",
        "SAMPLE",
        "QUIZ",
        "SURVEY",
        "EASY_ENTRY",
        "WEB_FORM",
    ]
    for entry_type in order:
        keywords = rules["entry_type_keywords"].get(entry_type, [])
        hits = _contains_any(text, keywords) + _contains_any(raw_type, keywords)
        if hits:
            return ClassificationResult(entry_type=entry_type, matched_terms=list(dict.fromkeys(hits)))

    if "応募する" in campaign.get("campaign_name", "") or "フォーム" in campaign.get("description", ""):
        return ClassificationResult(entry_type="WEB_FORM", matched_terms=["フォーム"])

    return ClassificationResult(entry_type="UNKNOWN", matched_terms=[])
