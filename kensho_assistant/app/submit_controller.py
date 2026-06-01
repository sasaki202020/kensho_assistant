from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .form_filler import fill_campaign_page
from .models import FillResult
from .paths import AFTER_SUBMIT_DIR
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
        "この応募を送信しますか？送信後は取り消せません。submit と入力した場合のみ送信。",
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
    choice = input("submit/hold/open/quit > ").strip().lower()
    if choice == "quit":
        raise SystemExit(0)
    if choice == "hold":
        result.decision = "hold"
        return result
    if choice == "open":
        print("browser is open; continue manually and rerun when ready")
        result.decision = "open"
        return result
    if choice != "submit":
        result.decision = "skip"
        return result
    consent_required = bool(result.consent_fields)
    if consent_required:
        print("consent checkbox must be checked manually before submit; submission stopped")
        result.decision = "hold"
        return result
    confirm = input("submit > ").strip().lower()
    if confirm != "submit":
        result.decision = "skip"
        return result
    submit_buttons = page.locator('button[type="submit"], input[type="submit"]')
    if submit_buttons.count() == 0:
        print("submit button not found; stopping before submission")
        return result
    submit_buttons.first.click()
    after_dir = AFTER_SUBMIT_DIR
    after_dir.mkdir(parents=True, exist_ok=True)
    after_path = after_dir / f"{campaign.get('campaign_id', 'campaign')}.png"
    page.screenshot(path=str(after_path), full_page=True)
    result.screenshot_after = str(after_path)
    result.submitted = True
    result.decision = "submit"
    return result
