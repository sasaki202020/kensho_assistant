from __future__ import annotations

import json
from pathlib import Path

from .form_analyzer import SUBMIT_SELECTOR
from .form_detector import extract_quiz_items
from .form_filler import DEFAULT_OPINION_TEXT
from .models import DetectedField
from .paths import PRE_SUBMIT_CHECKS_DIR


CAPTCHA_TERMS = ["captcha", "recaptcha", "hcaptcha", "私はロボットではありません", "認証"]
LOGIN_TERMS = ["ログイン", "会員登録", "sign in", "login", "ログインしてください"]
SNS_TERMS = ["xで", "twitter", "instagram", "フォロー", "リポスト", "いいね", "シェア", "x投稿"]
LINE_TERMS = ["line", "友だち追加", "友達追加", "line登録"]
QUIZ_TERMS = ["クイズ", "問題", "正解", "回答", "お答えください", "次のうち", "どれでしょうか"]
CONSENT_TERMS = ["同意", "利用規約", "応募規約", "プライバシーポリシー", "規約に同意"]
AGE_TERMS = ["年齢", "年齢確認", "年代", "生年月日"]
NEWSLETTER_TERMS = ["メルマガ", "newsletter", "メール配信", "登録"]
FREE_TEXT_TERMS = ["自由記述", "御意見", "ご意見", "御感想", "ご感想", "メッセージ", "コメント", "感想"]
ENDED_TERMS = ["募集終了", "受付終了", "終了しました", "応募終了", "締め切りました", "キャンペーンは終了"]

MANUAL_CHECK_FIELD_NAMES = {
    "consent",
    "age",
    "quiz_answer",
    "newsletter",
    "dm_opt_in",
    "free_text",
    "opinion",
}
HUMAN_CONFIRMATION_REASONS = {
    "consent": "同意チェック",
    "age": "年齢確認",
    "quiz_answer": "クイズ回答",
    "newsletter": "メルマガ登録",
    "dm_opt_in": "DM希望",
    "free_text": "自由記述",
    "opinion": "自由記述",
}


