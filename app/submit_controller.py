from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .form_filler import fill_campaign_page
from .models import FillResult
from .privacy_guard import redact_personal_info


def prompt_submission_summary(
    campaign: Mapping[str, str],
    risk_status: str,
    risk_reason: str,
    filled_fields: list[str],
    missing_fields: list[str],
    screenshot_before: str,
) -> str:
    lines = [
        f"campaign_name: {campaign.get('campaign_name', '')}",
        f"prize: {campaign.get('prize', '')}",
        f"winner_count: {campaign.get('winner_count', '')}",
        f"provider: {campaign.get('provider', '')}",
        f"deadline: {campaign.get('deadline', '')}",
        f"entry_url: {campaign.get('resolved_entry_url', '') or campaign.get('entry_url', '')}",
        f"risk_status: {risk_status}",
        f"risk_reason: {risk_reason}",
        f"filled_fields: {', '.join(filled_fields) if filled_fields else 'none'}",
        f"missing_fields: {', '.join(missing_fields) if missing_fields else 'none'}",
        f"screenshot_before: {screenshot_before}",
        "送信直前の確認です。実送信はしません。",
    ]
    return redact_personal_info("\n".join(lines))


def approve_and_submit(
    page,
    campaign: Mapping[str, str],
    profile: Mapping[str, str],
    risk_status: str,
    risk_reason: str,
    screenshot_dir: Path | None = None,
    save_screenshot: bool = True,
) -> FillResult | None:
    result = fill_campaign_page(page, campaign, profile, screenshot_dir=screenshot_dir, save_screenshot=save_screenshot)
    if result.decision != "fill":
        return result
    summary = prompt_submission_summary(
        campaign,
        risk_status,
        risk_reason,
        result.filled_fields,
        result.missing_fields,
        result.screenshot_before,
    )
    print(summary)
    result.submitted = False
    result.decision = "pre_submit_ready"
    return result
