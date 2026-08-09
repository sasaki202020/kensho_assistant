from __future__ import annotations

from datetime import date, datetime
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import re

from .value_parser import extract_yen_amounts, max_individual_value


HIGH_VALUE_CATEGORIES = (
    "車", "自動車", "バイク", "現金", "金券", "商品券", "海外旅行", "旅行券",
    "国内旅行", "パソコン", "PC", "スマートフォン", "大型家電", "高級時計", "ブランド",
)
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid"}
APPLICATION_MODES = (
    "AUTO_FILL_AVAILABLE",
    "MANUAL_WEB_FORM",
    "SNS_MANUAL",
    "INSTAGRAM_MANUAL",
    "X_MANUAL",
    "LINE_MANUAL",
    "MEMBER_REGISTRATION_REQUIRED",
    "PURCHASE_REQUIRED",
    "LOGIN_REQUIRED",
    "REVIEW_REQUIRED",
    "UNSUPPORTED",
)
APPLICATION_MODE_LABELS = {
    "AUTO_FILL_AVAILABLE": "入力補助可能",
    "MANUAL_WEB_FORM": "手動フォーム",
    "SNS_MANUAL": "SNSで手動応募",
    "INSTAGRAM_MANUAL": "Instagramで手動応募",
    "X_MANUAL": "Xで手動応募",
    "LINE_MANUAL": "LINEで手動応募",
    "MEMBER_REGISTRATION_REQUIRED": "会員登録が必要",
    "PURCHASE_REQUIRED": "購入が必要",
    "LOGIN_REQUIRED": "ログインが必要",
    "REVIEW_REQUIRED": "条件確認が必要",
    "UNSUPPORTED": "対応外フォーム",
}
APPLICATION_MODE_ACTIONS = {
    "AUTO_FILL_AVAILABLE": "応募準備",
    "MANUAL_WEB_FORM": "応募ページを開く",
    "SNS_MANUAL": "応募ページを開く",
    "INSTAGRAM_MANUAL": "応募ページを開く",
    "X_MANUAL": "応募ページを開く",
    "LINE_MANUAL": "応募ページを開く",
    "MEMBER_REGISTRATION_REQUIRED": "会員登録ページを開く",
    "PURCHASE_REQUIRED": "条件を見る",
    "LOGIN_REQUIRED": "ログインページを開く",
    "REVIEW_REQUIRED": "確認する",
    "UNSUPPORTED": "条件を見る",
}


def _text(row: Mapping[str, object]) -> str:
    return " ".join(str(row.get(key, "") or "") for key in ("campaign_name", "prize", "description", "category", "eligibility_summary", "notes", "status"))


def _truthy(value: object) -> bool:
    return str(value or "").strip().casefold() in {"true", "yes", "1", "必須", "required"}


def application_mode(row: Mapping[str, object]) -> str:
    """Return the safest user-facing application route for a discovered campaign.

    Discovery and application capability are intentionally separate. A campaign
    may remain visible while its route is manual or blocked; only an explicitly
    inspected READY_FOR_FILL form is eligible for the existing fill queue.
    """
    status = str(row.get("status", "") or "").strip().upper()
    text = _text(row).casefold()
    readiness = str(row.get("form_readiness_status", "") or "").strip().upper()

    if _truthy(row.get("purchase_required")) or status == "PURCHASE_REQUIRED" or any(keyword in text for keyword in ("購入必須", "購入条件", "購入時に", "購入者限定")):
        return "PURCHASE_REQUIRED"
    if status == "LINE_ACTION_REQUIRED" or _truthy(row.get("line_required")) or "line応募" in text:
        return "LINE_MANUAL"
    if status == "X_ACTION_REQUIRED" or status == "TWITTER_ACTION_REQUIRED" or _truthy(row.get("x_required")):
        return "X_MANUAL"
    if status == "INSTAGRAM_ACTION_REQUIRED" or "instagram" in text or "インスタグラム" in text:
        return "INSTAGRAM_MANUAL"
    if _truthy(row.get("sns_required")) or status == "SNS_ACTION_REQUIRED" or any(keyword in text for keyword in ("sns応募", "sns必須", "フォローして応募")):
        return "SNS_MANUAL"
    if status == "MEMBER_REGISTRATION_REQUIRED" or _truthy(row.get("account_required")) or any(keyword in text for keyword in ("会員登録必須", "会員登録が必要", "会員登録後")):
        return "MEMBER_REGISTRATION_REQUIRED"
    if status == "LOGIN_REQUIRED" or "ログイン必須" in text or "ログインが必要" in text:
        return "LOGIN_REQUIRED"
    if readiness == "NO_FORM" or status in {"UNSUPPORTED", "NO_FORM"}:
        return "UNSUPPORTED"
    if readiness == "READY_FOR_FILL":
        return "AUTO_FILL_AVAILABLE"
    if readiness == "REVIEW_ONLY":
        return "MANUAL_WEB_FORM"
    if readiness:
        return "REVIEW_REQUIRED"
    if status in {"SAFE_TO_FILL", "APPROVED", "PREPARED"}:
        return "REVIEW_REQUIRED"
    return "MANUAL_WEB_FORM"


def canonical_campaign_key(row: Mapping[str, object]) -> str:
    raw_url = str(row.get("official_campaign_url_raw", "") or row.get("official_campaign_url", "") or row.get("resolved_entry_url", "") or row.get("entry_url", ""))
    parsed = urlsplit(raw_url.strip())
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.casefold() not in TRACKING_PARAMS]
    canonical_url = urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path.rstrip("/"), urlencode(sorted(query)), "")) if parsed.scheme else ""
    pieces = [canonical_url, str(row.get("provider", "") or "").strip().casefold(), str(row.get("campaign_name", "") or "").strip().casefold(), str(row.get("prize", "") or "").strip().casefold(), str(row.get("deadline", "") or "").strip()]
    return "|".join(pieces)


