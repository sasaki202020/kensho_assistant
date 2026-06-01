from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import sys
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import requests

from .app.campaign_classifier import classify_campaign, load_rules
from .app.entry_logger import ensure_entries_store, load_entries, log_event, make_entry_id, safe_exception_message, upsert_entry
from .app.entry_history import (
    add_entry_history,
    build_entry_record,
    duplicate_entry_groups,
    export_entry_history_csv,
    load_entry_history,
    mark_entry_applied,
    search_entry_history,
    summarize_entry_history,
)
from .app.agent_dashboard.service import (
    build_agent_status_payload,
    save_agent_status_payload,
    save_agent_status_run_payload,
)
from .app.later_queue import (
    add_later_queue,
    bridge_later_queue_to_campaign,
    list_later_queue,
    remove_later_queue_item,
    search_later_queue,
    summarize_later_queue,
    later_queue_to_entry_history,
    update_later_queue_status,
)
from .app.entry_url_resolver import (
    has_resolved_form_url,
    is_rd_link,
    resolve_rd_url,
    target_url_for_campaign,
)
from .app.form_detector import detect_fields, extract_quiz_items
from .app.form_filler import fill_campaign_page
from .app.auto_apply_engine import AutoApplyEngine
from .app.engine import (
    load_form_analysis,
    load_pre_submit_check,
    mark_prepared_campaign_submitted,
    run_prepared_campaign_dry_run,
    run_prepared_campaigns_dry_run_all,
)
from .app.form_readiness import evaluate_form_readiness
from .app.auto_scan_report import build_auto_scan_report, save_auto_scan_report
from .app.apply_queue import (
    approve_queue_item,
    approved_queue_rows,
    build_apply_queue,
    build_apply_queue_report,
    _deadline_bucket,
    mark_prepare_cancelled,
    mark_prepared,
    save_apply_queue,
    save_apply_queue_report,
)
from .app.browser_manager import check_browser_doctor, close_browser_safely, open_url_in_chrome
from .app.knshow_scraper import collect_campaigns, save_campaigns
from .app.models import CAMPAIGN_HEADERS
from .app.research_engine import (
    build_research_report,
    collect_research_campaigns,
    refresh_campaign_research_fields,
    save_research_report,
)
from .app.run_mode import get_run_mode, normalize_run_mode
from .mail_importer import rescan_win_mail_candidates
from .app.paths import (
    AFTER_SUBMIT_DIR,
    BEFORE_SUBMIT_DIR,
    APPLY_QUEUE_CSV,
    APPLY_QUEUE_JSON,
    APPLY_QUEUE_MD,
    BLOCKED_CSV,
    CAMPAIGNS_CSV,
    CONFIG_DIR,
    DATA_DIR,
    AGENT_STATUS_JSON,
    ENTRIES_CSV,
    FORM_INSPECTIONS_JSONL,
    HOLDS_CSV,
    PROFILE_JSON,
    RELEASE_REPORT_JSON,
    RELEASE_REPORT_MD,
    ensure_runtime_dirs,
)
from .app.profile_manager import (
    PROFILE_ENC,
    decrypt_profile,
    encrypt_profile,
    load_example_profile,
    load_profile,
    profile_check,
    profile_missing_fields,
    rotate_profile_key,
)
from .app.privacy_guard import redact_personal_info
from .app.report_generator import generate_report, status_summary
from .app.release_report import build_release_report, latest_inspections, render_release_report, release_report_paths
from .app.version import APP_VERSION
from .app.safety_checker import evaluate_safety
from .app.storage import ensure_csv, read_csv_rows, write_csv_rows


ENTRY_STATUS_MAP = {
    "SAFE_TO_FILL": "READY_TO_FILL",
    "DUPLICATE_ENTRY": "SKIPPED",
    "X_ACTION_REQUIRED": "BLOCKED_X",
    "INSTAGRAM_ACTION_REQUIRED": "BLOCKED_INSTAGRAM",
    "LINE_ACTION_REQUIRED": "BLOCKED_LINE",
    "FACEBOOK_ACTION_REQUIRED": "BLOCKED_FACEBOOK",
    "APP_REQUIRED": "BLOCKED_APP",
    "LOGIN_REQUIRED": "BLOCKED_LOGIN",
    "MEMBER_REGISTRATION_REQUIRED": "BLOCKED_MEMBER_REGISTRATION",
    "AGE_RESTRICTED": "BLOCKED_AGE_RESTRICTED",
    "PURCHASE_REQUIRED": "BLOCKED_PURCHASE",
    "RECEIPT_REQUIRED": "BLOCKED_RECEIPT",
    "BARCODE_REQUIRED": "BLOCKED_BARCODE",
    "CAPTCHA_REQUIRED": "BLOCKED_CAPTCHA",
    "REGION_LIMITED": "BLOCKED_RULES",
    "AUTO_ENTRY_FORBIDDEN": "BLOCKED_RULES",
    "BLOCKED": "BLOCKED_RULES",
    "NEEDS_HUMAN_REVIEW": "HOLD",
    "SAFE_TO_REVIEW_ONLY": "HOLD",
    "RULES_UNCLEAR": "BLOCKED_RULES",
}


def _fill_priority(row: dict[str, str]) -> int:
    text = " ".join(
        [
            row.get("resolved_entry_url", ""),
            row.get("entry_url", ""),
            row.get("campaign_name", ""),
            row.get("entry_type_raw", ""),
        ]
    ).casefold()
    score = 0
    for keyword, value in {
        "app-form.net": 100,
        "cp-form.jp": 90,
        "form.run": 80,
        "google.com/forms": 70,
        "survey": 20,
        "quiz": 10,
        "アンケート": 20,
        "クイズ": 10,
        "カンタン応募": 5,
    }.items():
        if keyword in text:
            score += value
    final_url = row.get("resolved_entry_url", "")
    if final_url:
        final_text = final_url.casefold()
        for keyword, value in {
            "app-form.net": 100,
            "cp-form.jp": 90,
            "form.run": 80,
            "google.com/forms": 70,
            "survey": 20,
        }.items():
            if keyword in final_text:
                score += value
    return score


def _already_filled_or_done(campaign: dict[str, str], entries: list[dict[str, str]]) -> bool:
    campaign_id = campaign.get("campaign_id", "")
    entry_url = campaign.get("entry_url", "")
    for row in entries:
        if row.get("status") not in {"SUBMITTED", "FILLED_NEEDS_APPROVAL", "HOLD", "SKIPPED"}:
            continue
        if campaign_id and row.get("campaign_id") == campaign_id:
            return True
        if entry_url and row.get("entry_url") == entry_url:
            return True
    return False


def _campaigns_by_id(campaigns: list[dict[str, str]], campaign_id: str | None) -> list[dict[str, str]]:
    if not campaign_id:
        return campaigns
    return [row for row in campaigns if row.get("campaign_id", "") == campaign_id]


def _campaign_rows() -> list[dict[str, str]]:
    return read_csv_rows(CAMPAIGNS_CSV)


def _save_campaign_rows(rows: list[dict[str, str]]) -> None:
    write_csv_rows(CAMPAIGNS_CSV, rows, CAMPAIGN_HEADERS)


