from __future__ import annotations

import json
from pathlib import Path

from .form_analyzer import SUBMIT_SELECTOR
from .form_detector import extract_quiz_items
from .answer_assistant import build_answer_pack
from .models import DetectedField
from .paths import PRE_SUBMIT_CHECKS_DIR
from .site_templates import SiteTemplate, match_site_template, template_summary


CAPTCHA_TERMS = [
    "captcha",
    "recaptcha",
    "hcaptcha",
    "私はロボットではありません",
    "画像認証",
    "文字認証",
    "ロボット認証",
]
LOGIN_REQUIRED_TERMS = [
    "ログインが必要",
    "ログインが必須",
    "ログインしてください",
    "会員登録が必要",
    "会員登録してください",
    "login required",
    "sign in required",
]
SNS_TERMS = ["xで", "twitter", "instagram", "フォロー", "リポスト", "いいね", "シェア", "x投稿"]
LINE_TERMS = ["line", "友だち追加", "友達追加", "line登録"]
QUIZ_TERMS = ["クイズ", "問題", "正解", "お答えください", "次のうち", "どれでしょうか", "クイズの回答"]
CONSENT_TERMS = ["同意", "利用規約", "応募規約", "プライバシーポリシー", "規約に同意"]
AGE_TERMS = ["年齢確認", "年齢を確認", "年齢確認が必要"]
NEWSLETTER_TERMS = ["メルマガ", "newsletter", "メール配信", "登録"]
FREE_TEXT_TERMS = ["自由記述", "御意見", "ご意見", "御感想", "ご感想", "メッセージ", "コメント", "感想"]
DEFAULT_REVIEW_COMMENT_TEXT = "応募内容を確認し、ご意見・ご感想を入力してください。"
ENDED_TERMS = ["募集終了", "受付終了", "終了しました", "応募終了", "締め切りました", "キャンペーンは終了"]


def _body_requires_login(body_text: str) -> bool:
    normalized = " ".join((body_text or "").casefold().split())
    return any(term.casefold() in normalized for term in LOGIN_REQUIRED_TERMS)


