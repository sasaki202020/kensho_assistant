from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from .privacy_guard import assert_no_personal_info, sanitize_log_payload


class ErrorCategory(str, Enum):
    NONE = "NONE"
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    INPUT_REJECTED = "INPUT_REJECTED"
    VALUE_RESET = "VALUE_RESET"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    DYNAMIC_FIELD_TIMEOUT = "DYNAMIC_FIELD_TIMEOUT"
    NAVIGATION_TIMEOUT = "NAVIGATION_TIMEOUT"
    IFRAME_UNSUPPORTED = "IFRAME_UNSUPPORTED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    SNS_AUTH_REQUIRED = "SNS_AUTH_REQUIRED"
    EMAIL_OR_SMS_AUTH_REQUIRED = "EMAIL_OR_SMS_AUTH_REQUIRED"
    MULTI_STEP_UNSUPPORTED = "MULTI_STEP_UNSUPPORTED"
    SUBMIT_GUARD_TRIGGERED = "SUBMIT_GUARD_TRIGGERED"
    TERMS_RESTRICTION = "TERMS_RESTRICTION"
    MANUAL_JUDGMENT_REQUIRED = "MANUAL_JUDGMENT_REQUIRED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TrialRecord:
    site_id: str
    url_identifier: str
    started_at: str
    finished_at: str
    elapsed_seconds: int
    recognized_fields: int
    filled_fields: int
    unfilled_fields: int
    manual_interventions: int
    final_step: str
    error_category: str
    recoverable: bool
    unintended_submission: bool
    grade: str
    site_category: str = "unknown"
    last_successful_step: str = ""
    manual_action_fields: list[str] = field(default_factory=list)
    input_types: dict[str, str] = field(default_factory=dict)
    screenshot_path: str = ""
    trial_id: str = ""
    manifest_id: str = ""
    entry_id: str = ""
    attempt_no: int = 0
    run_id: str = ""
    git_commit_sha: str = ""
    config_fingerprint: str = ""
    execution_status: str = ""
    app_version: str = ""
    python_version: str = ""
    browser_name: str = ""
    browser_version: str = ""
    os_name: str = ""
    pilot_run_id: str = ""
    trial_number: int = 0
    result: str = ""
    stop_reason: str = ""
    pii_persisted: bool = False
    candidate_state_changed: bool = False
    auto_submit_detected: bool = False


def _strictly_sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _strictly_sanitize(item) for key, item in sanitize_log_payload(value).items()}
    if isinstance(value, list):
        return [_strictly_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_strictly_sanitize(item) for item in value]
    if isinstance(value, str):
        try:
            assert_no_personal_info(value)
        except ValueError:
            return "[redacted]"
    return value


def safe_url_identifier(url: str) -> str:
    parsed = urlsplit(str(url or ""))
    canonical = f"{parsed.scheme.lower()}://{parsed.hostname or ''}{parsed.path or '/'}"
    return f"url-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def safe_site_identifier(url: str) -> str:
    hostname = (urlsplit(str(url or "")).hostname or "unknown").casefold()
    return f"site-{hashlib.sha256(hostname.encode('utf-8')).hexdigest()[:12]}"


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def evaluate_trial(record: TrialRecord) -> str:
    error = str(record.error_category or ErrorCategory.NONE.value)
    if (
        record.unintended_submission
        or not record.recoverable
        or record.elapsed_seconds > 180
        or error in {ErrorCategory.UNKNOWN.value, ErrorCategory.SUBMIT_GUARD_TRIGGERED.value}
    ):
        return "C"
    if (
        record.manual_interventions <= 0
        and record.unfilled_fields <= 0
        and error == ErrorCategory.NONE.value
        and record.final_step in {"AWAITING_USER_SUBMIT", "AWAITING_CONFIRMATION"}
    ):
        return "A"
    if record.manual_interventions <= 2 or error in {
        ErrorCategory.LOGIN_REQUIRED.value,
        ErrorCategory.CAPTCHA_REQUIRED.value,
        ErrorCategory.SNS_AUTH_REQUIRED.value,
    }:
        return "B"
    return "C"


