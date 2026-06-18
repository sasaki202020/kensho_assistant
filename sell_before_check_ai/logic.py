"""4段階判定ロジック（ルールベース・ローカル完結）.

判定は必ず次の4段階のいずれかになります:
  問題なさそう / 確認推奨 / 即決注意 / 相談推奨

外部API・AIサービスへの送信は行いません。入力テキストは保存しません。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).parent / "rules.json"

CHECK_TYPES = {
    "flyer": "チラシチェック",
    "item": "商品チェック",
    "quote": "見積もりチェック",
}

DISCLAIMER = (
    "この判定はキーワードに基づく参考情報です。"
    "正確な査定額・真贋・法律判断を保証するものではなく、"
    "特定の事業者についての評価でもありません。"
)

HOTLINE_NOTE = "迷ったら消費者ホットライン「188（いやや）」へ。最寄りの消費生活センターにつながります。"


@lru_cache(maxsize=1)
def load_rules() -> dict[str, Any]:
    with RULES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def level_for_score(score: int, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = rules or load_rules()
    chosen = rules["levels"][0]
    for level in rules["levels"]:
        if score >= level["min_score"]:
            chosen = level
    return chosen


def evaluate(text: str, check_type: str, flags: list[str] | None = None) -> dict[str, Any]:
    """入力テキストとチェックボックスから4段階判定を返す。

    戻り値は表示にそのまま使える dict。入力テキストは戻り値に含めるのみで、
    サーバー側には一切保存しない。
    """
    rules = load_rules()
    if check_type not in CHECK_TYPES:
        check_type = "flyer"
    flags = flags or []
    text = (text or "").strip()

    score = 0
    hits: list[dict[str, Any]] = []
    for kw in rules["keywords"]:
        if check_type in kw["targets"] and kw["pattern"] in text:
            score += kw["score"]
            hits.append({"pattern": kw["pattern"], "score": kw["score"], "note": kw["note"]})

    flag_defs = {f["id"]: f for f in rules["flags"]}
    for flag_id in flags:
        f = flag_defs.get(flag_id)
        if f:
            score += f["score"]
            hits.append({"pattern": f["label"], "score": f["score"], "note": f["note"]})

    level = level_for_score(score, rules)
    return {
        "check_type": check_type,
        "check_type_label": CHECK_TYPES[check_type],
        "level_id": level["id"],
        "level_label": level["label"],
        "tone": level["tone"],
        "summary": level["summary"],
        "score": score,
        "hits": hits,
        "disclaimer": DISCLAIMER,
        "hotline": HOTLINE_NOTE,
        "stored": False,
    }
