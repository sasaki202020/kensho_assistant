from __future__ import annotations

from typing import Any

from .common import (
    BASE_DISPOSAL_FEE,
    BASE_WORK_FEE,
    build_legal_notices,
    clamp,
    default_value_range,
    determine_discount_ratio,
    determine_purchase_factor,
    estimate_rank_from_score,
    format_price,
    guess_category,
    guess_condition,
    rank_index,
    worse_rank,
)

HIGH_DEMAND_CATEGORIES = {"カメラ", "ブランド", "時計", "ゲーム", "パソコン", "家電", "テレビ"}


def _mapping_get(payload: Any, key: str, default: Any = None) -> Any:
    if payload is None:
        return default
    if isinstance(payload, dict):
        value = payload.get(key, default)
    else:
        value = getattr(payload, key, default)
    return default if value is None else value


def _category_bonus(category: str | None) -> int:
    return {
        "カメラ": 18,
        "ブランド": 20,
        "時計": 16,
        "ゲーム": 15,
        "パソコン": 14,
        "家電": 9,
        "テレビ": 6,
        "衣類": 4,
        "本": 1,
        "CD・DVD": 2,
        "家具": 3,
        "工具": 10,
        "危険物": -25,
        "雑貨": 0,
    }.get(category or "", 0)


def _condition_bonus(condition: str | None) -> int:
    return {
        "良好": 16,
        "標準": 6,
        "要確認": -18,
    }.get(condition or "標準", 0)


def _score_item(category: str | None, condition: str | None, median_price: int, image_count: int, legal_notices: list[dict[str, Any]]) -> int:
    score = 20
    score += _category_bonus(category)
    score += _condition_bonus(condition)
    score += min(10, image_count * 2)
    score += min(12, int(median_price / 1500))
    if any(notice["severity"] == "critical" for notice in legal_notices):
        score -= 35
    if category in HIGH_DEMAND_CATEGORIES and condition == "良好":
        score += 6
    return int(clamp(score, 0, 100))


def _rank_from_score(score: int, condition: str | None, has_critical_notice: bool) -> str:
    return estimate_rank_from_score(score, has_critical_notice, condition)


def _base_fee(rank: str, category: str | None, quantity: int, image_count: int) -> tuple[int, int]:
    work_fee = BASE_WORK_FEE.get(rank, 500)
    disposal_fee = BASE_DISPOSAL_FEE.get(rank, 0)
    if category in {"家電", "テレビ", "家具", "パソコン"}:
        work_fee += 300
    if category == "危険物":
        work_fee += 600
        disposal_fee += 1000
    if quantity > 1:
        work_fee += min(500, (quantity - 1) * 120)
    if image_count:
        work_fee += min(200, image_count * 30)
    return work_fee, disposal_fee


def build_item_estimate_payload(
    item: dict[str, Any],
    *,
    market_memo: dict[str, Any] | None = None,
    analysis: dict[str, Any] | None = None,
    options: dict[str, Any] | Any | None = None,
) -> dict[str, Any]:
    quantity = max(1, int(_mapping_get(item, "quantity", 1)))
    image_count = int(_mapping_get(item, "image_count", len(_mapping_get(item, "images", []))))
    name = _mapping_get(item, "name")
    brand = _mapping_get(item, "brand")
    model_number = _mapping_get(item, "model_number")
    category = _mapping_get(item, "category") or (analysis or {}).get("suggested_category") or guess_category(" ".join([str(name or ""), str(brand or ""), str(model_number or "")]))
    condition = (analysis or {}).get("suggested_condition") or guess_condition(" ".join([str(name or ""), str(brand or ""), str(model_number or ""), str(_mapping_get(item, "condition_note", ""))]))
    legal_notices = _mapping_get(analysis, "legal_notices", []) or build_legal_notices(" ".join([str(name or ""), str(brand or ""), str(model_number or ""), str(category or "")]), category, condition)

    analysis_range = (analysis or {}).get("estimated_value_range") or default_value_range(category, condition, image_count=image_count)
    memo_range = {
        "minimum": int(_mapping_get(market_memo, "lowest_price", analysis_range["minimum"])),
        "median": int(_mapping_get(market_memo, "median_price", analysis_range["median"])),
        "maximum": int(_mapping_get(market_memo, "highest_price", analysis_range["maximum"])),
    }

    resale_min = max(0, int(memo_range["minimum"] * quantity))
    resale_max = max(0, int(memo_range["maximum"] * quantity))
    resale_median = max(0, int(memo_range["median"] * quantity))
    purchase_override = _mapping_get(options, "purchase_override")
    work_override = _mapping_get(options, "work_fee_override")
    disposal_override = _mapping_get(options, "disposal_fee_override")
    discount_ratio = float(_mapping_get(options, "discount_ratio", determine_discount_ratio("C")))

    score = _score_item(category, condition, resale_median, image_count, legal_notices)
    analysis_rank = (_mapping_get(analysis, "rank_candidates", []) or [None])[0]
    score_rank = _rank_from_score(score, condition, any(notice["severity"] == "critical" for notice in legal_notices))
    rank_candidate = worse_rank(analysis_rank, score_rank) or score_rank

    purchase_factor = determine_purchase_factor(rank_candidate)
    purchase_estimate = purchase_override
    if purchase_estimate is None:
        purchase_estimate = _mapping_get(market_memo, "purchase_price")
    if purchase_estimate is None:
        purchase_estimate = int(resale_median * purchase_factor)
    purchase_estimate = max(0, int(purchase_estimate))

    work_fee_estimate, disposal_fee_estimate = _base_fee(rank_candidate, category, quantity, image_count)
    if work_override is not None:
        work_fee_estimate = max(0, int(work_override))
    if disposal_override is not None:
        disposal_fee_estimate = max(0, int(disposal_override))

    discount_possible_amount = int(max(0, (resale_median + purchase_estimate) - (work_fee_estimate + disposal_fee_estimate)) * discount_ratio)
    final_estimate_guide = max(0, work_fee_estimate + disposal_fee_estimate - purchase_estimate - discount_possible_amount)

    details = {
        "item_name": name,
        "category": category,
        "condition": condition,
        "quantity": quantity,
        "image_count": image_count,
        "analysis_source": (analysis or {}).get("source", "mock"),
        "market_keyword": _mapping_get(market_memo, "search_keyword"),
        "legal_notices": legal_notices,
        "notes": [
            "モック採点。",
            "実売・搬出条件・現場距離で最終調整が必要。",
        ],
    }

    return {
        "scope_type": "item",
        "job_id": _mapping_get(item, "job_id"),
        "item_id": _mapping_get(item, "id"),
        "resale_estimate_min": resale_min,
        "resale_estimate_max": resale_max,
        "purchase_estimate": purchase_estimate,
        "disposal_fee_estimate": disposal_fee_estimate,
        "work_fee_estimate": work_fee_estimate,
        "discount_possible_amount": discount_possible_amount,
        "final_estimate_guide": final_estimate_guide,
        "sale_value_score": score,
        "rank_candidate": rank_candidate,
        "details_json": details,
        "summary": {
            "category": category,
            "condition": condition,
            "score": score,
            "rank_candidate": rank_candidate,
        },
        "legal_notices": legal_notices,
        "analysis_rank": analysis_rank,
    }