def build_trial_record(
    *,
    site_id: str,
    url: str,
    started_at: str,
    finished_at: str,
    recognized_fields: int,
    filled_fields: int,
    unfilled_fields: int,
    manual_interventions: int,
    final_step: str,
    error_category: str = ErrorCategory.NONE.value,
    recoverable: bool = True,
    unintended_submission: bool = False,
    grade: str = "",
    site_category: str = "unknown",
    last_successful_step: str = "",
    manual_action_fields: Iterable[str] = (),
    input_types: Mapping[str, str] | None = None,
    screenshot_path: str = "",
    elapsed_seconds: int | None = None,
) -> TrialRecord:
    elapsed = elapsed_seconds
    if elapsed is None:
        elapsed = max(0, int((_parse_time(finished_at) - _parse_time(started_at)).total_seconds()))
    base = TrialRecord(
        site_id=str(site_id),
        url_identifier=safe_url_identifier(url),
        started_at=str(started_at),
        finished_at=str(finished_at),
        elapsed_seconds=int(elapsed),
        recognized_fields=max(0, int(recognized_fields)),
        filled_fields=max(0, int(filled_fields)),
        unfilled_fields=max(0, int(unfilled_fields)),
        manual_interventions=max(0, int(manual_interventions)),
        final_step=str(final_step),
        error_category=str(error_category or ErrorCategory.NONE.value),
        recoverable=bool(recoverable),
        unintended_submission=bool(unintended_submission),
        grade="",
        site_category=str(site_category or "unknown"),
        last_successful_step=str(last_successful_step),
        manual_action_fields=[str(item) for item in manual_action_fields],
        input_types={str(key): str(value) for key, value in (input_types or {}).items()},
        screenshot_path=str(screenshot_path or ""),
    )
    final_grade = str(grade or evaluate_trial(base)).upper()
    return TrialRecord(**{**asdict(base), "grade": final_grade if final_grade in {"A", "B", "C"} else "C"})


def _error_category_from_result(record: Mapping[str, Any], check: Mapping[str, Any]) -> str:
    if int(record.get("submit_guard_blocked_attempts", 0) or 0) > 0:
        return ErrorCategory.SUBMIT_GUARD_TRIGGERED.value
    text = " ".join(
        str(item)
        for item in (
            record.get("status", ""),
            record.get("skip_reason", ""),
            record.get("page_guard_reason", ""),
            record.get("entry_navigation_stop_reason", ""),
            record.get("needs_review_reasons", ""),
            check.get("danger_reasons", ""),
        )
    ).casefold()
    rules = (
        (("captcha", "recaptcha"), ErrorCategory.CAPTCHA_REQUIRED.value),
        (("login", "ログイン", "会員登録"), ErrorCategory.LOGIN_REQUIRED.value),
        (("sns", "x応募", "instagram", "facebook"), ErrorCategory.SNS_AUTH_REQUIRED.value),
        (("sms", "メール認証", "認証コード"), ErrorCategory.EMAIL_OR_SMS_AUTH_REQUIRED.value),
        (("value_reset", "value reset", "入力値が消", "値がリセット"), ErrorCategory.VALUE_RESET.value),
        (("input_rejected", "input rejected", "入力拒否"), ErrorCategory.INPUT_REJECTED.value),
        (("iframe",), ErrorCategory.IFRAME_UNSUPPORTED.value),
        (("timeout", "time out", "タイムアウト"), ErrorCategory.DYNAMIC_FIELD_TIMEOUT.value),
        (("validation", "入力エラー"), ErrorCategory.VALIDATION_FAILED.value),
        (("form_not_found", "フォームなし"), ErrorCategory.ELEMENT_NOT_FOUND.value),
        (("multi_step", "確認画面"), ErrorCategory.MULTI_STEP_UNSUPPORTED.value),
        (("terms", "規約制限", "応募条件不一致"), ErrorCategory.TERMS_RESTRICTION.value),
        (("manual_judgment", "人間の判断", "手動判断"), ErrorCategory.MANUAL_JUDGMENT_REQUIRED.value),
    )
    for terms, category in rules:
        if any(term in text for term in terms):
            return category
    if str(record.get("status", "")).upper() == "SKIPPED":
        return ErrorCategory.UNKNOWN.value
    return ErrorCategory.NONE.value


def trial_from_engine_result(
    *,
    campaign: Mapping[str, Any],
    url: str,
    result: Mapping[str, Any],
    started_at: str,
    finished_at: str,
) -> TrialRecord:
    record = result.get("record") if isinstance(result.get("record"), Mapping) else {}
    check = result.get("pre_submit_check") if isinstance(result.get("pre_submit_check"), Mapping) else {}
    missing = result.get("missing_fields") if isinstance(result.get("missing_fields"), list) else []
    manual_fields = [str(item) for item in missing]
    unresolved = max(int(record.get("unresolved_required_fields_count", 0) or 0), len(manual_fields))
    error_category = _error_category_from_result(record, check)
    status = str(record.get("status", "") or "").upper()
    submit_detected = bool(record.get("submit_button_detected", False))
    final_step = "AWAITING_USER_SUBMIT" if submit_detected and status != "SKIPPED" else status or "UNKNOWN"
    recoverable = error_category not in {ErrorCategory.UNKNOWN.value} and status != "SKIPPED"
    site_id = safe_site_identifier(url)
    input_types = record.get("input_types") if isinstance(record.get("input_types"), Mapping) else {}
    return build_trial_record(
        site_id=site_id,
        url=url,
        started_at=started_at,
        finished_at=finished_at,
        recognized_fields=int(record.get("total_fields_count", 0) or 0),
        filled_fields=int(record.get("filled_fields_count", 0) or 0),
        unfilled_fields=max(0, int(record.get("total_fields_count", 0) or 0) - int(record.get("filled_fields_count", 0) or 0)),
        manual_interventions=unresolved,
        final_step=final_step,
        error_category=error_category,
        recoverable=recoverable,
        unintended_submission=bool(
            record.get("submit_attempted", False)
            or record.get("submit_clicked", False)
            or record.get("auto_submitted", False)
        ),
        site_category=str(campaign.get("site_category", "unknown") or "unknown"),
        last_successful_step="fields_filled" if int(record.get("filled_fields_count", 0) or 0) else "form_detected",
        manual_action_fields=manual_fields,
        input_types=input_types,
        screenshot_path=str(record.get("screenshot_path", "") or ""),
    )


