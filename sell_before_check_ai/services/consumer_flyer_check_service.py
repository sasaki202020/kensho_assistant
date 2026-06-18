from __future__ import annotations

from typing import Any

from field_assessment_ai.services.common import clamp, normalize_text

from .common import (
    CONSUMER_DISCLAIMER,
    FLYER_ALERT_PHRASES,
    CheckAnalysis,
    build_consumer_market_links,
    build_consumer_market_query,
    confidence_label_from_score,
    detect_flyer_alert_phrases,
    unique_texts,
    verdict_from_score,
)


def _text_blob(payload: dict[str, Any]) -> str:
    parts = [
        payload.get("company_name"),
        payload.get("phone_number"),
        payload.get("flyer_text"),
        payload.get("outcall_fee_text"),
        payload.get("cancellation_fee_text"),
        payload.get("high_price_text"),
        payload.get("same_day_cash_text"),
        payload.get("inducement_text"),
        payload.get("memo"),
    ]
    return " ".join(normalize_text(str(part)) for part in parts if normalize_text(str(part)))


def analyze_flyer_check(payload: dict[str, Any]) -> CheckAnalysis:
    company_name = normalize_text(payload.get("company_name"))
    phone_number = normalize_text(payload.get("phone_number"))
    flyer_text = normalize_text(payload.get("flyer_text"))
    outcall_fee_text = normalize_text(payload.get("outcall_fee_text"))
    cancellation_fee_text = normalize_text(payload.get("cancellation_fee_text"))
    high_price_text = normalize_text(payload.get("high_price_text"))
    same_day_cash_text = normalize_text(payload.get("same_day_cash_text"))
    inducement_text = normalize_text(payload.get("inducement_text"))
    memo = normalize_text(payload.get("memo"))

    blob = _text_blob(payload)
    query = build_consumer_market_query(company_name, flyer_text, inducement_text, memo, ["訪問買取"])
    market_links = build_consumer_market_links(query or "訪問買取")
    alert_hits = detect_flyer_alert_phrases(blob)

    missing_info = unique_texts(
        [
            "業者名" if not company_name else "",
            "電話番号" if not phone_number else "",
            "チラシ文言" if not flyer_text else "",
            "出張費表記" if not outcall_fee_text else "",
            "キャンセル料表記" if not cancellation_fee_text else "",
        ]
    )

    next_actions = unique_texts(
        [
            "業者名と連絡先を控える" if not company_name or not phone_number else "",
            "書面と条件を確認する" if alert_hits else "",
            "家族と確認してから判断する" if alert_hits else "",
            "その場で即決しない" if any(hit in blob for hit in ["即日現金化", "その場で現金", "何でも買います"]) else "",
        ]
    )

    official_categories = unique_texts(
        [
            "訪問購入",
            "クーリングオフ",
            "飛び込み訪問買取",
            "消費者ホットライン188",
            "物品引渡し拒絶" if any(hit in blob for hit in ["即日現金化", "その場で現金"]) else "",
        ]
    )

    score = 18
    score += min(30, len(alert_hits) * 8)
    if company_name:
        score += 8
    if phone_number:
        score += 8
    if outcall_fee_text:
        score += 4
    if cancellation_fee_text:
        score += 4
    if high_price_text:
        score += 4
    if same_day_cash_text:
        score += 6
    if any(hit in blob for hit in ["何でも買います", "即日現金化", "その場で現金"]):
        score += 12
    if len(missing_info) >= 3:
        score += 10
    if len(missing_info) >= 4:
        score += 8
    score = int(clamp(score, 0, 100))

    strong_signal = any(hit in blob for hit in ["何でも買います", "即日現金化", "その場で現金"]) or len(alert_hits) >= 4
    verdict = verdict_from_score(score, critical=len(missing_info) >= 4 and strong_signal, strong_signal=strong_signal)
    if verdict == "問題なさそう" and len(alert_hits) >= 2:
        verdict = "確認推奨"
    if (
        verdict == "相談推奨"
        and company_name
        and phone_number
        and outcall_fee_text
        and cancellation_fee_text
    ):
        verdict = "確認推奨"

    caution_notes = unique_texts(
        [
            f"検出文言: {phrase}" for phrase in alert_hits
        ]
        + [
            "チラシ文言だけでは条件を断定しない。",
            CONSUMER_DISCLAIMER,
        ]
    )

    if "高価買取" in blob or "無料査定" in blob:
        caution_notes.append("高価買取や無料査定の表示は、条件と対象品目を必ず確認する。")

    check_points = unique_texts(
        [
            "業者名",
            "電話番号",
            "出張費",
            "キャンセル料",
            "即日現金化の条件",
            "買取対象品目",
        ]
    )

    extra_photo_requests = unique_texts(
        [
            "チラシ全体",
            "業者名と電話番号が分かる部分",
            "料金や条件が書かれた部分",
        ]
    )

    return CheckAnalysis(
        query=query or "訪問買取",
        market_links=market_links,
        verdict=verdict,
        reason=(
            "強い勧誘文言や即日現金化の表示があり、"
            "業者情報と条件の確認が必要。"
            if alert_hits or any(hit in blob for hit in ["即日現金化", "何でも買います", "その場で現金"])
            else "表示だけでは判断できる情報が不足している。"
        ),
        missing_info=missing_info,
        next_actions=next_actions,
        official_categories=official_categories,
        confidence_score=score,
        confidence_label=confidence_label_from_score(score),
        refusal_category="consult" if verdict == "相談推奨" else "general",
        caution_notes=caution_notes,
        extra_photo_requests=extra_photo_requests,
        check_points=check_points,
    )


def build_flyer_check_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = analyze_flyer_check(payload)
    return {
        "company_name": normalize_text(payload.get("company_name")) or None,
        "phone_number": normalize_text(payload.get("phone_number")) or None,
        "flyer_text": normalize_text(payload.get("flyer_text")) or None,
        "outcall_fee_text": normalize_text(payload.get("outcall_fee_text")) or None,
        "cancellation_fee_text": normalize_text(payload.get("cancellation_fee_text")) or None,
        "high_price_text": normalize_text(payload.get("high_price_text")) or None,
        "same_day_cash_text": normalize_text(payload.get("same_day_cash_text")) or None,
        "inducement_text": normalize_text(payload.get("inducement_text")) or None,
        "memo": normalize_text(payload.get("memo")) or None,
        "image_refs_json": list(payload.get("image_refs") or []),
        "market_query": analysis.query,
        "market_links_json": analysis.market_links,
        "caution_points_json": analysis.caution_notes,
        "check_points_json": analysis.check_points,
        "photo_requests_json": analysis.extra_photo_requests,
    }
