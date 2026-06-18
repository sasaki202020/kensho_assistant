from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
from typing import Any
from urllib.parse import quote_plus


PRICE_BUCKETS: dict[str, tuple[int, int, int]] = {
    "家電": (1500, 5000, 15000),
    "テレビ": (2000, 7000, 20000),
    "カメラ": (3000, 12000, 35000),
    "ゲーム": (1000, 8000, 25000),
    "ブランド": (5000, 20000, 50000),
    "時計": (3000, 15000, 50000),
    "本": (50, 300, 1000),
    "CD・DVD": (100, 800, 3000),
    "衣類": (300, 2500, 8000),
    "家具": (500, 3000, 15000),
    "工具": (1000, 8000, 25000),
    "パソコン": (3000, 10000, 40000),
    "雑貨": (100, 1000, 5000),
}

RANK_ORDER = ["A", "B", "C", "D", "E", "F"]

BASE_DISPOSAL_FEE = {
    "A": 0,
    "B": 0,
    "C": 0,
    "D": 500,
    "E": 1000,
    "F": 1500,
}

BASE_WORK_FEE = {
    "A": 300,
    "B": 500,
    "C": 700,
    "D": 1000,
    "E": 1200,
    "F": 1500,
}

LEGAL_DISCLAIMER = "法令適合を保証しない。実運用では古物商許可、一般廃棄物収集運搬、家電リサイクル、危険物の扱いを個別確認すること。"


@dataclass(slots=True)
class ItemContext:
    name: str | None = None
    category: str | None = None
    brand: str | None = None
    model_number: str | None = None
    condition_note: str | None = None
    quantity: int = 1
    memo: str | None = None
    image_count: int = 0


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def compact_tokens(*values: str | None) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_text(value)
        if not text:
            continue
        for token in text.replace("／", " ").replace("/", " ").split():
            token = token.strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            tokens.append(token)
    return tokens


def quote_query(value: str) -> str:
    return quote_plus(value, safe="")


def format_price(value: int | None) -> str:
    if value is None:
        return "未設定"
    return f"{value:,}円"


def clamp(value: int | float, minimum: int | float, maximum: int | float):
    return max(minimum, min(maximum, value))


def value_range_to_text(range_data: dict[str, int] | None) -> str:
    if not range_data:
        return "未設定"
    return f"{format_price(range_data['minimum'])} 〜 {format_price(range_data['maximum'])}"


def guess_category(text: str) -> str:
    normalized = normalize_text(text)
    candidates = [
        ("バッテリー", "危険物"),
        ("リチウム", "危険物"),
        ("充電池", "危険物"),
        ("テレビ", "テレビ"),
        ("冷蔵庫", "家電"),
        ("洗濯機", "家電"),
        ("電子レンジ", "家電"),
        ("エアコン", "家電"),
        ("カメラ", "カメラ"),
        ("レンズ", "カメラ"),
        ("ゲーム", "ゲーム"),
        ("switch", "ゲーム"),
        ("playstation", "ゲーム"),
        ("ps5", "ゲーム"),
        ("ブランド", "ブランド"),
        ("バッグ", "ブランド"),
        ("財布", "ブランド"),
        ("時計", "時計"),
        ("本", "本"),
        ("dvd", "CD・DVD"),
        ("cd", "CD・DVD"),
        ("レコード", "CD・DVD"),
        ("パソコン", "パソコン"),
        ("pc", "パソコン"),
        ("工具", "工具"),
        ("ドリル", "工具"),
        ("家具", "家具"),
        ("ソファ", "家具"),
        ("椅子", "家具"),
        ("衣類", "衣類"),
        ("パーカー", "衣類"),
        ("ジャケット", "衣類"),
    ]
    lower = normalized.lower()
    for needle, category in candidates:
        if needle in lower:
            return category
    return "雑貨"


def guess_condition(text: str) -> str:
    normalized = normalize_text(text).lower()
    if any(keyword in normalized for keyword in ["新品", "未使用", "美品", "良好", "箱あり", "動作確認済"]):
        return "良好"
    if any(keyword in normalized for keyword in ["動作未確認", "欠品", "破損", "割れ", "傷", "汚れ", "ジャンク", "不動", "故障"]):
        return "要確認"
    return "標準"


def default_value_range(category: str | None, condition: str | None, image_count: int = 0) -> dict[str, int]:
    base = PRICE_BUCKETS.get(category or "", PRICE_BUCKETS["雑貨"])
    minimum, median, maximum = base
    condition = condition or "標準"
    if condition == "良好":
        minimum = int(minimum * 1.1)
        median = int(median * 1.15)
        maximum = int(maximum * 1.2)
    elif condition == "要確認":
        minimum = int(minimum * 0.45)
        median = int(median * 0.6)
        maximum = int(maximum * 0.75)
    if image_count:
        median = int(median * (1 + min(image_count, 4) * 0.02))
        maximum = int(maximum * (1 + min(image_count, 4) * 0.03))
    return {"minimum": max(0, minimum), "median": max(0, median), "maximum": max(0, maximum)}


