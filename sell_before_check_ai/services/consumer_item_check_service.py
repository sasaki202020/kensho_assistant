from __future__ import annotations

from typing import Any

from field_assessment_ai.services.common import clamp, normalize_text

from .common import (
    CONSUMER_DISCLAIMER,
    ITEM_CATEGORY_GUIDANCE,
    CheckAnalysis,
    build_consumer_market_links,
    build_consumer_market_query,
    confidence_label_from_score,
    unique_texts,
    verdict_from_score,
)


ITEM_PRICE_BANDS: dict[str, tuple[int, int, int]] = {
    "着物": (500, 5000, 15000),
    "ミシン": (1000, 7000, 25000),
    "貴金属": (10000, 30000, 100000),
    "カメラ": (2000, 12000, 40000),
    "時計・ブランド品": (5000, 25000, 80000),
    "不用品回収対象品": (0, 1000, 5000),
}


def _canonical_category(value: str | None, text_blob: str) -> str:
    normalized = normalize_text(value)
    if normalized in ITEM_CATEGORY_GUIDANCE:
        return normalized
    aliases = [
        ("着物", "着物"),
        ("ミシン", "ミシン"),
        ("貴金属", "貴金属"),
        ("K18", "貴金属"),
        ("PT900", "貴金属"),
        ("Pt900", "貴金属"),
        ("18K", "貴金属"),
        ("カメラ", "カメラ"),
        ("レンズ", "カメラ"),
        ("時計", "時計・ブランド品"),
        ("ブランド", "時計・ブランド品"),
        ("不用品", "不用品回収対象品"),
        ("回収", "不用品回収対象品"),
    ]
    lowered = text_blob.lower()
    for needle, category in aliases:
        if needle.lower() in lowered:
            return category
    return normalized or "不用品回収対象品"


def _text_blob(payload: dict[str, Any]) -> str:
    parts = [
        payload.get("item_category"),
        payload.get("item_name"),
        payload.get("brand"),
        payload.get("model_number"),
        payload.get("condition_note"),
        payload.get("accessories"),
        payload.get("market_memo"),
        payload.get("memo"),
    ]
    return " ".join(normalize_text(str(part)) for part in parts if normalize_text(str(part)))


def _build_category_checks(category: str, text_blob: str) -> tuple[list[str], list[str], list[str]]:
    guidance = ITEM_CATEGORY_GUIDANCE.get(category, {})
    check_points = list(guidance.get("check_points", []))
    photo_requests = list(guidance.get("photo_requests", []))
    official_categories = list(guidance.get("official_categories", ["古物商", "消費者ホットライン188"]))

    if category == "着物" and "証紙" not in text_blob:
        check_points.append("証紙")
    if category == "ミシン" and "型番" not in text_blob:
        check_points.append("型番")
    if category == "貴金属" and "刻印" not in text_blob:
        check_points.append("刻印")
    if category == "時計・ブランド品" and "シリアル" not in text_blob:
        check_points.append("シリアル")

    return unique_texts(check_points), unique_texts(photo_requests), unique_texts(official_categories)


