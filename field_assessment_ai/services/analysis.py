from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .common import (
    ItemContext,
    build_legal_notices,
    build_search_terms,
    default_value_range,
    estimate_rank_from_score,
    guess_category,
    guess_condition,
    normalize_text,
    rank_index,
    worse_rank,
)

HIGH_VALUE_CATEGORIES = {"カメラ", "ブランド", "時計", "ゲーム", "パソコン", "工具"}


def _get(mapping: dict[str, Any], key: str, default: Any = None) -> Any:
    value = mapping.get(key, default)
    return default if value is None else value


def _build_context(payload: dict[str, Any]) -> ItemContext:
    quantity = int(payload.get("quantity") or 1)
    image_count = int(payload.get("image_count") or len(payload.get("image_ids") or []))
    return ItemContext(
        name=normalize_text(payload.get("name")),
        category=normalize_text(payload.get("category")),
        brand=normalize_text(payload.get("brand")),
        model_number=normalize_text(payload.get("model_number")),
        condition_note=normalize_text(payload.get("condition_note")),
        quantity=max(1, quantity),
        memo=normalize_text(payload.get("memo")),
        image_count=max(0, image_count),
    )


def _build_input_summary(context: ItemContext) -> str:
    tokens = [context.brand, context.name, context.model_number, context.category]
    joined = " / ".join([token for token in tokens if token])
    if not joined:
        joined = "商品情報なし"
    return joined


def _score_context(context: ItemContext, category: str, condition: str, legal_notices: list[dict[str, Any]]) -> int:
    score = 18
    if category in HIGH_VALUE_CATEGORIES:
        score += 20
    elif category in {"家電", "テレビ"}:
        score += 12
    elif category in {"衣類", "本", "CD・DVD", "雑貨"}:
        score += 4

    if condition == "良好":
        score += 16
    elif condition == "標準":
        score += 6
    else:
        score -= 16

    score += min(8, context.image_count * 2)
    score += min(8, max(0, context.quantity - 1) * 2)

    if any(notice["severity"] == "critical" for notice in legal_notices):
        score -= 35
    if any(keyword in (context.memo or "").lower() for keyword in ["まとめ売り", "セット"]):
        score += 5
    if category == "危険物":
        score -= 30

    return max(0, min(100, score))


def _build_check_points(category: str, condition: str, image_count: int) -> list[str]:
    checkpoints = [
        "型番・銘板・付属品の確認",
        "動作確認の可否を確認",
        "写真と現物の差分を確認",
    ]
    if image_count:
        checkpoints.append("画像で傷・割れ・欠品を再確認")
    if category in {"家電", "テレビ"}:
        checkpoints.extend(["通電確認", "年式確認", "家電リサイクル対象の確認"])
    elif category == "カメラ":
        checkpoints.extend(["レンズ・バッテリー・シャッター確認", "防湿庫保管歴の確認"])
    elif category == "ゲーム":
        checkpoints.extend(["起動確認", "付属品・箱・説明書の確認"])
    elif category == "ブランド":
        checkpoints.extend(["真贋確認", "型押し・シリアル確認"])
    elif category == "危険物":
        checkpoints.extend(["バッテリー膨張確認", "液漏れ確認", "破棄区分の確認"])
    if condition == "要確認":
        checkpoints.append("破損や欠品がないか再確認")
    return checkpoints


def _candidate_ranks(primary: str) -> list[str]:
    primary_index = rank_index(primary)
    alternate: list[str] = [primary]
    if primary_index > 0:
        alternate.append(["A", "B", "C", "D", "E", "F"][primary_index - 1])
    if primary_index < 5:
        alternate.append(["A", "B", "C", "D", "E", "F"][primary_index + 1])
    seen: list[str] = []
    for rank in alternate:
        if rank not in seen:
            seen.append(rank)
    return seen[:3]


class MockVisionAnalysisService:
    provider_name = "mock-vision"

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = _build_context(payload)
        text_blob = build_search_terms(
            context.brand,
            context.name,
            context.model_number,
            context.category,
            context.condition_note,
            context.memo,
        )
        category = context.category or guess_category(text_blob)
        condition = guess_condition(text_blob)
        value_range = default_value_range(category, condition, image_count=context.image_count)
        legal_notices = build_legal_notices(text_blob, category, condition)
        score = _score_context(context, category, condition, legal_notices)
        primary_rank = estimate_rank_from_score(score, any(n["severity"] == "critical" for n in legal_notices), condition)
        rank_candidates = _candidate_ranks(primary_rank)
        checkpoints = _build_check_points(category, condition, context.image_count)
        primary_name = " ".join(token for token in [context.brand, context.name, context.model_number] if token) or context.name or "仮商品候補"

        candidate_items = [
            {
                "name": primary_name,
                "category": category,
                "condition": condition,
                "rank_candidates": rank_candidates,
                "estimated_value_range": value_range,
                "check_points": checkpoints,
                "confidence": 0.88,
                "reasoning": "商品名・カテゴリ・状態から最も自然な候補を優先。",
            }
        ]

        bundle_name = f"{context.name or primary_name} まとめ売り候補"
        candidate_items.append(
            {
                "name": bundle_name,
                "category": category,
                "condition": "標準" if condition == "良好" else condition,
                "rank_candidates": _candidate_ranks("B" if primary_rank in {"A", "B", "C"} else "C"),
                "estimated_value_range": {
                    "minimum": max(0, int(value_range["minimum"] * 0.8)),
                    "median": max(0, int(value_range["median"] * 0.9)),
                    "maximum": max(0, int(value_range["maximum"] * 0.95)),
                },
                "check_points": ["まとめ売り可否", "同梱の欠品確認", "セット品の一点ごとの状態確認"],
                "confidence": 0.62,
                "reasoning": "セット品や複数点回収のまとめ売り候補としての見立て。",
            }
        )

        if any(notice["severity"] == "critical" for notice in legal_notices) or condition == "要確認":
            candidate_items.append(
                {
                    "name": f"{context.name or primary_name} 処分・部品取り候補",
                    "category": "危険物" if any(notice["severity"] == "critical" for notice in legal_notices) else category,
                    "condition": "要確認",
                    "rank_candidates": _candidate_ranks("F" if any(notice["severity"] == "critical" for notice in legal_notices) else "E"),
                    "estimated_value_range": {
                        "minimum": 0,
                        "median": max(0, int(value_range["median"] * 0.35)),
                        "maximum": max(0, int(value_range["maximum"] * 0.5)),
                    },
                    "check_points": ["安全確認", "分別確認", "搬出前確認"],
                    "confidence": 0.39,
                    "reasoning": "危険物・ジャンク・状態要確認の保守的候補。",
                }
            )

        notes = [
            f"画像数: {context.image_count} 枚",
            "モック査定。実査定は現物と追加写真で再確認。",
        ]
        if category == "危険物":
            notes.append("危険物候補は現場の保管・搬出ルールを優先。")

        return {
            "source": self.provider_name,
            "input_summary": _build_input_summary(context),
            "suggested_category": category,
            "suggested_condition": condition,
            "rank_candidates": rank_candidates,
            "estimated_value_range": value_range,
            "check_points": checkpoints,
            "candidate_items": candidate_items,
            "legal_notices": legal_notices,
            "analysis_notes": notes,
            "mock_mode": True,
        }


class OpenAIVisionAnalysisService:
    provider_name = "openai-vision"

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            "OpenAIVisionAnalysisService は未接続です。"
            " 実運用時はこのクラスを差し替えて OpenAI Vision API に接続してください。"
        )

