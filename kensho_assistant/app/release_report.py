from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .paths import (
    AUTO_SCAN_JSON,
    CAMPAIGNS_CSV,
    FORM_INSPECTIONS_JSONL,
    RELEASE_REPORT_JSON,
    RELEASE_REPORT_MD,
    RELEASE_REPORT_V02_JSON,
    RELEASE_REPORT_V02_MD,
    RELEASE_REPORT_V03_JSON,
    RELEASE_REPORT_V03_MD,
    RELEASE_REPORT_V04_JSON,
    RELEASE_REPORT_V04_MD,
)
from .entry_logger import load_entries
from .profile_manager import PROFILE_ENC
from .storage import read_csv_rows


def latest_inspections(path: Path | None = None) -> dict[str, dict]:
    source = path or FORM_INSPECTIONS_JSONL
    latest: dict[str, dict] = {}
    if not source.exists():
        return latest
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            latest[str(row.get("campaign_id", ""))] = row
    return latest


def build_release_report(
    campaigns_path: Path | None = None,
    entries_path: Path | None = None,
    inspections_path: Path | None = None,
    version: str = "v0.4.2-beta",
) -> dict[str, object]:
    campaigns = read_csv_rows(campaigns_path or CAMPAIGNS_CSV)
    entries = load_entries(entries_path) if entries_path else load_entries()
    inspections = latest_inspections(inspections_path)
    readiness = Counter(row.get("readiness_status", "") for row in inspections.values())
    submitted_count = sum(1 for row in entries if row.get("status") == "SUBMITTED")
    auto_scan_status = "MISSING"
    if AUTO_SCAN_JSON.exists():
        try:
            auto_scan = json.loads(AUTO_SCAN_JSON.read_text(encoding="utf-8"))
            auto_scan_status = "OK" if auto_scan.get("warning") == "OK" else "WARNING"
        except Exception:
            auto_scan_status = "WARNING"
    return {
        "version": version,
        "collected_count": len(campaigns),
        "analyzed_count": sum(1 for row in campaigns if row.get("status")),
        "resolved_count": sum(1 for row in campaigns if row.get("resolve_status") == "RESOLVED"),
        "inspected_count": len(inspections),
        "ready_for_fill_count": readiness.get("READY_FOR_FILL", 0),
        "review_only_count": readiness.get("REVIEW_ONLY", 0),
        "landing_page_count": readiness.get("LANDING_PAGE", 0),
        "search_only_count": readiness.get("SEARCH_ONLY", 0),
        "low_confidence_count": readiness.get("LOW_CONFIDENCE", 0),
        "submitted_count": submitted_count,
        "final_test_note": "本番profile相当テスト 1 件実施 / 応募送信なし",
        "auto_scan_status": auto_scan_status,
        "pytest_status": "run separately",
        "doctor_status": "run separately",
        "profile_store": PROFILE_ENC.name if PROFILE_ENC.exists() else "profile.json",
        "privacy_check_status": "manual log scan required",
        "known_limitations": [
        "この版でも本番送信を推奨しない",
        "REVIEW_ONLY は人間確認が必要",
        "年齢・同意・メルマガ・任意項目は自動入力しない",
        ],
        "next_steps": [
            "READY_FOR_FILL 候補を増やす",
            "REVIEW_ONLY の手動確認 UX を改善する",
            "本番送信は必ず人間確認後に判断する",
        ],
        "release_status": "OK" if submitted_count == 0 else "NG",
    }


def render_release_report(report: dict[str, object]) -> str:
    lines = [
        f"# Release report {report['version']}",
        f"- version: {report['version']}",
        f"- release_status: {report['release_status']}",
        f"- collected_count: {report['collected_count']}",
        f"- analyzed_count: {report['analyzed_count']}",
        f"- resolved_count: {report['resolved_count']}",
        f"- inspected_count: {report['inspected_count']}",
        f"- ready_for_fill_count: {report['ready_for_fill_count']}",
        f"- review_only_count: {report['review_only_count']}",
        f"- landing_page_count: {report['landing_page_count']}",
        f"- search_only_count: {report['search_only_count']}",
        f"- low_confidence_count: {report['low_confidence_count']}",
        f"- submitted_count: {report['submitted_count']}",
        f"- final_test_note: {report['final_test_note']}",
        f"- auto_scan: {report['auto_scan_status']}",
        f"- pytest_status: {report['pytest_status']}",
        f"- doctor_status: {report['doctor_status']}",
        f"- profile_store: {report['profile_store']}",
        f"- privacy_check_status: {report['privacy_check_status']}",
        "",
        "## known limitations",
    ]
    lines.extend(f"- {item}" for item in report["known_limitations"])
    lines.extend(["", "## next steps"])
    lines.extend(f"- {item}" for item in report["next_steps"])
    lines.extend(["", "## safety", "- 本番送信は人間確認が必要"])
    return "\n".join(lines) + "\n"


def release_report_paths(version: str) -> tuple[Path, Path]:
    if version.startswith("v0.4"):
        return RELEASE_REPORT_V04_MD, RELEASE_REPORT_V04_JSON
    if version.startswith("v0.3"):
        return RELEASE_REPORT_V03_MD, RELEASE_REPORT_V03_JSON
    if version.startswith("v0.2"):
        return RELEASE_REPORT_V02_MD, RELEASE_REPORT_V02_JSON
    return RELEASE_REPORT_MD, RELEASE_REPORT_JSON
