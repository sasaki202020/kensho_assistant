from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..app.auto_apply_engine import AutoApplyEngine
from ..app.engine import run_prepared_campaign_dry_run
from ..app.paths import APP_DIR, FORM_ANALYSIS_DIR, PACKAGE_ROOT, PRE_SUBMIT_CHECKS_DIR, SELF_TEST_LOG_MD
from ..app.browser_manager import check_chrome_available, close_browser_safely, open_url_in_chrome
from ..app.entry_logger import load_entries
from ..app.entry_history import export_entry_history_csv, load_entry_history, load_win_mail_candidates, summarize_entry_history, summarize_win_mail_candidates
from ..app.agent_dashboard.service import get_agent_org_summary, get_agent_summary, group_agent_teams, list_agents
from ..app.agent_control.agents import list_agent_definitions
from ..app.agent_control.controller import (
    cancel_job as cancel_agent_control_job,
    get_agent_control_report,
    get_agent_control_status,
    list_agent_control_agents,
    list_agent_control_events,
    list_agent_control_jobs,
    list_human_review_items,
    mark_reviewed_job,
    register_url_candidate,
    run_agent_job,
    run_daily_report_job,
    run_form_check_job,
    run_human_review_job,
    run_safety_check_job,
)
from ..app.later_queue import (
    add_later_queue,
    bridge_later_queue_to_campaign,
    list_later_queue,
    remove_later_queue_item,
    search_later_queue,
    summarize_later_queue,
    update_later_queue_status,
)
from ..app.version import APP_VERSION
from ..mail_importer import get_mail_sweepstake, load_mail_sweepstakes, mail_sweepstakes_summary, rescan_mail_sweepstakes, rescan_win_mail_candidates, update_mail_sweepstake
from ..mail_importer import sort_mail_sweepstakes
from ..app.apply_queue import build_apply_queue, _deadline_bucket, get_current_queue_item, get_next_queue_item, save_apply_queue
from ..ui.data_loader import (
    approve_queue_item,
    approved_queue_rows,
    load_latest_x_campaign_day,
    load_research_report,
    load_auto_scan_report,
    load_apply_queue,
    load_campaigns,
    load_form_inspections,
    load_recent_activity,
    load_release_report,
    load_masked_profile_preview,
    load_x_campaign_candidates_for_day,
    load_x_campaign_days,
    load_x_campaign_report_for_day,
    load_x_campaign_run_for_day,
    load_x_campaign_queue_for_day,
    mark_hold,
    mark_excluded,
    mark_manual_submitted,
    mark_prepared,
    mark_selected,
    mark_skipped,
    set_age_fill_user_approved,
    register_email_campaign,
    profile_storage_state,
    summarize_apply_queue,
    summarize_campaigns,
    update_apply_queue_status,
)
from ..app.research_engine import RESEARCH_CATEGORY_LABELS, annotate_research_rows
from ..app.profile_manager import load_profile
from ..app.run_mode import get_run_mode, normalize_run_mode
from ..app.entry_url_resolver import target_url_for_campaign

WEB_HOST = "127.0.0.1"
WEB_PORT = 8787
SAFE_WEB_ACTIONS = {
    "auto_scan": ["auto-scan", "--limit", "30"],
    "build_queue": ["build-queue", "--limit", "30"],
    "release_report": ["release-report", "--version", APP_VERSION],
    "research": ["research", "--limit", "30"],
    "research_report": ["research-report"],
    "doctor": ["doctor"],
    "browser_doctor": ["browser", "doctor"],
    "resolve_urls": ["resolve-urls", "--limit", "30"],
    "inspect_form": ["inspect-form", "--limit", "20"],
    "review": ["review", "--limit", "10"],
}
_OPEN_X_PREPARE_CONTEXTS: dict[str, object] = {}
NAV_ITEMS = [
    ("dashboard", "ダッシュボード", "/"),
    ("search", "懸賞を探す", "/search"),
    ("today", "今日の候補", "/today"),
    ("queue", "応募キュー", "/queue"),
    ("approved", "承認済み", "/approved"),
    ("entries", "応募履歴", "/entries"),
    ("later", "あとで応募", "/later-queue"),
    ("mail", "メール懸賞", "/mail"),
    ("review", "要確認", "/review"),
    ("campaigns", "キャンペーン一覧", "/campaigns"),
    ("research", "リサーチ", "/research"),
    ("x_research", "X懸賞", "/research/x-campaigns"),
    ("diagnosis", "フォーム診断", "/campaigns?status=要確認"),
    ("report", "レポート", "/security"),
    ("ai_agents", "AI担当者", "/ai-agents"),
    ("agent_control", "AI司令塔", "/agent-control"),
    ("security", "セキュリティ", "/security"),
    ("settings", "設定", "/security"),
    ("help", "ヘルプ・使い方", "/security"),
]
CATEGORY_LABELS = [
    "すべて",
    "大量当選",
    "締切間近",
    "食品",
    "飲料",
    "商品券",
    "家電",
    "日用品",
    "化粧品",
    "旅行",
    "映画・チケット",
    "Amazonギフト券",
    "QUOカード",
    "ビール",
    "コーヒー",
    "お菓子",
    "ゲーム",
    "スマホ",
    "防災用品",
]
SAFE_STATUS_FILTERS = [
    ("すべて", "safe"),
    ("REVIEW_ONLY", "review_only"),
    ("READY_FOR_FILL", "ready"),
]

MAIL_STATUS_FILTERS = [
    ("すべて", "all"),
    ("未確認", "ignored"),
    ("応募候補", "candidate"),
    ("応募済み", "added"),
    ("危険", "danger"),
    ("期限切れ", "expired"),
    ("重複", "duplicate"),
]
PRIZE_QUICK_LINKS = [
    ("食品", "食品"),
    ("飲料", "飲料"),
    ("商品券", "商品券"),
    ("家電", "家電"),
    ("旅行", "旅行"),
    ("Amazonギフト券", "Amazonギフト券"),
    ("QUOカード", "QUOカード"),
]

STATUS_DISPLAY_LABELS = {
    "REVIEW_ONLY": "要確認",
    "READY_FOR_FILL": "入力候補",
    "LANDING_PAGE": "案内ページ",
    "SEARCH_ONLY": "検索欄のみ",
    "LOW_CONFIDENCE": "信頼度低",
    "RESOLVED": "URL解決済み",
    "SUBMITTED": "送信済み",
}

METRIC_DISPLAY_LABELS = {
    "submitted_count": "送信件数",
    "collected_count": "収集件数",
    "resolved_count": "URL解決済み",
    "ready_for_fill_count": "入力候補",
    "review_only_count": "要確認",
}


def _text(row: dict[str, str]) -> str:
    return " ".join(
        row.get(field, "")
        for field in (
            "campaign_name",
            "prize",
            "provider",
            "category",
            "entry_type_raw",
            "description",
            "notes",
            "status",
            "resolve_status",
            "form_readiness_status",
        )
    ).casefold()


def _safe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    safe: list[dict[str, str]] = []
    for row in rows:
        status = row.get("form_readiness_status", "") or row.get("resolve_status", "") or row.get("status", "")
        safe.append(
            {
                "campaign_id": row.get("campaign_id", ""),
                "campaign_name": row.get("campaign_name", ""),
                "prize": row.get("prize", ""),
                "winner_count": row.get("winner_count", ""),
                "provider": row.get("provider", ""),
                "deadline": row.get("deadline", ""),
                "category": row.get("category", ""),
                "entry_type_raw": row.get("entry_type_raw", ""),
                "resolved_entry_url": row.get("resolved_entry_url", ""),
                "entry_url": row.get("entry_url", ""),
                "knshow_url": row.get("knshow_url", ""),
                "resolve_status": row.get("resolve_status", ""),
                "resolve_reason": row.get("resolve_reason", ""),
                "form_readiness_status": row.get("form_readiness_status", ""),
                "form_readiness_score": row.get("form_readiness_score", ""),
                "form_readiness_reason": row.get("form_readiness_reason", ""),
                "quiz_required": row.get("quiz_required", ""),
                "quiz_summary": row.get("quiz_summary", ""),
                "quiz_manual_required": row.get("quiz_manual_required", ""),
                "quiz_items": row.get("quiz_items", []),
                "selected_by_user": row.get("selected_by_user", ""),
                "excluded_by_user": row.get("excluded_by_user", ""),
                "status": row.get("status", ""),
                "research_keyword": row.get("research_keyword", ""),
                "research_category": row.get("research_category", ""),
                "research_source": row.get("research_source", ""),
                "discovered_at": row.get("discovered_at", ""),
                "opportunity_score": row.get("opportunity_score", ""),
                "opportunity_rank": row.get("opportunity_rank", ""),
                "opportunity_reason": row.get("opportunity_reason", ""),
                "risk_level": row.get("risk_level", ""),
                "risk_reasons": row.get("risk_reasons", ""),
                "recommendation_reason": row.get("recommendation_reason", ""),
                "next_action": row.get("next_action", ""),
                "one_line_reason": _one_line_reason(row.get("form_readiness_reason", "") or row.get("resolve_reason", "")),
                "risk_class": _risk_class(status),
            }
        )
    return safe


def _join_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value)


