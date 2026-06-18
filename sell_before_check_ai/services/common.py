from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from field_assessment_ai.services.common import (
    build_search_terms,
    format_price,
    join_html_list,
    normalize_text,
    quote_query,
)
from field_assessment_ai.services.market import build_search_links


CHECK_TYPE_LABELS = {
    "flyer": "チラシ",
    "item": "商品",
    "quote": "見積もり",
}

DEFAULT_VERDICTS = ["問題なさそう", "確認推奨", "即決注意", "相談推奨"]

CONSUMER_DISCLAIMER = (
    "本判定は参考情報です。正確な査定額、真贋、法律判断は保証しません。"
    "迷う場合は断定せず、188や消費生活センターに相談してください。"
)

CONSUMER_HOTLINE_NOTICE = "困ったときは消費者ホットライン188へ相談する。"

FLYER_ALERT_PHRASES = [
    "高価買取",
    "無料査定",
    "即日現金化",
    "何でも買います",
    "着物買取",
    "ミシン買取",
    "貴金属も査定",
    "ブランド品も査定",
    "その場で現金",
    "出張費無料",
    "キャンセル料無料",
]

ITEM_CATEGORY_GUIDANCE: dict[str, dict[str, Any]] = {
    "着物": {
        "check_points": [
            "証紙",
            "落款",
            "作家名",
            "産地",
            "素材",
            "正絹かどうか",
            "シミ",
            "カビ",
            "におい",
            "帯や小物の有無",
            "保管状態",
        ],
        "photo_requests": ["証紙の全体", "落款のアップ", "シミやカビの近接写真", "帯や小物の有無が分かる写真"],
        "official_categories": ["古物商", "消費者ホットライン188"],
    },
    "ミシン": {
        "check_points": [
            "メーカー",
            "型番",
            "家庭用 / 職業用 / ロックミシン",
            "フットコントローラー",
            "付属品",
            "説明書",
            "ケース",
            "動作確認",
            "試し縫い",
            "年式",
        ],
        "photo_requests": ["メーカー銘板", "型番のアップ", "付属品一式", "動作中の写真"],
        "official_categories": ["古物商", "消費者ホットライン188"],
    },
    "貴金属": {
        "check_points": [
            "刻印",
            "重量",
            "素材",
            "K18 / Pt900 など",
            "石の有無",
            "鑑定書",
            "購入証明",
            "グラム単価",
            "買取明細の有無",
        ],
        "photo_requests": ["刻印のアップ", "重量が分かる写真", "鑑定書や証明書", "石や留め具の写真"],
        "official_categories": ["古物商", "訪問購入", "消費者ホットライン188"],
    },
    "カメラ": {
        "check_points": [
            "メーカー",
            "型番",
            "レンズ",
            "バッテリー",
            "充電器",
            "動作確認",
            "シャッター",
            "液晶",
            "カビ",
        ],
        "photo_requests": ["型番の銘板", "レンズの状態", "液晶の写真", "付属品一式"],
        "official_categories": ["古物商", "消費者ホットライン188"],
    },
    "時計・ブランド品": {
        "check_points": [
            "刻印",
            "シリアル",
            "箱",
            "保証書",
            "付属品",
            "真贋確認",
            "動作確認",
        ],
        "photo_requests": ["シリアルや刻印のアップ", "箱と保証書", "全体像", "付属品一式"],
        "official_categories": ["古物商", "訪問購入", "消費者ホットライン188"],
    },
    "不用品回収対象品": {
        "check_points": [
            "品目分類",
            "家電リサイクル対象か",
            "搬出条件",
            "追加料金の有無",
            "当日追加請求の有無",
        ],
        "photo_requests": ["品目全体", "型番や銘板", "搬出経路", "追加料金の説明書面"],
        "official_categories": ["不用品回収", "一般廃棄物収集運搬", "家電リサイクル", "消費者ホットライン188"],
    },
}

QUOTE_RED_FLAG_PHRASES = [
    "当日追加請求",
    "追加料金",
    "別途",
    "見積書なし",
    "明細なし",
    "口頭のみ",
    "家電リサイクル不明",
    "パック料金",
    "キャンセル料",
]