class PreSubmitVerifier:
    def verify(self, page, campaign_id: str, fields: list[DetectedField]) -> dict[str, object]:
        try:
            body_text = page.locator("body").inner_text(timeout=5000) if page.locator("body").count() else ""
        except Exception:
            body_text = ""
        submit_candidates = self._submit_candidates(page)
        submit_button_detected = bool(submit_candidates)

        required_unfilled = [field.field_name for field in fields if field.required and not field.will_fill]
        required_checkbox_unchecked = page.locator('input[type="checkbox"][required]:not(:checked)').count()
        required_radio_groups = page.locator('input[type="radio"][required]').evaluate_all(
            """nodes => Array.from(new Set(nodes.map(node => node.name || node.id || 'radio')))"""
        )
        unchecked_radio_groups: list[str] = []
        for group in required_radio_groups:
            checked = page.locator(f'input[type="radio"][name="{group}"]:checked').count() if group else 0
            if not checked:
                unchecked_radio_groups.append(group)

        hard_reasons: list[str] = []
        manual_assist_reasons: list[str] = []
        review_reasons: list[str] = []
        review_items: list[dict[str, object]] = []

        total_fields_count = len(fields)
        filled_fields_count = sum(1 for field in fields if field.will_fill)
        fill_completion_rate = round((filled_fields_count / total_fields_count * 100.0), 2) if total_fields_count else 0.0
        unresolved_required_fields = self._unique_nonempty(
            required_unfilled + [str(group) for group in unchecked_radio_groups] + self._checkbox_required_names(page)
        )

        if not fields:
            hard_reasons.append("no_form")
            review_items.append(self._item("form", "フォームなし", "入力欄が見つかりませんでした", required=False))

        if self._contains(body_text, CAPTCHA_TERMS) or page.locator('[class*="captcha" i], [id*="captcha" i], iframe[src*="captcha" i]').count():
            hard_reasons.append("captcha_detected")
        if self._contains(body_text, ENDED_TERMS):
            hard_reasons.append("campaign_ended")

        if self._contains(body_text, LOGIN_TERMS) or page.locator('input[type="password"], [href*="login" i], [href*="signin" i]').count():
            manual_assist_reasons.append("login_required")
        if self._contains(body_text, SNS_TERMS):
            manual_assist_reasons.append("sns_condition")
        if self._contains(body_text, LINE_TERMS):
            manual_assist_reasons.append("line_condition")

        if required_unfilled:
            review_reasons.append("required_unfilled")
            for name in self._unique_nonempty(required_unfilled):
                review_items.append(self._field_item(fields, name, "required field is not auto-filled"))
        if required_checkbox_unchecked:
            review_reasons.append("required_checkbox_unchecked")
            review_items.append(self._item("checkbox", "同意チェック", "required checkbox is not checked", required=True))
        if unchecked_radio_groups:
            review_reasons.append("required_radio_unselected")
            for group in unchecked_radio_groups:
                review_items.append(self._item("radio", group, "required radio group is not selected", required=True))

        quiz_items = extract_quiz_items(page, limit=5)
        has_quiz = self._contains(body_text, QUIZ_TERMS) or bool(quiz_items) or any(field.field_name == "quiz_answer" for field in fields)
        if has_quiz:
            review_reasons.append("quiz_detected")
            for item in quiz_items:
                review_items.append(
                    {
                        "kind": "quiz",
                        "field_name": "quiz_answer",
                        "question_text": item.get("question_text", ""),
                        "candidate_answers": list(item.get("choices", [])),
                        "answer_field_selector": item.get("answer_field_selector", ""),
                        "required": bool(item.get("required", False)),
                        "reason": "quiz answer requires human confirmation",
                    }
                )
            if not quiz_items:
                review_items.append(self._item("quiz_answer", "クイズ", "quiz answer requires human confirmation", required=False))

        if self._contains(body_text, CONSENT_TERMS):
            review_reasons.append("consent_required")
            review_items.append(self._item("consent", "同意", "human confirmation required", required=True))
        if self._contains(body_text, AGE_TERMS) or any(field.field_name == "age" for field in fields):
            review_reasons.append("age_confirmation")
            review_items.append(self._item("age", "年齢確認", "human confirmation required", required=False))
        if self._contains(body_text, NEWSLETTER_TERMS):
            review_reasons.append("newsletter_opt_in")
            review_items.append(self._item("newsletter", "メルマガ", "human confirmation required", required=False))
        if self._contains(body_text, FREE_TEXT_TERMS):
            review_reasons.append("free_text_present")
            review_items.append(
                {
                    "kind": "free_text",
                    "field_name": "free_text",
                    "label": "自由記述",
                    "candidate_text": DEFAULT_OPINION_TEXT,
                    "required": False,
                    "reason": "free text requires human review",
                }
            )

        for field in fields:
            if field.field_name in {"free_text", "opinion"}:
                review_reasons.append("free_text_present")
            if field.field_name in {"free_text", "opinion"} and field.will_fill:
                review_items.append(
                    {
                        "kind": "free_text",
                        "field_name": field.field_name,
                        "label": field.label,
                        "selector": field.selector,
                        "candidate_text": field.value_preview or DEFAULT_OPINION_TEXT,
                        "required": field.required,
                        "reason": "candidate text should be human confirmed",
                    }
                )
            if field.field_name == "quiz_answer":
                review_reasons.append("quiz_detected")
                review_items.append(
                    {
                        "kind": "quiz",
                        "field_name": "quiz_answer",
                        "label": field.label,
                        "selector": field.selector,
                        "required": field.required,
                        "reason": field.skip_reason or field.reason or "quiz answer requires human confirmation",
                    }
                )
            if field.field_name in {"consent", "age", "newsletter", "dm_opt_in"}:
                review_reasons.append(f"{field.field_name}_present")
                review_items.append(
                    {
                        "kind": "checklist",
                        "field_name": field.field_name,
                        "label": field.label,
                        "selector": field.selector,
                        "required": field.required,
                        "reason": HUMAN_CONFIRMATION_REASONS.get(field.field_name, "human confirmation required"),
                    }
                )

        if not submit_button_detected:
            review_reasons.append("submit_button_not_detected")
        if any(self._contains(str(candidate.get("text", "")), ["確認"]) for candidate in submit_candidates):
            review_reasons.append("confirm_button_candidate")

        score = 100
        if hard_reasons:
            score = 0
        else:
            penalties = 0
            if manual_assist_reasons:
                penalties += 40 * len(manual_assist_reasons)
            if self._contains(body_text, QUIZ_TERMS) or any(field.field_name == "quiz_answer" for field in fields):
                penalties += 10
            if self._contains(body_text, CONSENT_TERMS):
                penalties += 5
            if self._contains(body_text, AGE_TERMS) or any(field.field_name == "age" for field in fields):
                penalties += 5
            if self._contains(body_text, NEWSLETTER_TERMS):
                penalties += 5
            if self._contains(body_text, FREE_TEXT_TERMS):
                penalties += 10
            if unresolved_required_fields:
                penalties += 10 * len(unresolved_required_fields)
            if not submit_button_detected:
                penalties += 20
            score = max(0, min(100, 100 - penalties))

        if hard_reasons:
            status = "SKIPPED"
        elif manual_assist_reasons:
            status = "MANUAL_ASSIST_READY"
        elif review_reasons:
            status = "REVIEW_FILL_READY" if score >= 60 else "MANUAL_ASSIST_READY"
        else:
            if score >= 90:
                status = "PRE_SUBMIT_READY"
            elif score >= 60:
                status = "REVIEW_FILL_READY"
            elif score >= 30:
                status = "MANUAL_ASSIST_READY"
            else:
                status = "SKIPPED"

        needs_review_reasons = self._unique_nonempty(
            hard_reasons + manual_assist_reasons + review_reasons + (["submit_button_not_detected"] if not submit_button_detected else [])
        )

        result = {
            "campaign_id": campaign_id,
            "url": page.url,
            "status": status,
            "pre_submit_score": score,
            "total_fields_count": total_fields_count,
            "filled_fields_count": filled_fields_count,
            "fill_completion_rate": fill_completion_rate,
            "unresolved_required_fields_count": len(unresolved_required_fields),
            "unresolved_required_fields": unresolved_required_fields,
            "required_unfilled": required_unfilled,
            "required_checkbox_unchecked": required_checkbox_unchecked,
            "required_radio_unselected": unchecked_radio_groups,
            "submit_button_detected": submit_button_detected,
            "needs_review_reasons": needs_review_reasons,
            "review_reasons": review_reasons,
            "manual_assist_reasons": manual_assist_reasons,
            "danger_reasons": hard_reasons,
            "review_items": review_items,
            "submit_button_candidates": submit_candidates,
            "html_snapshot_path": "",
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

    @staticmethod
    def _unique_nonempty(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            item = str(value).strip()
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    @staticmethod
    def _submit_candidates(page) -> list[dict[str, object]]:
        try:
            return page.locator(SUBMIT_SELECTOR).evaluate_all(
                """nodes => nodes.map((node, index) => ({
                    text: (node.innerText || node.value || node.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim(),
                    type: (node.type || '').toLowerCase(),
                    selector: node.id ? `#${CSS.escape(node.id)}` : (node.name ? `${node.tagName.toLowerCase()}[name="${CSS.escape(node.name)}"]` : `${node.tagName.toLowerCase()}:nth-of-type(${index + 1})`),
                    disabled: Boolean(node.disabled)
                }))"""
            )
        except Exception:
            return []

    @staticmethod
    def _checkbox_required_names(page) -> list[str]:
        try:
            return page.locator('input[type="checkbox"][required]').evaluate_all(
                """nodes => Array.from(new Set(nodes.map(node => node.name || node.id || 'checkbox')))"""
            )
        except Exception:
            return []

    @staticmethod
    def _item(kind: str, field_name: str, reason: str, required: bool = False) -> dict[str, object]:
        return {
            "kind": kind,
            "field_name": field_name,
            "label": field_name,
            "required": required,
            "reason": reason,
        }

    @staticmethod
    def _field_item(fields: list[DetectedField], field_name: str, reason: str) -> dict[str, object]:
        field = next((item for item in fields if item.field_name == field_name), None)
        if not field:
            return PreSubmitVerifier._item("field", field_name, reason, required=False)
        return {
            "kind": "field",
            "field_name": field.field_name,
            "label": field.label,
            "selector": field.selector,
            "required": field.required,
            "will_fill": field.will_fill,
            "reason": reason,
        }