def _one_line_reason(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""
    for separator in ("。", "．", ".", "！", "!", "？", "?"):
        if separator in text:
            text = text.split(separator, 1)[0].strip()
            break
    return text[:42]


def _truncate_text(value: str, limit: int = 120) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…"


def _safe_internal_next_url(next_url: str, default: str) -> str:
    candidate = (next_url or "").strip()
    if not candidate or any(char in candidate for char in ("\r", "\n")):
        return default
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return default
    if not candidate.startswith("/") or candidate.startswith("//"):
        return default
    return candidate


def _trusted_local_origin(value: str) -> bool:
    text = (value or "").strip()
    if not text or text.casefold() == "null":
        return False
    parsed = urlsplit(text)
    host = (parsed.hostname or "").casefold()
    return host in {"127.0.0.1", "localhost", "::1"}


def _risk_class(status: str) -> str:
    if status in {"LOW_CONFIDENCE", "SEARCH_ONLY", "LANDING_PAGE"} or status.startswith("BLOCKED"):
        return "danger-faded"
    return ""


def _mail_filter_rows(rows: list[dict[str, object]], status: str) -> list[dict[str, object]]:
    if status in {"", "all"}:
        return rows
    filtered: list[dict[str, object]] = []
    for row in rows:
        row_status = str(row.get("status", "ignored"))
        deadline_state = str(row.get("deadline_state", "unknown"))
        if status == "expired":
            if deadline_state == "expired":
                filtered.append(row)
            continue
        if row_status == status:
            filtered.append(row)
    return filtered


def _entry_status_label(status: str) -> str:
    mapping = {
        "APPLIED": "応募済み",
        "PENDING_RESULT": "当選確認待ち",
        "RESULT_CHECKED": "当選確認済み",
        "DUPLICATE": "重複",
        "SKIPPED": "スキップ",
        "HOLD": "保留",
        "unknown": "未設定",
    }
    return mapping.get(status, status or "未設定")


def _newsletter_status_label(status: str) -> str:
    mapping = {
        "unknown": "不明",
        "opt_in": "登録中",
        "opt_out": "解除済み",
        "unsubscribe_needed": "解除候補",
        "unsubscribed": "解除済み",
    }
    return mapping.get(status, status or "不明")


def _entry_deadline_bucket(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "unknown"
    if any(keyword in text for keyword in ("今日", "本日")):
        return "today"
    if "明日" in text:
        return "tomorrow"
    if "今週" in text or "週末" in text:
        return "week"
    if any(keyword in text for keyword in ("期限切れ", "終了")):
        return "expired"
    return "future"


def _entry_filter_rows(
    rows: list[dict[str, str]],
    query: str,
    deadline: str,
    result: str,
    newsletter: str,
    status: str,
) -> list[dict[str, str]]:
    query_text = query.casefold().strip()
    filtered: list[dict[str, str]] = []
    for row in rows:
        haystack = " ".join(
            row.get(field, "")
            for field in ("campaign_id", "title", "source_site", "url", "prize", "deadline", "status", "newsletter_status", "memo", "duplicate_key")
        ).casefold()
        if query_text and query_text not in haystack:
            continue
        if deadline != "all" and _entry_deadline_bucket(row.get("deadline", "")) != deadline:
            continue
        if result != "all":
            row_status = row.get("status", "").upper()
            if result == "pending" and row_status not in {"APPLIED", "PENDING_RESULT"}:
                continue
            if result == "applied" and row_status != "APPLIED":
                continue
            if result == "checked" and row_status != "RESULT_CHECKED":
                continue
            if result == "duplicate" and row_status != "DUPLICATE":
                continue
        if newsletter != "all" and row.get("newsletter_status", "unknown") != newsletter:
            continue
        if status != "all" and row.get("status", "") != status:
            continue
        filtered.append(row)
    return filtered


def _later_status_label(value: str) -> str:
    labels = {
        "queued": "登録済み",
        "needs_review": "要確認",
        "reviewing": "確認中",
        "ready_for_fill": "入力準備",
        "applied_manual": "手動応募済み",
        "skipped": "スキップ",
        "expired": "期限切れ",
    }
    return labels.get(value, value or "unknown")


def _later_status_sort_value(value: str) -> int:
    order = {
        "queued": 0,
        "needs_review": 1,
        "reviewing": 2,
        "ready_for_fill": 3,
        "applied_manual": 4,
        "skipped": 5,
        "expired": 6,
    }
    return order.get(value, 99)


def _later_deadline_bucket(value: str) -> tuple[int, str]:
    text = (value or "").strip()
    if not text or text.casefold() == "unknown":
        return (9999, "unknown")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(text, fmt).date()
            return ((dt - date.today()).days, text)
        except ValueError:
            continue
    if any(keyword in text for keyword in ("今日", "本日")):
        return (0, text)
    if "明日" in text:
        return (1, text)
    if any(keyword in text for keyword in ("今週", "週末")):
        return (7, text)
    return (9999, text)


def _later_filter_rows(rows: list[dict[str, str]], query: str, status: str) -> list[dict[str, str]]:
    query_text = query.casefold().strip()
    filtered: list[dict[str, str]] = []
    for row in rows:
        haystack = " ".join(
            row.get(field, "")
            for field in ("id", "title", "site_name", "url", "normalized_url", "deadline", "status", "source_type", "safety_memo", "review_note")
        ).casefold()
        if query_text and query_text not in haystack:
            continue
        if status != "all" and row.get("status", "") != status:
            continue
        filtered.append(row)
    return filtered


def _later_sort_rows(rows: list[dict[str, str]], sort: str = "deadline") -> list[dict[str, str]]:
    def sort_key(row: dict[str, str]) -> tuple[int, int, int, str, str]:
        deadline_bucket, _ = _later_deadline_bucket(row.get("deadline", ""))
        status_value = _later_status_sort_value(row.get("status", ""))
        if sort == "updated":
            return (status_value, 0, deadline_bucket, row.get("updated_at", ""), row.get("title", ""))
        return (deadline_bucket, status_value, 0, row.get("updated_at", ""), row.get("title", ""))

    return sorted(rows, key=sort_key)


def _parse_deadline(value: str) -> tuple[int, int, int]:
    text = (value or "").strip()
    if not text:
        return (9999, 12, 31)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(text, fmt).date()
            return (dt.year, dt.month, dt.day)
        except ValueError:
            pass
    m = re.search(r"(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})日", text)
    if m:
        year = int(m.group(1) or date.today().year)
        return (year, int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})/(\d{1,2})", text)
    if m:
        return (date.today().year, int(m.group(1)), int(m.group(2)))
    return (9999, 12, 31)


def _sort_campaign_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    def sort_key(row: dict[str, str]) -> tuple[int, int, int, str]:
        priority = 0
        status = row.get("form_readiness_status", "") or row.get("resolve_status", "") or row.get("status", "")
        if status == "REVIEW_ONLY":
            priority = 0
        elif status == "READY_FOR_FILL":
            priority = 1
        elif status == "RESOLVED":
            priority = 2
        elif status in {"LANDING_PAGE", "SEARCH_ONLY", "LOW_CONFIDENCE"} or status.startswith("BLOCKED"):
            priority = 3
        return (*_parse_deadline(row.get("deadline", "")), priority, row.get("campaign_name", ""))

    return sorted(rows, key=sort_key)


def _queue_sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    order = {"QUEUED": 0, "APPROVED": 1, "PREPARED": 2, "HOLD": 3, "SKIPPED": 4, "BLOCKED": 5, "MANUALLY_SUBMITTED": 6}

    def sort_key(row: dict[str, str]) -> tuple[int, int, int, str]:
        deadline_bucket, _ = _deadline_bucket(row.get("deadline", ""))
        readiness = 0 if row.get("readiness_status") == "READY_FOR_FILL" else 1
        return (deadline_bucket, readiness, order.get(row.get("queue_status", "QUEUED"), 9), row.get("campaign_name", ""))

    return sorted(rows, key=sort_key)


def _queue_session_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    session_rows = _queue_sort_rows(rows)
    return [row for row in session_rows if row.get("queue_status", "QUEUED") in {"QUEUED", "HOLD", "PREPARED"}]


def _queue_state_label(row: dict[str, str]) -> str:
    status = row.get("queue_status", "QUEUED")
    labels = {
        "QUEUED": "未処理",
        "APPROVED": "応募候補に承認済み",
        "PREPARED": "Chromeで応募準備済み",
        "MANUALLY_SUBMITTED": "手動送信済み",
        "HOLD": "保留",
        "SKIPPED": "スキップ",
        "BLOCKED": "除外",
    }
    return labels.get(status, status or "未処理")


def _queue_last_action_label(row: dict[str, str]) -> str:
    action = row.get("last_action", "")
    labels = {
        "PREPARED_WITH_CHROME": "応募ページをChromeで開きました。アプリは送信していません。",
        "PREPARE_CANCELLED_BY_USER": "応募準備はキャンセルされました。",
        "APPROVED_BY_USER": "応募対象に承認しました。",
        "MANUAL_SUBMITTED_RECORDED": "手動送信済みを記録しました。",
    }
    return labels.get(action, action or "なし")


def _dry_run_state_label(row: dict[str, str]) -> str:
    status = row.get("dry_run_status", "").strip()
    labels = {
        "PRE_SUBMIT_READY": "送信直前まで入力済み",
        "REVIEW_FILL_READY": "確認ありで入力済み",
        "MANUAL_ASSIST_READY": "手動補助が必要",
        "DRY_RUN_COMPLETED": "送信直前まで入力済み",
        "NEEDS_REVIEW": "確認ありで入力済み",
        "SKIPPED": "対象外",
    }
    return labels.get(status, status or "未実行")


def _dry_run_detail_label(row: dict[str, str]) -> str:
    summary = row.get("dry_run_reason_summary", "").strip()
    if summary:
        return summary
    status = row.get("dry_run_status", "")
    if status == "PRE_SUBMIT_READY":
        return "送信直前まで入力済みで、人間が最終確認して送信する状態です。"
    if status == "REVIEW_FILL_READY":
        return "基本入力は済んでいますが、確認項目があります。"
    if status == "MANUAL_ASSIST_READY":
        return "ログインやSNSなど、人間操作が必要です。"
    if status == "DRY_RUN_COMPLETED":
        return "送信せずに入力補助と送信前チェックまで完了しています。"
    if status == "NEEDS_REVIEW":
        return "送信前チェックで人間確認が必要です。"
    if row.get("dry_run_status", "") == "SKIPPED":
        return "危険または対象外判定です。"
    return "まだ dry_run を実行していません。"


def _parse_review_items(raw: str) -> list[dict[str, object]]:
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    items: list[dict[str, object]] = []
    for item in data:
        if isinstance(item, dict):
            items.append(item)
    return items


def _review_item_summary(item: dict[str, object]) -> str:
    kind = str(item.get("kind", "")).strip() or "item"
    field_name = str(item.get("field_name", "")).strip()
    label = str(item.get("label", "")).strip()
    reason = str(item.get("reason", "")).strip()
    parts = [part for part in [kind, field_name or label, reason] if part]
    return " / ".join(parts)


def _queue_risk_notice(row: dict[str, str]) -> str:
    joined = " ".join(
        str(row.get(field, ""))
        for field in ("risk_level", "risk_reasons", "skip_reason_summary", "form_readiness_reason", "resolve_reason")
    )
    if "DUPLICATE_ENTRY" in joined:
        return "注意：似た候補が見つかっています。必要なら詳細を確認してください。"
    return ""


def _queue_next_action_label(row: dict[str, str]) -> str:
    if row.get("manual_submitted_at", "").strip() or row.get("submission_method", "").strip().upper() == "MANUAL":
        return "次の候補へ進んでください。"
    status = row.get("queue_status", "QUEUED")
    if status == "PREPARED":
        return "Chrome上で内容を確認し、送信した場合だけ『手動送信済みにする』を押してください。"
    if status == "MANUALLY_SUBMITTED":
        return "次の候補へ進んでください。"
    if status == "APPROVED":
        return "Chromeで応募準備を押してください。"
    if status == "HOLD":
        return "保留のまま様子を見てください。"
    if status == "SKIPPED":
        return "次の候補を確認してください。"
    if status == "BLOCKED":
        return "除外済みです。"
    return row.get("next_action", "") or "Chromeで応募準備をしてください。"


def _decorate_queue_row(row: dict[str, str]) -> dict[str, str]:
    decorated = dict(row)
    decorated["state_label"] = _queue_state_label(row)
    decorated["last_action_label"] = _queue_last_action_label(row)
    decorated["next_action_label"] = _queue_next_action_label(row)
    decorated["auto_submit_label"] = "無効"
    decorated["manual_record_label"] = "手動送信済みを記録しました。" if row.get("manual_submitted_at", "").strip() or row.get("submission_method", "").strip().upper() == "MANUAL" else "送信した場合だけ記録してください"
    decorated["risk_notice"] = _queue_risk_notice(row)
    decorated["risk_detail"] = row.get("risk_level", "") or row.get("risk_reasons", "") or row.get("skip_reason_summary", "")
    decorated["dry_run_state_label"] = _dry_run_state_label(row)
    decorated["dry_run_detail_label"] = _dry_run_detail_label(row)
    decorated["dry_run_score_label"] = row.get("dry_run_pre_submit_score", "")
    decorated["dry_run_completion_label"] = row.get("dry_run_fill_completion_rate", "")
    decorated["dry_run_unresolved_label"] = row.get("dry_run_unresolved_required_fields_count", "")
    decorated["dry_run_submit_button_label"] = "あり" if row.get("dry_run_submit_button_detected", "").lower() == "true" else "なし"
    decorated["dry_run_review_items_label"] = row.get("dry_run_review_items", "")
    decorated["dry_run_review_items_parsed"] = _parse_review_items(row.get("dry_run_review_items", ""))
    decorated["dry_run_review_items_summary"] = [_review_item_summary(item) for item in decorated["dry_run_review_items_parsed"]]
    return decorated


def _approved_queue_sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    def sort_key(row: dict[str, str]) -> tuple[int, int, int, int, str]:
        order_text = row.get("approved_session_order", "").strip()
        try:
            order = int(order_text) if order_text else 9999
        except ValueError:
            order = 9999
        priority_text = row.get("priority_score", "") or row.get("readiness_score", "")
        try:
            priority = int(float(priority_text)) if priority_text else 0
        except ValueError:
            priority = 0
        opportunity_text = row.get("opportunity_score", "")
        try:
            opportunity = int(float(opportunity_text)) if opportunity_text else 0
        except ValueError:
            opportunity = 0
        deadline_bucket, _ = _deadline_bucket(row.get("deadline", ""))
        return (deadline_bucket, -priority, -opportunity, order, row.get("campaign_name", ""))

    return sorted(rows, key=sort_key)


def _approved_queue_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("queue_status", "") in {"APPROVED", "PREPARED", "HOLD"}]


def _research_rows(rows: list[dict[str, str]], query: str = "", category: str = "") -> list[dict[str, str]]:
    annotated = annotate_research_rows(rows)
    query_text = query.casefold().strip()
    category_text = category.casefold().strip()
    filtered: list[dict[str, str]] = []
    for row in annotated:
        haystack = _text(row)
        if query_text and query_text not in haystack:
            continue
        if category_text and category_text != "すべて":
            if category_text not in (row.get("research_category", "") or row.get("category", "")).casefold():
                continue
        filtered.append(row)
    filtered.sort(key=lambda row: (-int(row.get("opportunity_score", "0") or 0), row.get("deadline", ""), row.get("campaign_name", "")))
    return filtered


