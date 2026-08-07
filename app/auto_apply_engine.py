from __future__ import annotations

from collections.abc import Mapping

from .apply_run_logger import append_apply_run
from .answer_assistant import build_answer_pack
from .campaign_page_guard import CampaignPageGuardResult, evaluate_campaign_page
from .entry_navigator import advance_to_entry_form
from .field_mapper import FieldMapper
from .form_analyzer import FormAnalyzer
from .form_filler import apply_field_plan
from .pre_submit_verifier import PreSubmitVerifier, detect_pre_fill_safety_stop
from .paths import FORM_ANALYSIS_DIR, PRE_SUBMIT_CHECKS_DIR
from .run_mode import normalize_run_mode
from .site_templates import match_site_template, template_summary
from .submit_adapters.dry_run_submit import DryRunSubmitAdapter
from .submit_adapters.mock_submit import MockSubmitAdapter
from .submit_adapters.real_submit import RealSubmitAdapter
from .submit_adapters.base import SubmitResult
from .submission_guard import (
    install_submission_guard,
    install_submission_guard_on_context,
    release_submission_guard,
    submission_guard_snapshot,
)


class AutoApplyEngine:
    def __init__(self, run_mode: str = "dry_run") -> None:
        self.run_mode = normalize_run_mode(run_mode)
        self.analyzer = FormAnalyzer()
        self.mapper = FieldMapper()
        self.verifier = PreSubmitVerifier()

    def run(
        self,
        page,
        campaign: Mapping[str, str],
        profile: Mapping[str, str],
        *,
        persist_artifacts: bool = True,
        keep_submission_guard: bool = False,
        require_mapping_confirmation: bool = False,
        mapping_confirmed: bool = False,
    ) -> dict[str, object]:
        campaign_id = str(campaign.get("campaign_id") or campaign.get("queue_id") or "campaign")
        context_accessor = getattr(page, "context", None)
        context = context_accessor() if callable(context_accessor) else context_accessor
        if context is not None:
            install_submission_guard_on_context(context)
        install_submission_guard(page)
        navigation = advance_to_entry_form(page, max_steps=2)
        try:
            body_text = page.locator("body").inner_text(timeout=5000) if page.locator("body").count() else ""
        except Exception:
            body_text = ""
        try:
            page_title = str(page.title() or "")
        except Exception:
            page_title = ""
        page_guard = evaluate_campaign_page(campaign, body_text, page_title=page_title)
        pre_fill_stop = detect_pre_fill_safety_stop(page, body_text)
        if pre_fill_stop:
            page_guard = CampaignPageGuardResult(False, pre_fill_stop)
        if self.run_mode == "mock" and page_guard.reason == "campaign_mismatch":
            page_guard = evaluate_campaign_page({}, body_text, page_title=page_title)
        site_template = match_site_template(page.url, page_text=body_text)
        answer_pack = build_answer_pack(page, campaign, profile, site_template)
        analysis = self.analyzer.analyze(page, campaign_id, persist=persist_artifacts)
        allow_ai_answer_fill = self.run_mode == "mock"
        fields = self.mapper.map_fields(
            self.analyzer_fields(page),
            profile,
            allow_birthdate_fill=True,
            site_template=site_template,
            answer_overrides=answer_pack.get("answer_overrides", {}),
            allow_ai_answer_fill=allow_ai_answer_fill,
        )
        submit_guard = {"blockedAttempts": 0, "reasons": []}
        mapping_review_required = bool(require_mapping_confirmation and not mapping_confirmed)
        if page_guard.safe_to_fill and not mapping_review_required:
            try:
                filled_fields, missing_fields = apply_field_plan(
                    page,
                    fields,
                    profile,
                    answer_overrides=answer_pack.get("answer_overrides", {}),
                    allow_ai_answer_fill=allow_ai_answer_fill,
                )
            finally:
                submit_guard = (
                    submission_guard_snapshot(page)
                    if keep_submission_guard
                    else release_submission_guard(page)
                )
        else:
            for field in fields:
                field.will_fill = False
                field.value_preview = ""
                if mapping_review_required:
                    field.skip_reason = field.skip_reason or "欄対応の人間確認が必要です"
                else:
                    field.skip_reason = field.skip_reason or f"page_guard={page_guard.reason}"
            filled_fields = []
            missing_fields = [field.field_name for field in fields]
        pre_submit_check = self.verifier.verify(
            page,
            campaign_id,
            fields,
            site_template=site_template,
            campaign=campaign,
            profile=profile,
            answer_pack=answer_pack,
            allow_ai_resolved=allow_ai_answer_fill,
            persist=persist_artifacts,
        )
        if not page_guard.safe_to_fill:
            reasons = list(pre_submit_check.get("needs_review_reasons", []))
            if page_guard.reason not in reasons:
                reasons.insert(0, page_guard.reason)
            danger_reasons = list(pre_submit_check.get("danger_reasons", []))
            terminal_manual_stop = page_guard.reason in {
                "login_required",
                "sns_auth_required",
                "line_auth_required",
            }
            if not terminal_manual_stop and page_guard.reason not in danger_reasons:
                danger_reasons.insert(0, page_guard.reason)
            pre_submit_check["needs_review_reasons"] = reasons
            pre_submit_check["danger_reasons"] = danger_reasons
            pre_submit_check["status"] = "MANUAL_ASSIST_READY" if terminal_manual_stop else "SKIPPED"
            pre_submit_check["pre_submit_score"] = 30 if terminal_manual_stop else 0
            pre_submit_check["skip_reason"] = " / ".join(reasons)
        if mapping_review_required:
            reasons = list(pre_submit_check.get("needs_review_reasons", []))
            if "MAPPING_REVIEW_REQUIRED" not in reasons:
                reasons.insert(0, "MAPPING_REVIEW_REQUIRED")
            pre_submit_check["needs_review_reasons"] = reasons
            pre_submit_check["status"] = "REVIEW_FILL_READY"
            pre_submit_check["safety_memo"] = "初回フォームは欄対応を人間が確認するまで入力しません。"
        if int(submit_guard.get("blockedAttempts", 0) or 0) > 0:
            reasons = list(pre_submit_check.get("needs_review_reasons", []))
            if "SUBMIT_GUARD_TRIGGERED" not in reasons:
                reasons.insert(0, "SUBMIT_GUARD_TRIGGERED")
            pre_submit_check["needs_review_reasons"] = reasons
            pre_submit_check["status"] = "REVIEW_FILL_READY"
            pre_submit_check["safety_memo"] = "自動入力中の送信動作を遮断しました。手動で状態を確認してください。"
        adapter = self._adapter()
        if not persist_artifacts and self.run_mode in {"dry_run", "review"}:
            submit_result = SubmitResult(
                status="DRY_RUN_COMPLETED",
                submit_attempted=False,
                submit_clicked=False,
                auto_submitted=False,
                message="pilot dry run completed without persistent artifacts",
            )
            status = str(pre_submit_check.get("status") or submit_result.status)
        elif self.run_mode in {"dry_run", "review"}:
            submit_result = adapter.submit(page, {"campaign_id": campaign_id, "pre_submit_check": pre_submit_check})
            status = str(pre_submit_check.get("status") or submit_result.status)
        else:
            submit_result = adapter.submit(page, {"campaign_id": campaign_id, "pre_submit_check": pre_submit_check})
            status = submit_result.status
        total_fields_count = len(fields)
        filled_count = len(filled_fields)
        completion_rate = round((filled_count / total_fields_count * 100.0), 2) if total_fields_count else 0.0
        record = {
            "campaign_id": campaign_id,
            "title": campaign.get("campaign_name", ""),
            "url": page.url,
            "run_mode": self.run_mode,
            "status": status,
            "filled_fields_count": filled_count,
            "total_fields_count": total_fields_count,
            "fill_completion_rate": completion_rate,
            "skipped_fields_count": sum(1 for field in fields if not field.will_fill),
            "unresolved_required_fields_count": pre_submit_check.get("unresolved_required_fields_count", 0),
            "skip_reason": pre_submit_check.get("skip_reason", ""),
            "safety_memo": pre_submit_check.get("safety_memo", ""),
            "submit_attempted": submit_result.submit_attempted,
            "submit_clicked": submit_result.submit_clicked,
            "auto_submitted": submit_result.auto_submitted,
            "needs_review_reasons": pre_submit_check.get("needs_review_reasons", []),
            "review_items": pre_submit_check.get("review_items", []),
            "pre_submit_score": pre_submit_check.get("pre_submit_score", 0),
            "submit_button_detected": pre_submit_check.get("submit_button_detected", False),
            "screenshot_path": submit_result.screenshot_path,
            "html_snapshot_path": submit_result.html_snapshot_path,
            "ai_quiz_resolved": pre_submit_check.get("ai_quiz_resolved", False),
            "ai_comment_resolved": pre_submit_check.get("ai_comment_resolved", False),
            "ai_quiz_suggestion_count": pre_submit_check.get("ai_quiz_suggestion_count", 0),
            "entry_navigation_clicked_count": navigation.clicked_count,
            "entry_navigation_stop_reason": navigation.stop_reason,
            "mapping_review_required": mapping_review_required,
            "mapping_confirmed": bool(mapping_confirmed),
            "page_guard_reason": page_guard.reason,
            "submit_guard_blocked_attempts": int(submit_guard.get("blockedAttempts", 0) or 0),
            "submit_guard_reasons": list(submit_guard.get("reasons", []) or []),
            "analysis_path": str(FORM_ANALYSIS_DIR / f"{campaign_id}.json") if persist_artifacts else "",
            "check_path": str(PRE_SUBMIT_CHECKS_DIR / f"{campaign_id}.json") if persist_artifacts else "",
            **template_summary(site_template),
        }
        pre_submit_check["screenshot_path"] = submit_result.screenshot_path
        pre_submit_check["html_snapshot_path"] = submit_result.html_snapshot_path
        if persist_artifacts:
            self.verifier.save(campaign_id, pre_submit_check)
            append_apply_run(record)
        return {
            "record": record,
            "analysis": analysis,
            "pre_submit_check": pre_submit_check,
            "filled_fields": filled_fields,
            "missing_fields": missing_fields,
            "submit_result": submit_result,
            "analysis_path": str(FORM_ANALYSIS_DIR / f"{campaign_id}.json") if persist_artifacts else "",
        }

    def analyzer_fields(self, page):
        from .form_detector import detect_fields

        return detect_fields(page)

    def _adapter(self):
        if self.run_mode == "mock":
            return MockSubmitAdapter()
        if self.run_mode == "dry_run":
            return DryRunSubmitAdapter()
        if self.run_mode == "review":
            return DryRunSubmitAdapter()
        return RealSubmitAdapter()