def summarize_trials(records: Iterable[TrialRecord]) -> dict[str, Any]:
    rows = list(records)
    count = len(rows)
    grades = {grade: sum(row.grade == grade for row in rows) for grade in ("A", "B", "C")}
    elapsed = sorted(row.elapsed_seconds for row in rows)
    recoverable_errors = [row for row in rows if row.error_category != ErrorCategory.NONE.value]
    errors: dict[str, int] = {}
    categories: dict[str, dict[str, int]] = {}
    for row in rows:
        errors[row.error_category] = errors.get(row.error_category, 0) + 1
        bucket = categories.setdefault(row.site_category, {"total": 0, "a": 0, "a_plus_b": 0})
        bucket["total"] += 1
        bucket["a"] += int(row.grade == "A")
        bucket["a_plus_b"] += int(row.grade in {"A", "B"})
    category_rates = {
        key: {
            "total": value["total"],
            "a_rate": round(value["a"] / value["total"] * 100, 2),
            "a_plus_b_rate": round(value["a_plus_b"] / value["total"] * 100, 2),
        }
        for key, value in categories.items()
    }
    failures = sorted(
        ({"error_category": key, "count": value} for key, value in errors.items() if key != ErrorCategory.NONE.value),
        key=lambda item: (-item["count"], item["error_category"]),
    )[:3]
    p95 = elapsed[max(0, math.ceil(len(elapsed) * 0.95) - 1)] if elapsed else 0
    return {
        "trial_count": count,
        "site_count": len({row.site_id for row in rows}),
        "grade_counts": grades,
        "a_rate": round(grades["A"] / count * 100, 2) if count else 0.0,
        "a_plus_b_rate": round((grades["A"] + grades["B"]) / count * 100, 2) if count else 0.0,
        "error_category_counts": errors,
        "site_category_success_rates": category_rates,
        "median_elapsed_seconds": round(float(statistics.median(elapsed)), 2) if elapsed else 0.0,
        "p95_elapsed_seconds": p95,
        "recovery_success_rate": round(sum(row.recoverable for row in recoverable_errors) / len(recoverable_errors) * 100, 2) if recoverable_errors else 0.0,
        "manual_intervention_rate": round(sum(row.manual_interventions > 0 for row in rows) / count * 100, 2) if count else 0.0,
        "unintended_submission_count": sum(row.unintended_submission for row in rows),
        "top_failure_patterns": failures,
    }


class TrialStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, record: TrialRecord) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if record.manifest_id and record.entry_id and record.attempt_no:
            duplicate = any(
                existing.manifest_id == record.manifest_id
                and existing.entry_id == record.entry_id
                and existing.attempt_no == record.attempt_no
                for existing in self.load(manifest_id=record.manifest_id)
            )
            if duplicate:
                return self.path
        payload = _strictly_sanitize(asdict(record))
        assert_no_personal_info(payload)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return self.path

    def load(self, manifest_id: str = "") -> list[TrialRecord]:
        if not self.path.exists():
            return []
        records: list[TrialRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(TrialRecord(**json.loads(line)))
        if manifest_id:
            return [record for record in records if record.manifest_id == manifest_id]
        return records

    def export(self, records: Iterable[TrialRecord], output_dir: Path) -> dict[str, Path]:
        rows = list(records)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "trial_results.json"
        csv_path = output_dir / "trial_results.csv"
        summary_path = output_dir / "trial_summary.json"
        safe_rows = [_strictly_sanitize(asdict(row)) for row in rows]
        safe_summary = _strictly_sanitize(summarize_trials(rows))
        assert_no_personal_info(safe_rows)
        assert_no_personal_info(safe_summary)
        json_path.write_text(json.dumps(safe_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        summary_path.write_text(json.dumps(safe_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        fieldnames = list(asdict(rows[0]).keys()) if rows else list(TrialRecord.__dataclass_fields__.keys())
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for payload in safe_rows:
                payload["manual_action_fields"] = json.dumps(payload["manual_action_fields"], ensure_ascii=False)
                payload["input_types"] = json.dumps(payload["input_types"], ensure_ascii=False)
                writer.writerow(payload)
        return {"csv": csv_path, "json": json_path, "summary": summary_path}


class TrialStepLogger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def log(self, *, site_id: str, step: str, status: str, details: Mapping[str, Any] | None = None) -> Path:
        payload = _strictly_sanitize({
            "site_id": site_id,
            "step": step,
            "status": status,
            "details": dict(details or {}),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        assert_no_personal_info(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return self.path