def estimate_rank_from_score(score: int, has_critical_notice: bool, condition: str | None = None) -> str:
    if has_critical_notice:
        return "F"
    if condition == "要確認" and score < 35:
        return "E"
    if score >= 78:
        return "A"
    if score >= 58:
        return "B"
    if score >= 38:
        return "C"
    if score >= 20:
        return "D"
    return "E"


def determine_purchase_factor(rank: str) -> float:
    return {
        "A": 0.55,
        "B": 0.42,
        "C": 0.3,
        "D": 0.14,
        "E": 0.05,
        "F": 0.0,
    }.get(rank, 0.2)


def determine_discount_ratio(rank: str) -> float:
    return {
        "A": 0.18,
        "B": 0.15,
        "C": 0.12,
        "D": 0.08,
        "E": 0.05,
        "F": 0.0,
    }.get(rank, 0.1)


def build_legal_notices(text: str, category: str | None = None, condition: str | None = None) -> list[dict[str, Any]]:
    normalized = normalize_text(text).lower()
    notices: list[dict[str, Any]] = [
        {
            "code": "GENERAL_DISCLAIMER",
            "severity": "warning",
            "title": "法令適合の保証なし",
            "message": LEGAL_DISCLAIMER,
            "category": category,
            "legal_hint": "法令確認は現場運用で実施すること。",
        }
    ]

    battery_keywords = ["バッテリー", "電池", "リチウム", "充電池", "モバイルバッテリー"]
    appliance_keywords = ["テレビ", "冷蔵庫", "洗濯機", "エアコン"]
    hazardous_keywords = ["ガス", "スプレー", "塗料", "シンナー", "薬品", "医薬品", "刃物", "包丁", "火薬", "消火器"]

    if any(keyword in normalized for keyword in battery_keywords):
        notices.append(
            {
                "code": "BATTERY_CAUTION",
                "severity": "critical",
                "title": "バッテリー注意",
                "message": "リチウムイオン電池や膨張バッテリーは危険物として別管理を想定すること。",
                "category": category,
                "legal_hint": "破損・膨張・発火リスクを確認すること。",
            }
        )

    if any(keyword in normalized for keyword in appliance_keywords):
        notices.append(
            {
                "code": "HOME_APPLIANCE_RECYCLING",
                "severity": "warning",
                "title": "家電リサイクル注意",
                "message": "テレビ・冷蔵庫・洗濯機・エアコンは家電リサイクル対象の確認が必要。",
                "category": category,
                "legal_hint": "再販/処分前に品目分類と引取ルールを確認すること。",
            }
        )

    if any(keyword in normalized for keyword in hazardous_keywords) or condition == "要確認":
        notices.append(
            {
                "code": "HAZARDOUS_ITEM_CHECK",
                "severity": "warning",
                "title": "危険物・状態確認",
                "message": "危険物、刃物、薬品、液漏れ、破損は現物確認の対象。",
                "category": category,
                "legal_hint": "安全装備と搬出手順の確認を優先すること。",
            }
        )

    if category in {"危険物", "家電", "テレビ"}:
        notices.append(
            {
                "code": "LICENSE_CHECK",
                "severity": "warning",
                "title": "許可区分の確認",
                "message": "古物商、一般廃棄物収集運搬、家電リサイクルなどの許可区分を個別確認すること。",
                "category": category,
                "legal_hint": "案件の仕分け段階で担当区分を確認すること。",
            }
        )

    return notices


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def rank_index(rank: str | None) -> int:
    if not rank:
        return len(RANK_ORDER)
    upper = rank.upper()
    try:
        return RANK_ORDER.index(upper)
    except ValueError:
        return len(RANK_ORDER)


def worse_rank(*ranks: str | None) -> str | None:
    ranked = [rank for rank in ranks if rank]
    if not ranked:
        return None
    return max(ranked, key=rank_index)


def sanitize_filename(filename: str) -> str:
    text = normalize_text(filename)
    base = text.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return base or "upload.bin"


def build_search_terms(*parts: str | None) -> str:
    return " ".join(unique_preserve_order(compact_tokens(*parts)))


def join_html_list(values: list[str]) -> str:
    items = "".join(f"<li>{escape(value)}</li>" for value in values)
    return f"<ul>{items}</ul>" if items else "<p>なし</p>"