def detect_pre_fill_safety_stop(page, body_text: str) -> str:
    """Return a terminal reason that must be handled before profile fields are filled."""
    normalized = (body_text or "").casefold()
    if any(term.casefold() in normalized for term in CAPTCHA_TERMS):
        return "captcha_detected"
    try:
        if page.locator('[class*="captcha" i], [id*="captcha" i], iframe[src*="captcha" i]').count():
            return "captcha_detected"
    except Exception:
        pass
    if _body_requires_login(body_text):
        return "login_required"
    try:
        if page.locator('input[type="password"]').count():
            return "login_required"
    except Exception:
        pass
    if any(term.casefold() in normalized for term in SNS_TERMS):
        return "sns_auth_required"
    if any(term.casefold() in normalized for term in LINE_TERMS):
        return "line_auth_required"
    return ""

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
    def verify(
        self,
        page,
        campaign_id: str,
        fields: list[DetectedField],
        site_template: SiteTemplate | None = None,
        campaign: dict[str, str] | None = None,
        profile: dict[str, str] | None = None,
        answer_pack: dict[str, object] | None = None,
        allow_ai_resolved: bool = False,
        persist: bool = True,
    ) -> dict[str, object]:
        try:
            body_text = page.locator("body").inner_text(timeout=5000) if page.locator("body").count() else ""
        except Exception:
            body_text = ""
        if site_template is None:
            site_template = match_site_template(page.url, page_text=body_text)
        if answer_pack is None:
            try:
                answer_pack = build_answer_pack(page, campaign or {}, profile or {}, site_template)
            except Exception:
                answer_pack = {}
        quiz_suggestions = []
        comment_text = ""
        quiz_answer_override = ""
        if isinstance(answer_pack, dict):
            raw_quiz_suggestions = answer_pack.get("quiz_suggestions", [])
            if isinstance(raw_quiz_suggestions, list):
                quiz_suggestions = [item for item in raw_quiz_suggestions if isinstance(item, dict)]
            comment_text = str(answer_pack.get("comment_text", "")).strip()
            quiz_answer_override = str(answer_pack.get("quiz_answer", "")).strip()
        quiz_suggestion_map: dict[str, dict[str, object]] = {}
        for suggestion in quiz_suggestions:
            question_key = str(suggestion.get("question_text", "")).strip()
            if question_key and question_key not in quiz_suggestion_map:
                quiz_suggestion_map[question_key] = suggestion

        template_signal_score = 0
        template_signal_hits: dict[str, object] = {}
        template_skip_hits: list[str] = []
        if site_template is not None:
            template_signal_score, template_signal_hits = site_template.signal_score(body_text)
            template_skip_hits = site_template.skip_rule_hits(body_text)

        actionable_fields = [field for field in fields if field.field_name != "search"]
        submit_candidates = [
            candidate
            for candidate in self._submit_candidates(page)
            if "検索" not in str(candidate.get("text", "")) and "search" not in str(candidate.get("text", "")).casefold()
        ]
        submit_button_detected = bool(submit_candidates)

        field_summary = self._summarize_field_questions(actionable_fields)
        required_unfilled = list(field_summary["required_unfilled"])
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

        total_fields_count = int(field_summary["total_fields_count"])
        filled_fields_count = int(field_summary["filled_fields_count"])
        fill_completion_rate = round((filled_fields_count / total_fields_count * 100.0), 2) if total_fields_count else 0.0
        unresolved_required_fields = self._unique_nonempty(
            required_unfilled + [str(group) for group in unchecked_radio_groups] + self._checkbox_required_names(page)
        )

        if not actionable_fields:
            hard_reasons.append("no_form")
            review_items.append(self._item("form", "フォームなし", "入力欄が見つかりませんでした", required=False))

        if self._contains(body_text, CAPTCHA_TERMS) or page.locator('[class*="captcha" i], [id*="captcha" i], iframe[src*="captcha" i]').count():
            hard_reasons.append("captcha_detected")
        if self._contains(body_text, ENDED_TERMS):
            hard_reasons.append("campaign_ended")

        if _body_requires_login(body_text) or page.locator('input[type="password"], [href*="login" i], [href*="signin" i]').count():
            manual_assist_reasons.append("login_required")
        if self._contains(body_text, SNS_TERMS):
            manual_assist_reasons.append("sns_condition")
        if self._contains(body_text, LINE_TERMS):
            manual_assist_reasons.append("line_condition")

        has_quiz = self._contains(body_text, QUIZ_TERMS) or bool(quiz_suggestions) or any(field.field_name == "quiz_answer" for field in fields)
        ai_quiz_resolved = allow_ai_resolved and bool(quiz_answer_override)
        ai_comment_resolved = allow_ai_resolved and bool(comment_text)

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

        if has_quiz:
            if not ai_quiz_resolved:
                review_reasons.append("quiz_detected")
            for item in extract_quiz_items(page, limit=5):
                question_text = str(item.get("question_text", "")).strip()
                suggestion = quiz_suggestion_map.get(question_text, {})
                suggested_answer = str(suggestion.get("suggested_answer", "")).strip() if isinstance(suggestion, dict) else ""
                suggested_confidence = float(suggestion.get("confidence", 0.0) or 0.0) if isinstance(suggestion, dict) else 0.0
                review_items.append(
                    {
                        "kind": "quiz",
                        "field_name": "quiz_answer",
                        "question_text": question_text,
                        "candidate_answers": list(item.get("choices", [])),
                        "answer_field_selector": item.get("answer_field_selector", ""),
                        "required": bool(item.get("required", False)),
                        "suggested_answer": suggested_answer,
                        "suggested_confidence": suggested_confidence,
                        "suggested_reason": str(suggestion.get("reason", "")) if isinstance(suggestion, dict) else "",
                        "ai_resolved": bool(suggested_answer and suggested_confidence >= 0.7),
                        "reason": "quiz answer requires human confirmation" if not ai_quiz_resolved else "AI answer candidate generated",
                    }
                )
            if not quiz_suggestions:
                review_items.append(
                    {
                        "kind": "quiz",
                        "field_name": "quiz_answer",
                        "label": "クイズ",
                        "candidate_answers": [],
                        "answer_field_selector": "",
                        "required": False,
                        "suggested_answer": quiz_answer_override,
                        "suggested_confidence": 0.0,
                        "suggested_reason": "",
                        "ai_resolved": ai_quiz_resolved,
                        "reason": "quiz answer requires human confirmation" if not ai_quiz_resolved else "AI answer candidate generated",
                    }
                )

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
            if not ai_comment_resolved:
                review_reasons.append("free_text_present")
            review_items.append(
                {
                    "kind": "free_text",
                    "field_name": "free_text",
                    "label": "自由記述",
                    "candidate_text": comment_text or DEFAULT_REVIEW_COMMENT_TEXT,
                    "suggested_text": comment_text or DEFAULT_REVIEW_COMMENT_TEXT,
                    "suggested_confidence": 0.75 if comment_text else 0.0,
                    "required": False,
                    "ai_resolved": ai_comment_resolved,
                    "reason": "free text requires human review" if not ai_comment_resolved else "AI comment candidate generated",
                }
            )

        if site_template is not None:
            review_reasons.extend(
                f"site_template:{term}"
                for term in site_template.manual_review_terms
                if self._contains(body_text, [term])
            )
            if template_skip_hits:
                review_reasons.extend(f"site_template_skip:{term}" for term in template_skip_hits)
                review_items.append(
                    {
                        "kind": "template_skip_rule",
                        "field_name": "site_template",
                        "label": site_template.label,
                        "reason": f"site template skip rules matched: {', '.join(template_skip_hits)}",
                        "matched_terms": template_skip_hits,
                    }
                )

        for field in fields:
            if field.field_name in {"free_text", "opinion"}:
                if not ai_comment_resolved:
                    review_reasons.append("free_text_present")
                review_items.append(
                    {
                        "kind": "free_text",
                        "field_name": field.field_name,
                        "label": field.label,
                        "selector": field.selector,
                        "candidate_text": field.value_preview or comment_text or DEFAULT_REVIEW_COMMENT_TEXT,
                        "suggested_text": comment_text or field.value_preview or DEFAULT_REVIEW_COMMENT_TEXT,
                        "suggested_confidence": 0.75 if (comment_text or field.value_preview) else 0.0,
                        "required": field.required,
                        "ai_resolved": ai_comment_resolved,
                        "reason": "candidate text should be human confirmed" if not ai_comment_resolved else "AI comment candidate generated",
                    }
                )
            if field.field_name == "quiz_answer" and not quiz_suggestions:
                if not ai_quiz_resolved:
                    review_reasons.append("quiz_detected")
                review_items.append(
                    {
                        "kind": "quiz",
                        "field_name": "quiz_answer",
                        "label": field.label,
                        "selector": field.selector,
                        "required": field.required,
                        "suggested_answer": quiz_answer_override,
                        "suggested_confidence": 0.0,
                        "suggested_reason": "",
                        "ai_resolved": ai_quiz_resolved,
                        "reason": field.skip_reason or field.reason or ("quiz answer requires human confirmation" if not ai_quiz_resolved else "AI answer candidate generated"),
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
            if (self._contains(body_text, QUIZ_TERMS) or any(field.field_name == "quiz_answer" for field in fields)) and not ai_quiz_resolved:
                penalties += 10
            if self._contains(body_text, CONSENT_TERMS):
                penalties += 5
            if self._contains(body_text, AGE_TERMS) or any(field.field_name == "age" for field in fields):
                penalties += 5
            if self._contains(body_text, NEWSLETTER_TERMS):
                penalties += 5
            if self._contains(body_text, FREE_TEXT_TERMS) and not ai_comment_resolved:
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

        human_checklist: list[str] = []
        ai_candidates: list[str] = []
        for item in review_items:
            summary = self._item_summary(item)
            if not summary:
                continue
            if str(item.get("suggested_answer", "")).strip() or str(item.get("suggested_text", "")).strip() or str(item.get("candidate_text", "")).strip():
                ai_candidates.append(summary)
            else:
                human_checklist.append(summary)

        needs_review_reasons = self._unique_nonempty(
            hard_reasons + manual_assist_reasons + review_reasons + (["submit_button_not_detected"] if not submit_button_detected else [])
        )
        safety_memo = " / ".join(
            self._unique_nonempty(
                list(site_template.safety_notes if site_template is not None else [])
                + list(site_template.notes if site_template is not None else [])
            )
        )
        skip_reason = " / ".join(
            self._unique_nonempty(
                hard_reasons
                + manual_assist_reasons
                + review_reasons
                + template_skip_hits
            )
        )

        result = {
            "campaign_id": campaign_id,
            "url": page.url,
            **template_summary(site_template),
            "status": status,
            "pre_submit_score": score,
            "site_template_signal_score": template_signal_score,
            "site_template_signal_hits": template_signal_hits,
            "site_template_skip_hits": template_skip_hits,
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
            "human_checklist": human_checklist,
            "ai_candidates": ai_candidates,
            "submit_button_candidates": submit_candidates,
            "html_snapshot_path": "",
            "ai_quiz_resolved": ai_quiz_resolved,
            "ai_comment_resolved": ai_comment_resolved,
            "ai_quiz_suggestion_count": len(quiz_suggestions),
            "ai_comment_length": len(comment_text),
            "skip_reason": skip_reason,
            "safety_memo": safety_memo,
        }
        if persist:
            self.save(campaign_id, result)
        return result

    @staticmethod
    def _summarize_field_questions(fields: list[DetectedField]) -> dict[str, object]:
        groups: dict[str, list[DetectedField]] = {}
        labels: dict[str, str] = {}
        for index, field in enumerate(fields):
            if field.input_type.casefold() == "radio":
                group_name = (field.name or field.element_id or field.field_name or "radio").strip()
                key = f"radio:{group_name}"
                labels[key] = group_name
            else:
                identity = field.selector or field.name or field.element_id or field.field_name or str(index)
                key = f"field:{identity}"
                labels[key] = field.field_name or field.name or field.element_id or f"field_{index + 1}"
            groups.setdefault(key, []).append(field)

        required_unfilled: list[str] = []
        filled_fields_count = 0
        for key, grouped_fields in groups.items():
            filled = any(field.will_fill for field in grouped_fields)
            if filled:
                filled_fields_count += 1
            if any(field.required for field in grouped_fields) and not filled:
                required_unfilled.append(labels[key])
        return {
            "total_fields_count": len(groups),
            "filled_fields_count": filled_fields_count,
            "required_unfilled": required_unfilled,
        }

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
    def _item_summary(item: dict[str, object]) -> str:
        kind = str(item.get("kind", "")).strip() or "item"
        field_name = str(item.get("field_name", "")).strip()
        label = str(item.get("label", "")).strip()
        reason = str(item.get("reason", "")).strip()
        parts = [part for part in [kind, field_name or label, reason] if part]
        suggested = str(
            item.get("suggested_answer", "")
            or item.get("suggested_text", "")
            or item.get("candidate_text", "")
            or ""
        ).strip()
        confidence = item.get("suggested_confidence", item.get("confidence", ""))
        if suggested:
            parts.append(f"候補={suggested[:36]}")
        if confidence not in {"", None}:
            try:
                parts.append(f"信頼度={float(confidence):.2f}")
            except Exception:
                parts.append(f"信頼度={confidence}")
        return " / ".join(parts)

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