def build_job_estimate_payload(
    job: dict[str, Any],
    item_estimates: list[dict[str, Any]],
    *,
    options: dict[str, Any] | Any | None = None,
) -> dict[str, Any]:
    total_resale_min = sum(int(_mapping_get(item_estimate, "resale_estimate_min", 0)) for item_estimate in item_estimates)
    total_resale_max = sum(int(_mapping_get(item_estimate, "resale_estimate_max", 0)) for item_estimate in item_estimates)
    total_purchase = sum(int(_mapping_get(item_estimate, "purchase_estimate", 0)) for item_estimate in item_estimates)
    total_disposal = sum(int(_mapping_get(item_estimate, "disposal_fee_estimate", 0)) for item_estimate in item_estimates)
    total_work = sum(int(_mapping_get(item_estimate, "work_fee_estimate", 0)) for item_estimate in item_estimates)
    total_discount = sum(int(_mapping_get(item_estimate, "discount_possible_amount", 0)) for item_estimate in item_estimates)
    scores = [int(_mapping_get(item_estimate, "sale_value_score", 0)) for item_estimate in item_estimates]
    item_ranks = [_mapping_get(item_estimate, "rank_candidate") for item_estimate in item_estimates]
    legal_notices: list[dict[str, Any]] = []
    for item_estimate in item_estimates:
        legal_notices.extend(_mapping_get(item_estimate, "legal_notices", []))

    average_score = int(round(sum(scores) / len(scores))) if scores else 0
    has_critical = any(notice["severity"] == "critical" for notice in legal_notices)
    score_rank = estimate_rank_from_score(average_score, has_critical, None)
    overall_rank = worse_rank(score_rank, *item_ranks) or score_rank

    final_estimate_guide = max(0, total_work + total_disposal - total_purchase - total_discount)
    disposal_memo = " / ".join(
        [value for value in [
            "危険物・家電は個別確認",
            "搬出距離と仕分け量で変動",
        ] if value]
    )
    work_memo = " / ".join(
        [value for value in [
            "作業費は概算",
            "現場条件で再見積もり推奨",
        ] if value]
    )
    discount_override = _mapping_get(options, "discount_ratio")

    details = {
        "job_title": _mapping_get(job, "title"),
        "item_breakdown": [
            {
                "item_id": _mapping_get(item_estimate, "item_id"),
                "name": _mapping_get(_mapping_get(item_estimate, "details_json"), "item_name"),
                "rank_candidate": _mapping_get(item_estimate, "rank_candidate"),
                "resale_estimate_min": _mapping_get(item_estimate, "resale_estimate_min"),
                "resale_estimate_max": _mapping_get(item_estimate, "resale_estimate_max"),
                "purchase_estimate": _mapping_get(item_estimate, "purchase_estimate"),
                "final_estimate_guide": _mapping_get(item_estimate, "final_estimate_guide"),
            }
            for item_estimate in item_estimates
        ],
        "summary": {
            "item_count": len(item_estimates),
            "average_score": average_score,
            "rank_candidate": overall_rank,
        },
        "notes": [
            "案件全体の再販売見込み額と見積もり目安を集計。",
            "実運用では現場距離・搬出条件・法令区分を再確認。",
        ],
        "discount_ratio": discount_override,
    }

    return {
        "scope_type": "job",
        "job_id": _mapping_get(job, "id"),
        "item_id": None,
        "resale_estimate_min": total_resale_min,
        "resale_estimate_max": total_resale_max,
        "purchase_estimate": total_purchase,
        "disposal_fee_estimate": total_disposal,
        "work_fee_estimate": total_work,
        "discount_possible_amount": total_discount,
        "final_estimate_guide": final_estimate_guide,
        "sale_value_score": average_score,
        "rank_candidate": overall_rank,
        "details_json": details,
        "summary": {
            "item_count": len(item_estimates),
            "rank_candidate": overall_rank,
            "total_resale_min": total_resale_min,
            "total_resale_max": total_resale_max,
            "final_estimate_guide": final_estimate_guide,
        },
        "legal_notices": legal_notices,
        "work_memo": work_memo,
        "disposal_memo": disposal_memo,
    }

