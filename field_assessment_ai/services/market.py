from __future__ import annotations

from typing import Any

from .common import (
    build_legal_notices,
    build_search_terms,
    default_value_range,
    format_price,
    guess_category,
    guess_condition,
    normalize_text,
    quote_query,
)


def build_market_query(
    product_name: str | None = None,
    brand: str | None = None,
    model_number: str | None = None,
    category: str | None = None,
    extra_keywords: list[str] | None = None,
) -> str:
    tokens = build_search_terms(product_name, brand, model_number, category)
    extra = build_search_terms(*(extra_keywords or []))
    return " ".join(part for part in [tokens, extra] if part).strip()


def build_search_links(query: str) -> dict[str, str]:
    encoded = quote_query(query)
    return {
        "mercari": f"https://jp.mercari.com/search?keyword={encoded}",
        "yahoo_auction": f"https://auctions.yahoo.co.jp/search/search?p={encoded}",
        "ebay_sold": f"https://www.ebay.com/sch/i.html?_nkw={encoded}&LH_Complete=1&LH_Sold=1&_sop=13",
        "rakuma": f"https://fril.jp/s?query={encoded}",
        "surugaya": f"https://www.suruga-ya.jp/search?category=&search_word={encoded}",
        "bookoff": f"https://shopping.bookoff.co.jp/search/keyword/{encoded}",
        "geo": f"https://ec.geo-online.co.jp/shop/goods/search.aspx?search={encoded}",
        "hardoff": f"https://netmall.hardoff.co.jp/search/?q={encoded}",
    }


def build_market_memo_defaults(payload: dict[str, Any], analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    name = normalize_text(payload.get("name"))
    brand = normalize_text(payload.get("brand"))
    model_number = normalize_text(payload.get("model_number"))
    category = normalize_text(payload.get("category")) or (analysis or {}).get("suggested_category") or guess_category(" ".join([name, brand, model_number]))
    condition = normalize_text(payload.get("condition_note")) or (analysis or {}).get("suggested_condition") or guess_condition(" ".join([name, brand, model_number]))
    image_count = int(payload.get("image_count") or len(payload.get("image_ids") or []))
    value_range = (analysis or {}).get("estimated_value_range") or default_value_range(category, condition, image_count=image_count)
    query = build_market_query(name, brand, model_number, category, payload.get("extra_keywords"))
    search_links = build_search_links(query) if query else {}
    lowest = int(value_range["minimum"])
    median = int(value_range["median"])
    highest = int(value_range["maximum"])
    sold_count = max(1, int(max(median, 1) / 2500) + image_count)

    shipping_fee = 800
    if category in {"家電", "テレビ", "家具", "パソコン"}:
        shipping_fee = 1500
    elif category in {"本", "CD・DVD", "衣類"}:
        shipping_fee = 600

    marketplace_fee = max(0, int(median * 0.1))
    packing_fee = 300 if category not in {"家具", "家電", "テレビ", "パソコン"} else 700
    purchase_price = max(0, int(median * 0.35))
    disposal_fee_memo = "処分費は現場条件により変動"
    if category == "危険物":
        disposal_fee_memo = "危険物扱いのため別管理。バッテリー・液漏れ・発火リスクを確認"
    elif category in {"家電", "テレビ"}:
        disposal_fee_memo = "家電リサイクル対象の有無を確認"

    internal_memo = "モック相場メモ。公開前に実売と現場条件を再確認。"
    if condition == "要確認":
        internal_memo += " 状態要確認。"

    return {
        "lowest_price": lowest,
        "median_price": median,
        "highest_price": highest,
        "sold_count": sold_count,
        "purchase_price": purchase_price,
        "shipping_fee": shipping_fee,
        "marketplace_fee": marketplace_fee,
        "packing_fee": packing_fee,
        "disposal_fee_memo": disposal_fee_memo,
        "internal_memo": internal_memo,
        "search_keyword": query,
        "source_urls": list(search_links.values()),
        "legal_notices": build_legal_notices(" ".join([name, brand, model_number, category]), category, condition),
        "analysis_notes": [
            f"検索キーワード: {query}" if query else "検索キーワード未設定",
            "相場メモはモック値。実売確認前提。",
        ],
    }