@dataclass(slots=True)
class CheckAnalysis:
    query: str
    market_links: dict[str, str]
    verdict: str
    reason: str
    missing_info: list[str]
    next_actions: list[str]
    official_categories: list[str]
    confidence_score: int
    confidence_label: str
    refusal_category: str
    caution_notes: list[str]
    extra_photo_requests: list[str]
    check_points: list[str]


def normalize_check_type(check_type: str | None) -> str:
    value = normalize_text(check_type).lower()
    if value in {"flyer", "item", "quote"}:
        return value
    return "item"


def build_consumer_market_query(
    product_name: str | None = None,
    brand: str | None = None,
    model_number: str | None = None,
    category: str | None = None,
    extra_keywords: list[str] | None = None,
) -> str:
    tokens = build_search_terms(product_name, brand, model_number, category)
    extras = build_search_terms(*(extra_keywords or []))
    return " ".join(part for part in [tokens, extras] if part).strip()


def build_consumer_market_links(query: str) -> dict[str, str]:
    normalized_query = query or "売る前チェック 相場"
    encoded = quote_query(normalized_query)
    general_search = quote_query(f"{normalized_query} 買取 相場")
    specialist_search = quote_query(f"{normalized_query} 買取 専門店")
    sold_search = quote_query(f"site:auctions.yahoo.co.jp 落札 {normalized_query}")
    return {
        "mercari": f"https://jp.mercari.com/search?keyword={encoded}",
        "yahoo_auction": f"https://auctions.yahoo.co.jp/search/search?p={encoded}",
        "yahoo_auction_sold": f"https://www.google.com/search?q={sold_search}",
        "ebay": f"https://www.ebay.com/sch/i.html?_nkw={encoded}",
        "ebay_sold_completed": f"https://www.ebay.com/sch/i.html?_nkw={encoded}&LH_Complete=1&LH_Sold=1&_sop=13",
        "google": f"https://www.google.com/search?q={general_search}",
        "specialist_buyback": f"https://www.google.com/search?q={specialist_search}",
    }


def confidence_label_from_score(score: int) -> str:
    if score >= 80:
        return "高"
    if score >= 55:
        return "中"
    return "低"


def verdict_from_score(score: int, *, critical: bool = False, strong_signal: bool = False) -> str:
    if critical:
        return "相談推奨" if score >= 45 or strong_signal else "即決注意"
    if score >= 75:
        return "相談推奨"
    if score >= 58:
        return "即決注意"
    if score >= 38:
        return "確認推奨"
    return "問題なさそう"


def _find_hits(text: str, phrases: list[str]) -> list[str]:
    normalized = normalize_text(text)
    hits: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        if phrase in normalized and phrase not in seen:
            seen.add(phrase)
            hits.append(phrase)
    return hits


def detect_flyer_alert_phrases(text: str) -> list[str]:
    return _find_hits(text, FLYER_ALERT_PHRASES)


def detect_quote_missing_points(text: str) -> list[str]:
    hits = _find_hits(text, QUOTE_RED_FLAG_PHRASES)
    if "見積書" not in text and "明細" not in text:
        hits.append("見積書・明細の確認")
    if "家電" in text and "リサイクル" not in text:
        hits.append("家電リサイクル料金の扱い")
    return list(dict.fromkeys(hits))


def detect_item_missing_points(category: str | None, text: str) -> list[str]:
    normalized_category = normalize_text(category)
    guidance = ITEM_CATEGORY_GUIDANCE.get(normalized_category, {})
    required_points = list(guidance.get("check_points", []))
    hits = []
    for point in required_points:
        if point not in text:
            hits.append(point)
    return hits


def build_188_notice() -> dict[str, Any]:
    return {
        "code": "CONSUMER_HOTLINE_188",
        "severity": "warning",
        "title": "消費者ホットライン188",
        "message": CONSUMER_HOTLINE_NOTICE,
        "category": "相談窓口",
        "legal_hint": "困ったときは一人で抱え込まず相談する。",
    }


def render_link_list(links: dict[str, str]) -> str:
    items = "".join(
        f'<li><a href="{escape(url)}" target="_blank" rel="noreferrer">{escape(label)}</a></li>'
        for label, url in links.items()
    )
    return f"<ul>{items}</ul>" if items else "<p>なし</p>"


def unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