def cmd_collect(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    rows = collect_campaigns(limit=args.limit)
    save_campaigns(rows, CAMPAIGNS_CSV)
    log_event("collect", {"count": len(rows), "limit": args.limit})
    print(CAMPAIGNS_CSV)
    print(f"collected: {len(rows)}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    ensure_csv(CAMPAIGNS_CSV, CAMPAIGN_HEADERS)
    ensure_entries_store(ENTRIES_CSV)
    campaigns = _campaign_rows()
    entries = load_entries()
    rules = load_rules()
    blocked_rows: list[dict[str, str]] = []
    hold_rows: list[dict[str, str]] = []
    analyzed_rows: list[dict[str, str]] = []
    for campaign in campaigns:
        classification = classify_campaign(campaign, rules=rules)
        safety = evaluate_safety(campaign, classification, existing_entries=entries)
        row = dict(campaign)
        row["status"] = safety.status
        row["notes"] = redact_personal_info(
            "; ".join(
                filter(None, [row.get("notes", ""), f"entry_type={classification.entry_type}", f"risk={safety.risk_reason}"])
            ).strip("; ")
        )
        analyzed_rows.append(row)
        entry_status = ENTRY_STATUS_MAP.get(safety.status, "HOLD")
        entry_record = {
            "entry_id": make_entry_id(campaign.get("campaign_id", ""), campaign.get("entry_url", "")),
            "campaign_id": campaign.get("campaign_id", ""),
            "source": campaign.get("source", ""),
            "campaign_name": campaign.get("campaign_name", ""),
            "prize": campaign.get("prize", ""),
            "winner_count": campaign.get("winner_count", ""),
            "provider": campaign.get("provider", ""),
            "deadline": campaign.get("deadline", ""),
            "knshow_url": campaign.get("knshow_url", ""),
            "entry_url": campaign.get("entry_url", ""),
            "entry_type": classification.entry_type,
            "risk_level": safety.risk_level,
            "risk_reason": safety.risk_reason,
            "auto_submit_allowed": str(safety.auto_submit_allowed).lower(),
            "status": entry_status,
            "submitted_at": "",
            "screenshot_before": "",
            "screenshot_after": "",
            "notes": redact_personal_info(row["notes"]),
            "created_at": campaign.get("collected_at", datetime.now().astimezone().isoformat(timespec="seconds")),
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        upsert_entry(entry_record)
        if safety.status.startswith(("BLOCKED", "CAPTCHA", "LOGIN", "X_", "INSTAGRAM_", "LINE_", "FACEBOOK_", "AGE_", "PURCHASE_", "RECEIPT_", "BARCODE_", "AUTO_ENTRY_FORBIDDEN")) or safety.status == "DUPLICATE_ENTRY":
            blocked_rows.append(row)
        elif safety.status in {"NEEDS_HUMAN_REVIEW", "SAFE_TO_REVIEW_ONLY", "RULES_UNCLEAR"}:
            hold_rows.append(row)
    _save_campaign_rows(analyzed_rows)
    write_csv_rows(BLOCKED_CSV, blocked_rows, CAMPAIGN_HEADERS)
    write_csv_rows(HOLDS_CSV, hold_rows, CAMPAIGN_HEADERS)
    log_event("analyze", {"count": len(analyzed_rows), "blocked": len(blocked_rows), "holds": len(hold_rows)})
    print(f"analyzed: {len(analyzed_rows)}")
    print(f"blocked: {len(blocked_rows)}")
    print(f"hold: {len(hold_rows)}")
    return 0


def _load_profile_or_fail() -> dict[str, str]:
    profile = load_profile()
    if not profile:
        raise SystemExit(f"{PROFILE_JSON} is missing")
    missing = profile_missing_fields(profile)
    if missing:
        raise SystemExit(f"profile incomplete: {', '.join(missing)}")
    return profile


def cmd_profile_check(args: argparse.Namespace) -> int:
    _, missing = profile_check(encrypted=args.encrypted)
    store = PROFILE_ENC if args.encrypted or PROFILE_ENC.exists() else PROFILE_JSON
    print(f"profile store: {store}")
    print(f"complete: {not missing}")
    print(f"missing fields: {', '.join(missing) if missing else 'none'}")
    return 0


def cmd_profile_encrypt(args: argparse.Namespace) -> int:
    target = encrypt_profile(delete_plain=args.delete_plain)
    print(target)
    return 0


def cmd_profile_decrypt(args: argparse.Namespace) -> int:
    profile = decrypt_profile(output_path=args.output)
    print(f"written: {args.output}")
    print(f"complete: {not profile_missing_fields(profile)}")
    return 0


def cmd_profile_rotate_key(args: argparse.Namespace) -> int:
    rotate_profile_key(delete_plain=args.delete_plain)
    print("rotated")
    return 0


def cmd_fill(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    profile = _load_profile_or_fail()
    campaigns = _campaign_rows()
    entries = load_entries()
    candidate_rows = _campaigns_by_id(campaigns, args.campaign_id)
    safe_campaigns = sorted(
        [
            row
            for row in candidate_rows
            if row.get("status") == "SAFE_TO_FILL"
            and has_resolved_form_url(row)
            and (
                row.get("form_readiness_status", "") == "READY_FOR_FILL"
                or (args.force_review and row.get("form_readiness_status", "") == "REVIEW_ONLY")
            )
        ],
        key=_fill_priority,
        reverse=True,
    )
    if not args.force:
        safe_campaigns = [row for row in safe_campaigns if not _already_filled_or_done(row, entries)]
    if args.limit:
        safe_campaigns = safe_campaigns[: args.limit]
    if not safe_campaigns:
        if args.campaign_id:
            selected = _campaigns_by_id(campaigns, args.campaign_id)
            if not selected:
                print(f"campaign_id not found: {args.campaign_id}")
            else:
                row = selected[0]
                print(
                    f"campaign_id={args.campaign_id} readiness={row.get('form_readiness_status', '') or 'UNKNOWN'} "
                    f"reason={row.get('form_readiness_reason', '') or 'inspect-form required'}"
                )
            return 0
        unresolved = [row for row in campaigns if row.get("status") == "SAFE_TO_FILL" and is_rd_link(row.get("entry_url", ""))]
        resolved = [row for row in campaigns if row.get("status") == "SAFE_TO_FILL" and row.get("form_readiness_status", "") == "READY_FOR_FILL"]
        inspected_nonready = [
            row
            for row in campaigns
            if row.get("status") == "SAFE_TO_FILL"
            and row.get("form_readiness_status", "") not in {"", "READY_FOR_FILL"}
        ]
        if resolved:
            print("no unprocessed READY_FOR_FILL campaigns")
        elif inspected_nonready:
            review_only_count = sum(1 for row in inspected_nonready if row.get("form_readiness_status") == "REVIEW_ONLY")
            print("READY_FOR_FILL の案件はありません。")
            if review_only_count:
                print(f"ただし REVIEW_ONLY の候補が {review_only_count} 件あります。")
                print("次のコマンドで確認できます:")
                print("python main.py review --limit 5")
                print("REVIEW_ONLY は、年齢・同意・地域など人間確認が必要なため、自動入力対象から外しています。")
            else:
                print("現在の検査結果では安全入力対象が見つかっていません。")
        elif unresolved:
            print("この案件は rd リンクのままです。先に `python main.py resolve-urls --limit 20` を実行してください。")
        else:
            print("READY_FOR_FILL の案件がありません。先に inspect-form を実行してください。")
        return 0
    save_screenshot = os.environ.get("KENSHO_SAVE_SCREENSHOT", "0").strip().lower() not in {"0", "false", "no", "off"}
    processed = 0
    submitted = 0
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SystemExit(f"playwright is required for fill: {safe_exception_message(exc)}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        for campaign in safe_campaigns:
            processed += 1
            entry_url = campaign.get("entry_url", "") or campaign.get("knshow_url", "")
            target_url = target_url_for_campaign(campaign)
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            result = fill_campaign_page(
                page,
                campaign,
                profile,
                screenshot_dir=BEFORE_SUBMIT_DIR,
                save_screenshot=save_screenshot,
            )

            if not result:
                continue

            if result.decision == "hold":
                entry_state = "HOLD"
            elif result.decision == "open":
                entry_state = "FILLED_NEEDS_APPROVAL"
            elif result.decision == "skip":
                entry_state = "SKIPPED"
            elif result.decision == "fill":
                entry_state = "SUBMITTED" if result.submitted else "FILLED_NEEDS_APPROVAL"
            else:
                entry_state = "SKIPPED"
            if result.submitted:
                submitted += 1

            entry_id = make_entry_id(campaign.get("campaign_id", ""), entry_url)
            upsert_entry(
                {
                    "entry_id": entry_id,
                    "campaign_id": campaign.get("campaign_id", ""),
                    "source": campaign.get("source", ""),
                    "campaign_name": campaign.get("campaign_name", ""),
                    "prize": campaign.get("prize", ""),
                    "winner_count": campaign.get("winner_count", ""),
                    "provider": campaign.get("provider", ""),
                    "deadline": campaign.get("deadline", ""),
                    "knshow_url": campaign.get("knshow_url", ""),
                    "entry_url": entry_url,
                    "entry_type": campaign.get("entry_type_raw", ""),
                    "risk_level": "low",
                    "risk_reason": campaign.get("notes", ""),
                    "auto_submit_allowed": "true",
                    "status": entry_state,
                    "submitted_at": datetime.now().astimezone().isoformat(timespec="seconds") if result.submitted else "",
                    "screenshot_before": result.screenshot_before,
                    "screenshot_after": result.screenshot_after,
                    "notes": redact_personal_info(result.notes),
                    "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }
            )
        browser.close()
    log_event("fill", {"count": processed, "submitted": submitted})
    print(f"processed: {processed}")
    print(f"submitted: {submitted}")
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    profile = _load_profile_or_fail()
    if not args.require_user_approved:
        print("この案件は承認済み応募キュー専用です。--require-user-approved を付けてください。")
        return 1
    campaigns = _campaign_rows()
    selected = _campaigns_by_id(campaigns, args.campaign_id)
    if not selected:
        print(f"campaign_id not found: {args.campaign_id}")
        return 1
    campaign = selected[0]
    queue_rows = {row.get("campaign_id", ""): row for row in read_csv_rows(APPLY_QUEUE_CSV)}
    queue_item = queue_rows.get(args.campaign_id, {})
    if queue_item.get("approved_by_user", "") != "true" or queue_item.get("queue_status", "") not in {"APPROVED", "PREPARED"}:
        print("この案件は承認済みではありません。先に応募候補に承認してください。")
        return 1
    if not (
        not campaign.get("status", "").startswith("BLOCKED")
        and has_resolved_form_url(campaign)
        and campaign.get("form_readiness_status") in {"READY_FOR_FILL", "REVIEW_ONLY"}
    ):
        print(f"この案件は応募準備対象外です: {campaign.get('form_readiness_reason', '') or 'inspect-form required'}")
        return 1
    original_queue_status = queue_item.get("queue_status", "APPROVED")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SystemExit(f"playwright is required for prepare: {safe_exception_message(exc)}")

    save_screenshot = not args.no_screenshot
    if args.allow_age_fill:
        from .ui.data_loader import set_age_fill_user_approved

        set_age_fill_user_approved(args.campaign_id, True)
    context = None
    with sync_playwright() as playwright:
        try:
            context, page, actual_browser = open_url_in_chrome(playwright, target_url_for_campaign(campaign), args.browser)
        except Exception as exc:
            raise SystemExit(f"browser launch failed: {safe_exception_message(exc)}")
        if args.browser == "chrome" and actual_browser != "chrome":
            print("Chromeが見つからないため Chromium で起動しました。")
        result = fill_campaign_page(
            page,
            campaign,
            profile,
            screenshot_dir=BEFORE_SUBMIT_DIR,
            save_screenshot=save_screenshot,
            allow_age_fill=args.allow_age_fill,
            auto_confirm_known_fields=getattr(args, "yes_known_fields", False),
        )
        if result and result.decision == "fill":
            mark_prepared(campaign.get("campaign_id", ""))
            print("Chromeで応募ページを開きました")
            print("アプリは応募送信していません")
            print("内容を確認してください")
            print("送信した場合だけ、Web UIで「手動送信済みにする」を押してください")
            print("送信しない場合は「保留」または「スキップ」を選んでください")
            print("queue_status: PREPARED")
            print("last_action: PREPARED_WITH_CHROME")
            print("prepared_at: saved")
        elif result and result.decision == "n":
            mark_prepare_cancelled(campaign.get("campaign_id", ""), original_queue_status)
            print("応募準備はキャンセルされました")
            print("送信はしていません")
            print("必要ならもう一度「Chromeで応募準備」を押してください")
            print(f"queue_status: {original_queue_status}")
            print("last_action: PREPARE_CANCELLED_BY_USER")
        elif result and result.decision == "hold":
            mark_prepare_cancelled(campaign.get("campaign_id", ""), original_queue_status)
            print("応募準備は保留しました")
            print("送信はしていません")
            print(f"queue_status: {original_queue_status}")
            print("last_action: PREPARE_CANCELLED_BY_USER")
        elif result and result.decision == "open":
            mark_prepare_cancelled(campaign.get("campaign_id", ""), original_queue_status)
            print("応募ページを開いたままにしました")
            print("送信はしていません")
            print(f"queue_status: {original_queue_status}")
            print("last_action: PREPARE_CANCELLED_BY_USER")
        print("submitted: 0")
        if args.keep_open:
            input("ブラウザを閉じるには Enter を押してください。送信は自動実行していません。")
        close_browser_safely(context)
    return 0


def cmd_auto_apply(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    run_mode = normalize_run_mode(args.run_mode or get_run_mode())
    profile = _load_profile_or_fail()
    campaigns = _campaign_rows()
    selected = _campaigns_by_id(campaigns, args.campaign_id)
    if not selected:
        print(f"campaign_id not found: {args.campaign_id}")
        return 1
    campaign = selected[0]
    if run_mode != "mock":
        queue_rows = {row.get("campaign_id", ""): row for row in read_csv_rows(APPLY_QUEUE_CSV)}
        queue_item = queue_rows.get(args.campaign_id, {})
        if queue_item.get("queue_status", "") not in {"APPROVED", "PREPARED"}:
            print("dry_run/review は APPROVED または PREPARED の候補だけ実行します。")
            return 1
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SystemExit(f"playwright is required for auto-apply: {safe_exception_message(exc)}")
    with sync_playwright() as playwright:
        context = None
        try:
            context, page, actual_browser = open_url_in_chrome(playwright, target_url_for_campaign(campaign), args.browser)
            engine = AutoApplyEngine(run_mode)
            result = engine.run(page, campaign, profile)
            record = result["record"]
            print(f"run_mode: {record['run_mode']}")
            print(f"status: {record['status']}")
            print(f"filled_fields_count: {record['filled_fields_count']}")
            print(f"submit_attempted: {str(record['submit_attempted']).lower()}")
            print(f"submit_clicked: {str(record['submit_clicked']).lower()}")
            print(f"auto_submitted: {str(record['auto_submitted']).lower()}")
            if run_mode in {"dry_run", "review"}:
                mark_prepared(campaign.get("campaign_id", ""))
            if args.keep_open:
                input("ブラウザを閉じるには Enter を押してください。実サイト送信は実行していません。")
        finally:
            if context and not args.keep_open:
                close_browser_safely(context)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    command = args.apply_command
    if command == "dry-run":
        result = run_prepared_campaign_dry_run(args.campaign_id, browser=args.browser, keep_open=args.keep_open)
        _print_apply_result(result)
        return 0 if result.get("ok") else 1
    if command == "dry-run-all":
        results = run_prepared_campaigns_dry_run_all(status=args.status, limit=args.limit, browser=args.browser)
        ok_count = sum(1 for result in results if result.get("ok"))
        print(f"processed: {len(results)}")
        print(f"ok: {ok_count}")
        print(f"failed: {len(results) - ok_count}")
        for result in results:
            reason_list = result.get("needs_review_reasons", []) or []
            reason_text = "; ".join(str(reason) for reason in reason_list if str(reason).strip()) or "-"
            print(
                f"{result.get('campaign_id', '')} | {result.get('status', '')} | "
                f"submit_clicked={str(result.get('submit_clicked', False)).lower()} | "
                f"auto_submitted={str(result.get('auto_submitted', False)).lower()} | "
                f"needs_review_reasons={reason_text}"
            )
        return 0 if ok_count == len(results) else 1
    if command == "show-analysis":
        print(json.dumps(load_form_analysis(args.campaign_id), ensure_ascii=False, indent=2))
        return 0
    if command == "show-check":
        print(json.dumps(load_pre_submit_check(args.campaign_id), ensure_ascii=False, indent=2))
        return 0
    if command == "mark-submitted":
        ok = mark_prepared_campaign_submitted(args.campaign_id)
        print(f"mark_submitted: {'ok' if ok else 'not_found'}")
        return 0 if ok else 1
    print(f"unknown apply command: {command}")
    return 1


def _print_apply_result(result: dict[str, object]) -> None:
    print(f"campaign_id: {result.get('campaign_id', '')}")
    print(f"status: {result.get('status', '')}")
    print(f"filled_fields_count: {result.get('filled_fields_count', 0)}")
    print(f"submit_attempted: {str(result.get('submit_attempted', False)).lower()}")
    print(f"submit_clicked: {str(result.get('submit_clicked', False)).lower()}")
    print(f"auto_submitted: {str(result.get('auto_submitted', False)).lower()}")
    reason_list = result.get("needs_review_reasons", []) or []
    reason_text = "; ".join(str(reason) for reason in reason_list if str(reason).strip()) or "-"
    print(f"needs_review_reasons: {reason_text}")
    print(f"screenshot_path: {result.get('screenshot_path', '')}")
    print(f"analysis_path: {result.get('analysis_path', '')}")
    print(f"check_path: {result.get('check_path', '')}")


def _approved_queue_sort_key(row: dict[str, str]) -> tuple[int, int, int, int, str]:
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


def cmd_approve_campaign(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    if approve_queue_item(args.campaign_id, note=args.note or "", age_fill_user_approved=False):
        print(f"approved: {args.campaign_id}")
        return 0
    print(f"campaign_id not found or not eligible: {args.campaign_id}")
    return 1


def cmd_approved_queue(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    rows = sorted(approved_queue_rows(), key=_approved_queue_sort_key)
    if args.limit:
        rows = rows[: args.limit]
    for row in rows:
        print(
            f"{row.get('campaign_id', '')} | {row.get('campaign_name', '')} | {row.get('deadline', '')} | "
            f"{row.get('readiness_status', '')} | {row.get('queue_status', '')} | "
            f"manual_review_required_fields={row.get('manual_review_required_fields', '')} | "
            f"next_action={row.get('next_action', '')} | approved_session_order={row.get('approved_session_order', '') or '-'} | "
            f"opportunity_score={row.get('opportunity_score', '')} | priority_score={row.get('priority_score', '') or row.get('readiness_score', '')}"
        )
    print(f"approved_total: {len(rows)}")
    return 0


def cmd_browser_doctor(args: argparse.Namespace) -> int:
    for name, value in check_browser_doctor().items():
        print(f"{name}: {value}")
    return 0


def _safe_form_campaigns(limit: int | None = None, campaign_id: str | None = None) -> list[dict[str, str]]:
    campaigns = _campaign_rows()
    campaigns = _campaigns_by_id(campaigns, campaign_id)
    rows = sorted(
        [row for row in campaigns if row.get("status") == "SAFE_TO_FILL" and has_resolved_form_url(row)],
        key=_fill_priority,
        reverse=True,
    )
    return rows[:limit] if limit else rows


def _inspection_record(campaign: dict[str, str], page, profile: dict[str, str]) -> dict[str, object]:
    from .app.form_filler import plan_field_filling

    fields = plan_field_filling(detect_fields(page), profile)
    quiz_items = extract_quiz_items(page)
    submit_button_detected = page.locator('button[type="submit"], input[type="submit"]').count() > 0
    landing_links_detected = page.locator('a:has-text("応募"), a:has-text("詳しくはこちら"), a:has-text("キャンペーン詳細")').count() > 0
    readiness = evaluate_form_readiness(
        fields=fields,
        detected_forms_count=page.locator("form").count(),
        submit_button_detected=submit_button_detected,
        landing_links_detected=landing_links_detected,
        safety_status=campaign.get("status", ""),
        quiz_required=bool(quiz_items),
    )
    quiz_summary = "; ".join(
        str(item.get("question_text", "")).strip()[:120]
        for item in quiz_items
        if str(item.get("question_text", "")).strip()
    )
    return {
        "campaign_id": campaign.get("campaign_id", ""),
        "campaign_name": campaign.get("campaign_name", ""),
        "resolved_entry_url": campaign.get("resolved_entry_url", ""),
        "resolved_domain": campaign.get("resolved_domain", ""),
        "detected_forms_count": page.locator("form").count(),
        "readiness_status": readiness.readiness_status,
        "readiness_score": readiness.readiness_score,
        "readiness_reason": readiness.readiness_reason,
        "major_fields_detected": readiness.major_fields_detected,
        "search_only_detected": readiness.search_only_detected,
        "submit_button_detected": readiness.submit_button_detected,
        "landing_links_detected": readiness.landing_links_detected,
        "quiz_required": readiness.quiz_required,
        "quiz_summary": quiz_summary,
        "quiz_manual_required": bool(quiz_items),
        "quiz_items": quiz_items,
        "detected_fields": [
            {
                "field_name": field.field_name,
                "input_type": field.input_type,
                "selector": field.selector,
                "label_text": field.label,
                "aria_label": field.aria_label,
                "placeholder": field.placeholder,
                "name": field.name,
                "id": field.element_id,
                "nearby_text": field.nearby_text,
                "required": field.required,
                "confidence": field.confidence,
                "detected_from": field.detected_from,
                "reason": field.reason,
                "will_fill": field.will_fill,
                "skip_reason": field.skip_reason,
            }
            for field in fields
        ],
        "inspected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def cmd_inspect_form(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    profile = _load_profile_or_fail()
    campaigns = _safe_form_campaigns(args.limit, args.campaign_id)
    if not campaigns:
        print("no SAFE_TO_FILL campaigns with resolved_entry_url")
        return 0
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SystemExit(f"playwright is required for inspect-form: {safe_exception_message(exc)}")
    FORM_INSPECTIONS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    inspected = 0
    campaign_by_id = {row.get("campaign_id", ""): row for row in _campaign_rows()}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        with FORM_INSPECTIONS_JSONL.open("a", encoding="utf-8") as handle:
            for campaign in campaigns:
                target_url = target_url_for_campaign(campaign)
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                record = _inspection_record(campaign, page, profile)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                campaign.update(
                    {
                        "form_readiness_status": record["readiness_status"],
                        "form_readiness_score": str(record["readiness_score"]),
                        "form_readiness_reason": record["readiness_reason"],
                        "inspected_at": record["inspected_at"],
                    }
                )
                campaign_by_id[campaign.get("campaign_id", "")] = campaign
                print(
                    f"{campaign.get('campaign_id', '')}: readiness={record['readiness_status']} "
                    f"forms={record['detected_forms_count']} fields={len(record['detected_fields'])}"
                )
                inspected += 1
        browser.close()
    _save_campaign_rows(list(campaign_by_id.values()))
    log_event("inspect_form", {"count": inspected})
    print(FORM_INSPECTIONS_JSONL)
    print(f"inspected: {inspected}")
    return 0


def cmd_resolve_urls(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    campaigns = _campaign_rows()
    candidates = [
        row
        for row in campaigns
        if is_rd_link(row.get("entry_url", "") or row.get("knshow_url", ""))
        and (args.force or not row.get("resolved_entry_url", ""))
    ]
    candidates.sort(key=lambda row: (row.get("status", "") != "SAFE_TO_FILL", -_fill_priority(row)))
    candidates = candidates[: args.limit] if args.limit else candidates
    if not candidates:
        print("no rd links to resolve")
        return 0
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SystemExit(f"playwright is required for resolve-urls: {safe_exception_message(exc)}")
    by_id = {row.get("campaign_id", ""): row for row in campaigns}
    resolved = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        for index, campaign in enumerate(candidates, start=1):
            rd_url = campaign.get("entry_url", "") or campaign.get("knshow_url", "")
            try:
                result = resolve_rd_url(page, rd_url)
                campaign.update(
                    {
                        "resolved_entry_url": result.resolved_entry_url,
                        "resolved_domain": result.resolved_domain,
                        "resolve_status": result.resolve_status,
                        "resolve_reason": result.resolve_reason,
                        "resolved_at": result.resolved_at,
                    }
                )
                resolved += 1
                print(f"{index}: {campaign.get('campaign_id', '')} {result.resolve_status} {result.resolved_entry_url}")
            except Exception as exc:
                campaign.update(
                    {
                        "resolved_entry_url": "",
                        "resolved_domain": "",
                        "resolve_status": "ERROR",
                        "resolve_reason": safe_exception_message(exc),
                        "resolved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    }
                )
                print(f"{index}: {campaign.get('campaign_id', '')} ERROR")
            time.sleep(1.0)
        browser.close()
    _save_campaign_rows(list(by_id.values()))
    log_event("resolve_urls", {"count": len(candidates), "resolved": resolved})
    print(f"processed: {len(candidates)}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(redact_personal_info(status_summary()))
    return 0


def cmd_agent_status_generate(args: argparse.Namespace) -> int:
    output_path = Path(args.output) if getattr(args, "output", "") else AGENT_STATUS_JSON
    payload = save_agent_status_payload(output_path)
    print(output_path.resolve())
    print(f"agents: {len(payload.get('agents', []))}")
    print(f"updated_at: {payload.get('updated_at', '')}")
    return 0


def cmd_agent_status_run(args: argparse.Namespace) -> int:
    task = str(getattr(args, "task", "") or "").strip()
    if not task:
        raise SystemExit("--task is required")
    mode = str(getattr(args, "mode", "normal") or "normal").strip() or "normal"
    output_path = Path(args.output) if getattr(args, "output", "") else AGENT_STATUS_JSON
    payload = save_agent_status_run_payload(task, output_path, mode=mode)
    print(output_path.resolve())
    print(f"task: {payload.get('task', '')}")
    print(f"mode: {payload.get('mode', '')}")
    print(f"agents: {len(payload.get('agents', []))}")
    print(f"updated_at: {payload.get('updated_at', '')}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    print(redact_personal_info(generate_report()))
    return 0


def _review_next_action(fields: list[dict[str, object]], reason: str) -> str:
    names = {str(field.get("field_name", "")) for field in fields}
    required_skipped = [field for field in fields if field.get("required") and not field.get("will_fill")]
    if "age" in names:
        return "年齢項目があるため、ユーザーが手動確認してください"
    if required_skipped:
        return "必須だが自動入力しない項目を手動確認してください"
    if "主要項目" in reason:
        return "主要項目が不足しているため、自動入力対象外です"
    return "フォーム内容を手動確認してください"


def cmd_review(args: argparse.Namespace) -> int:
    campaigns = {row.get("campaign_id", ""): row for row in _campaign_rows()}
    inspections = latest_inspections()
    rows = [row for row in inspections.values() if row.get("readiness_status") == "REVIEW_ONLY"][: args.limit]
    for row in rows:
        campaign = campaigns.get(str(row.get("campaign_id", "")), {})
        fields = list(row.get("detected_fields", []))
        quiz_items = list(row.get("quiz_items", []))
        required_skipped = [
            field.get("field_name", "")
            for field in fields
            if field.get("required") and not field.get("will_fill")
        ]
        blocked = [
            field.get("field_name", "")
            for field in fields
            if field.get("field_name") in {"age", "consent", "newsletter"}
        ]
        manual = sorted(set(required_skipped + blocked + (["quiz"] if row.get("quiz_required") else [])))
        lines = [
            f"campaign_id: {row.get('campaign_id', '')}",
            f"campaign_name: {campaign.get('campaign_name', '')}",
            f"resolved_entry_url: {row.get('resolved_entry_url', '')}",
            f"readiness_status: {row.get('readiness_status', '')}",
            f"readiness_reason: {row.get('readiness_reason', '')}",
            f"quiz_required: {row.get('quiz_required', False)}",
            f"quiz_summary: {row.get('quiz_summary', '') or 'none'}",
            f"detected_fields: {len(fields)}",
            f"will_fill_count: {sum(1 for field in fields if field.get('will_fill'))}",
            f"required_but_skipped_fields: {', '.join(required_skipped) or 'none'}",
            f"manual_review_required_fields: {', '.join(manual) or 'none'}",
            f"blocked_auto_fill_fields: {', '.join(blocked) or 'none'}",
            f"next_action: {_review_next_action(fields, str(row.get('readiness_reason', '')))}",
        ]
        if quiz_items:
            lines.extend(
                [
                    "quiz_items:",
                    *[
                        f"- {item.get('question_text', '')} / choices: {', '.join(item.get('choices', [])) or 'none'}"
                        for item in quiz_items
                    ],
                ]
            )
        lines.extend([
            "",
        ])
        print(redact_personal_info("\n".join(lines)))
    print(f"review_only: {len(rows)}")
    return 0


def cmd_release_report(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    version = getattr(args, "version", APP_VERSION)
    report = build_release_report(version=version)
    md_path, json_path = release_report_paths(version)
    md_path.write_text(render_release_report(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(md_path)
    print(json_path)
    print(f"release_status: {report['release_status']}")
    return 0


def _print_entry_rows(rows: list[dict[str, str]], limit: int | None = None) -> None:
    shown = rows if limit is None else rows[:limit]
    for row in shown:
        print(
            "\t".join(
                [
                    row.get("campaign_id", ""),
                    row.get("title", ""),
                    row.get("deadline", ""),
                    row.get("status", ""),
                    row.get("newsletter_status", ""),
                    row.get("applied_at", ""),
                    row.get("result_check_date", ""),
                    row.get("duplicate_key", ""),
                ]
            )
        )


def cmd_entries_list(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    rows = load_entry_history()
    rows = sorted(rows, key=lambda row: (row.get("deadline", ""), row.get("title", ""), row.get("campaign_id", "")))
    _print_entry_rows(rows, getattr(args, "limit", None))
    summary = summarize_entry_history(rows)
    print(f"total: {summary.get('total', 0)}")
    print(f"applied: {summary.get('applied', 0)}")
    print(f"result_pending: {summary.get('result_pending', 0)}")
    print(f"newsletter_unsubscribe_needed: {summary.get('newsletter_unsubscribe_needed', 0)}")
    print(f"duplicate_candidates: {summary.get('duplicate_candidates', 0)}")
    return 0


def cmd_entries_search(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    rows = search_entry_history(args.keyword)
    rows = sorted(rows, key=lambda row: (row.get("deadline", ""), row.get("title", ""), row.get("campaign_id", "")))
    _print_entry_rows(rows, getattr(args, "limit", None))
    print(f"matched: {len(rows)}")
    return 0


def cmd_entries_add(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    record = build_entry_record(
        campaign_id=getattr(args, "campaign_id", ""),
        title=getattr(args, "title", ""),
        source_site=getattr(args, "source_site", ""),
        url=args.url,
        prize=getattr(args, "prize", ""),
        deadline=getattr(args, "deadline", ""),
        applied_at=getattr(args, "applied_at", ""),
        result_check_date=getattr(args, "result_check_date", ""),
        status=getattr(args, "status", "APPLIED"),
        newsletter_status=getattr(args, "newsletter_status", "unknown"),
        pii_used=getattr(args, "pii_used", False),
        memo=getattr(args, "memo", ""),
        duplicate_key=getattr(args, "duplicate_key", ""),
    )
    saved = add_entry_history(record)
    print(saved.get("campaign_id", ""))
    print(saved.get("title", ""))
    print(saved.get("status", ""))
    print(saved.get("duplicate_key", ""))
    return 0


def cmd_entries_mark_applied(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    record = mark_entry_applied(
        args.campaign_id,
        url=getattr(args, "url", ""),
        title=getattr(args, "title", ""),
        source_site=getattr(args, "source_site", ""),
        prize=getattr(args, "prize", ""),
        deadline=getattr(args, "deadline", ""),
        result_check_date=getattr(args, "result_check_date", ""),
        newsletter_status=getattr(args, "newsletter_status", "unknown"),
        memo=getattr(args, "memo", ""),
        pii_used=getattr(args, "pii_used", False),
    )
    print(record.get("campaign_id", ""))
    print(record.get("title", ""))
    print(record.get("applied_at", ""))
    print(record.get("status", ""))
    return 0


def cmd_entries_duplicates(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    groups = duplicate_entry_groups()
    for group in groups:
        print(f"{group['duplicate_key']}\t{group['count']}")
        for row in group["items"]:
            print(f"  - {row.get('campaign_id', '')}\t{row.get('title', '')}\t{row.get('status', '')}")
    print(f"duplicate_groups: {len(groups)}")
    return 0


def cmd_entries_export_csv(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    path = export_entry_history_csv()
    print(path)
    return 0


def cmd_entries_win_mail_rescan(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    rows = rescan_win_mail_candidates()
    print(len(rows))
    for row in rows[:10]:
        print("\t".join([row.get("subject", ""), row.get("sender", ""), row.get("status", "")]))
    return 0


def _later_deadline_key(value: str) -> tuple[int, str]:
    text = value.strip()
    if not text or text.casefold() == "unknown":
        return (9999, text or "unknown")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(text, fmt).date()
            return ((dt - datetime.now().date()).days, text)
        except ValueError:
            continue
    if "今日" in text:
        return (0, text)
    if "明日" in text:
        return (1, text)
    return (9999, text)


def _later_sort_key(row: dict[str, str]) -> tuple[int, str, str, str]:
    deadline_bucket, _ = _later_deadline_key(row.get("deadline", ""))
    return (deadline_bucket, row.get("updated_at", ""), row.get("title", ""), row.get("id", ""))


def _later_find_row(item_id: str) -> dict[str, str]:
    for row in list_later_queue():
        if row.get("id", "") == item_id:
            return row
    return {}


def cmd_later_add_url(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    row, created, reason = add_later_queue(args.url)
    print(row.get("id", ""))
    print(row.get("title", ""))
    print(row.get("site_name", ""))
    print(row.get("deadline", ""))
    print(row.get("status", ""))
    print(row.get("safety_memo", ""))
    if not created and reason == "duplicate":
        print(f"duplicate: {row.get('id', '')}")
    return 0


def cmd_later_list(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    all_rows = sorted(list_later_queue(), key=_later_sort_key)
    rows = all_rows
    if getattr(args, "limit", None):
        rows = rows[: args.limit]
    for row in rows:
        print(
            f"{row.get('id', '')} | {row.get('title', '')} | {row.get('site_name', '')} | {row.get('url', '')} | "
            f"{row.get('deadline', '')} | {row.get('status', '')} | safety_memo={row.get('safety_memo', '')} | "
            f"review_note={row.get('review_note', '')} | {row.get('created_at', '')} | {row.get('updated_at', '')}"
        )
    summary = summarize_later_queue(all_rows)
    print(f"total: {summary.get('total', 0)}")
    print(f"queued: {summary.get('queued', 0)}")
    print(f"needs_review: {summary.get('needs_review', 0)}")
    print(f"reviewing: {summary.get('reviewing', 0)}")
    print(f"ready_for_fill: {summary.get('ready_for_fill', 0)}")
    print(f"applied_manual: {summary.get('applied_manual', 0)}")
    print(f"skipped: {summary.get('skipped', 0)}")
    print(f"expired: {summary.get('expired', 0)}")
    return 0


def cmd_later_review(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    row = _later_find_row(args.id)
    if not row:
        print(f"later_id not found: {args.id}")
        return 1
    note_parts = ["reviewing"]
    campaign = bridge_later_queue_to_campaign(row.get("url", ""))
    if campaign:
        note_parts.append(f"matched_campaign_id={campaign.get('campaign_id', '')}")
        note_parts.append(f"form_readiness_status={campaign.get('form_readiness_status', 'unknown') or 'unknown'}")
        note_parts.append(f"next_action={campaign.get('next_action', '') or 'inspect-form / review'}")
    else:
        note_parts.append("matched_campaign_id=none")
        note_parts.append("next_action=existing form_readiness / review needed")
    updated = update_later_queue_status(
        row.get("id", ""),
        status="reviewing",
        review_note="; ".join(note_parts),
    )
    if updated:
        print(updated.get("id", ""))
        print(updated.get("status", ""))
        print(updated.get("review_note", ""))
        if campaign:
            print(campaign.get("campaign_id", ""))
            print(campaign.get("form_readiness_status", ""))
        return 0
    print(f"later_id not found: {args.id}")
    return 1


def cmd_later_prepare_fill(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    row = _later_find_row(args.id)
    if not row:
        print(f"later_id not found: {args.id}")
        return 1
    campaign = bridge_later_queue_to_campaign(row.get("url", ""))
    note_parts = ["ready_for_fill"]
    if campaign:
        note_parts.append(f"matched_campaign_id={campaign.get('campaign_id', '')}")
        note_parts.append(f"form_readiness_status={campaign.get('form_readiness_status', 'unknown') or 'unknown'}")
        if campaign.get("campaign_id", ""):
            note_parts.append(
                "bridge_command="
                f"python main.py prepare --campaign-id {campaign.get('campaign_id', '')} --browser chrome --keep-open --no-screenshot --require-user-approved"
            )
    else:
        note_parts.append("matched_campaign_id=none")
        note_parts.append("bridge_command=inspect-form / review needed")
    updated = update_later_queue_status(
        row.get("id", ""),
        status="ready_for_fill",
        review_note="; ".join(note_parts),
    )
    if updated:
        print(updated.get("id", ""))
        print(updated.get("status", ""))
        print(updated.get("review_note", ""))
        if campaign:
            print(campaign.get("campaign_id", ""))
            print(campaign.get("form_readiness_status", ""))
        return 0
    print(f"later_id not found: {args.id}")
    return 1


def cmd_later_mark_applied_manual(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    row = _later_find_row(args.id)
    if not row:
        print(f"later_id not found: {args.id}")
        return 1
    updated = update_later_queue_status(
        row.get("id", ""),
        status="applied_manual",
        review_note="manual application recorded",
    )
    if updated:
        history_record = later_queue_to_entry_history(updated)
        print(history_record.get("campaign_id", ""))
        print(updated.get("id", ""))
        print(updated.get("status", ""))
        print("entry_history_synced")
        return 0
    print(f"later_id not found: {args.id}")
    return 1


def cmd_later_skip(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    row = _later_find_row(args.id)
    if not row:
        print(f"later_id not found: {args.id}")
        return 1
    updated = update_later_queue_status(row.get("id", ""), status="skipped", review_note="user skipped")
    if updated:
        print(updated.get("id", ""))
        print(updated.get("status", ""))
        return 0
    print(f"later_id not found: {args.id}")
    return 1


def cmd_later_remove(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    removed = remove_later_queue_item(args.id)
    if not removed:
        print(f"later_id not found: {args.id}")
        return 1
    print(removed.get("id", ""))
    print("removed")
    return 0


def cmd_auto_scan(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    collect_args = argparse.Namespace(limit=args.limit)
    analyze_args = argparse.Namespace()
    resolve_args = argparse.Namespace(limit=args.limit, force=False)
    inspect_args = argparse.Namespace(limit=args.inspect_limit, campaign_id=None)
    review_args = argparse.Namespace(limit=args.review_limit)
    release_args = argparse.Namespace(version=APP_VERSION)
    cmd_collect(collect_args)
    cmd_analyze(analyze_args)
    cmd_resolve_urls(resolve_args)
    profile = load_example_profile()
    campaigns = _safe_form_campaigns(inspect_args.limit, inspect_args.campaign_id)
    if campaigns:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise SystemExit(f"playwright is required for auto-scan: {safe_exception_message(exc)}")
        FORM_INSPECTIONS_JSONL.parent.mkdir(parents=True, exist_ok=True)
        campaign_by_id = {row.get("campaign_id", ""): row for row in _campaign_rows()}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            with FORM_INSPECTIONS_JSONL.open("a", encoding="utf-8") as handle:
                for campaign in campaigns:
                    target_url = target_url_for_campaign(campaign)
                    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    record = _inspection_record(campaign, page, profile)
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    campaign.update(
                        {
                            "form_readiness_status": record["readiness_status"],
                            "form_readiness_score": str(record["readiness_score"]),
                            "form_readiness_reason": record["readiness_reason"],
                            "inspected_at": record["inspected_at"],
                        }
                    )
                    campaign_by_id[campaign.get("campaign_id", "")] = campaign
                    print(
                        f"{campaign.get('campaign_id', '')}: readiness={record['readiness_status']} "
                        f"forms={record['detected_forms_count']} fields={len(record['detected_fields'])}"
                    )
            browser.close()
    cmd_review(review_args)
    cmd_build_queue(argparse.Namespace(limit=args.limit))
    cmd_research_report(argparse.Namespace())
    cmd_release_report(release_args)
    report = build_auto_scan_report()
    md_path, json_path = save_auto_scan_report(report)
    print(md_path)
    print(json_path)
    print(f"submitted_count: {report['submitted_count']}")
    print(f"warning: {report['warning']}")
    return 0


def cmd_build_queue(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    campaigns = _campaign_rows()
    inspections = latest_inspections()
    entries = load_entries()
    existing_rows = []
    if APPLY_QUEUE_CSV.exists():
        existing_rows = read_csv_rows(APPLY_QUEUE_CSV)
    queue_rows = build_apply_queue(campaigns, inspections, entries, existing_rows, limit=args.limit)
    save_apply_queue(queue_rows)
    report = build_apply_queue_report(queue_rows)
    md_path, json_path = save_apply_queue_report(report)
    log_event("build_queue", {"count": len(queue_rows), "warning": report["warning"]})
    print(APPLY_QUEUE_CSV)
    print(md_path)
    print(json_path)
    print(f"queue_count: {len(queue_rows)}")
    print(f"submitted_count_auto: {report['submitted_count_auto']}")
    print(f"warning: {report['warning']}")
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    rows = collect_research_campaigns(keyword=args.keyword or "", category=args.category or "", limit=args.limit)
    if rows:
        save_campaigns(rows, CAMPAIGNS_CSV)
        refreshed = refresh_campaign_research_fields(CAMPAIGNS_CSV)
    else:
        refreshed = []
    log_event("research", {"count": len(rows), "keyword": args.keyword or "", "category": args.category or ""})
    print(CAMPAIGNS_CSV)
    print(f"research_count: {len(rows)}")
    print(f"refreshed: {len(refreshed)}")
    return 0


def cmd_research_report(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    refreshed = refresh_campaign_research_fields(CAMPAIGNS_CSV)
    report = build_research_report(refreshed)
    md_path, json_path = save_research_report(report)
    log_event("research_report", {"total": report["total"], "score_80_plus": report["score_bins"]["80_plus"]})
    print(md_path)
    print(json_path)
    print(f"total: {report['total']}")
    print(f"score_80_plus: {report['score_bins']['80_plus']}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    export_dir = CONFIG_DIR.parent / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    for source in (CAMPAIGNS_CSV, ENTRIES_CSV, BLOCKED_CSV, HOLDS_CSV):
        if source.exists():
            shutil.copy2(source, export_dir / source.name)
    (export_dir / "status_report.txt").write_text(redact_personal_info(status_summary()), encoding="utf-8")
    print(export_dir)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    profile_source = "profile.enc" if PROFILE_ENC.exists() else "profile.json"
    profile_store = PROFILE_ENC if PROFILE_ENC.exists() else PROFILE_JSON
    try:
        load_profile()
        profile_status = "ok"
    except Exception:
        profile_status = "missing"
    checks = [
        ("python_version", sys.version.split()[0]),
        ("platform", platform.platform()),
        ("playwright", "ok" if importlib.util.find_spec("playwright") else "missing"),
        ("profile_json", "ok" if PROFILE_JSON.exists() else "missing"),
        ("profile_enc", "ok" if PROFILE_ENC.exists() else "missing"),
        ("profile_store", profile_status),
        ("data_dir", "ok" if DATA_DIR.exists() else "missing"),
        ("screenshots_dir", "ok" if BEFORE_SUBMIT_DIR.exists() and AFTER_SUBMIT_DIR.exists() else "missing"),
    ]
    required_packages = ["requests", "bs4", "yaml", "pandas", "pydantic", "rich", "typer", "dotenv", "pytest"]
    for package in required_packages:
        checks.append((package, "ok" if importlib.util.find_spec(package) else "missing"))
    try:
        probe = DATA_DIR / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(("write_permissions", "ok"))
    except Exception:
        checks.append(("write_permissions", "missing"))
    for name, value in checks:
        print(f"{name}: {value}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="Kensho entry assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="collect campaigns from knshow")
    collect.add_argument("--limit", type=int, default=20, help="number of campaigns to collect")
    collect.set_defaults(func=cmd_collect)

    analyze = subparsers.add_parser("analyze", help="classify campaigns and save blocked rows")
    analyze.set_defaults(func=cmd_analyze)

    fill = subparsers.add_parser("fill", help="open campaigns and fill safe forms")
    fill.add_argument("--limit", type=int, default=5, help="number of campaigns to process")
    fill.add_argument("--campaign-id", help="process one campaign id")
    fill.add_argument("--force-review", action="store_true", help="allow REVIEW_ONLY campaign")
    fill.add_argument("--force", action="store_true", help="reprocess HOLD or SKIPPED campaign")
    fill.set_defaults(func=cmd_fill)

    prepare = subparsers.add_parser("prepare", help="open one campaign and prepare safe fields without submitting")
    prepare.add_argument("--campaign-id", required=True, help="prepare one campaign id")
    prepare.add_argument("--browser", choices=("chrome", "chromium"), default="chrome", help="headed browser to use")
    prepare.add_argument("--keep-open", action="store_true", help="keep browser open until user closes it")
    prepare.add_argument("--no-screenshot", action="store_true", help="disable screenshots")
    prepare.add_argument("--force-review", action="store_true", help="allow REVIEW_ONLY campaign")
    prepare.add_argument("--require-user-approved", action="store_true", help="require approved queue status before prepare")
    prepare.add_argument("--allow-age-fill", action="store_true", help="allow age / birth date fill for approved campaigns")
    prepare.add_argument(
        "--yes-known-fields",
        action="store_true",
        help="fill planned known fields without the y/n prompt; never submits",
    )
    prepare.set_defaults(func=cmd_prepare)

    auto_apply = subparsers.add_parser("auto-apply", help="run mock/dry_run/review auto apply engine")
    auto_apply.add_argument("--campaign-id", required=True, help="campaign id")
    auto_apply.add_argument("--run-mode", choices=("mock", "dry_run", "review"), default="", help="override KENSHO_RUN_MODE")
    auto_apply.add_argument("--browser", choices=("chrome", "chromium"), default="chrome", help="headed browser to use")
    auto_apply.add_argument("--keep-open", action="store_true", help="keep browser open after processing")
    auto_apply.set_defaults(func=cmd_auto_apply)

    apply_parser = subparsers.add_parser("apply", help="dry-run prepared campaigns and inspect results")
    apply_sub = apply_parser.add_subparsers(dest="apply_command", required=True)
    apply_dry_run = apply_sub.add_parser("dry-run", help="dry-run one PREPARED campaign")
    apply_dry_run.add_argument("--campaign-id", required=True, help="campaign id")
    apply_dry_run.add_argument("--browser", choices=("chrome", "chromium"), default="chromium", help="headed browser to use")
    apply_dry_run.add_argument("--keep-open", action="store_true", help="keep browser open after dry-run")
    apply_dry_run.set_defaults(func=cmd_apply)
    apply_dry_run_all = apply_sub.add_parser("dry-run-all", help="dry-run multiple prepared campaigns")
    apply_dry_run_all.add_argument("--status", default="PREPARED", help="queue_status to process")
    apply_dry_run_all.add_argument("--limit", type=int, default=12, help="max campaigns")
    apply_dry_run_all.add_argument("--browser", choices=("chrome", "chromium"), default="chromium", help="headed browser to use")
    apply_dry_run_all.set_defaults(func=cmd_apply)
    apply_show_analysis = apply_sub.add_parser("show-analysis", help="show form analysis JSON")
    apply_show_analysis.add_argument("--campaign-id", required=True, help="campaign id")
    apply_show_analysis.set_defaults(func=cmd_apply)
    apply_show_check = apply_sub.add_parser("show-check", help="show pre-submit check JSON")
    apply_show_check.add_argument("--campaign-id", required=True, help="campaign id")
    apply_show_check.set_defaults(func=cmd_apply)
    apply_mark_submitted = apply_sub.add_parser("mark-submitted", help="mark one campaign manually submitted")
    apply_mark_submitted.add_argument("--campaign-id", required=True, help="campaign id")
    apply_mark_submitted.set_defaults(func=cmd_apply)

    approve_campaign = subparsers.add_parser("approve-campaign", help="mark a campaign as approved for manual submission")
    approve_campaign.add_argument("--campaign-id", required=True, help="approve one campaign id")
    approve_campaign.add_argument("--note", default="", help="approval note")
    approve_campaign.set_defaults(func=cmd_approve_campaign)

    approved_queue = subparsers.add_parser("approved-queue", help="show approved queue entries")
    approved_queue.add_argument("--limit", type=int, default=30, help="number of approved items to show")
    approved_queue.set_defaults(func=cmd_approved_queue)

    inspect_form = subparsers.add_parser("inspect-form", help="inspect safe campaign forms without filling")
    inspect_form.add_argument("--limit", type=int, default=1, help="number of campaigns to inspect")
    inspect_form.add_argument("--campaign-id", help="inspect one campaign id")
    inspect_form.set_defaults(func=cmd_inspect_form)

    resolve_urls = subparsers.add_parser("resolve-urls", help="resolve knshow rd links to external entry URLs")
    resolve_urls.add_argument("--limit", type=int, default=20, help="number of rd links to resolve")
    resolve_urls.add_argument("--force", action="store_true", help="resolve even when resolved_entry_url exists")
    resolve_urls.set_defaults(func=cmd_resolve_urls)

    status = subparsers.add_parser("status", help="show current status summary")
    status.set_defaults(func=cmd_status)

    agent_status = subparsers.add_parser("agent-status", help="generate or inspect AI agent status")
    agent_status_sub = agent_status.add_subparsers(dest="agent_status_command", required=True)
    agent_status_generate = agent_status_sub.add_parser("generate", help="generate agent_status.json safely")
    agent_status_generate.add_argument("--output", default="", help="output json path")
    agent_status_generate.set_defaults(func=cmd_agent_status_generate)
    agent_status_run = agent_status_sub.add_parser("run", help="run safe local checks and update agent_status.json")
    agent_status_run.add_argument("--task", required=True, help="task label to record safely")
    agent_status_run.add_argument("--mode", default="normal", choices=["normal", "release"], help="agent organization mode")
    agent_status_run.add_argument("--output", default="", help="output json path")
    agent_status_run.set_defaults(func=cmd_agent_status_run)

    report = subparsers.add_parser("report", help="show a markdown report")
    report.set_defaults(func=cmd_report)

    review = subparsers.add_parser("review", help="show REVIEW_ONLY campaigns")
    review.add_argument("--limit", type=int, default=5, help="number of campaigns to show")
    review.set_defaults(func=cmd_review)

    build_queue = subparsers.add_parser("build-queue", help="build a manual review queue")
    build_queue.add_argument("--limit", type=int, default=30, help="number of campaigns to include")
    build_queue.set_defaults(func=cmd_build_queue)

    entries = subparsers.add_parser("entries", help="manage entry history")
    entries_sub = entries.add_subparsers(dest="entries_command", required=True)
    entries_list = entries_sub.add_parser("list", help="list entry history")
    entries_list.add_argument("--limit", type=int, default=100, help="number of rows to show")
    entries_list.set_defaults(func=cmd_entries_list)
    entries_search = entries_sub.add_parser("search", help="search entry history")
    entries_search.add_argument("--keyword", required=True, help="search keyword")
    entries_search.add_argument("--limit", type=int, default=100, help="number of rows to show")
    entries_search.set_defaults(func=cmd_entries_search)
    entries_add = entries_sub.add_parser("add", help="add an entry history record")
    entries_add.add_argument("--campaign-id", default="", help="campaign id")
    entries_add.add_argument("--title", default="", help="title")
    entries_add.add_argument("--source-site", default="", help="source site")
    entries_add.add_argument("--url", required=True, help="entry url")
    entries_add.add_argument("--prize", default="", help="prize")
    entries_add.add_argument("--deadline", default="", help="deadline")
    entries_add.add_argument("--applied-at", default="", help="applied timestamp")
    entries_add.add_argument("--result-check-date", default="", help="result check date")
    entries_add.add_argument("--status", default="APPLIED", help="entry status")
    entries_add.add_argument("--newsletter-status", default="unknown", choices=("unknown", "opt_in", "opt_out", "unsubscribe_needed", "unsubscribed"), help="newsletter status")
    entries_add.add_argument("--pii-used", action="store_true", help="record as pii used")
    entries_add.add_argument("--memo", default="", help="memo")
    entries_add.add_argument("--duplicate-key", default="", help="duplicate key")
    entries_add.set_defaults(func=cmd_entries_add)
    entries_mark = entries_sub.add_parser("mark-applied", help="mark a campaign as applied")
    entries_mark.add_argument("--campaign-id", required=True, help="campaign id")
    entries_mark.add_argument("--url", default="", help="entry url")
    entries_mark.add_argument("--title", default="", help="title")
    entries_mark.add_argument("--source-site", default="", help="source site")
    entries_mark.add_argument("--prize", default="", help="prize")
    entries_mark.add_argument("--deadline", default="", help="deadline")
    entries_mark.add_argument("--result-check-date", default="", help="result check date")
    entries_mark.add_argument("--newsletter-status", default="unknown", choices=("unknown", "opt_in", "opt_out", "unsubscribe_needed", "unsubscribed"), help="newsletter status")
    entries_mark.add_argument("--pii-used", action="store_true", help="record as pii used")
    entries_mark.add_argument("--memo", default="", help="memo")
    entries_mark.set_defaults(func=cmd_entries_mark_applied)
    entries_duplicates = entries_sub.add_parser("duplicates", help="show duplicate entry history groups")
    entries_duplicates.set_defaults(func=cmd_entries_duplicates)
    entries_export = entries_sub.add_parser("export-csv", help="export entry history as csv")
    entries_export.set_defaults(func=cmd_entries_export_csv)
    entries_mail = entries_sub.add_parser("win-mail-rescan", help="rescan win mail candidates")
    entries_mail.set_defaults(func=cmd_entries_win_mail_rescan)

    later = subparsers.add_parser("later", help="manage later apply queue")
    later_sub = later.add_subparsers(dest="later_command", required=True)
    later_add = later_sub.add_parser("add-url", help="add a later apply candidate by url")
    later_add.add_argument("--url", required=True, help="candidate url")
    later_add.set_defaults(func=cmd_later_add_url)
    later_list = later_sub.add_parser("list", help="list later apply queue")
    later_list.add_argument("--limit", type=int, default=30, help="number of rows to show")
    later_list.set_defaults(func=cmd_later_list)
    later_review = later_sub.add_parser("review", help="move a later apply candidate to reviewing")
    later_review.add_argument("--id", required=True, help="later queue id")
    later_review.set_defaults(func=cmd_later_review)
    later_prepare = later_sub.add_parser("prepare-fill", help="bridge a later apply candidate to existing fill prep")
    later_prepare.add_argument("--id", required=True, help="later queue id")
    later_prepare.set_defaults(func=cmd_later_prepare_fill)
    later_applied = later_sub.add_parser("mark-applied-manual", help="mark a later apply candidate as manually applied")
    later_applied.add_argument("--id", required=True, help="later queue id")
    later_applied.set_defaults(func=cmd_later_mark_applied_manual)
    later_skip = later_sub.add_parser("skip", help="skip a later apply candidate")
    later_skip.add_argument("--id", required=True, help="later queue id")
    later_skip.set_defaults(func=cmd_later_skip)
    later_remove = later_sub.add_parser("remove", help="remove a later apply candidate")
    later_remove.add_argument("--id", required=True, help="later queue id")
    later_remove.set_defaults(func=cmd_later_remove)

    research = subparsers.add_parser("research", help="collect research candidates by keyword or category")
    research.add_argument("--keyword", default="", help="research keyword")
    research.add_argument("--category", default="", help="research category")
    research.add_argument("--limit", type=int, default=30, help="number of campaigns to collect")
    research.set_defaults(func=cmd_research)

    research_report = subparsers.add_parser("research-report", help="write research report")
    research_report.set_defaults(func=cmd_research_report)

    release_report = subparsers.add_parser("release-report", help="write release report")
    release_report.add_argument("--version", default=APP_VERSION, help="release version label")
    release_report.set_defaults(func=cmd_release_report)

    auto_scan = subparsers.add_parser("auto-scan", help="run safe scan only")
    auto_scan.add_argument("--limit", type=int, default=30, help="number of campaigns to collect")
    auto_scan.add_argument("--inspect-limit", type=int, default=20, help="number of campaigns to inspect")
    auto_scan.add_argument("--review-limit", type=int, default=10, help="number of REVIEW_ONLY campaigns to show")
    auto_scan.set_defaults(func=cmd_auto_scan)

    export = subparsers.add_parser("export", help="copy current outputs to export/")
    export.set_defaults(func=cmd_export)

    doctor = subparsers.add_parser("doctor", help="check runtime readiness")
    doctor.set_defaults(func=cmd_doctor)

    browser = subparsers.add_parser("browser", help="browser commands")
    browser_sub = browser.add_subparsers(dest="browser_command", required=True)
    browser_doctor = browser_sub.add_parser("doctor", help="check Chrome preparation browser")
    browser_doctor.set_defaults(func=cmd_browser_doctor)

    profile = subparsers.add_parser("profile", help="profile commands")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    profile_check = profile_sub.add_parser("check", help="check profile store")
    profile_check.add_argument("--encrypted", action="store_true", help="check encrypted profile store")
    profile_check.set_defaults(func=cmd_profile_check)
    profile_encrypt = profile_sub.add_parser("encrypt", help="encrypt profile.json to profile.enc")
    profile_encrypt.add_argument("--delete-plain", action="store_true", help="delete profile.json after encryption")
    profile_encrypt.set_defaults(func=cmd_profile_encrypt)
    profile_decrypt = profile_sub.add_parser("decrypt", help="decrypt profile.enc to a file")
    profile_decrypt.add_argument("--output", required=True, help="output json path")
    profile_decrypt.set_defaults(func=cmd_profile_decrypt)
    profile_rotate = profile_sub.add_parser("rotate-key", help="re-encrypt profile with a new key")
    profile_rotate.add_argument("--delete-plain", action="store_true", help="delete profile.json after rotation")
    profile_rotate.set_defaults(func=cmd_profile_rotate_key)

    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_runtime_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(safe_exception_message(exc))
