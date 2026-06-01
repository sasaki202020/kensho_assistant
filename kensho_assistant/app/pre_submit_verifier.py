from __future__ import annotations

import json
from pathlib import Path

from .form_analyzer import SUBMIT_SELECTOR
from .models import DetectedField
from .paths import PRE_SUBMIT_CHECKS_DIR


CAPTCHA_TERMS = ["captcha", "recaptcha", "hcaptcha", "私はロボットではありません", "認証"]
LOGIN_TERMS = ["ログイン", "会員登録", "sign in", "login"]
SNS_TERMS = ["xで", "twitter", "instagram", "line", "フォロー", "リポスト", "いいね"]
QUIZ_TERMS = ["クイズ", "問題", "正解", "回答"]
CONFIRM_TERMS = ["確認", "confirm"]


class PreSubmitVerifier:
    def verify(self, page, campaign_id: str, fields: list[DetectedField]) -> dict[str, object]:
        required_unfilled = [field.field_name for field in fields if field.required and not field.will_fill]
        required_checkbox_unchecked = page.locator('input[type="checkbox"][required]:not(:checked)').count()
        required_radio_groups = page.locator('input[type="radio"][required]').evaluate_all(
            """nodes => Array.from(new Set(nodes.map(node => node.name || node.id || 'radio')))"""
        )
        unchecked_radio_groups = []
        for group in required_radio_groups:
            checked = page.locator(f'input[type="radio"][name="{group}"]:checked').count() if group else 0
            if not checked:
                unchecked_radio_groups.append(group)
        body_text = page.locator("body").inner_text(timeout=5000) if page.locator("body").count() else ""
        submit_candidates = page.locator(SUBMIT_SELECTOR).evaluate_all(
            """nodes => nodes.map((node, index) => ({
                text: (node.innerText || node.value || node.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim(),
                type: (node.type || '').toLowerCase(),
                selector: node.id ? `#${CSS.escape(node.id)}` : `${node.tagName.toLowerCase()}:nth-of-type(${index + 1})`,
                disabled: Boolean(node.disabled)
            }))"""
        )
        reasons: list[str] = []
        danger: list[str] = []
        if required_unfilled:
            reasons.append("required_unfilled")
        if required_checkbox_unchecked:
            reasons.append("required_checkbox_unchecked")
        if unchecked_radio_groups:
            reasons.append("required_radio_unselected")
        if self._contains(body_text, QUIZ_TERMS):
            reasons.append("quiz_like_field")
        if self._contains(body_text, CAPTCHA_TERMS) or page.locator('[class*="captcha" i], [id*="captcha" i], iframe[src*="captcha" i]').count():
            danger.append("captcha_like_element")
        if self._contains(body_text, LOGIN_TERMS):
            danger.append("login_required")
        if self._contains(body_text, SNS_TERMS):
            danger.append("sns_condition")
        if any(self._contains(str(candidate.get("text", "")), CONFIRM_TERMS) for candidate in submit_candidates):
            reasons.append("confirmation_button_candidate")
        if danger:
            status = "SKIPPED"
        elif reasons:
            status = "NEEDS_REVIEW"
        else:
            status = "DRY_RUN_COMPLETED"
        result = {
            "campaign_id": campaign_id,
            "url": page.url,
            "status": status,
            "required_unfilled": required_unfilled,
            "required_checkbox_unchecked": required_checkbox_unchecked,
            "required_radio_unselected": unchecked_radio_groups,
            "needs_review_reasons": reasons,
            "danger_reasons": danger,
            "submit_button_candidates": submit_candidates,
        }
        self.save(campaign_id, result)
        return result

    def save(self, campaign_id: str, result: dict[str, object]) -> Path:
        PRE_SUBMIT_CHECKS_DIR.mkdir(parents=True, exist_ok=True)
        path = PRE_SUBMIT_CHECKS_DIR / f"{campaign_id}.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _contains(text: str, terms: list[str]) -> bool:
        lowered = (text or "").casefold()
        return any(term.casefold() in lowered for term in terms)
