from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .ranking import canonical_campaign_key
from .sources import parse_listing
from ..knshow_scraper import save_campaigns


def merge_imported_campaigns(existing: Iterable[dict[str, str]], imported: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    merged = [dict(row) for row in existing]
    by_key = {canonical_campaign_key(row): row for row in merged if canonical_campaign_key(row).strip("|")}
    for incoming in imported:
        row = dict(incoming)
        key = canonical_campaign_key(row)
        previous = by_key.get(key)
        if previous is None:
            row.setdefault("source_urls", row.get("source_url", ""))
            merged.append(row)
            by_key[key] = row
            continue
        sources = {value for value in str(previous.get("source_urls", "") or "").split("\n") if value}
        if row.get("source_url"):
            sources.add(str(row["source_url"]))
        previous["source_urls"] = "\n".join(sorted(sources))
        previous.setdefault("official_campaign_url_raw", row.get("official_campaign_url_raw", ""))
    return merged


def import_listing_html(source: str, html: str, source_url: str, existing: Iterable[dict[str, str]] = ()) -> list[dict[str, str]]:
    return merge_imported_campaigns(existing, parse_listing(source, html, source_url))


def import_listing_file(source: str, html_path: str | Path, source_url: str, existing: Iterable[dict[str, str]] = ()) -> list[dict[str, str]]:
    path = Path(html_path)
    html = path.read_text(encoding="utf-8")
    return import_listing_html(source, html, source_url, existing)


def save_imported_listing(source: str, html_path: str | Path, source_url: str, existing: Iterable[dict[str, str]] = ()) -> Path:
    return save_campaigns(import_listing_file(source, html_path, source_url, existing))

