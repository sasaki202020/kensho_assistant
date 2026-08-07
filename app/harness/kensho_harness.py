from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from kensho_assistant.app.apply_queue import mark_dry_run_result
from kensho_assistant.app.engine import load_form_analysis, load_pre_submit_check, run_engine
from kensho_assistant.app.entry_url_resolver import target_url_for_campaign
from kensho_assistant.app.later_queue import bridge_later_queue_to_campaign, list_later_queue
from kensho_assistant.app.paths import APPLY_QUEUE_CSV, CAMPAIGNS_CSV, RESEARCH_KENSHO_HARNESS_DIR
from kensho_assistant.app.privacy_guard import redact_personal_info
from kensho_assistant.app.storage import read_csv_rows

from .run_store import build_output_dir, timestamp, write_json
from .task_models import HarnessRunResult


VALID_MODES: set[str] = {"dry_run", "review"}


def _campaign_rows() -> list[dict[str, str]]:
    campaigns = read_csv_rows(CAMPAIGNS_CSV)
    queue_rows = read_csv_rows(APPLY_QUEUE_CSV)
    queue_by_id = {row.get("campaign_id", ""): row for row in queue_rows if row.get("campaign_id", "")}
    merged_rows: list[dict[str, str]] = []
    for campaign in campaigns:
        queue_item = queue_by_id.get(campaign.get("campaign_id", ""), {})
        merged_rows.append({**campaign, **queue_item})
    return merged_rows


def _campaign_for_id(campaign_id: str) -> dict[str, str]:
    if not campaign_id:
        return {}
    for row in _campaign_rows():
        if row.get("campaign_id", "") == campaign_id:
            return row
    return {}


def _later_row(later_id: str) -> dict[str, str]:
    target = (later_id or "").strip()
    if not target:
        return {}
    for row in list_later_queue():
        if row.get("id", "") == target:
            return row
    return {}


def _campaign_from_later_row(later_row: Mapping[str, str]) -> dict[str, str]:
    later_id = (later_row.get("id", "") or "").strip()
    url = (later_row.get("url", "") or "").strip()
    if not later_id or not url:
        return {}
    return {
        "campaign_id": later_id,
        "campaign_name": later_row.get("title", "") or "unknown",
        "provider": later_row.get("site_name", "") or "unknown",
        "deadline": later_row.get("deadline", "") or "unknown",
        "resolved_entry_url": url,
        "entry_url": url,
        "queue_status": "",
        "form_readiness_status": "NEEDS_REVIEW",
        "source": "later_queue",
    }


def _build_plan(
    *,
    campaign_id: str,
    mode: str,
    source: str,
    campaign: Mapping[str, str],
    later_row: Mapping[str, str] | None = None,
) -> dict[str, object]:
    plan = {
        "campaign_id": campaign_id,
        "mode": mode,
        "source": source,
        "title": campaign.get("campaign_name", ""),
        "provider": campaign.get("provider", ""),
        "queue_status": campaign.get("queue_status", ""),
        "readiness_status": campaign.get("form_readiness_status", ""),
        "resolved_entry_url": campaign.get("resolved_entry_url", "") or campaign.get("entry_url", ""),
        "steps": [
            "load_campaign",
            "run_safe_input_fill",
            "save_form_analysis",
            "save_pre_submit_check",
            "write_apply_run_report",
        ],
        "prohibited_actions": [
            "submit",
            "confirm",
            "complete",
            "auto_submit",
            "captcha_bypass",
            "login_bypass",
            "sns_action",
        ],
        "safety_notes": [
            "送信ボタンはクリックしない",
            "CAPTCHA 回避はしない",
            "個人情報はログに出さない",
        ],
    }
    if later_row:
        plan["later_bridge"] = {
            "later_id": later_row.get("id", ""),
            "later_status": later_row.get("status", ""),
            "later_site_name": later_row.get("site_name", ""),
            "later_review_note": later_row.get("review_note", ""),
        }
    return plan


def _write_failure(
    *,
    output_dir: Path,
    plan: dict[str, object],
    campaign_id: str,
    source: str,
    mode: str,
    reason: str,
    later_row: Mapping[str, str] | None = None,
) -> HarnessRunResult:
    report = {
        "status": "failed",
        "campaign_id": campaign_id,
        "source": source,
        "mode": mode,
        "reason": redact_personal_info(reason),
        "submitted_count_auto": 0,
        "submit_attempted": False,
        "submit_clicked": False,
        "auto_submitted": False,
        "later_bridge": {
            "later_id": later_row.get("id", "") if later_row else "",
            "later_status": later_row.get("status", "") if later_row else "",
        },
        "files": ["run_plan.json", "run_report.json"],
        "created_at": timestamp(),
    }
    files = {
        "run_plan": str(write_json(output_dir / "run_plan.json", plan)),
        "run_report": str(write_json(output_dir / "run_report.json", report)),
    }
    return HarnessRunResult(output_dir=str(output_dir), files=files, status="failed")


