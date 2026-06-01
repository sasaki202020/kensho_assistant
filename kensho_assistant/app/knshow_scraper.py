from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, urljoin
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .models import CAMPAIGN_HEADERS
from .paths import CAMPAIGNS_CSV
from .storage import ensure_csv, read_csv_rows, write_csv_rows


BASE_URL = "https://www.knshow.com/list/s4/"
TOP_URL = "https://www.knshow.com/"
SEARCH_URL = "https://www.knshow.com/search?do=true&keyword="
ROBOTS_URL = "https://www.knshow.com/robots.txt"
USER_AGENT = "KenshoAssistant/0.1 (+local personal-use; contact: local)"
DEFAULT_TOP_KEYWORDS = ["ビール", "食品", "飲料", "Amazonギフト券", "QUOカード", "家電", "コーヒー", "お菓子"]


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def robots_allows(url: str, user_agent: str = USER_AGENT) -> bool:
    try:
        robots_text = requests.get(ROBOTS_URL, headers={"User-Agent": user_agent}, timeout=20).text
    except Exception:
        return False
    parsed = urlparse(url)
    target = parsed.path
    if parsed.query:
        target = f"{target}?{parsed.query}"
    disallow_rules: list[str] = []
    current_agents: list[str] = []
    for raw_line in robots_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key_lower = key.casefold()
        value_lower = value.casefold()
        if key_lower == "user-agent":
            current_agents = [value_lower]
            continue
        if key_lower == "disallow" and ("*" in current_agents or not current_agents):
            if value:
                disallow_rules.append(value)
    for rule in disallow_rules:
        if rule == "/*?view=" and "?view=" in target:
            return False
        if rule.endswith("/") and target.startswith(rule):
            return False
        if rule and rule in target:
            return False
    return True


def _page_url(page: int) -> str:
    if page <= 1:
        return BASE_URL
    return BASE_URL.rstrip("/") + f"/page:{page}"


def _parse_count(text: str) -> str:
    match = re.search(r"当選人数[^\d]*(\d[\d,]*)\s*名様", text)
    if match:
        return match.group(1)
    match = re.search(r"当選人数[^\n]*?不明", text)
    if match:
        return "不明"
    return ""


def _extract_text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def build_keyword_search_url(keyword: str) -> str:
    if not keyword:
        return SEARCH_URL
    return f"{SEARCH_URL}{quote(keyword)}"


def _parse_card(li, page_url: str) -> dict[str, str]:
    title_link = li.select_one("h3.listTitle a[href^='/detail/']")
    title = _extract_text(title_link)
    detail_href = title_link.get("href", "") if title_link else ""
    campaign_id = ""
    if detail_href:
        match = re.search(r"/detail/([^/.]+)", detail_href)
        if match:
            campaign_id = match.group(1)
    if not campaign_id and title:
        campaign_id = re.sub(r"[^a-zA-Z0-9]+", "-", title)[:32].strip("-")

    raw_type = _extract_text(li.select_one("h3.listTitle span"))
    description = _extract_text(li.select_one("div.listP"))
    text = _extract_text(li)
    provider = ""
    provider_match = re.search(r"提供[:：]\s*([^\n]+)", text)
    if provider_match:
        provider = provider_match.group(1).strip()
    deadline = ""
    deadline_match = re.search(r"締切[:：]\s*([^\n]+)", text)
    if deadline_match:
        deadline = deadline_match.group(1).strip()
    category = " > ".join(_extract_text(item.select_one("a span")) for item in li.select("ol.topicpath-themelist > li") if _extract_text(item.select_one("a span")))
    entry_link = li.select_one("a[href^='/rd/']")
    entry_url = urljoin(page_url, entry_link.get("href", "")) if entry_link else ""
    if not entry_url:
        entry_url = urljoin(page_url, detail_href)

    return {
        "campaign_id": campaign_id,
        "source": "knshow",
        "campaign_name": title,
        "prize": title,
        "winner_count": _parse_count(text),
        "provider": provider,
        "deadline": deadline,
        "knshow_url": urljoin(page_url, detail_href),
        "entry_url": entry_url,
        "description": description,
        "category": category,
        "entry_type_raw": raw_type,
        "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "DISCOVERED",
        "notes": "",
    }


