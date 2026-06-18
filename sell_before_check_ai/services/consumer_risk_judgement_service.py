from __future__ import annotations

from typing import Any

from .common import CONSUMER_DISCLAIMER, CONSUMER_HOTLINE_NOTICE, normalize_check_type, unique_texts
from .consumer_flyer_check_service import analyze_flyer_check
from .consumer_item_check_service import analyze_item_check
from .consumer_quote_check_service import analyze_quote_check
from .refusal_phrase_service import pick_refusal_phrase


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        value = row.get(key, default)
    else:
        value = getattr(row, key, default)
    return default if value is None else value


def _official_info_payload(row: Any) -> dict[str, Any]:
    links = list(_row_get(row, "reference_links_json", []) or [])
    return {
        "id": _row_get(row, "id"),
        "category": _row_get(row, "category"),
        "title": _row_get(row, "title"),
        "summary": _row_get(row, "summary"),
        "content": _row_get(row, "content"),
        "reference_links": links,
        "caution_level": _row_get(row, "caution_level"),
    }


def _select_official_infos(available_rows: list[Any], categories: list[str]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    category_set = {category for category in categories if category}
    for row in available_rows:
        row_category = _row_get(row, "category")
        row_id = int(_row_get(row, "id", 0) or 0)
        if row_id and row_id in seen_ids:
            continue
        if row_category in category_set or row_category == "消費者ホットライン188":
            selected.append(_official_info_payload(row))
            if row_id:
                seen_ids.add(row_id)
    if not selected:
        for row in available_rows:
            if _row_get(row, "category") == "消費者ホットライン188":
                selected.append(_official_info_payload(row))
                break
    return selected


def _analysis_for_check(check_type: str, payload: dict[str, Any]) -> Any:
    normalized = normalize_check_type(check_type)
    if normalized == "flyer":
        return analyze_flyer_check(payload)
    if normalized == "quote":
        return analyze_quote_check(payload)
    return analyze_item_check(payload)


def build_risk_judgement_context(
    check_type: str,
    payload: dict[str, Any],
    official_info_rows: list[Any],
    refusal_phrase_rows: list[Any],
) -> dict[str, Any]:
    normalized_type = normalize_check_type(check_type)
    analysis = _analysis_for_check(normalized_type, payload)
    selected_official_infos = _select_official_infos(official_info_rows, analysis.official_categories)
    reference_links: list[str] = []
    for info in selected_official_infos:
        reference_links.extend(info.get("reference_links") or [])
    reference_links = unique_texts(reference_links)
    refusal_phrase = pick_refusal_phrase(
        [
            {
                "phrase": _row_get(row, "phrase"),
                "category": _row_get(row, "category"),
                "note": _row_get(row, "note"),
            }
            for row in refusal_phrase_rows
        ],
        verdict=analysis.verdict,
        category_hint=_row_get(payload, "item_category") or _row_get(payload, "category") or _row_get(payload, "memo"),
        check_type=normalized_type,
    )
    if not refusal_phrase:
        refusal_phrase = "今日はこの場で決めず、家族と確認してから判断します。"

    return {
        "check_type": normalized_type,
        "judgement_result": analysis.verdict,
        "reason": analysis.reason,
        "missing_info": analysis.missing_info,
        "next_actions": analysis.next_actions,
        "official_categories": analysis.official_categories,
        "official_infos": selected_official_infos,
        "reference_links": reference_links,
        "confidence_score": analysis.confidence_score,
        "confidence_label": analysis.confidence_label,
        "refusal_phrase": refusal_phrase,
        "caution_notes": analysis.caution_notes,
        "market_links": analysis.market_links,
        "query": analysis.query,
        "check_points": analysis.check_points,
        "extra_photo_requests": analysis.extra_photo_requests,
        "hotline_notice": CONSUMER_HOTLINE_NOTICE,
        "disclaimer": CONSUMER_DISCLAIMER,
        "analysis": analysis,
    }
