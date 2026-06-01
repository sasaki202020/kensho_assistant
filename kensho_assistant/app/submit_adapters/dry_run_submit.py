from __future__ import annotations

import json
from pathlib import Path

from ..form_analyzer import SUBMIT_SELECTOR
from ..paths import DRY_RUN_SCREENSHOTS_DIR, DRY_RUN_SNAPSHOTS_DIR
from .base import BaseSubmitAdapter, SubmitResult


class DryRunSubmitAdapter(BaseSubmitAdapter):
    def submit(self, page, context: dict[str, object]) -> SubmitResult:
        campaign_id = str(context.get("campaign_id", "campaign"))
        DRY_RUN_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        DRY_RUN_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        screenshot_path = DRY_RUN_SCREENSHOTS_DIR / f"{campaign_id}.png"
        html_path = DRY_RUN_SNAPSHOTS_DIR / f"{campaign_id}.html"
        buttons_path = DRY_RUN_SNAPSHOTS_DIR / f"{campaign_id}_submit_candidates.json"
        page.screenshot(path=str(screenshot_path), full_page=True)
        html_path.write_text(page.content(), encoding="utf-8")
        candidates = page.locator(SUBMIT_SELECTOR).evaluate_all(
            """nodes => nodes.map((node, index) => ({
                text: (node.innerText || node.value || node.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim(),
                selector: node.id ? `#${CSS.escape(node.id)}` : `${node.tagName.toLowerCase()}:nth-of-type(${index + 1})`,
                type: (node.type || '').toLowerCase(),
                disabled: Boolean(node.disabled)
            }))"""
        )
        buttons_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return SubmitResult(
            status="DRY_RUN_COMPLETED",
            submit_attempted=False,
            submit_clicked=False,
            auto_submitted=False,
            screenshot_path=str(screenshot_path),
            html_snapshot_path=str(html_path),
            message="dry run completed without clicking submit",
        )