def _collect_from_page_url(page_url: str, limit: int, sleep_seconds: float = 1.0) -> list[dict[str, str]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not robots_allows(page_url):
        raise RuntimeError("robots.txt does not allow collecting from the target page")
    session = _session()
    response = session.get(page_url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select("ol.KnshowList > li")
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for li in cards:
        row = _parse_card(li, page_url)
        campaign_id = row.get("campaign_id") or row.get("campaign_name")
        if campaign_id in seen:
            continue
        seen.add(campaign_id)
        items.append(row)
        if len(items) >= limit:
            break
    time.sleep(sleep_seconds)
    return items


def collect_campaigns(limit: int = 20, sleep_seconds: float = 1.0) -> list[dict[str, str]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not robots_allows(BASE_URL):
        raise RuntimeError("robots.txt does not allow collecting from the target list page")
    session = _session()
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    page = 1
    while len(items) < limit:
        page_url = _page_url(page)
        response = session.get(page_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select("ol.KnshowList > li")
        if not cards:
            break
        for li in cards:
            row = _parse_card(li, page_url)
            campaign_id = row.get("campaign_id") or row.get("campaign_name")
            if campaign_id in seen:
                continue
            seen.add(campaign_id)
            items.append(row)
            if len(items) >= limit:
                break
        page += 1
        time.sleep(sleep_seconds)
    return items


def get_top_keywords(limit: int = 12) -> list[str]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    try:
        response = _session().get(TOP_URL, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        keywords: list[str] = []
        for anchor in soup.select("a[href*='/keyword/'], a[href*='/search?keyword=']"):
            text = _extract_text(anchor)
            if text and text not in keywords and len(text) <= 20:
                keywords.append(text)
            if len(keywords) >= limit:
                break
        return keywords or DEFAULT_TOP_KEYWORDS[:limit]
    except Exception:
        return DEFAULT_TOP_KEYWORDS[:limit]


def get_category_links(limit: int = 12) -> list[tuple[str, str]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    try:
        response = _session().get(TOP_URL, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        links: list[tuple[str, str]] = []
        for anchor in soup.select("a[href]"):
            text = _extract_text(anchor)
            href = anchor.get("href", "")
            if not text or not href:
                continue
            if any(existing_text == text for existing_text, _ in links):
                continue
            if "/list/" in href or "/keyword/" in href or "/search?" in href:
                links.append((text, urljoin(TOP_URL, href)))
            if len(links) >= limit:
                break
        return links
    except Exception:
        return [
            ("大量当選", BASE_URL),
            ("締切間近", BASE_URL),
            ("食品", build_keyword_search_url("食品")),
            ("飲料", build_keyword_search_url("飲料")),
            ("商品券", build_keyword_search_url("商品券")),
            ("家電", build_keyword_search_url("家電")),
        ][:limit]


def collect_by_keyword(keyword: str, limit: int = 20, sleep_seconds: float = 1.0) -> list[dict[str, str]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    return _collect_from_page_url(build_keyword_search_url(keyword), limit=limit, sleep_seconds=sleep_seconds)


def collect_by_category(category_url: str, limit: int = 20, sleep_seconds: float = 1.0) -> list[dict[str, str]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    return _collect_from_page_url(category_url, limit=limit, sleep_seconds=sleep_seconds)


def save_campaigns(rows: Iterable[dict[str, str]], path: str | Path | None = None) -> Path:
    campaigns_path = Path(path) if path else CAMPAIGNS_CSV
    ensure_csv(campaigns_path, CAMPAIGN_HEADERS)
    existing_rows = read_csv_rows(campaigns_path)
    merged_by_id = {row.get("campaign_id", ""): row for row in existing_rows if row.get("campaign_id", "")}
    enrichment_fields = {
        "resolved_entry_url",
        "resolved_domain",
        "resolve_status",
        "resolve_reason",
        "resolved_at",
        "form_readiness_status",
        "form_readiness_score",
        "form_readiness_reason",
        "inspected_at",
        "research_keyword",
        "research_category",
        "research_source",
        "discovered_at",
        "opportunity_score",
        "opportunity_rank",
        "opportunity_reason",
        "risk_level",
        "risk_reasons",
        "recommendation_reason",
        "next_action",
    }
    for row in rows:
        campaign_id = row.get("campaign_id", "")
        if not campaign_id:
            continue
        previous = merged_by_id.get(campaign_id, {})
        merged = {**previous, **row}
        for field in enrichment_fields:
            if previous.get(field):
                merged[field] = previous[field]
        merged_by_id[campaign_id] = merged
    write_csv_rows(campaigns_path, merged_by_id.values(), CAMPAIGN_HEADERS)
    return campaigns_path
