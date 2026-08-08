from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class SOURCE_LAYOUT_CHANGED(RuntimeError):
    pass


def _clean(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _row(source: str, title_node, source_url: str, deadline: str, sponsor: str, prize: str = "") -> dict[str, str]:
    href = title_node.get("href", "") if title_node else ""
    title = _clean(title_node)
    return {
        "campaign_id": re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-")[:48] or "unknown",
        "source": source,
        "source_site": source,
        "source_mode": "existing_auto" if source == "knshow" else "user_initiated",
        "campaign_name": title,
        "prize": prize or title,
        "provider": sponsor,
        "deadline": deadline,
        "source_url": source_url,
        "official_campaign_url_raw": urljoin(source_url, href) if href else "",
        "entry_url": urljoin(source_url, href) if href else "",
        "status": "DISCOVERED",
    }


def parse_listing(source: str, html: str, source_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    rows: list[dict[str, str]] = []
    if source == "knshow":
        cards = soup.select("ol.KnshowList > li")
        for card in cards:
            title = card.select_one("h3.listTitle a")
            text = _clean(card)
            rows.append(_row("knshow", title, source_url, _extract(text, r"締切[:：]\s*([^ ]+)"), _extract(text, r"提供[:：]\s*([^ ]+)")))
    elif source == "chance":
        cards = soup.select("article.campaign")
        for card in cards:
            rows.append(_row("chance", card.select_one("a.title"), source_url, _clean(card.select_one(".deadline")), _clean(card.select_one(".sponsor"))))
    elif source == "ken-kaku":
        cards = soup.select(".entry")
        for card in cards:
            rows.append(_row("ken-kaku", card.select_one("h2 a"), source_url, _clean(card.select_one(".deadline")), "", _clean(card.select_one(".prize"))))
    else:
        raise SOURCE_LAYOUT_CHANGED("SOURCE_LAYOUT_CHANGED")
    if not rows:
        raise SOURCE_LAYOUT_CHANGED("SOURCE_LAYOUT_CHANGED")
    return rows


def _extract(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""

