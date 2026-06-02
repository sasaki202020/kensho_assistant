from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from ..form_analyzer import SUBMIT_SELECTOR
from ..paths import ALLOWED_SUBMIT_DOMAINS_JSON
from .base import BaseSubmitAdapter, SubmitResult


class MockSubmitAdapter(BaseSubmitAdapter):
    def __init__(self, allowed_domains_path: str | Path | None = None) -> None:
        self.allowed_domains_path = Path(allowed_domains_path) if allowed_domains_path else ALLOWED_SUBMIT_DOMAINS_JSON

    def submit(self, page, context: dict[str, object]) -> SubmitResult:
        if not self._is_allowed(page.url):
            raise RuntimeError(f"mock submit blocked for non-allowed url: {page.url}")
        check = context.get("pre_submit_check")
        if isinstance(check, dict) and check.get("status") != "PRE_SUBMIT_READY":
            return SubmitResult(status=str(check.get("status", "NEEDS_REVIEW")), message="pre-submit check blocked mock submit")
        button = page.locator('button[type="submit"], input[type="submit"]').first
        if button.count() == 0:
            button = page.locator(SUBMIT_SELECTOR).first
        if button.count() == 0:
            return SubmitResult(status="NEEDS_REVIEW", message="submit button not found")
        button.click()
        return SubmitResult(status="MOCK_SUBMITTED", submit_attempted=True, submit_clicked=True, auto_submitted=True)

    def _is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme == "file":
            try:
                return "tests/mock_forms" in Path(parsed.path).as_posix()
            except Exception:
                return False
        allowed = self._allowed_domains()
        return parsed.hostname in allowed

    def _allowed_domains(self) -> set[str]:
        if not self.allowed_domains_path.exists():
            return {"localhost", "127.0.0.1"}
        data = json.loads(self.allowed_domains_path.read_text(encoding="utf-8"))
        return {str(item).strip().lower() for item in data if str(item).strip()}
