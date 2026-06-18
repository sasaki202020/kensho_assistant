from __future__ import annotations

from typing import Any

from field_assessment_ai.services.common import clamp, normalize_text

from .common import (
    CONSUMER_DISCLAIMER,
    CheckAnalysis,
    build_consumer_market_links,
    build_consumer_market_query,
    confidence_label_from_score,
    detect_quote_missing_points,
    unique_texts,
    verdict_from_score,
)


def _text_blob(payload: dict[str, Any]) -> str:
    parts = [
        payload.get("offered_price"),
        payload.get("work_fee"),
        payload.get("disposal_fee"),
        payload.get("outcall_fee"),
        payload.get("appraisal_fee"),
        payload.get("cancellation_fee"),
        payload.get("home_appliance_recycling_fee"),
        payload.get("additional_charge_conditions"),
        payload.get("package_price"),
        payload.get("same_day_extra_charge"),
        payload.get("estimate_sheet_present"),
        payload.get("memo"),
    ]
    return " ".join(normalize_text(str(part)) for part in parts if normalize_text(str(part)))


def analyze_quote_check(payload: dict[str, Any]) -> CheckAnalysis:
    offered_price = int(payload.get("offered_price") or 0)
    work_fee = int(payload.get("work_fee") or 0)
    disposal_fee = int(payload.get("disposal_fee") or 0)
    outcall_fee = int(payload.get("outcall_fee") or 0)
    appraisal_fee = int(payload.get("appraisal_fee") or 0)
    cancellation_fee = int(payload.get("cancellation_fee") or 0)
    home_appliance_recycling_fee = payload.get("home_appliance_recycling_fee")
    package_price = int(payload.get("package_price") or 0)
    same_day_extra_charge = int(payload.get("same_day_extra_charge") or 0)
    estimate_sheet_present = bool(payload.get("estimate_sheet_present"))
    additional_charge_conditions = normalize_text(payload.get("additional_charge_conditions"))
    memo = normalize_text(payload.get("memo"))

    blob = _text_blob(payload)
    query = build_consumer_market_query("不用品回収", memo, additional_charge_conditions, "見積もり")
    market_links = build_consumer_market_links(query or "不用品回収 見積もり")
    red_flags = detect_quote_missing_points(blob)

    missing_info = unique_texts(
        [
            "業者提示額" if offered_price <= 0 else "",
            "作業費" if work_fee <= 0 else "",
            "処分費" if disposal_fee <= 0 else "",
            "出張費" if outcall_fee <= 0 else "",
            "査定料" if appraisal_fee <= 0 else "",
            "キャンセル料" if cancellation_fee <= 0 else "",
            "家電リサイクル料金" if home_appliance_recycling_fee in (None, "") else "",
            "追加料金条件" if not additional_charge_conditions else "",
            "パック料金" if package_price <= 0 else "",
            "当日追加請求の有無" if same_day_extra_charge <= 0 else "",
            "見積書・明細の有無" if not estimate_sheet_present else "",
        ]
    )

    next_actions = unique_texts(
        [
            "見積書と明細を紙またはメールで受け取る",
            "追加料金の条件を確認する" if not additional_charge_conditions else "",
            "家電リサイクル対象の扱いを確認する" if home_appliance_recycling_fee in (None, "") else "",
            "当日追加請求の内訳を確認する" if same_day_extra_charge else "",
            "家族と確認してから判断する" if not estimate_sheet_present or same_day_extra_charge else "",
            "188へ相談する" if not estimate_sheet_present or same_day_extra_charge else "",
        ]
    )

    official_categories = unique_texts(
        [
            "不用品回収",
            "一般廃棄物収集運搬",
            "家電リサイクル",
            "クーリングオフ",
            "消費者ホットライン188",
            "訪問購入" if offered_price > 0 else "",
        ]
    )

    score = 20
    if not estimate_sheet_present:
        score += 22
    if not additional_charge_conditions:
        score += 16
    if same_day_extra_charge:
        score += min(22, 10 + int(same_day_extra_charge / 5000))
    if cancellation_fee:
        score += 8
    if home_appliance_recycling_fee in (None, ""):
        score += 10
    if package_price and same_day_extra_charge and same_day_extra_charge > package_price:
        score += 18
    if offered_price > 0 and package_price > 0 and offered_price > package_price * 2:
        score += 12
    if any(flag in blob for flag in ["口頭のみ", "見積書なし", "明細なし"]):
        score += 10
    if any(flag in blob for flag in ["当日追加請求", "追加料金", "別途"]):
        score += 10
    score = int(clamp(score, 0, 100))

    critical = not estimate_sheet_present and (same_day_extra_charge > 0 or not additional_charge_conditions)
    strong_signal = same_day_extra_charge > 0 or not estimate_sheet_present or not additional_charge_conditions
    verdict = verdict_from_score(score, critical=critical, strong_signal=strong_signal)
    if not estimate_sheet_present or same_day_extra_charge > package_price > 0:
        verdict = "相談推奨"
    elif verdict == "問題なさそう" and strong_signal:
        verdict = "確認推奨"

    reason = (
        "見積書がなく、追加請求や料金内訳の確認が必要。"
        if not estimate_sheet_present or not additional_charge_conditions
        else "追加料金の条件が見えるため、内容を紙面で確認したい。"
    )
    if same_day_extra_charge > 0:
        reason = "当日追加請求が大きい場合は、即決せず内訳確認が必要。"

    caution_notes = unique_texts(
        [
            f"検出文言: {phrase}" for phrase in red_flags
        ]
        + [
            CONSUMER_DISCLAIMER,
            "相場や料金は参考情報。正確な法律判断はしない。",
            "見積書や明細がない場合は記録を残す。",
        ]
    )

    if home_appliance_recycling_fee in (None, ""):
        caution_notes.append("家電リサイクル対象の有無と料金は必ず確認する。")

    check_points = unique_texts(
        [
            "料金内訳",
            "追加料金条件",
            "見積書の有無",
            "当日追加請求の有無",
            "家電リサイクル料金",
        ]
    )

    photo_requests = unique_texts(
        [
            "見積書の全体",
            "料金内訳の部分",
            "追加料金条件の説明部分",
        ]
    )

    return CheckAnalysis(
        query=query or "不用品回収 見積もり",
        market_links=market_links,
        verdict=verdict,
        reason=reason,
        missing_info=missing_info,
        next_actions=next_actions,
        official_categories=official_categories,
        confidence_score=score,
        confidence_label=confidence_label_from_score(score),
        refusal_category="quote",
        caution_notes=caution_notes,
        extra_photo_requests=photo_requests,
        check_points=check_points,
    )


