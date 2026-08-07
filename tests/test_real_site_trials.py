from __future__ import annotations

import json

from kensho_assistant.app.real_site_trials import (
    ErrorCategory,
    TrialStore,
    build_trial_record,
    evaluate_trial,
    safe_site_identifier,
    summarize_trials,
    trial_from_engine_result,
)


def _trial(**overrides):
    values = {
        "site_id": "site-001",
        "url": "https://example.com/form?email=secret@example.com",
        "started_at": "2026-07-18T10:00:00+09:00",
        "finished_at": "2026-07-18T10:01:00+09:00",
        "recognized_fields": 8,
        "filled_fields": 8,
        "unfilled_fields": 0,
        "manual_interventions": 0,
        "final_step": "AWAITING_USER_SUBMIT",
        "error_category": ErrorCategory.NONE.value,
        "recoverable": True,
        "unintended_submission": False,
        "site_category": "standard_form",
        "input_types": {"email": "email", "phone": "tel"},
    }
    values.update(overrides)
    return build_trial_record(**values)


def test_trial_grading_is_mechanical() -> None:
    assert evaluate_trial(_trial()) == "A"
    assert evaluate_trial(_trial(manual_interventions=2, error_category="LOGIN_REQUIRED")) == "B"
    assert evaluate_trial(_trial(unintended_submission=True)) == "C"
    assert evaluate_trial(_trial(error_category="UNKNOWN", recoverable=False)) == "C"
    assert evaluate_trial(_trial(finished_at="2026-07-18T10:04:01+09:00")) == "C"


def test_trial_store_redacts_url_and_never_persists_values(tmp_path) -> None:
    store = TrialStore(tmp_path / "trials.jsonl")
    record = _trial()
    store.append(record)
    text = store.path.read_text(encoding="utf-8")
    assert "secret@example.com" not in text
    assert "example.com" not in text
    assert "input_types" in text
    assert "input_values" not in text
    assert json.loads(text)["grade"] == "A"


def test_trial_store_redacts_pii_again_when_exporting(tmp_path) -> None:
    store = TrialStore(tmp_path / "trials.jsonl")
    record = _trial(manual_action_fields=["secret@example.com を手動確認"])
    store.append(record)
    paths = store.export([record], tmp_path / "export")

    for path in paths.values():
        text = path.read_text(encoding="utf-8-sig")
        assert "secret@example.com" not in text
        assert "[redacted]" in text or path.name == "trial_summary.json"


def test_same_domain_has_stable_site_identifier_without_exposing_hostname() -> None:
    first = safe_site_identifier("https://example.com/form-a?token=secret")
    second = safe_site_identifier("https://example.com/form-b")
    other = safe_site_identifier("https://other.example/form")
    assert first == second
    assert first != other
    assert "example.com" not in first


def test_ninety_trial_summary_exports_required_metrics(tmp_path) -> None:
    trials = []
    for index in range(90):
        grade = "A" if index < 60 else "B" if index < 80 else "C"
        trials.append(_trial(site_id=f"site-{index // 3:03d}", grade=grade, elapsed_seconds=index + 1))
    summary = summarize_trials(trials)
    assert summary["trial_count"] == 90
    assert summary["site_count"] == 30
    assert summary["a_rate"] == 66.67
    assert summary["a_plus_b_rate"] == 88.89
    assert summary["unintended_submission_count"] == 0
    assert len(summary["top_failure_patterns"]) <= 3

    store = TrialStore(tmp_path / "trials.jsonl")
    paths = store.export(trials, tmp_path / "export")
    assert paths["csv"].exists()
    assert paths["json"].exists()
    assert paths["summary"].exists()


def test_engine_result_maps_manual_handoff_and_known_errors() -> None:
    result = {
        "record": {
            "status": "REVIEW_FILL_READY",
            "total_fields_count": 8,
            "filled_fields_count": 7,
            "unresolved_required_fields_count": 1,
            "submit_button_detected": True,
            "needs_review_reasons": ["captcha detected"],
            "submit_guard_blocked_attempts": 0,
        },
        "missing_fields": ["agreement"],
        "pre_submit_check": {"human_checklist": ["CAPTCHAを手動確認"]},
    }
    trial = trial_from_engine_result(
        campaign={"campaign_id": "campaign-1", "site_category": "standard_form"},
        url="https://example.com/form",
        result=result,
        started_at="2026-07-18T10:00:00+09:00",
        finished_at="2026-07-18T10:01:00+09:00",
    )
    assert trial.error_category == "CAPTCHA_REQUIRED"
    assert trial.manual_interventions == 1
    assert trial.final_step == "AWAITING_USER_SUBMIT"
    assert trial.grade == "B"


def test_engine_result_classifies_common_recovery_failures() -> None:
    cases = {
        "input_rejected": ErrorCategory.INPUT_REJECTED.value,
        "value_reset": ErrorCategory.VALUE_RESET.value,
        "SMS認証が必要": ErrorCategory.EMAIL_OR_SMS_AUTH_REQUIRED.value,
        "規約制限": ErrorCategory.TERMS_RESTRICTION.value,
        "手動判断が必要": ErrorCategory.MANUAL_JUDGMENT_REQUIRED.value,
    }
    for reason, expected in cases.items():
        trial = trial_from_engine_result(
            campaign={"campaign_id": "campaign-1"},
            url="https://example.com/form",
            result={
                "record": {
                    "status": "REVIEW_FILL_READY",
                    "skip_reason": reason,
                    "submit_button_detected": True,
                }
            },
            started_at="2026-07-18T10:00:00+09:00",
            finished_at="2026-07-18T10:01:00+09:00",
        )
        assert trial.error_category == expected
