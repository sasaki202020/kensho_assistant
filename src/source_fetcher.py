from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


@dataclass
class SourceDocument:
    topic: str
    official_url: str | None
    title: str
    fetched_at: str
    status: str
    summary_lines: list[str]
    raw_text: str
    warnings: list[str]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.parts.append(text)


def _fetch_url(url: str) -> tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_charset() or "utf-8"
        html = response.read().decode(content_type, errors="replace")
    return html, content_type


def _extract_title(html: str, fallback: str) -> str:
    patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r"<title[^>]*>(.*?)</title>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.I | re.S)
        if match:
            title = re.sub(r"\s+", " ", match.group(1)).strip()
            if title:
                return title
    return fallback


def _summarize_text(items: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        text = re.sub(r"\s+", " ", item).strip()
        if len(text) < 20:
            continue
        if text in seen:
            continue
        seen.append(text)
    return seen[:18]


def _collect_relevant_excerpt(parts: list[str]) -> list[str]:
    keywords = [
        "令和8年度（月額）",
        "国民年金（老齢基礎年金（満額））",
        "厚生年金（夫婦2人分の老齢基礎年金を含む標準的な年金額）",
        "年金生活者支援給付金の給付基準額",
        "1.9％",
        "2.0％",
        "3.2％",
        "70,608円",
        "237,279円",
    ]
    matched_indexes: list[int] = []
    for index, part in enumerate(parts):
        if any(keyword in part for keyword in keywords):
            matched_indexes.extend(range(max(0, index - 2), min(len(parts), index + 3)))
    ordered: list[str] = []
    for index in sorted(set(matched_indexes)):
        text = parts[index]
        if text not in ordered:
            ordered.append(text)
    return ordered


def fetch_source_document(
    topic: str,
    official_url: str | None,
    output_dir: Path,
) -> SourceDocument:
    fetched_at = datetime.now().isoformat(timespec="seconds")
    warnings: list[str] = []

    if not official_url:
        title = topic
        summary_lines = [
            "公式URLは未指定です。",
            "この実行はサンプルモードです。",
            "制度名・金額・対象条件は、公式情報で確認できた場合のみ採用してください。",
        ]
        raw_text = "\n".join(summary_lines)
        document = SourceDocument(
            topic=topic,
            official_url=None,
            title=title,
            fetched_at=fetched_at,
            status="sample",
            summary_lines=summary_lines,
            raw_text=raw_text,
            warnings=["公式URL未指定のため、数値・制度名はサンプル扱いです。"],
        )
        _write_sources(output_dir, document)
        return document

    try:
        html, _charset = _fetch_url(official_url)
        extractor = TextExtractor()
        extractor.feed(html)
        title = _extract_title(html, topic)
        summary_lines = _collect_relevant_excerpt(extractor.parts)
        if not summary_lines:
            summary_lines = _summarize_text(extractor.parts)
        if not summary_lines:
            summary_lines = ["本文の抽出に失敗したため、タイトルとURLのみ記録しました。"]
            warnings.append("公式URLの本文抽出が不十分です。")
        raw_text = "\n".join(summary_lines[:18])
        document = SourceDocument(
            topic=topic,
            official_url=official_url,
            title=title,
            fetched_at=fetched_at,
            status="fetched",
            summary_lines=summary_lines,
            raw_text=raw_text,
            warnings=warnings,
        )
    except (urllib.error.URLError, TimeoutError, ValueError, UnicodeDecodeError) as exc:
        document = SourceDocument(
            topic=topic,
            official_url=official_url,
            title=topic,
            fetched_at=fetched_at,
            status="fetch_failed",
            summary_lines=[f"公式URLの取得に失敗しました: {exc}"],
            raw_text=str(exc),
            warnings=[f"公式URL取得失敗: {exc}"],
        )
    _write_sources(output_dir, document)
    return document


def _write_sources(output_dir: Path, document: SourceDocument) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "sources_summary.md"
    text_lines = [
        f"# sources_summary",
        "",
        f"- topic: {document.topic}",
        f"- status: {document.status}",
        f"- title: {document.title}",
        f"- official_url: {document.official_url or 'なし'}",
        f"- fetched_at: {document.fetched_at}",
        "",
        "## 要点",
    ]
    text_lines.extend(f"- {line}" for line in document.summary_lines)
    summary_path.write_text("\n".join(text_lines) + "\n", encoding="utf-8")

    sources_path = output_dir / "sources.txt"
    source_text = [
        f"title: {document.title}",
        f"url: {document.official_url or 'なし'}",
        f"status: {document.status}",
        f"fetched_at: {document.fetched_at}",
    ]
    if document.summary_lines:
        source_text.append("key_points:")
        source_text.extend(f"- {line}" for line in document.summary_lines[:10])
    sources_path.write_text("\n".join(source_text) + "\n", encoding="utf-8")