def write_harness_timeout(
    *,
    campaign_id: str = "",
    later_id: str = "",
    mode: str = "dry_run",
    timeout_sec: int = 60,
    output_root: Path | None = None,
) -> HarnessRunResult:
    """Persist a safe terminal record after an isolated browser worker times out."""
    campaign_id = (campaign_id or "").strip()
    later_id = (later_id or "").strip()
    source = "later" if later_id else "prepared"
    later_row = _later_row(later_id) if later_id else {}
    campaign = _campaign_for_id(campaign_id) if campaign_id else {}
    if later_row and not campaign:
        campaign = _campaign_from_later_row(later_row)
    effective_id = campaign_id or later_id or "unknown"
    output_dir = build_output_dir(
        f"kensho-harness-{effective_id}-{source}-{mode}",
        output_root=output_root,
        base_dir=RESEARCH_KENSHO_HARNESS_DIR,
    )
    plan = _build_plan(
        campaign_id=effective_id,
        mode=mode,
        source=source,
        campaign=campaign,
        later_row=later_row,
    )
    target_url = (
        campaign.get("resolved_entry_url", "")
        or campaign.get("entry_url", "")
        or later_row.get("url", "")
    )
    report = {
        "status": "TIMEOUT",
        "campaign_id": effective_id,
        "source": source,
        "mode": mode,
        "reason": "timeout",
        "timeout_sec": max(0, int(timeout_sec)),
        "url": target_url,
        "final_url": target_url,
        "submitted_count_auto": 0,
        "submit_attempted": False,
        "submit_clicked": False,
        "auto_submitted": False,
        "later_bridge": {
            "later_id": later_row.get("id", ""),
            "later_status": later_row.get("status", ""),
        },
        "files": ["run_plan.json", "run_report.json"],
        "created_at": timestamp(),
        "safety": {
            "no_submit": True,
            "no_auto_submit": True,
            "process_tree_terminated": True,
        },
    }
    files = {
        "run_plan": str(write_json(output_dir / "run_plan.json", plan)),
        "run_report": str(write_json(output_dir / "run_report.json", report)),
    }
    return HarnessRunResult(output_dir=str(output_dir), files=files, status="TIMEOUT")


