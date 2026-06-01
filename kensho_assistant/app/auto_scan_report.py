from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from .paths import AUTO_SCAN_JSON, AUTO_SCAN_MD, CAMPAIGNS_CSV, ENTRIES_CSV, FORM_INSPECTIONS_JSONL
from .release_report import latest_inspections, build_release_report
from .storage import read_csv_rows


def _parse_relative_deadline(text: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now()
    text = text or ""
    if "本日締切" in text:
        return now
    if "明日締切" in text:
        return now + timedelta(days=1)
    if "明後日締切" in text:
        return now + timedelta(days=2)
    return None


def build_auto_scan_report(
    campaigns_path: Path | None = None,
    entries_path: Path | None = None,
    inspections_path: Path | None = None,
) -> dict[str, object]:
    campaigns = read_csv_rows(campaigns_path or CAMPAIGNS_CSV)
    entries = read_csv_rows(entries_path or ENTRIES_CSV)
    inspections = latest_inspections(inspections_path or FORM_INSPECTIONS_JSONL)
    release_report = build_release_report(campaigns_path, entries_path, inspections_path)
    status_counts = Counter(row.get("form_readiness_status", "") or row.get("resolve_status", "") or row.get("status", "") for row in campaigns)
    due_soon = sum(1 for row in campaigns if (_parse_relative_deadline(row.get("deadline", "")) or datetime.max) <= datetime.now() + timedelta(days=3))
    selected = [row for row in campaigns if row.get("selected_by_user") == "true"][:10]
    today_candidates = {
        "review_only": [row.get("campaign_name", "") for row in campaigns if row.get("form_readiness_status") == "REVIEW_ONLY"][:10],
        "due_soon": [row.get("campaign_name", "") for row in campaigns if (_parse_relative_deadline(row.get("deadline", "")) or datetime.max) <= datetime.now() + timedelta(days=3)][:10],
        "low_risk": [row.get("campaign_name", "") for row in campaigns if row.get("status", "") == "SAFE_TO_FILL" and row.get("form_readiness_status", "") in {"READY_FOR_FILL", "REVIEW_ONLY"}][:10],
        "web_form": [row.get("campaign_name", "") for row in campaigns if row.get("form_readiness_status", "") in {"READY_FOR_FILL", "REVIEW_ONLY"}][:10],
        "selected": [row.get("campaign_name", "") for row in selected],
    }
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "collected_count": len(campaigns),
        "analyzed_count": sum(1 for row in campaigns if row.get("status")),
        "resolved_count": sum(1 for row in campaigns if row.get("resolve_status") == "RESOLVED"),
        "inspected_count": len(inspections),
        "review_only_count": status_counts.get("REVIEW_ONLY", 0),
        "ready_for_fill_count": status_counts.get("READY_FOR_FILL", 0),
        "landing_page_count": status_counts.get("LANDING_PAGE", 0),
        "search_only_count": status_counts.get("SEARCH_ONLY", 0),
        "low_confidence_count": status_counts.get("LOW_CONFIDENCE", 0),
        "submitted_count": release_report.get("submitted_count", 0),
        "today_candidates": today_candidates,
        "need_human_review": [
            "REVIEW_ONLY は人間確認が必要",
            "応募送信は行っていない",
            "年齢・同意・メルマガ・任意項目は自動入力しない",
        ],
        "next_actions": [
            "REVIEW_ONLY を確認する",
            "URL 解決を進める",
            "フォーム診断を確認する",
        ],
        "warning": "WARNING" if release_report.get("submitted_count", 0) != 0 else "OK",
    }
    return report


def render_auto_scan_report(report: dict[str, object]) -> str:
    lines = [
        "# Auto scan latest",
        f"- generated_at: {report['generated_at']}",
        f"- warning: {report['warning']}",
        f"- collected_count: {report['collected_count']}",
        f"- analyzed_count: {report['analyzed_count']}",
        f"- resolved_count: {report['resolved_count']}",
        f"- inspected_count: {report['inspected_count']}",
        f"- review_only_count: {report['review_only_count']}",
        f"- ready_for_fill_count: {report['ready_for_fill_count']}",
        f"- landing_page_count: {report['landing_page_count']}",
        f"- search_only_count: {report['search_only_count']}",
        f"- low_confidence_count: {report['low_confidence_count']}",
        f"- submitted_count: {report['submitted_count']}",
        "",
        "## 今日見るべき候補",
    ]
    for key, items in report["today_candidates"].items():
        lines.append(f"- {key}: {len(items)}")
        for item in items:
            lines.append(f"  - {item}")
    lines.extend(["", "## 人間確認が必要な項目"])
    lines.extend(f"- {item}" for item in report["need_human_review"])
    lines.extend(["", "## 次のおすすめアクション"])
    lines.extend(f"- {item}" for item in report["next_actions"])
    if report["warning"] == "WARNING":
        lines.extend(["", "## WARNING", "- submitted_count が 0 ではありません"])
    return "\n".join(lines) + "\n"


def save_auto_scan_report(report: dict[str, object]) -> tuple[Path, Path]:
    AUTO_SCAN_MD.write_text(render_auto_scan_report(report), encoding="utf-8")
    AUTO_SCAN_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return AUTO_SCAN_MD, AUTO_SCAN_JSON
