from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

from .autopilot_shared import LeadRecord, compact_text, read_csv_rows, write_csv_rows

LEAD_COLUMNS = [
    "company_name",
    "industry",
    "area",
    "website_url",
    "contact_url",
    "source_url",
    "source_type",
    "confidence",
    "status",
]

_BLOCKED_HOSTS = {
    "x.com",
    "twitter.com",
    "www.facebook.com",
    "facebook.com",
    "instagram.com",
    "www.instagram.com",
    "maps.google.com",
    "www.google.com",
    "tabelog.com",
    "hotpepper.jp",
    "townpage.jp",
    "navitime.co.jp",
    "gourmet.yahoo.co.jp",
    "retty.me",
    "ekiten.jp",
}

_SAMPLE_LEADS = [
    LeadRecord("サンプル整骨院 北九州", "整骨院", "北九州市 小倉北区", "", "", "sample://fixture/1", "sample_fixture", 0.82, "new"),
    LeadRecord("サンプル整体院 みらい", "整体院", "北九州市 小倉北区", "", "", "sample://fixture/2", "sample_fixture", 0.79, "new"),
    LeadRecord("サンプル鍼灸院 あさひ", "鍼灸院", "北九州市 小倉北区", "", "", "sample://fixture/3", "sample_fixture", 0.74, "new"),
]


def _normalize_url(url: str) -> str:
    value = (url or "").strip()
    if value.startswith("//"):
        value = "https:" + value
    return value


def _host_is_useful(url: str) -> bool:
    host = urlparse(url).netloc.casefold()
    if not host:
        return False
    if host in _BLOCKED_HOSTS:
        return False
    if host.endswith(".google.com") or host.endswith(".facebook.com") or host.endswith(".instagram.com"):
        return False
    return True


def _title_to_company(title: str, industry: str) -> str:
    text = compact_text(title, 60)
    for suffix in ("| Google 検索", "| Yahoo!検索", "| Yahoo! JAPAN", "- Google Search"):
        text = text.replace(suffix, "")
    if industry and industry in text:
        return text.split(industry, 1)[0].strip(" -｜|")
    return text.strip(" -｜|")


def load_manual_leads(csv_path: Path, *, industry: str, area: str, limit: int) -> list[LeadRecord]:
    rows = read_csv_rows(csv_path)
    leads: list[LeadRecord] = []
    for row in rows[:limit]:
        lead = LeadRecord.from_row(row, default_industry=industry, default_area=area)
        if not lead.company_name:
            continue
        leads.append(lead)
    return leads


def search_public_leads(area: str, industry: str, limit: int) -> list[LeadRecord]:
    query = f"{area} {industry} 公式サイト"
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        response = requests.get(search_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    leads: list[LeadRecord] = []
    seen: set[str] = set()
    for result in soup.select(".result"):
        link = result.select_one("a.result__a")
        if not link:
            continue
        url = _normalize_url(link.get("href", ""))
        if not url or not _host_is_useful(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        title = compact_text(link.get_text(" ", strip=True), 80)
        snippet_node = result.select_one(".result__snippet")
        snippet = compact_text(snippet_node.get_text(" ", strip=True) if snippet_node else "", 160)
        company_name = _title_to_company(title, industry)
        confidence = 0.7
        if "公式" in title or "公式" in snippet:
            confidence += 0.1
        if area and area[:3] in title:
            confidence += 0.05
        leads.append(
            LeadRecord(
                company_name=company_name or title,
                industry=industry,
                area=area,
                website_url=url,
                contact_url="",
                source_url=url,
                source_type="search_public",
                confidence=min(confidence, 0.98),
                status="new",
            )
        )
        if len(leads) >= limit:
            break
    return leads


def fallback_sample_leads(area: str, industry: str, limit: int) -> list[LeadRecord]:
    leads: list[LeadRecord] = []
    for sample in _SAMPLE_LEADS[:limit]:
        leads.append(
            replace(
                sample,
                industry=industry or sample.industry,
                area=area or sample.area,
            )
        )
    return leads


def find_leads(
    area: str,
    industry: str,
    limit: int,
    *,
    lead_csv: Path | None = None,
    sample: bool = False,
) -> list[LeadRecord]:
    if lead_csv and lead_csv.exists():
        leads = load_manual_leads(lead_csv, industry=industry, area=area, limit=limit)
        if leads:
            return leads
    if sample:
        return fallback_sample_leads(area, industry, limit)
    leads = search_public_leads(area, industry, limit)
    return leads


def save_generated_leads(path: Path, leads: Iterable[LeadRecord]) -> Path:
    return write_csv_rows(path, (lead.to_row() for lead in leads), LEAD_COLUMNS)