def _parse_manual(row: Mapping[str, object]) -> int | None:
    raw = row.get("manual_value_yen", row.get("explicit_value_yen", ""))
    try:
        value = int(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _deadline_days(value: object) -> int | None:
    raw = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
        try:
            return (datetime.strptime(raw[:10] if fmt != "%Y年%m月%d日" else raw, fmt).date() - date.today()).days
        except ValueError:
            continue
    return None


def _priority(row: Mapping[str, object], value: int | None, review_status: str) -> tuple[int, list[str]]:
    reasons: list[str] = []
    if value is None:
        price_points = 15 if review_status == "NEEDS_REVIEW" else 0
    elif value >= 1_000_000:
        price_points = 35
    elif value >= 300_000:
        price_points = 30
    elif value >= 100_000:
        price_points = 24
    elif value >= 50_000:
        price_points = 18
    elif value >= 30_000:
        price_points = 12
    else:
        price_points = 0
    if price_points:
        reasons.append(f"賞品価値 +{price_points}")

    try:
        winners = int(re.sub(r"[^0-9]", "", str(row.get("winner_count", ""))) or "0")
    except ValueError:
        winners = 0
    winner_points = min(12, max(0, winners))
    if winner_points:
        reasons.append(f"当選人数 +{winner_points}")

    friction = 20
    friction_reasons = (("purchase_required", "購入必須"), ("account_required", "会員登録必須"), ("sns_required", "SNS必須"), ("free_text_required", "自由記述必須"))
    for field, label in friction_reasons:
        if str(row.get(field, "")).casefold() in {"true", "yes", "1", "必須"}:
            friction -= {"purchase_required": 7, "account_required": 4, "sns_required": 6, "free_text_required": 3}[field]
            reasons.append(f"{label}で減点")
    reasons.append(f"応募の簡単さ +{max(0, friction)}")

    confidence_points = 10 if review_status == "CONFIRMED" else 5 if review_status == "NEEDS_REVIEW" else 0
    if confidence_points:
        reasons.append(f"価格情報 +{confidence_points}")
    url_points = 5 if row.get("official_campaign_url_raw") or row.get("resolved_entry_url") or row.get("entry_url") else 0
    if url_points:
        reasons.append(f"公式URL確認 +{url_points}")
    eligibility_points = 5 if row.get("eligibility_summary") else 0
    if eligibility_points:
        reasons.append(f"応募条件確認 +{eligibility_points}")
    days = _deadline_days(row.get("deadline"))
    deadline_points = 6 if days is not None and 0 <= days <= 7 else 4 if days is not None and days > 7 else 0
    if deadline_points:
        reasons.append(f"締切 +{deadline_points}")
    return min(100, price_points + winner_points + friction + confidence_points + url_points + eligibility_points + deadline_points), reasons


def assess_campaign(row: Mapping[str, object], threshold_yen: int = 30_000) -> dict[str, object]:
    text = _text(row)
    manual = _parse_manual(row)
    parsed = extract_yen_amounts(text) if manual is None else []
    value = manual if manual is not None else max_individual_value(parsed)
    basis = "manual" if manual is not None else "explicit_text" if value is not None else "unknown"
    category_candidate = any(category.casefold() in text.casefold() for category in HIGH_VALUE_CATEGORIES)
    review_status = "CONFIRMED" if value is not None and value >= threshold_yen else "NEEDS_REVIEW" if value is None and category_candidate else "UNKNOWN"
    is_high_value = bool((value is not None and value >= threshold_yen) or review_status == "NEEDS_REVIEW" or str(row.get("high_value_manual", "")).casefold() in {"true", "1", "yes"})
    score, reasons = _priority(row, value, review_status)
    result = dict(row)
    result.update({
        "official_campaign_url_raw": row.get("official_campaign_url_raw", row.get("resolved_entry_url", row.get("entry_url", ""))),
        "canonical_campaign_key": canonical_campaign_key(row),
        "explicit_value_yen": value if basis == "explicit_text" else "",
        "estimated_value_yen": "",
        "max_individual_prize_value_yen": value or "",
        "value_basis": "category_candidate" if value is None and category_candidate else basis,
        "value_confidence": "high" if review_status == "CONFIRMED" else "medium" if review_status == "NEEDS_REVIEW" else "low",
        "value_review_status": review_status,
        "is_high_value": is_high_value,
        "priority_score": score,
        "priority_reasons": reasons,
        "priority_label": "応募優先度スコア",
    })
    mode = application_mode(result)
    result.update({
        "discovery_status": "DISPLAY" if is_high_value else "HIDDEN_NOT_HIGH_VALUE",
        "application_mode": mode,
        "application_mode_label": APPLICATION_MODE_LABELS[mode],
        "application_action": APPLICATION_MODE_ACTIONS[mode],
    })
    return result


def filter_high_value_campaigns(rows: list[Mapping[str, object]], threshold_yen: int = 30_000) -> list[dict[str, object]]:
    assessed = [assess_campaign(row, threshold_yen) for row in rows]
    return sorted((row for row in assessed if row["is_high_value"] and str(row.get("status", "")).upper() not in {"EXPIRED", "CLOSED"}), key=lambda row: (-int(row["priority_score"]), str(row.get("deadline", "")), str(row.get("campaign_name", ""))))
