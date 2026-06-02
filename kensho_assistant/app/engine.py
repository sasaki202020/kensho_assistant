from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from .apply_queue import load_apply_queue, mark_dry_run_result, mark_manual_submitted
from .auto_apply_engine import AutoApplyEngine
from .browser_manager import close_browser_safely, launch_chrome_headed
from .entry_url_resolver import target_url_for_campaign
from .paths import APPLY_QUEUE_CSV, CAMPAIGNS_CSV, FORM_ANALYSIS_DIR, PRE_SUBMIT_CHECKS_DIR
from .privacy_guard import redact_personal_info
from .profile_manager import load_profile
from .storage import read_csv_rows


def _campaign_for_id(campaign_id: str) -> dict[str, str]:
    campaigns = read_csv_rows(CAMPAIGNS_CSV)
    queue_rows = load_apply_queue(APPLY_QUEUE_CSV)
    queue_item = next((row for row in queue_rows if row.get("campaign_id") == campaign_id or row.get("queue_id") == campaign_id), {})
    campaign = next((row for row in campaigns if row.get("campaign_id") == campaign_id), {})
    merged = {**campaign, **queue_item}
    if not merged:
        raise ValueError(f"campaign_id not found: {campaign_id}")
    return merged


def run_engine(url: str, campaign_id: str, run_mode: str = "dry_run", keep_open: bool = False) -> dict[str, object]:
    campaign = _campaign_for_id(campaign_id)
    campaign["resolved_entry_url"] = url
    return _run_campaign(campaign, run_mode=run_mode, keep_open=keep_open)


def run_prepared_campaign_dry_run(campaign_id: str, browser: str = "chromium", keep_open: bool = False) -> dict[str, object]:
    campaign = _campaign_for_id(campaign_id)
    queue_status = campaign.get("queue_status", "")
    if queue_status != "PREPARED":
        raise ValueError(f"campaign is not PREPARED: {campaign_id}")
    return _run_campaign(campaign, run_mode="dry_run", browser=browser, keep_open=keep_open)


def run_prepared_campaign_pre_submit_audit(campaign_id: str, browser: str = "chromium", keep_open: bool = False) -> dict[str, object]:
    return run_prepared_campaign_dry_run(campaign_id, browser=browser, keep_open=keep_open)


def run_prepared_campaigns_dry_run_all(status: str = "PREPARED", limit: int = 12, browser: str = "chromium") -> list[dict[str, object]]:
    rows = [
        row for row in load_apply_queue(APPLY_QUEUE_CSV)
        if row.get("queue_status", "") == status and row.get("campaign_id", "")
    ][: max(limit, 0)]
    results: list[dict[str, object]] = []
    for row in rows:
        try:
            results.append(run_prepared_campaign_dry_run(row["campaign_id"], browser=browser))
        except Exception as exc:
            campaign_id = row.get("campaign_id", "")
            mark_dry_run_result(campaign_id, "SKIPPED")
            results.append({"campaign_id": campaign_id, "ok": False, "status": "SKIPPED", "message": redact_personal_info(str(exc))})
    return results


def mark_prepared_campaign_submitted(campaign_id: str) -> bool:
    return mark_manual_submitted(campaign_id)


def load_form_analysis(campaign_id: str) -> dict[str, object]:
    path = FORM_ANALYSIS_DIR / f"{campaign_id}.json"
    if not path.exists():
        return {"status": "missing", "campaign_id": campaign_id}
    return json.loads(path.read_text(encoding="utf-8"))


def load_pre_submit_check(campaign_id: str) -> dict[str, object]:
    path = PRE_SUBMIT_CHECKS_DIR / f"{campaign_id}.json"
    if not path.exists():
        return {"status": "missing", "campaign_id": campaign_id}
    return json.loads(path.read_text(encoding="utf-8"))


def load_pre_submit_audit(campaign_id: str) -> dict[str, object]:
    return load_pre_submit_check(campaign_id)


def _run_campaign(campaign: dict[str, str], run_mode: str, browser: str = "chromium", keep_open: bool = False) -> dict[str, object]:
    profile = load_profile()
    campaign_id = campaign.get("campaign_id", "")
    with sync_playwright() as playwright:
        context, _actual_browser = launch_chrome_headed(playwright, browser)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(8000)
        page.goto(target_url_for_campaign(campaign), wait_until="domcontentloaded", timeout=15000)
        try:
            result = AutoApplyEngine(run_mode).run(page, campaign, profile)
            record = result["record"]
            analysis_path = FORM_ANALYSIS_DIR / f"{campaign_id}.json"
            check_path = PRE_SUBMIT_CHECKS_DIR / f"{campaign_id}.json"
            if run_mode == "dry_run":
                mark_dry_run_result(
                    campaign_id,
                    str(record.get("status", "")),
                    needs_review_reasons=record.get("needs_review_reasons", []),
                    screenshot_path=str(record.get("screenshot_path", "")),
                    analysis_path=str(analysis_path),
                    check_path=str(check_path),
                    pre_submit_score=record.get("pre_submit_score", 0),
                    total_fields_count=record.get("total_fields_count", 0),
                    fill_completion_rate=record.get("fill_completion_rate", 0),
                    unresolved_required_fields_count=record.get("unresolved_required_fields_count", 0),
                    review_items=record.get("review_items", []),
                    submit_button_detected=record.get("submit_button_detected", False),
                    html_snapshot_path=str(record.get("html_snapshot_path", "")),
                )
            return {
                "campaign_id": campaign_id,
                "ok": True,
                "run_mode": run_mode,
                "status": record.get("status", ""),
                "filled_fields_count": record.get("filled_fields_count", 0),
                "total_fields_count": record.get("total_fields_count", 0),
                "fill_completion_rate": record.get("fill_completion_rate", 0),
                "submit_attempted": record.get("submit_attempted", False),
                "submit_clicked": record.get("submit_clicked", False),
                "auto_submitted": record.get("auto_submitted", False),
                "needs_review_reasons": record.get("needs_review_reasons", []),
                "review_items": record.get("review_items", []),
                "pre_submit_score": record.get("pre_submit_score", 0),
                "unresolved_required_fields_count": record.get("unresolved_required_fields_count", 0),
                "submit_button_detected": record.get("submit_button_detected", False),
                "screenshot_path": record.get("screenshot_path", ""),
                "html_snapshot_path": record.get("html_snapshot_path", ""),
                "analysis_path": str(analysis_path),
                "check_path": str(check_path),
            }
        finally:
            if not keep_open:
                close_browser_safely(context)