def run_kensho_harness(
    *,
    campaign_id: str = "",
    later_id: str = "",
    mode: str = "dry_run",
    keep_open: bool = False,
    output_root: Path | None = None,
) -> HarnessRunResult:
    mode = (mode or "dry_run").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"unsupported mode: {mode}")
    campaign_id = (campaign_id or "").strip()
    later_id = (later_id or "").strip()
    if not campaign_id and not later_id:
        raise ValueError("campaign_id or later_id is required")

    source = "prepared"
    later_row: dict[str, str] = {}
    synthetic_campaign: dict[str, str] = {}
    if later_id:
        source = "later"
        later_row = _later_row(later_id)
        if not later_row:
            output_dir = build_output_dir(
                f"kensho-harness-{later_id or 'later'}-{mode}",
                output_root=output_root,
                base_dir=RESEARCH_KENSHO_HARNESS_DIR,
            )
            plan = _build_plan(campaign_id=campaign_id or later_id, mode=mode, source=source, campaign={}, later_row={})
            return _write_failure(
                output_dir=output_dir,
                plan=plan,
                campaign_id=campaign_id or later_id,
                source=source,
                mode=mode,
                reason=f"later_id not found: {later_id}",
            )
        bridged_campaign = bridge_later_queue_to_campaign(later_row.get("url", ""))
        if not bridged_campaign or not (bridged_campaign.get("campaign_id", "") or "").strip():
            bridged_campaign = _campaign_from_later_row(later_row)
            synthetic_campaign = bridged_campaign
        if not bridged_campaign:
            raise ValueError(f"later queue URL is missing: {later_id}")
        if campaign_id and campaign_id != bridged_campaign.get("campaign_id", ""):
            raise ValueError("campaign_id and later_id refer to different campaigns")
        campaign_id = bridged_campaign.get("campaign_id", "")

    campaign = synthetic_campaign or _campaign_for_id(campaign_id)
    if not campaign:
        output_dir = build_output_dir(
            f"kensho-harness-{campaign_id or later_id or 'unknown'}-{mode}",
            output_root=output_root,
            base_dir=RESEARCH_KENSHO_HARNESS_DIR,
        )
        plan = _build_plan(campaign_id=campaign_id or later_id or "unknown", mode=mode, source=source, campaign={}, later_row=later_row)
        return _write_failure(
            output_dir=output_dir,
            plan=plan,
            campaign_id=campaign_id or later_id or "unknown",
            source=source,
            mode=mode,
            reason=f"campaign_id not found: {campaign_id or later_id}",
            later_row=later_row,
        )

    if source == "prepared" and campaign.get("queue_status", "") != "PREPARED":
        output_dir = build_output_dir(
            f"kensho-harness-{campaign_id}-{mode}",
            output_root=output_root,
            base_dir=RESEARCH_KENSHO_HARNESS_DIR,
        )
        plan = _build_plan(campaign_id=campaign_id, mode=mode, source=source, campaign=campaign, later_row=later_row)
        return _write_failure(
            output_dir=output_dir,
            plan=plan,
            campaign_id=campaign_id,
            source=source,
            mode=mode,
            reason=f"campaign is not PREPARED: {campaign_id}",
            later_row=later_row,
        )

    output_dir = build_output_dir(
        f"kensho-harness-{campaign_id}-{source}-{mode}",
        output_root=output_root,
        base_dir=RESEARCH_KENSHO_HARNESS_DIR,
    )
    plan = _build_plan(campaign_id=campaign_id, mode=mode, source=source, campaign=campaign, later_row=later_row)
    write_json(output_dir / "run_plan.json", plan)
    write_json(output_dir / "campaign.json", campaign)
    if later_row:
        write_json(output_dir / "later_bridge.json", later_row)

    target_url = target_url_for_campaign(campaign)
    try:
        engine_kwargs = {"campaign": synthetic_campaign} if synthetic_campaign else {}
        result = run_engine(target_url, campaign_id, run_mode=mode, keep_open=keep_open, **engine_kwargs)
    except Exception as exc:
        return _write_failure(
            output_dir=output_dir,
            plan=plan,
            campaign_id=campaign_id,
            source=source,
            mode=mode,
            reason=str(exc),
            later_row=later_row,
        )

    analysis = load_form_analysis(campaign_id)
    pre_submit_check = load_pre_submit_check(campaign_id)
    if source == "prepared":
        mark_dry_run_result(
            campaign_id,
            str(result.get("status", "")),
            needs_review_reasons=result.get("needs_review_reasons", []),
            screenshot_path=str(result.get("screenshot_path", "")),
            analysis_path=str(result.get("analysis_path", "")),
            check_path=str(result.get("check_path", "")),
            pre_submit_score=result.get("pre_submit_score", 0),
            total_fields_count=result.get("total_fields_count", 0),
            fill_completion_rate=result.get("fill_completion_rate", 0),
            unresolved_required_fields_count=result.get("unresolved_required_fields_count", 0),
            review_items=result.get("review_items", []),
            submit_button_detected=result.get("submit_button_detected", False),
            html_snapshot_path=str(result.get("html_snapshot_path", "")),
        )

    write_json(output_dir / "dry_run_result.json", result)
    write_json(output_dir / "form_analysis.json", analysis)
    write_json(output_dir / "pre_submit_check.json", pre_submit_check)

    report = {
        "status": "success" if result.get("ok", True) else "failed",
        "campaign_id": campaign_id,
        "title": campaign.get("campaign_name", ""),
        "url": target_url,
        "source": source,
        "mode": mode,
        "queue_status": campaign.get("queue_status", ""),
        "readiness_status": campaign.get("form_readiness_status", ""),
        "submitted_count_auto": 0,
        "submit_attempted": False,
        "submit_clicked": False,
        "auto_submitted": False,
        "filled_fields_count": result.get("filled_fields_count", 0),
        "total_fields_count": result.get("total_fields_count", 0),
        "fill_completion_rate": result.get("fill_completion_rate", 0),
        "pre_submit_score": result.get("pre_submit_score", 0),
        "unresolved_required_fields_count": result.get("unresolved_required_fields_count", 0),
        "needs_review_reasons": result.get("needs_review_reasons", []),
        "review_items": result.get("review_items", []),
        "submit_button_detected": result.get("submit_button_detected", False),
        "profile_readiness": result.get("profile_readiness", {}),
        "analysis_path": str(output_dir / "form_analysis.json"),
        "check_path": str(output_dir / "pre_submit_check.json"),
        "dry_run_result_path": str(output_dir / "dry_run_result.json"),
        "later_bridge": {
            "later_id": later_row.get("id", "") if later_row else "",
            "later_status": later_row.get("status", "") if later_row else "",
            "later_review_note": later_row.get("review_note", "") if later_row else "",
        },
        "created_at": timestamp(),
        "files": [
            "run_plan.json",
            "campaign.json",
            "dry_run_result.json",
            "form_analysis.json",
            "pre_submit_check.json",
            "run_report.json",
        ]
        + (["later_bridge.json"] if later_row else []),
        "safety": {
            "no_submit": True,
            "no_auto_submit": True,
            "no_personal_info_logged": True,
            "later_queue_connected": bool(later_row),
        },
    }
    write_json(output_dir / "run_report.json", report)
    files = {
        "run_plan": str(output_dir / "run_plan.json"),
        "campaign": str(output_dir / "campaign.json"),
        "dry_run_result": str(output_dir / "dry_run_result.json"),
        "form_analysis": str(output_dir / "form_analysis.json"),
        "pre_submit_check": str(output_dir / "pre_submit_check.json"),
        "run_report": str(output_dir / "run_report.json"),
    }
    if later_row:
        files["later_bridge"] = str(output_dir / "later_bridge.json")
    return HarnessRunResult(output_dir=str(output_dir), files=files, status=str(report["status"]))