def _x_campaign_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    def sort_key(row: dict[str, object]) -> tuple[int, int, int, float, str, str]:
        try:
            total = int(float(row.get("total_score", 0) or 0))
        except (TypeError, ValueError):
            total = 0
        try:
            safety = int(float(row.get("safety_score", 0) or 0))
        except (TypeError, ValueError):
            safety = 0
        try:
            trust = int(float(row.get("trust_score", 0) or 0))
        except (TypeError, ValueError):
            trust = 0
        try:
            confidence = float(row.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        return (-total, -safety, -trust, -confidence, str(row.get("deadline", "")), str(row.get("title", "")))

    return sorted(rows, key=sort_key)


def _x_campaign_summary(rows: list[dict[str, object]]) -> dict[str, int]:
    summary = {
        "total": len(rows),
        "review": 0,
        "watch": 0,
        "skip": 0,
        "human_review": 0,
        "blocked": 0,
        "with_url": 0,
        "missing_url": 0,
    }
    for row in rows:
        recommendation = str(row.get("recommendation", row.get("queue_status", "watch")))
        status = str(row.get("status", "research_found"))
        if recommendation == "review":
            summary["review"] += 1
        elif recommendation == "watch":
            summary["watch"] += 1
        elif recommendation == "skip":
            summary["skip"] += 1
        if status == "review_pending":
            summary["human_review"] += 1
        elif status == "skipped":
            summary["blocked"] += 1
        if row.get("post_url"):
            summary["with_url"] += 1
        else:
            summary["missing_url"] += 1
    summary["human_review"] = summary["human_review"] or summary["review"]
    summary["blocked"] = summary["blocked"] or summary["skip"]
    return summary


def _x_queue_sort_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    order = {"review_pending": 0, "user_selected": 1, "apply_prepare_only": 2, "skipped": 3}

    def sort_key(row: dict[str, object]) -> tuple[int, int, int, float, str, str]:
        try:
            total = int(float(row.get("total_score", 0) or 0))
        except (TypeError, ValueError):
            total = 0
        try:
            safety = int(float(row.get("safety_score", 0) or 0))
        except (TypeError, ValueError):
            safety = 0
        try:
            trust = int(float(row.get("trust_score", 0) or 0))
        except (TypeError, ValueError):
            trust = 0
        try:
            confidence = float(row.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        return (
            order.get(str(row.get("status", "review_pending")), 9),
            -total,
            -safety,
            -trust,
            -confidence,
            str(row.get("deadline", "")),
            str(row.get("title", "")),
        )

    return sorted(rows, key=sort_key)


def _x_queue_summary(rows: list[dict[str, object]]) -> dict[str, int]:
    summary = {
        "total": len(rows),
        "review_pending": 0,
        "user_selected": 0,
        "apply_prepare_only": 0,
        "skipped": 0,
        "prepare_ready": 0,
        "prepare_warning": 0,
        "prepare_blocked": 0,
    }
    for row in rows:
        status = str(row.get("status", "review_pending"))
        summary[status] = summary.get(status, 0) + 1
        safety = int(float(row.get("safety_score", 0) or 0))
        if safety >= 70:
            summary["prepare_ready"] += 1
        elif safety >= 50:
            summary["prepare_warning"] += 1
        else:
            summary["prepare_blocked"] += 1
    return summary


def _queue_session_index(rows: list[dict[str, str]], campaign_id: str) -> int:
    for index, row in enumerate(rows):
        if row.get("campaign_id") == campaign_id or row.get("queue_id") == campaign_id:
            return index
    return 0


def display_status_label(value: str) -> str:
    return STATUS_DISPLAY_LABELS.get(value, value)


def display_metric_label(value: str) -> str:
    return METRIC_DISPLAY_LABELS.get(value, value)


def normalize_status_filter(value: str) -> str:
    reverse = {label: key for key, label in STATUS_DISPLAY_LABELS.items()}
    return reverse.get(value, value)


def _filter_campaigns(rows: list[dict[str, str]], query: str, category: str, mode: str) -> list[dict[str, str]]:
    query_text = query.casefold().strip()
    filtered: list[dict[str, str]] = []
    for row in rows:
        haystack = _text(row)
        if query_text and query_text not in haystack:
            continue
        if category and category != "すべて" and category.casefold() not in haystack:
            continue
        if mode == "review_only" and row.get("form_readiness_status") != "REVIEW_ONLY":
            continue
        if mode == "ready" and row.get("form_readiness_status") != "READY_FOR_FILL":
            continue
        if mode == "safe" and row.get("form_readiness_status") not in {"REVIEW_ONLY", "READY_FOR_FILL"}:
            continue
        filtered.append(row)
    return filtered


def _context_common() -> dict[str, object]:
    release_report = load_release_report()
    auto_scan = load_auto_scan_report()
    research_report = load_research_report()
    campaigns = load_campaigns()
    apply_queue = load_apply_queue()
    later_queue = list_later_queue()
    inspections = load_form_inspections()
    entry_history_rows = load_entry_history()
    mail_rows = load_mail_sweepstakes()
    win_mail_rows = load_win_mail_candidates()
    summary = summarize_campaigns()
    return {
        "release_report": release_report,
        "auto_scan": auto_scan,
        "research_report": research_report,
        "campaigns": _safe_rows(campaigns),
        "apply_queue": apply_queue,
        "later_queue": later_queue,
        "later_queue_summary": summarize_later_queue(later_queue),
        "campaign_count": len(campaigns),
        "summary": summary,
        "queue_summary": summarize_apply_queue(apply_queue),
        "inspections": inspections,
        "activity": load_recent_activity(),
        "profile_state": profile_storage_state(),
        "app_version": APP_VERSION,
        "selected_count": sum(1 for row in campaigns if row.get("selected_by_user") == "true"),
        "excluded_count": sum(1 for row in campaigns if row.get("excluded_by_user") == "true"),
        "entry_history": entry_history_rows,
        "entry_history_summary": summarize_entry_history(entry_history_rows),
        "mail_sweepstakes": mail_rows,
        "mail_summary": mail_sweepstakes_summary(mail_rows),
        "win_mail_candidates": win_mail_rows,
        "win_mail_summary": summarize_win_mail_candidates(win_mail_rows),
        "safety_note": "本番送信は人間確認が必要",
        "site_note": "懸賞生活の公式ツールではありません",
        "display_status_label": display_status_label,
        "display_metric_label": display_metric_label,
        "entry_status_label": _entry_status_label,
        "newsletter_status_label": _newsletter_status_label,
        "later_status_label": _later_status_label,
        "truncate_text": _truncate_text,
    }


def _category_links(query: str, mode: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for label in CATEGORY_LABELS:
        links.append(
            {
                "label": label,
                "href": f"/search?category={quote_plus(label)}&mode={quote_plus(mode)}&q={quote_plus(query)}",
            }
        )
    return links


def _prize_links(query: str, mode: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for label, keyword in PRIZE_QUICK_LINKS:
        links.append(
            {
                "label": label,
                "href": f"/search?q={quote_plus(keyword)}&category={quote_plus(label)}&mode={quote_plus(mode)}",
            }
        )
    return links


def _render(request: Request, template_name: str, **context: object) -> HTMLResponse:
    common = _context_common()
    common.update(context)
    common["request"] = request
    common["nav_items"] = NAV_ITEMS
    common["category_labels"] = CATEGORY_LABELS
    templates = request.app.state.templates
    return templates.TemplateResponse(request, template_name, common)


def _run_safe_action(name: str) -> str:
    if name not in SAFE_WEB_ACTIONS:
        return "unsupported"
    command = [sys.executable, str(PACKAGE_ROOT.parent / "main.py"), *SAFE_WEB_ACTIONS[name]]
    subprocess.run(command, check=False, capture_output=True, text=True)
    return "ok"


def _start_chrome_prepare(campaign_id: str, allow_age_fill: bool = False) -> str:
    try:
        command = [
            sys.executable,
            str(PACKAGE_ROOT.parent / "main.py"),
            "prepare",
            "--campaign-id",
            campaign_id,
            "--browser",
            "chrome",
            "--keep-open",
            "--no-screenshot",
            "--require-user-approved",
        ]
        if allow_age_fill:
            command.append("--allow-age-fill")
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(
            command,
            cwd=str(PACKAGE_ROOT.parent),
            creationflags=creationflags,
        )
        return "started"
    except Exception:
        return "launch_failed"


def _start_x_campaign_prepare(candidate_id: str, target_url: str) -> str:
    if not target_url:
        return "missing_url"
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return "missing_playwright"
    try:
        with sync_playwright() as playwright:
            context, _page, _browser = open_url_in_chrome(playwright, target_url, "chrome")
            previous = _OPEN_X_PREPARE_CONTEXTS.pop(candidate_id, None)
            if previous is not None:
                close_browser_safely(previous)
            _OPEN_X_PREPARE_CONTEXTS[candidate_id] = context
            return "started"
    except Exception:
        return "launch_failed"


def _prepare_command(campaign_id: str, allow_age_fill: bool = False) -> str:
    command = [
        "python",
        "main.py",
        "prepare",
        "--campaign-id",
        campaign_id,
        "--browser",
        "chrome",
        "--keep-open",
        "--no-screenshot",
        "--require-user-approved",
    ]
    if allow_age_fill:
        command.append("--allow-age-fill")
    return " ".join(command)


def _queue_item_for_id(queue_id: str) -> dict[str, str]:
    for row in load_apply_queue():
        if row.get("queue_id") == queue_id or row.get("campaign_id") == queue_id:
            return row
    for row in load_campaigns():
        if row.get("campaign_id") == queue_id:
            return row
    return {}


def _x_queue_item_for_id(candidate_id: str, day: str = "") -> dict[str, object]:
    rows = load_x_campaign_queue_for_day(day or None)
    for row in rows:
        if str(row.get("candidate_id", "")) == candidate_id or str(row.get("id", "")) == candidate_id:
            return row
        if candidate_id and str(row.get("post_url", "")) == candidate_id:
            return row
    candidates = load_x_campaign_candidates_for_day(day or None)
    for row in candidates:
        if str(row.get("candidate_id", "")) == candidate_id or str(row.get("post_url", "")) == candidate_id:
            return row
    return {}


async def _request_payload(request: Request) -> dict[str, object]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
            if isinstance(payload, dict):
                return payload
        except Exception:
            return {}
    try:
        form = await request.form()
    except Exception:
        return {}
    return {str(key): value for key, value in form.items()}


def create_app() -> FastAPI:
    app = FastAPI(title="懸賞応募アシスタント Web UI")
    templates = Jinja2Templates(directory=str(APP_DIR.parent / "web" / "templates"))
    app.state.templates = templates
    app.state.web_host = WEB_HOST
    app.state.web_port = WEB_PORT
    app.mount("/static", StaticFiles(directory=str(APP_DIR.parent / "web" / "static")), name="static")

    @app.middleware("http")
    async def block_cross_origin_state_changes(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin", "")
            referer = request.headers.get("referer", "")
            source = origin or referer
            if source and not _trusted_local_origin(source):
                return PlainTextResponse("Forbidden", status_code=403)
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        report = load_release_report()
        auto_scan = load_auto_scan_report()
        research_report = load_research_report()
        summary = summarize_campaigns()
        browser_state = check_chrome_available()
        profile_state = profile_storage_state()
        today_candidates = _sort_campaign_rows(
            [row for row in load_campaigns() if row.get("form_readiness_status") in {"REVIEW_ONLY", "READY_FOR_FILL"}]
        )[:6]
        return _render(
            request,
            "dashboard.html",
            page_title="ダッシュボード",
            active_page="dashboard",
            report=report,
            auto_scan=auto_scan,
            research_report=research_report,
            summary=summary,
            browser_prepare_status="OK" if browser_state.get("headed_launch") == "ok" else "要確認",
            today_candidates=_safe_rows(today_candidates),
            browser_state=browser_state,
            profile_state=profile_state,
            entry_summary=summarize_entry_history(load_entry_history()),
            research_summary={
                "total": research_report.get("total", 0) if research_report else 0,
                "score_80_plus": research_report.get("score_bins", {}).get("80_plus", 0) if research_report else 0,
                "review_only": sum(1 for row in load_campaigns() if row.get("form_readiness_status") == "REVIEW_ONLY"),
                "exclude": research_report.get("score_bins", {}).get("0_39", 0) if research_report else 0,
                "deadline_soon": research_report.get("deadline_soon_count", 0) if research_report else 0,
                "queue_candidates": len(research_report.get("top_candidates", [])) if research_report else 0,
            },
            safety_checklist=[
                ("profile.enc", profile_state.get("profile_enc", "未検出")),
                ("profile.json", "不在" if profile_state.get("profile_json") == "未検出" else "検出"),
                ("スクショ保存", "OFF"),
                ("ログマスキング", "ON"),
                ("release-report", "OK" if report.get("release_status") == "OK" else "要確認"),
                ("Chrome応募準備", "OK" if browser_state.get("headed_launch") == "ok" else "要確認"),
            ],
        )

    @app.get("/today", response_class=HTMLResponse)
    def today(request: Request) -> HTMLResponse:
        today_candidates = _sort_campaign_rows(
            [row for row in load_campaigns() if row.get("form_readiness_status") in {"REVIEW_ONLY", "READY_FOR_FILL"}]
        )[:12]
        return _render(
            request,
            "dashboard.html",
            page_title="今日の候補",
            active_page="today",
            report=load_release_report(),
            auto_scan=load_auto_scan_report(),
            summary=summarize_campaigns(),
            today_candidates=_safe_rows(today_candidates),
        )

    @app.get("/ai-agents", response_class=HTMLResponse)
    def ai_agents(request: Request, mode: str = "normal") -> HTMLResponse:
        resolved_mode = mode if mode in {"normal", "release"} else "normal"
        agents = list_agents(mode=resolved_mode)
        summary = get_agent_summary(mode=resolved_mode)
        org_summary = get_agent_org_summary(mode=resolved_mode)
        team_groups = group_agent_teams(mode=resolved_mode)
        return _render(
            request,
            "agent_dashboard.html",
            page_title="AI担当者",
            active_page="ai_agents",
            agents=agents,
            agent_summary=summary,
            agent_org_summary=org_summary,
            agent_team_groups=team_groups,
            agent_mode=resolved_mode,
            agent_view_mode="現在はJSON結果表示モードです。",
        )

    @app.get("/agent-control", response_class=HTMLResponse)
    def agent_control(request: Request, agent: str = "", job_id: str = "", target_url: str = "") -> HTMLResponse:
        status = get_agent_control_status()
        report = get_agent_control_report()
        agents = list_agent_control_agents()
        jobs = list_agent_control_jobs(limit=50)
        events = list_agent_control_events(limit=12)
        human_review_jobs = list_human_review_items(limit=20)
        selected_agent = agent or (agents[0].get("agent_name", "") if agents else "")
        selected_job = job_id
        if not selected_job and jobs:
            selected_job = str(jobs[0].get("job_id", ""))
        selected_job_row = next((row for row in jobs if str(row.get("job_id", "")) == selected_job), {})
        return _render(
            request,
            "agent_control.html",
            page_title="AI司令塔",
            active_page="agent_control",
            agent_control_status=status,
            agent_control_report=report,
            agent_control_agents=agents,
            agent_control_jobs=jobs,
            agent_control_events=events,
            agent_control_human_review_jobs=human_review_jobs,
            agent_control_selected_agent=selected_agent,
            agent_control_selected_job=selected_job_row,
            agent_definitions=list_agent_definitions(),
            agent_control_target_url=target_url,
        )

    @app.post("/agent-control/register-url")
    def agent_control_register_url(
        target_url: str = Form(default=""),
        next_url: str = Form(default="/agent-control"),
    ) -> RedirectResponse:
        job = run_agent_job("QueueAgent", action="register_url", target_url=target_url)
        message = job.get("result_summary", "done") if job else "failed"
        return RedirectResponse(
            url=f"/agent-control?agent=QueueAgent&job_id={quote_plus(job.get('job_id', ''))}&target_url={quote_plus(target_url)}&message={quote_plus(message)}",
            status_code=303,
        )

    @app.post("/agent-control/form-check")
    def agent_control_form_check(
        target_url: str = Form(default=""),
        next_url: str = Form(default="/agent-control"),
    ) -> RedirectResponse:
        job = run_agent_job("FormCheckAgent", action="form_check", target_url=target_url)
        message = job.get("result_summary", "done") if job else "failed"
        return RedirectResponse(
            url=f"/agent-control?agent=FormCheckAgent&job_id={quote_plus(job.get('job_id', ''))}&target_url={quote_plus(target_url)}&message={quote_plus(message)}",
            status_code=303,
        )

    @app.post("/agent-control/safety-check")
    def agent_control_safety_check(
        target_url: str = Form(default=""),
        next_url: str = Form(default="/agent-control"),
    ) -> RedirectResponse:
        job = run_agent_job("SafetyAgent", action="safety_check", target_url=target_url)
        message = job.get("result_summary", "done") if job else "failed"
        return RedirectResponse(
            url=f"/agent-control?agent=SafetyAgent&job_id={quote_plus(job.get('job_id', ''))}&target_url={quote_plus(target_url)}&message={quote_plus(message)}",
            status_code=303,
        )

    @app.post("/agent-control/mark-reviewed")
    def agent_control_mark_reviewed(
        job_id: str = Form(default=""),
        note: str = Form(default="確認済み"),
        next_url: str = Form(default="/agent-control"),
    ) -> RedirectResponse:
        job = mark_reviewed_job(job_id, note=note)
        message = job.get("result_summary", "done") if job else "failed"
        return RedirectResponse(
            url=f"/agent-control?agent=HumanReviewAgent&job_id={quote_plus(job.get('job_id', ''))}&message={quote_plus(message)}",
            status_code=303,
        )

    @app.get("/agent-control/daily-report", response_class=HTMLResponse)
    def agent_control_daily_report(request: Request) -> HTMLResponse:
        status = get_agent_control_status()
        report = run_agent_job("ReportAgent", action="report")
        daily_report = get_agent_control_report()
        return _render(
            request,
            "agent_control.html",
            page_title="AI司令塔",
            active_page="agent_control",
            agent_control_status=status,
            agent_control_report=daily_report,
            agent_control_agents=list_agent_control_agents(),
            agent_control_jobs=list_agent_control_jobs(limit=50),
            agent_control_events=list_agent_control_events(limit=12),
            agent_control_human_review_jobs=list_human_review_items(limit=20),
            agent_control_selected_agent="ReportAgent",
            agent_control_selected_job=report,
            agent_definitions=list_agent_definitions(),
            agent_control_target_url="",
        )

    @app.post("/agent-control/run")
    def agent_control_run(
        agent_name: str = Form(...),
        action: str = Form(default=""),
        target_url: str = Form(default=""),
    ) -> RedirectResponse:
        job = run_agent_job(agent_name, action=action, target_url=target_url)
        message = job.get("result_summary", "done") if job else "failed"
        return RedirectResponse(url=f"/agent-control?agent={quote_plus(agent_name)}&job_id={quote_plus(job.get('job_id', ''))}&message={quote_plus(message)}", status_code=303)

    @app.post("/agent-control/cancel")
    def agent_control_cancel(
        agent_name: str = Form(default=""),
        job_id: str = Form(default=""),
    ) -> RedirectResponse:
        job = cancel_agent_control_job(job_id=job_id or None, agent_name=agent_name)
        message = job.get("result_summary", "cancelled") if job else "not_found"
        selected = job.get("job_id", "") if job else ""
        return RedirectResponse(url=f"/agent-control?agent={quote_plus(agent_name)}&job_id={quote_plus(selected)}&message={quote_plus(message)}", status_code=303)

    @app.get("/api/agent-control/status")
    def api_agent_control_status() -> dict[str, object]:
        return get_agent_control_status()

    @app.get("/api/agent-control/jobs")
    def api_agent_control_jobs() -> dict[str, object]:
        status = get_agent_control_status()
        return {"items": list_agent_control_jobs(limit=100), "summary": status.get("summary", {})}

    @app.get("/api/agent-control/human-review")
    def api_agent_control_human_review() -> dict[str, object]:
        return {"items": list_human_review_items(limit=100), "count": len(list_human_review_items(limit=100))}

    @app.post("/api/agent-control/run")
    async def api_agent_control_run(request: Request) -> dict[str, object]:
        payload = await _request_payload(request)
        agent_name = str(payload.get("agent_name", "") or "").strip()
        action = str(payload.get("action", "") or "").strip()
        target_url = str(payload.get("target_url", "") or "").strip()
        job = run_agent_job(agent_name, action=action, target_url=target_url)
        return {
            "status": job.get("status", "failed") if job else "failed",
            "job": job,
            "submitted_count_auto": 0,
            "safe_to_submit": False,
        }

    @app.post("/api/agent-control/register-url")
    async def api_agent_control_register_url(request: Request) -> dict[str, object]:
        payload = await _request_payload(request)
        target_url = str(payload.get("target_url", "") or "").strip()
        job = run_agent_job("QueueAgent", action="register_url", target_url=target_url)
        return {
            "status": job.get("status", "failed") if job else "failed",
            "job": job,
            "submitted_count_auto": 0,
            "safe_to_submit": False,
        }

    @app.post("/api/agent-control/form-check")
    async def api_agent_control_form_check(request: Request) -> dict[str, object]:
        payload = await _request_payload(request)
        target_url = str(payload.get("target_url", "") or "").strip()
        job = run_agent_job("FormCheckAgent", action="form_check", target_url=target_url)
        return {
            "status": job.get("status", "failed") if job else "failed",
            "job": job,
            "submitted_count_auto": 0,
            "safe_to_submit": False,
        }

    @app.post("/api/agent-control/safety-check")
    async def api_agent_control_safety_check(request: Request) -> dict[str, object]:
        payload = await _request_payload(request)
        target_url = str(payload.get("target_url", "") or "").strip()
        job = run_agent_job("SafetyAgent", action="safety_check", target_url=target_url)
        return {
            "status": job.get("status", "failed") if job else "failed",
            "job": job,
            "submitted_count_auto": 0,
            "safe_to_submit": False,
        }

    @app.post("/api/agent-control/mark-reviewed")
    async def api_agent_control_mark_reviewed(request: Request) -> dict[str, object]:
        payload = await _request_payload(request)
        job_id = str(payload.get("job_id", "") or "").strip()
        note = str(payload.get("note", "") or "").strip()
        job = mark_reviewed_job(job_id, note=note)
        return {
            "status": job.get("status", "failed") if job else "failed",
            "job": job,
            "submitted_count_auto": 0,
            "safe_to_submit": False,
        }

    @app.post("/api/agent-control/cancel")
    async def api_agent_control_cancel(request: Request) -> dict[str, object]:
        payload = await _request_payload(request)
        agent_name = str(payload.get("agent_name", "") or "").strip()
        job_id = str(payload.get("job_id", "") or "").strip()
        job = cancel_agent_control_job(job_id=job_id or None, agent_name=agent_name)
        return {
            "status": job.get("status", "failed") if job else "failed",
            "job": job,
            "submitted_count_auto": 0,
            "safe_to_submit": False,
        }

    @app.get("/api/agent-control/report")
    def api_agent_control_report() -> dict[str, object]:
        return get_agent_control_report()

    @app.get("/api/agent-control/daily-report")
    def api_agent_control_daily_report() -> dict[str, object]:
        return get_agent_control_report()

    @app.get("/queue", response_class=HTMLResponse)
    def queue(request: Request, status: str = "all") -> HTMLResponse:
        browser_state = check_chrome_available()
        browser_checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
        rows = load_apply_queue()
        if not rows:
            rows = build_apply_queue(load_campaigns(), load_form_inspections(), load_entries(), [], limit=30)
            save_apply_queue(rows)
        rows = _queue_sort_rows(rows)
        if status and status != "all":
            rows = [row for row in rows if row.get("queue_status", "QUEUED") == status]
        detail = _decorate_queue_row(rows[0]) if rows else {}
        queue_rows = []
        for row in rows:
            decorated = _decorate_queue_row(row)
            bucket, label = _deadline_bucket(row.get("deadline", ""))
            queue_rows.append(
                {
                    **decorated,
                    "deadline_bucket": bucket,
                    "deadline_label": label,
                    "one_line_reason": _one_line_reason(row.get("skip_reason_summary", "")),
                    "queue_class": "danger-faded" if row.get("queue_status") in {"BLOCKED", "SKIPPED", "MANUALLY_SUBMITTED"} else "",
                }
            )
        x_day = load_latest_x_campaign_day()
        x_queue_rows = _x_queue_sort_rows(load_x_campaign_queue_for_day(x_day))
        for row in x_queue_rows:
            try:
                safety_score = int(float(row.get("safety_score", 0) or 0))
            except (TypeError, ValueError):
                safety_score = 0
            row["safety_badge"] = "green" if safety_score >= 70 else "orange" if safety_score >= 50 else "red"
            row["prepare_allowed"] = row.get("status") == "user_selected" and safety_score >= 50
            row["prepare_disabled"] = row.get("status") != "user_selected" or safety_score < 50
            row["prepare_warning"] = safety_score < 70
        return _render(
            request,
            "queue.html",
            page_title="応募キュー",
            active_page="queue",
            queue_rows=queue_rows,
            x_queue_rows=x_queue_rows,
            x_queue_day=x_day,
            x_queue_summary=_x_queue_summary(x_queue_rows),
            detail=detail,
            queue_summary=summarize_apply_queue(queue_rows),
            browser_state=browser_state,
            browser_checked_at=browser_checked_at,
            prepare_command=_prepare_command(detail.get("campaign_id", "<campaign_id>")) if detail else _prepare_command("<campaign_id>"),
            queue_status_filters=[
                ("すべて", "all"),
                ("未処理", "QUEUED"),
                ("承認済み", "APPROVED"),
                ("応募準備済み", "PREPARED"),
                ("手動送信済み", "MANUALLY_SUBMITTED"),
                ("保留", "HOLD"),
                ("スキップ", "SKIPPED"),
                ("除外", "BLOCKED"),
            ],
        )

    @app.get("/queue/session", response_class=HTMLResponse)
    def queue_session(request: Request, campaign_id: str = "") -> HTMLResponse:
        browser_state = check_chrome_available()
        browser_checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
        rows = load_apply_queue()
        if not rows:
            rows = build_apply_queue(load_campaigns(), load_form_inspections(), load_entries(), [], limit=30)
            save_apply_queue(rows)
        session_rows = _queue_session_rows(rows)
        x_day = load_latest_x_campaign_day()
        x_queue_rows = _x_queue_sort_rows(load_x_campaign_queue_for_day(x_day))
        for row in x_queue_rows:
            try:
                safety_score = int(float(row.get("safety_score", 0) or 0))
            except (TypeError, ValueError):
                safety_score = 0
            row["safety_badge"] = "green" if safety_score >= 70 else "orange" if safety_score >= 50 else "red"
            row["prepare_allowed"] = row.get("status") == "user_selected" and safety_score >= 50
            row["prepare_disabled"] = row.get("status") != "user_selected" or safety_score < 50
            row["prepare_warning"] = safety_score < 70
        if not session_rows:
            return _render(
                request,
                "queue_session.html",
                page_title="応募キュー連続処理",
                active_page="queue",
                queue_has_items=False,
                queue_summary=summarize_apply_queue(rows),
                queue_rows=[],
                x_queue_rows=x_queue_rows,
                x_queue_day=x_day,
                x_queue_summary=_x_queue_summary(x_queue_rows),
                current={},
                previous={},
                next_item={},
                current_index=0,
                prepare_command=_prepare_command("<campaign_id>"),
                browser_state=browser_state,
                browser_checked_at=browser_checked_at,
            )
        current_index = _queue_session_index(session_rows, campaign_id or session_rows[0].get("campaign_id", ""))
        current = _decorate_queue_row(get_current_queue_item(session_rows, current_index))
        previous = _decorate_queue_row(get_current_queue_item(session_rows, current_index - 1)) if current_index > 0 else {}
        next_item = _decorate_queue_row(get_next_queue_item(session_rows, current.get("campaign_id", "")))
        return _render(
            request,
            "queue_session.html",
            page_title="応募キュー連続処理",
            active_page="queue",
            queue_has_items=True,
            queue_summary=summarize_apply_queue(rows),
            queue_rows=session_rows,
            x_queue_rows=x_queue_rows,
            x_queue_day=x_day,
            x_queue_summary=_x_queue_summary(x_queue_rows),
            current=current,
            previous=previous,
            next_item=next_item,
            current_index=current_index,
            prepare_command=_prepare_command(current.get("campaign_id", "")),
            browser_state=browser_state,
            browser_checked_at=browser_checked_at,
        )

    @app.get("/approved", response_class=HTMLResponse)
    def approved(request: Request) -> HTMLResponse:
        rows = load_apply_queue()
        if not rows:
            rows = build_apply_queue(load_campaigns(), load_form_inspections(), load_entries(), [], limit=30)
            save_apply_queue(rows)
        approved_rows = [_decorate_queue_row(row) for row in _approved_queue_sort_rows(_approved_queue_rows(rows))]
        detail = approved_rows[0] if approved_rows else {}
        return _render(
            request,
            "approved.html",
            page_title="承認済み応募キュー",
            active_page="approved",
            queue_rows=approved_rows,
            detail=detail,
            queue_summary=summarize_apply_queue(rows),
            approved_count=sum(1 for row in rows if row.get("queue_status", "") == "APPROVED"),
            prepared_count=sum(1 for row in rows if row.get("queue_status", "") == "PREPARED"),
            hold_count=sum(1 for row in rows if row.get("queue_status", "") == "HOLD"),
        )

    @app.get("/approved/session", response_class=HTMLResponse)
    def approved_session(request: Request, campaign_id: str = "") -> HTMLResponse:
        rows = load_apply_queue()
        if not rows:
            rows = build_apply_queue(load_campaigns(), load_form_inspections(), load_entries(), [], limit=30)
            save_apply_queue(rows)
        approved_rows = [_decorate_queue_row(row) for row in _approved_queue_sort_rows(_approved_queue_rows(rows))]
        if not approved_rows:
            return _render(
                request,
                "approved_session.html",
                page_title="承認済み応募キュー連続処理",
                active_page="approved",
                queue_has_items=False,
                queue_summary=summarize_apply_queue(rows),
                queue_rows=[],
                current={},
                previous={},
                next_item={},
                current_index=0,
                prepare_command=_prepare_command("<campaign_id>"),
            )
        current_index = _queue_session_index(approved_rows, campaign_id or approved_rows[0].get("campaign_id", ""))
        current = get_current_queue_item(approved_rows, current_index)
        previous = get_current_queue_item(approved_rows, current_index - 1) if current_index > 0 else {}
        next_item = get_next_queue_item(approved_rows, current.get("campaign_id", ""))
        return _render(
            request,
            "approved_session.html",
            page_title="承認済み応募キュー連続処理",
            active_page="approved",
            queue_has_items=True,
            queue_summary=summarize_apply_queue(rows),
            queue_rows=approved_rows,
            current=current,
            previous=previous,
            next_item=next_item,
            current_index=current_index,
            prepare_command=_prepare_command(current.get("campaign_id", "")),
        )

    @app.get("/approved/session/{campaign_id}", response_class=HTMLResponse)
    def approved_session_campaign(request: Request, campaign_id: str) -> HTMLResponse:
        return approved_session(request, campaign_id=campaign_id)

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request, q: str = "", category: str = "すべて", mode: str = "safe") -> HTMLResponse:
        rows = _sort_campaign_rows(_filter_campaigns(load_campaigns(), q, category, mode))
        selected = request.query_params.get("selected", "")
        detail = None
        if selected:
            for row in rows:
                if row.get("campaign_id") == selected:
                    detail = row
                    break
        if detail is None and rows:
            detail = rows[0]
        return _render(
            request,
            "search.html",
            page_title="懸賞を探す",
            active_page="search",
            q=q,
            category=category,
            mode=mode,
            category_links=_category_links(q, mode),
            prize_links=_prize_links(q, mode),
            status_filters=SAFE_STATUS_FILTERS,
            results=_safe_rows(rows),
            detail=_safe_rows([detail])[0] if detail else {},
            active_filters={
                "web_form_only": mode in {"safe", "review_only", "ready"},
                "include_review_only": mode in {"safe", "review_only"},
                "ready_for_fill_only": mode == "ready",
                "deadline_before_only": True,
                "massive_only": False,
                "exclude_x": True,
                "exclude_instagram": True,
                "exclude_line": True,
                "exclude_app": True,
                "exclude_member_registration": True,
                "exclude_receipt": True,
                "exclude_purchase": True,
                "exclude_captcha": True,
                "exclude_age": True,
            },
        )

    @app.get("/mail", response_class=HTMLResponse)
    def mail_page(request: Request) -> HTMLResponse:
        status = request.query_params.get("status", "all")
        mail_rows = sort_mail_sweepstakes(_mail_filter_rows(load_mail_sweepstakes(), status))
        return _render(
            request,
            "mail.html",
            page_title="メール懸賞",
            active_page="mail",
            mail_rows=mail_rows,
            mail_summary=mail_sweepstakes_summary(mail_rows),
            mail_status_filters=MAIL_STATUS_FILTERS,
            mail_status=status,
        )

    @app.get("/api/mail-sweepstakes")
    def api_mail_sweepstakes() -> dict[str, object]:
        rows = sort_mail_sweepstakes(load_mail_sweepstakes())
        return {"items": rows, "summary": mail_sweepstakes_summary(rows)}

    @app.post("/api/mail-sweepstakes/rescan")
    def api_mail_rescan() -> dict[str, object]:
        rows = rescan_mail_sweepstakes()
        return {"status": "ok", "items": rows, "summary": mail_sweepstakes_summary(rows)}

    @app.post("/mail/rescan")
    def mail_rescan(request: Request, next_url: str = Form(default="/mail")) -> RedirectResponse:
        rescan_mail_sweepstakes()
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/mail"), status_code=303)

    @app.post("/api/mail-sweepstakes/{mail_id}/add-candidate")
    def api_mail_add_candidate(mail_id: str) -> dict[str, object]:
        mail_item = get_mail_sweepstake(mail_id)
        if not mail_item:
            return {"status": "not_found"}
        if register_email_campaign(mail_item):
            update_mail_sweepstake(
                mail_id,
                {
                    "status": "added",
                    "selected_by_user": True,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            return {"status": "ok", "mail_id": mail_id}
        return {"status": "duplicate", "mail_id": mail_id}

    @app.post("/mail/{mail_id}/add-candidate")
    def mail_add_candidate(mail_id: str, next_url: str = Form(default="/mail")) -> RedirectResponse:
        mail_item = get_mail_sweepstake(mail_id)
        if mail_item:
            if register_email_campaign(mail_item):
                update_mail_sweepstake(
                    mail_id,
                    {
                        "status": "added",
                        "selected_by_user": True,
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/mail"), status_code=303)

    @app.post("/api/mail-sweepstakes/{mail_id}/mark-danger")
    def api_mail_mark_danger(mail_id: str) -> dict[str, object]:
        mail_item = get_mail_sweepstake(mail_id)
        if not mail_item:
            return {"status": "not_found"}
        update_mail_sweepstake(
            mail_id,
            {
                "status": "danger",
                "excluded_by_user": True,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        return {"status": "ok", "mail_id": mail_id}

    @app.post("/mail/{mail_id}/mark-danger")
    def mail_mark_danger(mail_id: str, next_url: str = Form(default="/mail")) -> RedirectResponse:
        mail_item = get_mail_sweepstake(mail_id)
        if mail_item:
            update_mail_sweepstake(
                mail_id,
                {
                    "status": "danger",
                    "excluded_by_user": True,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/mail"), status_code=303)

    @app.post("/api/mail-sweepstakes/{mail_id}/open")
    def api_mail_open(mail_id: str) -> RedirectResponse:
        mail_item = get_mail_sweepstake(mail_id)
        target = str(mail_item.get("campaign_url", "")) if mail_item else ""
        return RedirectResponse(url=target or "/mail", status_code=303)

    @app.post("/mail/{mail_id}/open")
    def mail_open(mail_id: str, next_url: str = Form(default="/mail")) -> RedirectResponse:
        mail_item = get_mail_sweepstake(mail_id)
        target = str(mail_item.get("campaign_url", "")) if mail_item else ""
        return RedirectResponse(url=target or _safe_internal_next_url(next_url, "/mail"), status_code=303)

    @app.get("/later-queue", response_class=HTMLResponse)
    def later_queue(
        request: Request,
        q: str = "",
        status: str = "all",
        sort: str = "deadline",
    ) -> HTMLResponse:
        rows = _later_filter_rows(list_later_queue(), q, status)
        rows = _later_sort_rows(rows, sort)
        selected = request.query_params.get("selected", "")
        detail = {}
        if selected:
            detail = next((row for row in rows if row.get("id", "") == selected), {})
        if not detail and rows:
            detail = rows[0]
        return _render(
            request,
            "later_queue.html",
            page_title="あとで応募",
            active_page="later",
            later_rows=rows,
            later_summary=summarize_later_queue(list_later_queue()),
            detail=detail,
            q=q,
            status=status,
            sort=sort,
            later_message=request.query_params.get("message", ""),
            later_error=request.query_params.get("error", ""),
            later_status_filters=[
                ("すべて", "all"),
                ("queued", "queued"),
                ("needs_review", "needs_review"),
                ("reviewing", "reviewing"),
                ("ready_for_fill", "ready_for_fill"),
                ("applied_manual", "applied_manual"),
                ("skipped", "skipped"),
                ("expired", "expired"),
            ],
            later_sort_filters=[
                ("締切順", "deadline"),
                ("更新順", "updated"),
            ],
        )

    @app.post("/later-queue/add-url")
    def later_queue_add_url(request: Request, url: str = Form(...)) -> RedirectResponse:
        row, created, reason = add_later_queue(url)
        message = "登録しました" if created else "重複のため既存候補を返しました"
        if reason == "duplicate":
            message = "重複のため既存候補を返しました"
        return RedirectResponse(url=f"/later-queue?selected={row.get('id', '')}&message={quote_plus(message)}", status_code=303)

    @app.post("/later-queue/{item_id}/review")
    def later_queue_review(item_id: str, next_url: str = Form(default="/later-queue")) -> RedirectResponse:
        updated = update_later_queue_status(item_id, status="reviewing", review_note="web review requested")
        target = _safe_internal_next_url(next_url, "/later-queue")
        if updated:
            return RedirectResponse(url=f"{target}?selected={updated.get('id', '')}&message={quote_plus('reviewing')}", status_code=303)
        return RedirectResponse(url=f"{target}?error={quote_plus('not_found')}", status_code=303)

    @app.post("/later-queue/{item_id}/prepare-fill")
    def later_queue_prepare_fill(item_id: str, next_url: str = Form(default="/later-queue")) -> RedirectResponse:
        updated = update_later_queue_status(item_id, status="ready_for_fill", review_note="web prepare fill requested")
        target = _safe_internal_next_url(next_url, "/later-queue")
        if updated:
            return RedirectResponse(url=f"{target}?selected={updated.get('id', '')}&message={quote_plus('ready_for_fill')}", status_code=303)
        return RedirectResponse(url=f"{target}?error={quote_plus('not_found')}", status_code=303)

    @app.post("/later-queue/{item_id}/mark-applied-manual")
    def later_queue_mark_applied_manual(item_id: str, next_url: str = Form(default="/later-queue")) -> RedirectResponse:
        updated = update_later_queue_status(item_id, status="applied_manual", review_note="manual application recorded")
        if updated:
            later_queue_to_entry_history(updated)
        target = _safe_internal_next_url(next_url, "/later-queue")
        if updated:
            return RedirectResponse(url=f"{target}?selected={updated.get('id', '')}&message={quote_plus('applied_manual')}", status_code=303)
        return RedirectResponse(url=f"{target}?error={quote_plus('not_found')}", status_code=303)

    @app.post("/later-queue/{item_id}/skip")
    def later_queue_skip(item_id: str, next_url: str = Form(default="/later-queue")) -> RedirectResponse:
        updated = update_later_queue_status(item_id, status="skipped", review_note="user skipped")
        target = _safe_internal_next_url(next_url, "/later-queue")
        if updated:
            return RedirectResponse(url=f"{target}?selected={updated.get('id', '')}&message={quote_plus('skipped')}", status_code=303)
        return RedirectResponse(url=f"{target}?error={quote_plus('not_found')}", status_code=303)

    @app.post("/later-queue/{item_id}/remove")
    def later_queue_remove(item_id: str, next_url: str = Form(default="/later-queue")) -> RedirectResponse:
        removed = remove_later_queue_item(item_id)
        target = _safe_internal_next_url(next_url, "/later-queue")
        if removed:
            return RedirectResponse(url=f"{target}?message={quote_plus('removed')}", status_code=303)
        return RedirectResponse(url=f"{target}?error={quote_plus('not_found')}", status_code=303)

    @app.get("/entries", response_class=HTMLResponse)
    def entries_page(
        request: Request,
        q: str = "",
        deadline: str = "all",
        result: str = "all",
        newsletter: str = "all",
        status: str = "all",
    ) -> HTMLResponse:
        rows = _entry_filter_rows(load_entry_history(), q, deadline, result, newsletter, status)
        detail = {}
        selected = request.query_params.get("selected", "")
        if selected:
            for row in rows:
                if row.get("campaign_id") == selected:
                    detail = row
                    break
        if not detail and rows:
            detail = rows[0]
        win_mail_rows = load_win_mail_candidates()
        return _render(
            request,
            "entries.html",
            page_title="応募履歴",
            active_page="entries",
            entry_rows=rows,
            entry_summary=summarize_entry_history(load_entry_history()),
            detail=detail,
            q=q,
            deadline=deadline,
            result=result,
            newsletter=newsletter,
            status=status,
            entry_deadline_filters=[
                ("すべて", "all"),
                ("今日", "today"),
                ("明日", "tomorrow"),
                ("今週", "week"),
                ("将来", "future"),
                ("期限切れ", "expired"),
            ],
            entry_result_filters=[
                ("すべて", "all"),
                ("応募済み", "applied"),
                ("当選確認待ち", "pending"),
                ("当選確認済み", "checked"),
                ("重複", "duplicate"),
            ],
            entry_newsletter_filters=[
                ("すべて", "all"),
                ("不明", "unknown"),
                ("登録中", "opt_in"),
                ("解除候補", "unsubscribe_needed"),
                ("解除済み", "unsubscribed"),
                ("解除済み", "opt_out"),
            ],
            entry_status_filters=[
                ("すべて", "all"),
                ("APPLIED", "APPLIED"),
                ("PENDING_RESULT", "PENDING_RESULT"),
                ("RESULT_CHECKED", "RESULT_CHECKED"),
                ("DUPLICATE", "DUPLICATE"),
                ("HOLD", "HOLD"),
                ("SKIPPED", "SKIPPED"),
            ],
            win_mail_candidates=win_mail_rows,
            win_mail_summary=summarize_win_mail_candidates(win_mail_rows),
        )

    @app.get("/api/entries")
    def api_entries() -> dict[str, object]:
        rows = load_entry_history()
        return {"items": rows, "summary": summarize_entry_history(rows)}

    @app.post("/entries/export-csv")
    def entries_export_csv(request: Request, next_url: str = Form(default="/entries")) -> RedirectResponse:
        export_entry_history_csv()
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/entries"), status_code=303)

    @app.post("/entries/win-mails/rescan")
    def entries_win_mail_rescan(request: Request, next_url: str = Form(default="/entries")) -> RedirectResponse:
        rescan_win_mail_candidates()
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/entries"), status_code=303)

    @app.post("/queue/{queue_id}/prepare")
    def queue_prepare(queue_id: str, next_url: str = Form(default="/queue")) -> RedirectResponse:
        mark_prepared(queue_id)
        matched = next((row for row in load_apply_queue() if row.get("queue_id") == queue_id or row.get("campaign_id") == queue_id), None)
        if matched:
            mark_selected(matched.get("campaign_id", queue_id), reason="応募キューから準備")
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)

    @app.post("/queue/{queue_id}/approve")
    def queue_approve(
        queue_id: str,
        next_url: str = Form(default="/approved"),
        approved_note: str = Form(default=""),
        age_fill_user_approved: str = Form(default="false"),
    ) -> RedirectResponse:
        approved = approve_queue_item(
            queue_id,
            note=approved_note or "応募候補に承認",
            age_fill_user_approved=age_fill_user_approved.lower() in {"1", "true", "yes", "on"},
        )
        matched = next((row for row in load_apply_queue() if row.get("queue_id") == queue_id or row.get("campaign_id") == queue_id), None)
        if matched:
            mark_selected(matched.get("campaign_id", queue_id), reason=approved_note or "応募候補に承認")
        target = _safe_internal_next_url(next_url, "/approved")
        if not approved:
            target = f"{target}?error=approval_failed"
        return RedirectResponse(url=target, status_code=303)

    @app.post("/api/queue/{queue_id}/approve")
    def api_queue_approve(
        queue_id: str,
        approved_note: str = Form(default=""),
        age_fill_user_approved: str = Form(default="false"),
    ) -> dict[str, object]:
        ok = approve_queue_item(
            queue_id,
            note=approved_note or "応募候補に承認",
            age_fill_user_approved=age_fill_user_approved.lower() in {"1", "true", "yes", "on"},
        )
        matched = next((row for row in load_apply_queue() if row.get("queue_id") == queue_id or row.get("campaign_id") == queue_id), None)
        return {
            "status": "ok" if ok else "not_found",
            "queue_id": queue_id,
            "queue_status": "APPROVED" if ok else "",
            "approved_by_user": "true" if ok else "false",
            "approved_at": matched.get("approved_at", "") if matched else "",
            "approved_note": matched.get("approved_note", "") if matched else approved_note or "",
            "auto_submit_allowed": "false",
        }

    @app.post("/queue/{queue_id}/chrome-prepare")
    def queue_chrome_prepare(queue_id: str, next_url: str = Form(default="/queue")) -> RedirectResponse:
        item = _queue_item_for_id(queue_id)
        approved = item.get("approved_by_user", "") == "true" and item.get("queue_status", "") in {"APPROVED", "PREPARED"}
        if approved:
            if _start_chrome_prepare(queue_id) == "started":
                mark_prepared(queue_id)
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)

    @app.post("/queue/{queue_id}/hold")
    def queue_hold(queue_id: str, next_url: str = Form(default="/queue")) -> RedirectResponse:
        mark_hold(queue_id)
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)

    @app.post("/queue/{queue_id}/skip")
    def queue_skip(queue_id: str, next_url: str = Form(default="/queue")) -> RedirectResponse:
        mark_skipped(queue_id)
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)

    @app.post("/queue/{queue_id}/manual-submitted")
    def queue_manual_submitted(queue_id: str, next_url: str = Form(default="/queue")) -> RedirectResponse:
        mark_manual_submitted(queue_id)
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)

    @app.post("/api/approved/{queue_id}/prepare")
    def api_approved_prepare(queue_id: str, allow_age_fill: bool = False) -> dict[str, object]:
        return _prepare_api_payload(queue_id, allow_age_fill=allow_age_fill)

    @app.post("/api/approved/{queue_id}/dry-run")
    def api_approved_dry_run(queue_id: str) -> dict[str, object]:
        try:
            result = run_prepared_campaign_dry_run(queue_id)
            return {"ok": True, "submitted_count_auto": 0, **result}
        except Exception as exc:
            return {"ok": False, "queue_id": queue_id, "status": "failed", "message": str(exc), "submitted_count_auto": 0}

    @app.post("/api/approved/{queue_id}/review-run")
    def api_approved_review_run(queue_id: str) -> dict[str, object]:
        return _auto_apply_api_payload(queue_id, run_mode="review")

    @app.post("/api/mock-submit-test")
    def api_mock_submit_test() -> dict[str, object]:
        mock_path = PACKAGE_ROOT / "tests" / "mock_forms" / "basic.html"
        campaign = {
            "campaign_id": "mock_basic",
            "campaign_name": "mock basic form",
            "resolved_entry_url": mock_path.resolve().as_uri(),
        }
        return _run_auto_apply_for_campaign(campaign, run_mode="mock", keep_open=False)

    @app.get("/api/approved/{queue_id}/analysis")
    def api_approved_analysis(queue_id: str) -> dict[str, object]:
        path = FORM_ANALYSIS_DIR / f"{queue_id}.json"
        if not path.exists():
            return {"status": "missing", "queue_id": queue_id}
        import json

        return {"status": "ok", "queue_id": queue_id, "path": str(path), "data": json.loads(path.read_text(encoding="utf-8"))}

    @app.get("/api/approved/{queue_id}/pre-submit-check")
    def api_approved_pre_submit_check(queue_id: str) -> dict[str, object]:
        path = PRE_SUBMIT_CHECKS_DIR / f"{queue_id}.json"
        if not path.exists():
            return {"status": "missing", "queue_id": queue_id}
        import json

        return {"status": "ok", "queue_id": queue_id, "path": str(path), "data": json.loads(path.read_text(encoding="utf-8"))}

    @app.get("/api/approved/{queue_id}/screenshot")
    def api_approved_screenshot(queue_id: str):
        item = _queue_item_for_id(queue_id)
        path_text = item.get("dry_run_screenshot_path", "") if item else ""
        path = Path(path_text) if path_text else PACKAGE_ROOT / "screenshots" / "dry_run" / f"{queue_id}.png"
        if not path.exists():
            return PlainTextResponse("screenshot missing", status_code=404)
        return FileResponse(path)

    @app.post("/api/approved/{queue_id}/manual-submitted")
    def api_approved_manual_submitted(queue_id: str) -> dict[str, object]:
        ok = mark_manual_submitted(queue_id)
        return {"status": "ok" if ok else "not_found", "queue_id": queue_id, "queue_status": "MANUALLY_SUBMITTED" if ok else ""}

    @app.post("/api/approved/{queue_id}/hold")
    def api_approved_hold(queue_id: str) -> dict[str, object]:
        ok = mark_hold(queue_id)
        return {"status": "ok" if ok else "not_found", "queue_id": queue_id, "queue_status": "HOLD" if ok else ""}

    @app.post("/api/approved/{queue_id}/skip")
    def api_approved_skip(queue_id: str) -> dict[str, object]:
        ok = mark_skipped(queue_id)
        return {"status": "ok" if ok else "not_found", "queue_id": queue_id, "queue_status": "SKIPPED" if ok else ""}

    def _append_self_test_log(queue_id: str, note1: str, note2: str, note3: str) -> bool:
        note1 = note1.strip()
        note2 = note2.strip()
        note3 = note3.strip()
        if not any([note1, note2, note3]):
            return False
        SELF_TEST_LOG_MD.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        item = _queue_item_for_id(queue_id)
        lines = [
            "## " + timestamp,
            f"- campaign_id: {item.get('campaign_id', queue_id)}",
            f"- campaign_name: {item.get('campaign_name', '')}",
            f"- 迷ったところ: {note1 or 'なし'}",
            f"- 応募したいと思ったか: {note2 or 'なし'}",
            f"- 次回改善したい点: {note3 or 'なし'}",
            "",
        ]
        with SELF_TEST_LOG_MD.open("a", encoding="utf-8") as handle:
            if SELF_TEST_LOG_MD.stat().st_size == 0:
                handle.write("# 自己テストログ\n\n")
            handle.write("\n".join(lines))
        return True

    @app.get("/queue/session/{campaign_id}", response_class=HTMLResponse)
    def queue_session_campaign(request: Request, campaign_id: str) -> HTMLResponse:
        return queue_session(request, campaign_id=campaign_id)

    @app.post("/queue/session/{queue_id}/self-test-note")
    def queue_session_self_test_note(
        queue_id: str,
        next_url: str = Form(default="/queue/session"),
        note_confusion: str = Form(default=""),
        note_interest: str = Form(default=""),
        note_improve: str = Form(default=""),
    ) -> RedirectResponse:
        _append_self_test_log(queue_id, note_confusion, note_interest, note_improve)
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue/session"), status_code=303)

    @app.post("/queue/session/{queue_id}/prepare")
    def queue_session_prepare(queue_id: str, next_url: str = Form(default="/queue/session")) -> RedirectResponse:
        mark_prepared(queue_id)
        matched = next((row for row in load_apply_queue() if row.get("queue_id") == queue_id or row.get("campaign_id") == queue_id), None)
        if matched:
            mark_selected(matched.get("campaign_id", queue_id), reason="応募キュー連続処理から準備")
        session_rows = _queue_session_rows(load_apply_queue())
        next_item = get_next_queue_item(session_rows, queue_id)
        target = _safe_internal_next_url(next_url, "/queue/session")
        if next_item:
            target = f"/queue/session/{next_item.get('campaign_id', queue_id)}"
        return RedirectResponse(url=target, status_code=303)

    @app.post("/queue/session/{queue_id}/chrome-prepare")
    def queue_session_chrome_prepare(queue_id: str, next_url: str = Form(default="/queue/session")) -> RedirectResponse:
        item = _queue_item_for_id(queue_id)
        approved = item.get("approved_by_user", "") == "true" and item.get("queue_status", "") in {"APPROVED", "PREPARED"}
        if approved:
            if _start_chrome_prepare(queue_id) == "started":
                mark_prepared(queue_id)
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue/session"), status_code=303)

    @app.post("/queue/session/{queue_id}/manual-submitted")
    def queue_session_manual_submitted(queue_id: str, next_url: str = Form(default="/queue/session")) -> RedirectResponse:
        mark_manual_submitted(queue_id)
        session_rows = _queue_session_rows(load_apply_queue())
        next_item = get_next_queue_item(session_rows, queue_id)
        target = _safe_internal_next_url(next_url, "/queue/session")
        if next_item:
            target = f"/queue/session/{next_item.get('campaign_id', queue_id)}"
        return RedirectResponse(url=target, status_code=303)

    @app.post("/queue/session/{queue_id}/skip")
    def queue_session_skip(queue_id: str, next_url: str = Form(default="/queue/session")) -> RedirectResponse:
        mark_skipped(queue_id)
        session_rows = _queue_session_rows(load_apply_queue())
        next_item = get_next_queue_item(session_rows, queue_id)
        target = _safe_internal_next_url(next_url, "/queue/session")
        if next_item:
            target = f"/queue/session/{next_item.get('campaign_id', queue_id)}"
        return RedirectResponse(url=target, status_code=303)

    @app.post("/queue/session/{queue_id}/hold")
    def queue_session_hold(queue_id: str, next_url: str = Form(default="/queue/session")) -> RedirectResponse:
        mark_hold(queue_id)
        session_rows = _queue_session_rows(load_apply_queue())
        next_item = get_next_queue_item(session_rows, queue_id)
        target = _safe_internal_next_url(next_url, "/queue/session")
        if next_item:
            target = f"/queue/session/{next_item.get('campaign_id', queue_id)}"
        return RedirectResponse(url=target, status_code=303)

    def _prepare_api_payload(queue_id: str, allow_age_fill: bool = False) -> dict[str, object]:
        item = _queue_item_for_id(queue_id)
        fallback_command = _prepare_command(queue_id, allow_age_fill=allow_age_fill)
        if not item:
            return {
                "ok": False,
                "campaign_id": queue_id,
                "campaign_name": "",
                "action": "prepare_failed",
                "browser": "chrome",
                "queue_status": "",
                "message": "対象の候補が見つかりませんでした。",
                "next_action": "応募キューを更新してください。",
                "submitted_count_auto": 0,
                "fallback_command": fallback_command,
                "fallback_help": "start_chrome_prepare.bat を使うか、browser doctor を確認してください。",
            }
        approved = item.get("approved_by_user", "") == "true" and item.get("queue_status", "") in {"APPROVED", "PREPARED"}
        if not approved:
            return {
                "ok": False,
                "campaign_id": item.get("campaign_id", queue_id),
                "campaign_name": item.get("campaign_name", ""),
                "action": "prepare_failed",
                "browser": "chrome",
                "queue_status": item.get("queue_status", ""),
                "message": "承認済みではありません。先に応募候補に承認してください。",
                "next_action": "応募候補に承認してから再実行してください。",
                "submitted_count_auto": 0,
                "fallback_command": fallback_command,
                "fallback_help": "APPROVED 以外は prepare しません。",
            }
        effective_allow_age_fill = allow_age_fill or item.get("age_fill_user_approved", "") == "true"
        if allow_age_fill and item.get("age_fill_user_approved", "") != "true":
            set_age_fill_user_approved(item.get("campaign_id", queue_id), True)
        launch_status = _start_chrome_prepare(queue_id, allow_age_fill=effective_allow_age_fill)
        if launch_status == "started":
            mark_prepared(item.get("campaign_id", queue_id))
            return {
                "ok": True,
                "campaign_id": item.get("campaign_id", queue_id),
                "campaign_name": item.get("campaign_name", ""),
                "action": "prepare_started",
                "browser": "chrome",
                "queue_status": "PREPARED",
                "message": "Chromeを開きました。安全な項目だけ入力補助し、入力レビューで停止しました。送信はしていません。アプリは応募送信していません。年齢・同意・クイズ・メルマガは自動操作しません。Chrome上で確認してください。",
                "next_action": "Chrome上で内容を確認し、送信した場合だけ『手動送信済みにする』を押してください。",
                "submitted_count_auto": 0,
                "fallback_command": fallback_command,
                "fallback_help": "start_chrome_prepare.bat が使えます。",
            }
        message = "Chrome起動に失敗しました。" if launch_status == "launch_failed" else "start_chrome_prepare.bat が見つかりません。"
        return {
            "ok": False,
            "campaign_id": item.get("campaign_id", queue_id),
            "campaign_name": item.get("campaign_name", ""),
            "action": "prepare_failed",
            "browser": "chrome",
            "queue_status": item.get("queue_status", ""),
            "message": message,
            "next_action": "browser doctor を確認してください。",
            "submitted_count_auto": 0,
            "fallback_command": fallback_command,
            "fallback_help": "python main.py prepare --campaign-id <campaign_id> --browser chrome --keep-open --no-screenshot --force-review",
        }

    def _auto_apply_api_payload(queue_id: str, run_mode: str = "") -> dict[str, object]:
        item = _queue_item_for_id(queue_id)
        if not item:
            return {"ok": False, "queue_id": queue_id, "status": "not_found", "submitted_count_auto": 0}
        if item.get("queue_status", "") not in {"APPROVED", "PREPARED"}:
            return {"ok": False, "queue_id": queue_id, "status": "not_prepared", "submitted_count_auto": 0}
        campaigns = load_campaigns()
        campaign = next((row for row in campaigns if row.get("campaign_id") == item.get("campaign_id", queue_id)), item)
        return _run_auto_apply_for_campaign(campaign, run_mode=run_mode or get_run_mode(), keep_open=False)

    def _run_auto_apply_for_campaign(campaign: dict[str, str], run_mode: str, keep_open: bool = False) -> dict[str, object]:
        mode = normalize_run_mode(run_mode)
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return {"ok": False, "status": "playwright_missing", "message": str(exc), "submitted_count_auto": 0}
        try:
            profile = load_profile()
            with sync_playwright() as playwright:
                context, page, _actual_browser = open_url_in_chrome(playwright, target_url_for_campaign(campaign), "chrome")
                try:
                    result = AutoApplyEngine(mode).run(page, campaign, profile)
                    record = result["record"]
                    if mode != "mock":
                        mark_prepared(campaign.get("campaign_id", ""))
                    return {
                        "ok": True,
                        "campaign_id": campaign.get("campaign_id", ""),
                        "run_mode": mode,
                        "status": record.get("status", ""),
                        "filled_fields_count": record.get("filled_fields_count", 0),
                        "submit_attempted": record.get("submit_attempted", False),
                        "submit_clicked": record.get("submit_clicked", False),
                        "auto_submitted": record.get("auto_submitted", False),
                        "submitted_count_auto": 1 if record.get("auto_submitted") and mode == "mock" else 0,
                        "needs_review_reasons": record.get("needs_review_reasons", []),
                        "screenshot_path": record.get("screenshot_path", ""),
                    }
                finally:
                    if not keep_open:
                        close_browser_safely(context)
        except Exception as exc:
            return {"ok": False, "status": "failed", "message": str(exc), "submitted_count_auto": 0}

    @app.post("/api/queue/{queue_id}/prepare")
    def api_queue_prepare(queue_id: str, allow_age_fill: bool = False) -> dict[str, object]:
        return _prepare_api_payload(queue_id, allow_age_fill=allow_age_fill)

    @app.post("/api/queue/{queue_id}/manual-submitted")
    def api_queue_manual_submitted(queue_id: str) -> dict[str, object]:
        ok = mark_manual_submitted(queue_id)
        return {"status": "ok" if ok else "not_found", "queue_id": queue_id, "queue_status": "MANUALLY_SUBMITTED" if ok else ""}

    @app.post("/api/queue/{queue_id}/skip")
    def api_queue_skip(queue_id: str) -> dict[str, object]:
        ok = mark_skipped(queue_id)
        return {"status": "ok" if ok else "not_found", "queue_id": queue_id, "queue_status": "SKIPPED" if ok else ""}

    @app.post("/api/queue/{queue_id}/hold")
    def api_queue_hold(queue_id: str) -> dict[str, object]:
        ok = mark_hold(queue_id)
        return {"status": "ok" if ok else "not_found", "queue_id": queue_id, "queue_status": "HOLD" if ok else ""}

    @app.get("/campaigns", response_class=HTMLResponse)
    def campaigns(request: Request, status: str = "", selected: str = "") -> HTMLResponse:
        status = normalize_status_filter(status)
        rows = load_campaigns()
        if status:
            rows = [row for row in rows if row.get("form_readiness_status") == status or row.get("resolve_status") == status or row.get("status") == status]
        detail_source = next((row for row in rows if row.get("campaign_id") == selected), rows[0] if rows else {})
        return _render(
            request,
            "campaigns.html",
            page_title="キャンペーン一覧",
            active_page="campaigns",
            campaigns=_safe_rows(rows),
            detail=_safe_rows([detail_source])[0] if detail_source else {},
            selected_campaign_id=selected,
            selected_count=sum(1 for row in rows if row.get("selected_by_user") == "true"),
            excluded_count=sum(1 for row in rows if row.get("excluded_by_user") == "true"),
        )

    @app.get("/research", response_class=HTMLResponse)
    def research(request: Request, q: str = "", category: str = "すべて") -> HTMLResponse:
        rows = _research_rows(load_campaigns(), query=q, category=category)[:30]
        report = load_research_report()
        return _render(
            request,
            "research.html",
            page_title="リサーチ",
            active_page="research",
            q=q,
            category=category,
            category_labels=RESEARCH_CATEGORY_LABELS,
            research_rows=_safe_rows(rows),
            research_report=report,
            research_summary={
                "total": len(rows),
                "score_80_plus": sum(1 for row in rows if int(row.get("opportunity_score", "0") or 0) >= 80),
                "review_only": sum(1 for row in rows if row.get("form_readiness_status") == "REVIEW_ONLY"),
                "ready_for_fill": sum(1 for row in rows if row.get("form_readiness_status") == "READY_FOR_FILL"),
                "exclude": sum(1 for row in rows if str(row.get("risk_level", "")).lower() == "high"),
                "deadline_soon": sum(1 for row in rows if _deadline_bucket(row.get("deadline", ""))[0] in {0, 1, 2}),
            },
        )

    @app.post("/research/{campaign_id}/add-to-queue")
    def research_add_to_queue(
        campaign_id: str,
        next_url: str = Form(default="/research"),
        reason: str = Form(default="リサーチから応募キューに追加"),
    ) -> RedirectResponse:
        matched = next((row for row in load_campaigns() if row.get("campaign_id") == campaign_id), None)
        if matched:
            mark_selected(campaign_id, reason=reason)
            queue_rows = build_apply_queue(load_campaigns(), load_form_inspections(), load_entries(), load_apply_queue(), limit=30)
            save_apply_queue(queue_rows)
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/research"), status_code=303)

    @app.get("/research/x-campaigns", response_class=HTMLResponse)
    def research_x_campaigns(request: Request, date: str = "") -> HTMLResponse:
        day = date or load_latest_x_campaign_day()
        rows = _x_campaign_rows(load_x_campaign_candidates_for_day(day))
        run = load_x_campaign_run_for_day(day)
        report = load_x_campaign_report_for_day(day)
        return _render(
            request,
            "x_campaigns.html",
            page_title="X懸賞候補",
            active_page="x_research",
            x_campaign_rows=rows,
            x_campaign_run=run,
            x_campaign_report=report,
            x_campaign_date=day,
            x_campaign_days=load_x_campaign_days(),
            x_campaign_summary=_x_campaign_summary(rows),
        )

    @app.get("/api/research/x-campaigns")
    def api_research_x_campaigns(date: str = "") -> dict[str, object]:
        day = date or load_latest_x_campaign_day()
        rows = _x_campaign_rows(load_x_campaign_candidates_for_day(day))
        run = load_x_campaign_run_for_day(day)
        report = load_x_campaign_report_for_day(day)
        return {
            "date": day,
            "count": len(rows),
            "run": run,
            "summary": _x_campaign_summary(rows),
            "candidates": rows,
            "report_path": report.get("report_path", ""),
            "generated_at": report.get("generated_at", run.get("generated_at", "")),
        }

    @app.get("/api/research/x-campaigns/report")
    def api_research_x_campaigns_report(date: str = "") -> dict[str, object]:
        day = date or load_latest_x_campaign_day()
        report = load_x_campaign_report_for_day(day)
        rows = _x_campaign_rows(load_x_campaign_candidates_for_day(day))
        return {
            "date": day,
            "generated_at": report.get("generated_at", ""),
            "report_path": report.get("report_path", ""),
            "summary": _x_campaign_summary(rows),
            "candidates": rows,
            "report": report,
        }

    @app.post("/research/x-campaigns/{candidate_id}/queue")
    def research_x_campaign_queue(
        candidate_id: str,
        queue_status: str = Form(default="review_pending"),
        queue_reason: str = Form(default="人間確認へ送る"),
        date: str = Form(default=""),
        next_url: str = Form(default="/research/x-campaigns"),
    ) -> RedirectResponse:
        day = date or load_latest_x_campaign_day()
        from ..app.research.hermes_x_search import update_x_campaign_queue_state

        update_x_campaign_queue_state(candidate_id, day=day, queue_status=queue_status, queue_reason=queue_reason)
        redirect_url = _safe_internal_next_url(next_url, "/research/x-campaigns")
        if "?" not in redirect_url:
            redirect_url = f"{redirect_url}?date={day}"
        return RedirectResponse(url=redirect_url, status_code=303)

    @app.post("/queue/x/{candidate_id}/select")
    def queue_x_select(candidate_id: str, next_url: str = Form(default="/queue")) -> RedirectResponse:
        from ..app.research.hermes_x_search import update_x_campaign_queue_state

        candidate = _x_queue_item_for_id(candidate_id)
        day = str(candidate.get("day", "")) if isinstance(candidate, dict) else ""
        update_x_campaign_queue_state(
            candidate_id,
            day=day or None,
            queue_status="user_selected",
            queue_reason="応募候補に追加",
        )
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)

    @app.post("/queue/x/{candidate_id}/skip")
    def queue_x_skip(candidate_id: str, next_url: str = Form(default="/queue"), skip_reason: str = Form(default="スキップ")) -> RedirectResponse:
        from ..app.research.hermes_x_search import update_x_campaign_queue_state

        candidate = _x_queue_item_for_id(candidate_id)
        day = str(candidate.get("day", "")) if isinstance(candidate, dict) else ""
        update_x_campaign_queue_state(
            candidate_id,
            day=day or None,
            queue_status="skipped",
            queue_reason=skip_reason or "スキップ",
        )
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)

    @app.post("/queue/x/{candidate_id}/open-prepare")
    def queue_x_open_prepare(candidate_id: str, next_url: str = Form(default="/queue")) -> RedirectResponse:
        candidate = _x_queue_item_for_id(candidate_id)
        target_url = str(candidate.get("campaign_url", "")) or str(candidate.get("post_url", "")) if candidate else ""
        safety_score = 0
        try:
            safety_score = int(float(candidate.get("safety_score", 0) or 0))
        except Exception:
            safety_score = 0
        if not candidate or candidate.get("status") != "user_selected" or not target_url or safety_score < 50:
            return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)
        launch_status = _start_x_campaign_prepare(candidate_id, target_url)
        if launch_status == "started":
            from ..app.research.hermes_x_search import update_x_campaign_queue_state

            day = str(candidate.get("day", "")) if isinstance(candidate, dict) else ""
            update_x_campaign_queue_state(
                candidate_id,
                day=day or None,
                queue_status="apply_prepare_only",
                queue_reason="Chromeで応募準備",
            )
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)

    @app.post("/api/research/x-campaigns/select")
    async def api_research_x_campaigns_select(request: Request) -> dict[str, object]:
        payload = await _request_payload(request)
        day = str(payload.get("date", "") or "")
        candidate_id = str(payload.get("candidate_id", "") or payload.get("id", "") or payload.get("post_url", ""))
        post_url = str(payload.get("post_url", "") or "")
        reason = str(payload.get("reason", "") or payload.get("queue_reason", "") or "応募候補に追加")
        from ..app.research.hermes_x_search import update_x_campaign_queue_state

        ok = update_x_campaign_queue_state(candidate_id, day=day or None, queue_status="user_selected", queue_reason=reason, post_url=post_url)
        candidate = _x_queue_item_for_id(candidate_id, day)
        return {
            "status": "ok" if ok else "not_found",
            "action": "selected",
            "date": day or load_latest_x_campaign_day(),
            "candidate_id": candidate.get("candidate_id", candidate_id),
            "post_url": candidate.get("post_url", post_url),
            "campaign_url": candidate.get("campaign_url", ""),
            "queue_status": "user_selected" if ok else "",
            "summary": _x_queue_summary(_x_queue_sort_rows(load_x_campaign_queue_for_day(day or None))),
        }

    @app.post("/api/research/x-campaigns/skip")
    async def api_research_x_campaigns_skip(request: Request) -> dict[str, object]:
        payload = await _request_payload(request)
        day = str(payload.get("date", "") or "")
        candidate_id = str(payload.get("candidate_id", "") or payload.get("id", "") or payload.get("post_url", ""))
        post_url = str(payload.get("post_url", "") or "")
        reason = str(payload.get("reason", "") or payload.get("skip_reason", "") or "スキップ")
        from ..app.research.hermes_x_search import update_x_campaign_queue_state

        ok = update_x_campaign_queue_state(candidate_id, day=day or None, queue_status="skipped", queue_reason=reason, post_url=post_url)
        candidate = _x_queue_item_for_id(candidate_id, day)
        return {
            "status": "ok" if ok else "not_found",
            "action": "skipped",
            "date": day or load_latest_x_campaign_day(),
            "candidate_id": candidate.get("candidate_id", candidate_id),
            "post_url": candidate.get("post_url", post_url),
            "campaign_url": candidate.get("campaign_url", ""),
            "queue_status": "skipped" if ok else "",
            "summary": _x_queue_summary(_x_queue_sort_rows(load_x_campaign_queue_for_day(day or None))),
        }

    @app.post("/api/queue/open-prepare")
    async def api_queue_open_prepare(request: Request) -> dict[str, object]:
        payload = await _request_payload(request)
        day = str(payload.get("date", "") or "")
        candidate_id = str(payload.get("candidate_id", "") or payload.get("id", "") or payload.get("post_url", ""))
        post_url = str(payload.get("post_url", "") or "")
        candidate = _x_queue_item_for_id(candidate_id, day)
        if not candidate:
            return {"status": "not_found", "ok": False, "reason": "candidate_not_found"}
        safety_score = 0
        try:
            safety_score = int(float(candidate.get("safety_score", 0) or 0))
        except Exception:
            safety_score = 0
        if candidate.get("status") != "user_selected":
            return {"status": "blocked", "ok": False, "reason": "user_selected_required", "safety_score": safety_score}
        target_url = str(candidate.get("campaign_url", "")) or str(candidate.get("post_url", "")) or post_url
        if not target_url:
            return {"status": "blocked", "ok": False, "reason": "missing_url", "safety_score": safety_score}
        if safety_score < 50:
            return {"status": "blocked", "ok": False, "reason": "safety_too_low", "safety_score": safety_score, "target_url": target_url}
        launch_status = _start_x_campaign_prepare(candidate.get("candidate_id", candidate_id), target_url)
        if launch_status != "started":
            return {"status": "failed", "ok": False, "reason": launch_status, "safety_score": safety_score, "target_url": target_url}
        from ..app.research.hermes_x_search import update_x_campaign_queue_state

        update_x_campaign_queue_state(
            candidate.get("candidate_id", candidate_id),
            day=day or None,
            queue_status="apply_prepare_only",
            queue_reason="Chromeで応募準備",
            post_url=str(candidate.get("post_url", post_url)),
        )
        return {
            "status": "ok",
            "ok": True,
            "reason": "opened",
            "candidate_id": candidate.get("candidate_id", candidate_id),
            "post_url": candidate.get("post_url", post_url),
            "campaign_url": target_url,
            "safety_score": safety_score,
            "queue_status": "apply_prepare_only",
        }

    @app.post("/queue/x/{candidate_id}/open-prepare")
    def queue_x_open_prepare_form(candidate_id: str, next_url: str = Form(default="/queue")) -> RedirectResponse:
        candidate = _x_queue_item_for_id(candidate_id)
        if not candidate:
            return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)
        target_url = str(candidate.get("campaign_url", "")) or str(candidate.get("post_url", ""))
        if not target_url:
            return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)
        safety_score = 0
        try:
            safety_score = int(float(candidate.get("safety_score", 0) or 0))
        except Exception:
            safety_score = 0
        if candidate.get("status") != "user_selected" or safety_score < 50:
            return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)
        launch_status = _start_x_campaign_prepare(candidate_id, target_url)
        if launch_status == "started":
            from ..app.research.hermes_x_search import update_x_campaign_queue_state

            day = str(candidate.get("day", "")) if isinstance(candidate, dict) else ""
            update_x_campaign_queue_state(
                candidate_id,
                day=day or None,
                queue_status="apply_prepare_only",
                queue_reason="Chromeで応募準備",
                post_url=str(candidate.get("post_url", "")),
            )
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/queue"), status_code=303)

    @app.get("/review", response_class=HTMLResponse)
    def review(request: Request) -> HTMLResponse:
        rows = _sort_campaign_rows([row for row in load_campaigns() if row.get("form_readiness_status") == "REVIEW_ONLY"])
        inspections = load_form_inspections()
        detail_rows = []
        for row in rows[:20]:
            inspection = inspections.get(row.get("campaign_id", ""), {})
            detail_rows.append(
                {
                    **_safe_rows([row])[0],
                    "readiness_reason": row.get("form_readiness_reason", ""),
                    "quiz_required": row.get("quiz_required", ""),
                    "quiz_summary": row.get("quiz_summary", ""),
                    "quiz_items": inspection.get("quiz_items", []),
                    "manual_review_required_fields": _join_value(inspection.get("manual_review_required_fields", "")),
                    "blocked_auto_fill_fields": _join_value(inspection.get("blocked_auto_fill_fields", "")),
                    "required_but_skipped_fields": _join_value(inspection.get("required_but_skipped_fields", "")),
                    "next_action": _join_value(inspection.get("next_action", "人間確認してください")) or "人間確認してください",
                }
            )
        return _render(
            request,
            "review.html",
            page_title="要確認",
            active_page="review",
            review_rows=detail_rows,
        )

    @app.get("/security", response_class=HTMLResponse)
    def security(request: Request) -> HTMLResponse:
        report = load_release_report()
        browser_state = check_chrome_available()
        browser_checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
        browser_ready = "利用可能" if browser_state.get("headed_launch") == "ok" else "要確認"
        return _render(
            request,
            "security.html",
            page_title="セキュリティ",
            active_page="security",
            report=report,
            storage=profile_storage_state(),
            profile_preview=load_masked_profile_preview(),
            auto_scan=load_auto_scan_report(),
            browser_state=browser_state,
            browser_checked_at=browser_checked_at,
            security_items=[
                ("localhost限定", "ON"),
                ("自動送信", "無効"),
                ("暗号化保存", "ON"),
                ("平文プロフィール", "未検出が望ましい"),
                ("環境変数ファイル", "画面表示なし"),
                ("ログマスキング", "ON"),
                ("スクリーンショット保存", "OFF"),
                ("submitted_count", str(load_release_report().get("submitted_count", 0))),
                ("Chrome応募準備", browser_ready),
                ("専用Chromeプロファイル", "使用中"),
                ("普段使いChromeプロファイル", "使用しない"),
            ],
        )

    @app.post("/action/{name}")
    def action(name: str, request: Request, next_url: str = Form(default="/")) -> RedirectResponse:
        _run_safe_action(name)
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/"), status_code=303)

    @app.post("/campaigns/{campaign_id}/select")
    def select_campaign(campaign_id: str, request: Request, reason: str = Form(default="ユーザー選択"), next_url: str = Form(default="/campaigns")) -> RedirectResponse:
        matched = any(row.get("campaign_id") == campaign_id for row in load_campaigns())
        if matched:
            mark_selected(campaign_id, reason=reason)
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/campaigns"), status_code=303)

    @app.post("/campaigns/{campaign_id}/exclude")
    def exclude_campaign(campaign_id: str, request: Request, reason: str = Form(default="ユーザー除外"), next_url: str = Form(default="/campaigns")) -> RedirectResponse:
        matched = any(row.get("campaign_id") == campaign_id for row in load_campaigns())
        if matched:
            mark_excluded(campaign_id, reason=reason)
        return RedirectResponse(url=_safe_internal_next_url(next_url, "/campaigns"), status_code=303)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "host": WEB_HOST,
            "port": WEB_PORT,
            "submitted_count": load_release_report().get("submitted_count", 0),
        }

    return app
