from __future__ import annotations

from collections.abc import Mapping

from .apply_run_logger import append_apply_run
from .field_mapper import FieldMapper
from .form_analyzer import FormAnalyzer
from .form_filler import apply_field_plan
from .pre_submit_verifier import PreSubmitVerifier
from .run_mode import normalize_run_mode
from .submit_adapters.dry_run_submit import DryRunSubmitAdapter
from .submit_adapters.mock_submit import MockSubmitAdapter
from .submit_adapters.real_submit import RealSubmitAdapter


class AutoApplyEngine:
    def __init__(self, run_mode: str = "dry_run") -> None:
        self.run_mode = normalize_run_mode(run_mode)
        self.analyzer = FormAnalyzer()
        self.mapper = FieldMapper()
        self.verifier = PreSubmitVerifier()

    def run(self, page, campaign: Mapping[str, str], profile: Mapping[str, str]) -> dict[str, object]:
        campaign_id = str(campaign.get("campaign_id") or campaign.get("queue_id") or "campaign")
        analysis = self.analyzer.analyze(page, campaign_id)
        fields = self.mapper.map_fields(self.analyzer_fields(page), profile, allow_birthdate_fill=True)
        filled_fields, missing_fields = apply_field_plan(page, fields, profile)
        pre_submit_check = self.verifier.verify(page, campaign_id, fields)
        adapter = self._adapter()
        if self.run_mode == "review":
            submit_result = DryRunSubmitAdapter().submit(page, {"campaign_id": campaign_id})
            status = "NEEDS_REVIEW"
        elif self.run_mode == "dry_run":
            submit_result = adapter.submit(page, {"campaign_id": campaign_id, "pre_submit_check": pre_submit_check})
            status = pre_submit_check.get("status") or submit_result.status
        else:
            submit_result = adapter.submit(page, {"campaign_id": campaign_id, "pre_submit_check": pre_submit_check})
            status = submit_result.status
        if self.run_mode != "mock":
            submit_result.submit_attempted = False
            submit_result.submit_clicked = False
            submit_result.auto_submitted = False
        record = {
            "campaign_id": campaign_id,
            "title": campaign.get("campaign_name", ""),
            "url": page.url,
            "run_mode": self.run_mode,
            "status": status,
            "filled_fields_count": len(filled_fields),
            "skipped_fields_count": sum(1 for field in fields if not field.will_fill),
            "submit_attempted": submit_result.submit_attempted,
            "submit_clicked": submit_result.submit_clicked,
            "auto_submitted": submit_result.auto_submitted,
            "needs_review_reasons": pre_submit_check.get("needs_review_reasons", []),
            "screenshot_path": submit_result.screenshot_path,
        }
        append_apply_run(record)
        return {
            "record": record,
            "analysis": analysis,
            "pre_submit_check": pre_submit_check,
            "filled_fields": filled_fields,
            "missing_fields": missing_fields,
            "submit_result": submit_result,
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