def analyze_item_check(payload: dict[str, Any]) -> CheckAnalysis:
    item_category = normalize_text(payload.get("item_category"))
    item_name = normalize_text(payload.get("item_name"))
    brand = normalize_text(payload.get("brand"))
    model_number = normalize_text(payload.get("model_number"))
    condition_note = normalize_text(payload.get("condition_note"))
    accessories = normalize_text(payload.get("accessories"))
    market_memo = normalize_text(payload.get("market_memo"))
    additional_photo_requests = normalize_text(payload.get("additional_photo_requests"))
    check_points_text = normalize_text(payload.get("check_points"))
    memo = normalize_text(payload.get("memo"))
    offered_price = int(payload.get("offered_price") or 0)
    image_count = int(payload.get("image_count") or len(payload.get("image_refs") or []))

    text_blob = _text_blob(payload)
    category = _canonical_category(item_category, text_blob)
    query = build_consumer_market_query(item_name, brand, model_number, category, [memo, market_memo])
    market_links = build_consumer_market_links(query or category)
    category_check_points, category_photo_requests, official_categories = _build_category_checks(category, text_blob)

    check_points = unique_texts(category_check_points + ([check_points_text] if check_points_text else []))
    photo_requests = unique_texts(category_photo_requests + ([additional_photo_requests] if additional_photo_requests else []))

    missing_info: list[str] = []
    if not item_name:
        missing_info.append("商品名")
    if category == "着物":
        for point in ["証紙", "落款", "作家名", "産地", "素材", "正絹かどうか"]:
            if point not in text_blob:
                missing_info.append(point)
    elif category == "ミシン":
        for point in ["メーカー", "型番", "家庭用 / 職業用 / ロックミシン", "フットコントローラー", "付属品", "説明書", "動作確認", "試し縫い", "年式"]:
            if point not in text_blob:
                missing_info.append(point)
    elif category == "貴金属":
        for point in ["刻印", "重量", "素材", "K18", "Pt900", "石の有無", "鑑定書", "購入証明", "グラム単価"]:
            if point.lower() not in text_blob.lower():
                missing_info.append(point)
    elif category == "カメラ":
        for point in ["メーカー", "型番", "レンズ", "バッテリー", "充電器", "動作確認", "シャッター"]:
            if point not in text_blob:
                missing_info.append(point)
    elif category == "時計・ブランド品":
        for point in ["刻印", "シリアル", "箱", "保証書", "真贋確認", "動作確認"]:
            if point not in text_blob:
                missing_info.append(point)
    elif category == "不用品回収対象品":
        for point in ["品目分類", "家電リサイクル対象", "搬出条件", "追加料金", "当日追加請求"]:
            if point not in text_blob:
                missing_info.append(point)

    if not brand and category in {"ミシン", "カメラ", "時計・ブランド品"}:
        missing_info.append("ブランド・メーカー")
    if not model_number and category in {"ミシン", "カメラ", "時計・ブランド品"}:
        missing_info.append("型番・モデル")
    if not accessories and category in {"着物", "ミシン", "カメラ", "時計・ブランド品"}:
        missing_info.append("付属品")

    missing_info = unique_texts(missing_info)
    price_band = ITEM_PRICE_BANDS.get(category, (100, 1000, 5000))
    median_price = price_band[1]
    ratio = offered_price / max(1, median_price)

    score = 16
    if category == "貴金属":
        score += 20
    elif category == "ミシン":
        score += 14
    elif category == "着物":
        score += 12
    elif category == "時計・ブランド品":
        score += 15
    elif category == "カメラ":
        score += 10
    score += min(20, len(missing_info) * 3)
    if offered_price > 0:
        if ratio <= 0.15:
            score += 26
        elif ratio <= 0.3:
            score += 14
        elif ratio <= 0.5:
            score += 6
    if not model_number and category in {"ミシン", "カメラ", "時計・ブランド品"}:
        score += 10
    if category == "貴金属" and any(token in text_blob.lower() for token in ["刻印未確認", "未確認", "不明"]):
        score += 14
    if category == "ミシン" and ("型番不明" in text_blob or not model_number):
        score += 12
    if category == "着物" and any(token in text_blob for token in ["証紙", "落款", "作家名"]) and offered_price <= 2000:
        score += 10
    if category == "不用品回収対象品" and offered_price <= 0:
        score += 10

    score = int(clamp(score, 0, 100))
    critical = category == "貴金属" and any(token in text_blob.lower() for token in ["刻印未確認", "未確認", "不明"])
    strong_signal = category in {"貴金属", "ミシン"} and offered_price > 0
    verdict = verdict_from_score(score, critical=critical, strong_signal=strong_signal)

    if category == "貴金属" and critical:
        verdict = "相談推奨"
    elif category == "ミシン" and (not model_number or offered_price <= 1000):
        verdict = "即決注意"
    elif category == "着物" and (len(missing_info) >= 4 or offered_price <= 2000):
        verdict = "即決注意" if offered_price <= 2000 else "確認推奨"
    elif category == "不用品回収対象品" and offered_price <= 0:
        verdict = "確認推奨"

    next_actions = unique_texts(
        [
            "証紙や刻印、型番を追加撮影する" if category in {"着物", "貴金属", "ミシン", "カメラ", "時計・ブランド品"} else "",
            "見積書と買取明細を紙またはメールで受け取る" if verdict != "問題なさそう" else "",
            "その場で即決しない" if verdict in {"即決注意", "相談推奨"} else "",
            "家族と確認してから判断する" if verdict in {"確認推奨", "即決注意", "相談推奨"} else "",
            "188へ相談する" if verdict == "相談推奨" else "",
        ]
    )

    caution_notes = unique_texts(
        [
            f"不足項目: {value}" for value in missing_info[:8]
        ]
        + [
            CONSUMER_DISCLAIMER,
            f"相場は参考値。{category}の真贋や正確な査定額は保証しない。",
        ]
    )

    if category == "貴金属":
        caution_notes.append("真贋や素材の断定はしない。刻印・重量・鑑定書を確認する。")
    if category == "不用品回収対象品":
        caution_notes.append("家電リサイクル対象や追加料金の扱いを事前に確認する。")

    return CheckAnalysis(
        query=query or category,
        market_links=market_links,
        verdict=verdict,
        reason=(
            "提示額が相場感に比べて低い、または真贋・型番・刻印などの確認情報が不足している。"
            if verdict != "問題なさそう"
            else "入力情報だけでは大きな不安材料が見えない。"
        ),
        missing_info=missing_info,
        next_actions=next_actions,
        official_categories=official_categories,
        confidence_score=score,
        confidence_label=confidence_label_from_score(score),
        refusal_category="gold" if category == "貴金属" else ("consult" if verdict == "相談推奨" else "general"),
        caution_notes=caution_notes,
        extra_photo_requests=photo_requests,
        check_points=check_points,
    )


def build_item_check_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = analyze_item_check(payload)
    return {
        "item_category": normalize_text(payload.get("item_category")) or None,
        "item_name": normalize_text(payload.get("item_name")) or None,
        "brand": normalize_text(payload.get("brand")) or None,
        "model_number": normalize_text(payload.get("model_number")) or None,
        "condition_note": normalize_text(payload.get("condition_note")) or None,
        "accessories": normalize_text(payload.get("accessories")) or None,
        "offered_price": int(payload.get("offered_price") or 0) or None,
        "market_memo": normalize_text(payload.get("market_memo")) or None,
        "additional_photo_requests_text": normalize_text(payload.get("additional_photo_requests")) or None,
        "check_points_text": normalize_text(payload.get("check_points")) or None,
        "memo": normalize_text(payload.get("memo")) or None,
        "image_refs_json": list(payload.get("image_refs") or []),
        "market_query": analysis.query,
        "market_links_json": analysis.market_links,
        "caution_points_json": analysis.caution_notes,
        "check_points_json": analysis.check_points,
        "photo_requests_json": analysis.extra_photo_requests,
    }

