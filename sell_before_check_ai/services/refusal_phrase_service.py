from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RefusalPhrase

from .common import normalize_text


def build_refusal_phrase_seeds() -> list[dict[str, Any]]:
    return [
        {
            "category": "general",
            "phrase": "今日はこの場で決めず、家族と確認してから判断します。",
            "note": "まず持ち帰って確認したいときの基本文例。",
        },
        {
            "category": "general",
            "phrase": "見積書と買取明細を紙またはメールでください。",
            "note": "書面確認を求める文例。",
        },
        {
            "category": "general",
            "phrase": "他社にも確認してから、必要であればこちらから連絡します。",
            "note": "比較検討したいときの文例。",
        },
        {
            "category": "gold",
            "phrase": "貴金属や時計は今日は売る予定がありません。",
            "note": "貴金属・時計向けの断り文例。",
        },
        {
            "category": "quote",
            "phrase": "追加料金の条件を確認してから判断します。",
            "note": "見積もり条件を詰めたいときの文例。",
        },
        {
            "category": "quote",
            "phrase": "契約内容を確認したいので、品物はまだ引き渡しません。",
            "note": "契約前に引渡しを止める文例。",
        },
        {
            "category": "consult",
            "phrase": "いったん消費生活センターに相談します。",
            "note": "相談優先の文例。",
        },
    ]


def default_refusal_phrase_rows() -> list[dict[str, Any]]:
    return build_refusal_phrase_seeds()


def pick_refusal_phrase(
    phrases: list[dict[str, Any]],
    *,
    verdict: str,
    category_hint: str | None = None,
    check_type: str | None = None,
) -> str:
    normalized_category = normalize_text(category_hint).lower()
    normalized_check_type = normalize_text(check_type).lower()

    candidates: list[str] = []
    if verdict == "相談推奨":
        candidates.extend([
            "いったん消費生活センターに相談します。",
            "今日はこの場で決めず、家族と確認してから判断します。",
        ])
    elif verdict == "即決注意":
        candidates.extend([
            "見積書と買取明細を紙またはメールでください。",
            "追加料金の条件を確認してから判断します。",
        ])
    elif verdict == "確認推奨":
        candidates.extend([
            "今日はこの場で決めず、家族と確認してから判断します。",
            "他社にも確認してから、必要であればこちらから連絡します。",
        ])
    else:
        candidates.extend([
            "他社にも確認してから、必要であればこちらから連絡します。",
            "見積書と買取明細を紙またはメールでください。",
        ])

    if "貴金属" in normalized_category or "時計" in normalized_category:
        candidates.insert(0, "貴金属や時計は今日は売る予定がありません。")
    if normalized_check_type == "quote":
        candidates.insert(0, "契約内容を確認したいので、品物はまだ引き渡しません。")
        candidates.insert(0, "追加料金の条件を確認してから判断します。")

    for candidate in candidates:
        for row in phrases:
            if normalize_text(row.get("phrase")) == candidate:
                return candidate

    if phrases:
        return normalize_text(phrases[0].get("phrase"))
    return candidates[0] if candidates else "今日はこの場で決めず、家族と確認してから判断します。"


def ensure_refusal_phrases_seeded(session: Session) -> int:
    existing = session.scalar(select(RefusalPhrase.id).limit(1))
    if existing is not None:
        return 0
    rows = [RefusalPhrase(**row) for row in build_refusal_phrase_seeds()]
    session.add_all(rows)
    session.commit()
    return len(rows)