def build_quote_check_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = analyze_quote_check(payload)
    return {
        "offered_price": int(payload.get("offered_price") or 0) or None,
        "work_fee": int(payload.get("work_fee") or 0) or None,
        "disposal_fee": int(payload.get("disposal_fee") or 0) or None,
        "outcall_fee": int(payload.get("outcall_fee") or 0) or None,
        "appraisal_fee": int(payload.get("appraisal_fee") or 0) or None,
        "cancellation_fee": int(payload.get("cancellation_fee") or 0) or None,
        "home_appliance_recycling_fee": payload.get("home_appliance_recycling_fee"),
        "additional_charge_conditions": normalize_text(payload.get("additional_charge_conditions")) or None,
        "package_price": int(payload.get("package_price") or 0) or None,
        "same_day_extra_charge": int(payload.get("same_day_extra_charge") or 0) or None,
        "estimate_sheet_present": bool(payload.get("estimate_sheet_present")),
        "memo": normalize_text(payload.get("memo")) or None,
        "image_refs_json": list(payload.get("image_refs") or []),
        "market_query": analysis.query,
        "market_links_json": analysis.market_links,
        "caution_points_json": analysis.caution_notes,
        "check_points_json": analysis.check_points,
        "photo_requests_json": analysis.extra_photo_requests,
    }

