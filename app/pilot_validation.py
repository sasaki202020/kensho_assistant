from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..pilot.build_fingerprint import build_fingerprint, default_pilot_files
from .auto_apply_engine import AutoApplyEngine
from .entry_url_resolver import target_url_for_campaign
from .real_site_trials import (
    ErrorCategory,
    TrialRecord,
    TrialStore,
    build_trial_record,
    safe_site_identifier,
    trial_from_engine_result,
)
from .pilot_safety import (
    compare_storage_snapshots,
    ensure_pilot_storage,
    scan_for_forbidden_values,
    sensitive_profile_values,
    snapshot_storage,
)
from .submission_guard import INSTALL_SCRIPT, install_submission_guard_on_context
from .version import APP_VERSION


PILOT_SITE_COUNT = 5
PILOT_ATTEMPTS_PER_SITE = 3


class PilotTrialStore(TrialStore):
    """Marker store that prevents pilot evidence from entering normal trial history."""


def _canonical_hash(value: Any, length: int = 16) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _safe_candidate_ref(row: Mapping[str, Any]) -> str:
    value = str(row.get("campaign_id", "") or row.get("queue_id", "")).strip()
    if not value or "://" in value or "@" in value:
        raise ValueError("candidate_ref must be a non-PII local identifier")
    return value


def create_pilot_manifest(
    candidates: Iterable[Mapping[str, Any]],
    *,
    limit_sites: int = PILOT_SITE_COUNT,
) -> dict[str, Any]:
    entries: list[dict[str, str]] = []
    seen_sites: set[str] = set()
    for row in candidates:
        url = target_url_for_campaign(dict(row))
        if not str(url).startswith(("http://", "https://")):
            continue
        site_id = safe_site_identifier(url)
        if site_id in seen_sites:
            continue
        candidate_ref = _safe_candidate_ref(row)
        entry_id = f"entry-{_canonical_hash({'candidate_ref': candidate_ref, 'site_id': site_id}, 12)}"
        entries.append(
            {
                "entry_id": entry_id,
                "candidate_ref": candidate_ref,
                "site_id": site_id,
                "site_category": str(row.get("site_category", "unknown") or "unknown"),
            }
        )
        seen_sites.add(site_id)
        if len(entries) >= limit_sites:
            break
    if len(entries) != limit_sites:
        raise ValueError(f"pilot requires {limit_sites} unique sites; found {len(entries)}")
    core = {
        "mode": "pilot",
        "attempts_per_site": PILOT_ATTEMPTS_PER_SITE,
        "entries": entries,
    }
    return {
        "manifest_id": f"pilot-{_canonical_hash(core)}",
        **core,
    }


def save_pilot_manifest(manifest: Mapping[str, Any], path: Path) -> Path:
    validation = validate_pilot_manifest(manifest)
    if not validation["valid"]:
        raise ValueError("invalid pilot manifest: " + ", ".join(validation["errors"]))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_pilot_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validation = validate_pilot_manifest(data)
    if not validation["valid"]:
        raise ValueError("invalid pilot manifest: " + ", ".join(validation["errors"]))
    return data


def validate_pilot_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    entries = manifest.get("entries") if isinstance(manifest.get("entries"), list) else []
    if manifest.get("mode") != "pilot":
        errors.append("mode must be pilot")
    if int(manifest.get("attempts_per_site", 0) or 0) != PILOT_ATTEMPTS_PER_SITE:
        errors.append("attempts_per_site must be 3")
    if len(entries) != PILOT_SITE_COUNT:
        errors.append("entries must contain exactly 5 sites")
    site_ids: set[str] = set()
    entry_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            errors.append("entry must be an object")
            continue
        forbidden_text = json.dumps(dict(entry), ensure_ascii=False)
        if "://" in forbidden_text or "@" in forbidden_text:
            errors.append("entry contains URL or PII")
        site_id = str(entry.get("site_id", ""))
        entry_id = str(entry.get("entry_id", ""))
        if not site_id or not entry_id or not entry.get("candidate_ref"):
            errors.append("entry identifiers are required")
        if site_id in site_ids or entry_id in entry_ids:
            errors.append("duplicate site_id or entry_id")
        site_ids.add(site_id)
        entry_ids.add(entry_id)
    core = {
        "mode": manifest.get("mode"),
        "attempts_per_site": manifest.get("attempts_per_site"),
        "entries": entries,
    }
    expected_id = f"pilot-{_canonical_hash(core)}"
    if manifest.get("manifest_id") != expected_id:
        errors.append("manifest_id does not match content")
    return {"valid": not errors, "errors": errors, "site_count": len(site_ids)}


def build_pilot_plan(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    validation = validate_pilot_manifest(manifest)
    if not validation["valid"]:
        raise ValueError("invalid pilot manifest: " + ", ".join(validation["errors"]))
    plan: list[dict[str, Any]] = []
    for entry in manifest["entries"]:
        for attempt_no in range(1, PILOT_ATTEMPTS_PER_SITE + 1):
            plan.append({**entry, "manifest_id": manifest["manifest_id"], "attempt_no": attempt_no})
    return plan


def config_fingerprint() -> str:
    return _canonical_hash(
        {
            "app_version": APP_VERSION,
            "mode": "pilot",
            "run_mode": "dry_run",
            "auto_submit": False,
            "submission_guard": hashlib.sha256(INSTALL_SCRIPT.encode("utf-8")).hexdigest(),
        }
    )


def git_commit_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "unavailable"


def git_branch_name() -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            check=True,
            capture_output=True,
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "unavailable"
    except Exception:
        return "unavailable"


def git_worktree_status() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "unavailable"


def pilot_build_preflight(
    manifest: Mapping[str, Any],
    *,
    manifest_path: Path | None = None,
    candidates_path: Path | None = None,
) -> dict[str, Any]:
    current_branch = git_branch_name()
    current_head = git_commit_sha()
    worktree_status = git_worktree_status()
    expected_branch = str(manifest.get("git_branch", "") or "").strip()
    expected_head = str(manifest.get("pilot_commit", "") or "").strip()
    expected_fingerprint = str(manifest.get("build_fingerprint_sha256", "") or "").strip()
    errors: list[str] = []

    if worktree_status == "unavailable":
        errors.append("worktree_unavailable")
    elif worktree_status:
        errors.append("worktree_dirty")
    if not expected_branch:
        errors.append("manifest_git_branch_missing")
    elif current_branch == "unavailable":
        errors.append("git_branch_unavailable")
    elif expected_branch != current_branch:
        errors.append("git_branch_mismatch")
    if not expected_head:
        errors.append("manifest_pilot_commit_missing")
    elif current_head == "unavailable":
        errors.append("git_head_unavailable")
    elif expected_head != current_head:
        errors.append("git_head_mismatch")
    if not expected_fingerprint:
        errors.append("manifest_build_fingerprint_missing")
    fingerprint_matches: bool | None = None
    if manifest_path is not None or candidates_path is not None:
        if manifest_path is None or candidates_path is None:
            errors.append("fingerprint_inputs_missing")
        else:
            project_root = Path(__file__).resolve().parents[1]
            resolved_inputs = [Path(manifest_path).resolve(), Path(candidates_path).resolve()]
            if any(project_root not in path.parents and path != project_root for path in resolved_inputs):
                errors.append("fingerprint_path_outside_project")
            elif not all(path.is_file() for path in resolved_inputs):
                errors.append("fingerprint_input_not_found")
            elif expected_fingerprint:
                try:
                    actual_fingerprint = build_fingerprint(
                        default_pilot_files(),
                        resolved_inputs[0],
                        resolved_inputs[1],
                    )
                    fingerprint_matches = actual_fingerprint == expected_fingerprint
                    if not fingerprint_matches:
                        errors.append("build_fingerprint_mismatch")
                except Exception:
                    errors.append("build_fingerprint_unavailable")

    return {
        "valid": not errors,
        "errors": errors,
        "current_branch": current_branch,
        "current_head": current_head,
        "worktree_clean": worktree_status == "",
        "expected_branch": expected_branch,
        "expected_head": expected_head,
        "has_build_fingerprint": bool(expected_fingerprint),
        "fingerprint_matches": fingerprint_matches,
    }


def pilot_candidate_preflight(
    manifest: Mapping[str, Any],
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    candidate_map: dict[str, Mapping[str, Any]] = {}
    for row in candidates:
        try:
            candidate_map[_safe_candidate_ref(row)] = row
        except ValueError:
            continue
    missing_count = 0
    site_mismatch_count = 0
    ineligible_count = 0
    for entry in manifest.get("entries", []):
        candidate = candidate_map.get(str(entry.get("candidate_ref", "")))
        if candidate is None:
            missing_count += 1
            continue
        try:
            url = target_url_for_campaign(dict(candidate))
            if safe_site_identifier(url) != str(entry.get("site_id", "")):
                site_mismatch_count += 1
        except Exception:
            site_mismatch_count += 1
        if str(candidate.get("queue_status", "") or "") not in {"APPROVED", "PREPARED", "HOLD"}:
            ineligible_count += 1
    errors: list[str] = []
    if missing_count:
        errors.append("candidate_ref_missing")
    if site_mismatch_count:
        errors.append("candidate_site_mismatch")
    if ineligible_count:
        errors.append("candidate_not_approved")
    return {
        "valid": not errors,
        "errors": errors,
        "missing_count": missing_count,
        "site_mismatch_count": site_mismatch_count,
        "ineligible_count": ineligible_count,
    }


def pilot_structure_summary(records: Iterable[TrialRecord], manifest_id: str) -> dict[str, Any]:
    rows = [record for record in records if record.manifest_id == manifest_id]
    per_site: dict[str, int] = {}
    attempts_by_entry: dict[str, set[int]] = {}
    duplicate_keys: set[tuple[str, str, int]] = set()
    seen_keys: set[tuple[str, str, int]] = set()
    for row in rows:
        per_site[row.site_id] = per_site.get(row.site_id, 0) + 1
        attempts_by_entry.setdefault(row.entry_id, set()).add(row.attempt_no)
        key = (row.manifest_id, row.entry_id, row.attempt_no)
        if key in seen_keys:
            duplicate_keys.add(key)
        seen_keys.add(key)
    structural_pass = (
        len(rows) == PILOT_SITE_COUNT * PILOT_ATTEMPTS_PER_SITE
        and len(per_site) == PILOT_SITE_COUNT
        and all(count == PILOT_ATTEMPTS_PER_SITE for count in per_site.values())
        and all(attempts == {1, 2, 3} for attempts in attempts_by_entry.values())
        and not duplicate_keys
    )
    return {
        "manifest_id": manifest_id,
        "trial_count": len(rows),
        "site_count": len(per_site),
        "per_site_trial_counts": per_site,
        "duplicate_trial_keys": len(duplicate_keys),
        "structural_pass": structural_pass,
    }


def _build_evidence(
    trial: TrialRecord,
    *,
    plan_item: Mapping[str, Any],
    run_id: str,
    actual_browser: str,
    browser_version: str,
    execution_status: str,
) -> TrialRecord:
    trial_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{plan_item['manifest_id']}:{plan_item['entry_id']}:{plan_item['attempt_no']}"))
    return replace(
        trial,
        trial_id=trial_id,
        manifest_id=str(plan_item["manifest_id"]),
        entry_id=str(plan_item["entry_id"]),
        attempt_no=int(plan_item["attempt_no"]),
        run_id=run_id,
        git_commit_sha=git_commit_sha(),
        config_fingerprint=config_fingerprint(),
        execution_status=execution_status,
        app_version=APP_VERSION,
        python_version=platform.python_version(),
        browser_name=actual_browser,
        browser_version=browser_version,
        os_name=platform.system(),
        pilot_run_id=run_id,
        trial_number=int(plan_item["attempt_no"]),
        result=trial.grade,
        stop_reason=trial.error_category if trial.error_category != ErrorCategory.NONE.value else "",
        pii_persisted=False,
        candidate_state_changed=False,
        auto_submit_detected=trial.unintended_submission,
    )


def run_pilot_manifest(
    manifest: Mapping[str, Any],
    *,
    candidates: Iterable[Mapping[str, Any]],
    store: TrialStore,
    browser: Any,
    actual_browser: str,
    engine: Any,
    profile: Mapping[str, Any],
    review_callback: Callable[[Any, TrialRecord], None],
    protected_storage_root: Path,
    pilot_storage_root: Path,
) -> dict[str, Any]:
    if not isinstance(store, PilotTrialStore):
        raise ValueError("pilot_store_required")
    if str(getattr(engine, "run_mode", "")) != "dry_run":
        raise ValueError("pilot-run requires a dry_run engine")
    ensure_pilot_storage(pilot_storage_root)
    try:
        protected_before = snapshot_storage(protected_storage_root, excluded_root=pilot_storage_root)
    except Exception as exc:
        raise RuntimeError("candidate_state_snapshot_failed") from exc
    plan = build_pilot_plan(manifest)
    candidate_map = {_safe_candidate_ref(row): dict(row) for row in candidates}
    existing = {
        (record.manifest_id, record.entry_id, record.attempt_no)
        for record in store.load(manifest_id=str(manifest["manifest_id"]))
    }
    run_id = str(uuid.uuid4())
    recorded = 0
    already_recorded = 0
    contexts_created = 0
    halted = False
    halt_reason = ""
    browser_version = str(getattr(browser, "version", "unknown") or "unknown")
    for plan_item in plan:
        key = (str(plan_item["manifest_id"]), str(plan_item["entry_id"]), int(plan_item["attempt_no"]))
        if key in existing:
            already_recorded += 1
            continue
        campaign = candidate_map.get(str(plan_item["candidate_ref"]))
        if campaign is None:
            raise ValueError(f"candidate_ref not found: {plan_item['candidate_ref']}")
        url = target_url_for_campaign(campaign)
        if safe_site_identifier(url) != plan_item["site_id"]:
            raise ValueError(f"candidate site mismatch: {plan_item['entry_id']}")
        context = browser.new_context()
        install_submission_guard_on_context(context)
        contexts_created += 1
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            result = engine.run(
                page,
                campaign,
                profile,
                persist_artifacts=False,
                keep_submission_guard=True,
            )
            finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
            trial = trial_from_engine_result(
                campaign=campaign,
                url=url,
                result=result,
                started_at=started_at,
                finished_at=finished_at,
            )
            trial = _build_evidence(
                trial,
                plan_item=plan_item,
                run_id=run_id,
                actual_browser=actual_browser,
                browser_version=browser_version,
                execution_status="COMPLETED",
            )
            record = result.get("record") if isinstance(result.get("record"), Mapping) else {}
            unsafe_artifact_paths = [
                str(record.get(key, "") or "")
                for key in ("screenshot_path", "html_snapshot_path", "analysis_path", "check_path", "trace_path", "storage_state_path")
            ]
            if any(unsafe_artifact_paths):
                trial = replace(
                    trial,
                    execution_status="ERROR",
                    result="C",
                    stop_reason="UNSAFE_ARTIFACT_POLICY",
                )
            review_callback(page, trial)
        except Exception:
            finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
            trial = build_trial_record(
                site_id=str(plan_item["site_id"]),
                url=url,
                started_at=started_at,
                finished_at=finished_at,
                recognized_fields=0,
                filled_fields=0,
                unfilled_fields=0,
                manual_interventions=1,
                final_step="PILOT_ERROR",
                error_category=ErrorCategory.UNKNOWN.value,
                recoverable=False,
                unintended_submission=False,
                site_category=str(plan_item.get("site_category", "unknown")),
            )
            trial = _build_evidence(
                trial,
                plan_item=plan_item,
                run_id=run_id,
                actual_browser=actual_browser,
                browser_version=browser_version,
                execution_status="ERROR",
            )
        finally:
            context.close()
        try:
            protected_after = snapshot_storage(protected_storage_root, excluded_root=pilot_storage_root)
        except Exception as exc:
            raise RuntimeError("candidate_state_snapshot_failed") from exc
        state_comparison = compare_storage_snapshots(protected_before, protected_after)
        if not state_comparison["identical"]:
            trial = replace(
                trial,
                execution_status="ERROR",
                candidate_state_changed=True,
                result="C",
                stop_reason="CANDIDATE_STATE_CHANGED",
            )
        if trial.screenshot_path or trial.stop_reason == "UNSAFE_ARTIFACT_POLICY":
            trial = replace(
                trial,
                execution_status="ERROR",
                result="C",
                stop_reason="UNSAFE_ARTIFACT_POLICY",
            )
        try:
            store.append(trial)
        except Exception as exc:
            raise RuntimeError("pilot_evidence_write_failed") from exc
        try:
            pii_scan = scan_for_forbidden_values(pilot_storage_root, sensitive_profile_values(profile))
        except Exception as exc:
            raise RuntimeError("pii_persistence_check_failed") from exc
        existing.add(key)
        recorded += 1
        if not pii_scan["clean"]:
            halted = True
            halt_reason = "PII_PERSISTED_OR_UNSAFE_ARTIFACT"
        elif trial.candidate_state_changed:
            halted = True
            halt_reason = "CANDIDATE_STATE_CHANGED"
        elif trial.stop_reason == "UNSAFE_ARTIFACT_POLICY":
            halted = True
            halt_reason = "UNSAFE_ARTIFACT_POLICY"
        elif trial.unintended_submission:
            halted = True
            halt_reason = "UNINTENDED_SUBMISSION"
        elif trial.error_category in {
            ErrorCategory.SUBMIT_GUARD_TRIGGERED.value,
            ErrorCategory.CAPTCHA_REQUIRED.value,
            ErrorCategory.LOGIN_REQUIRED.value,
            ErrorCategory.SNS_AUTH_REQUIRED.value,
            ErrorCategory.EMAIL_OR_SMS_AUTH_REQUIRED.value,
            ErrorCategory.UNKNOWN.value,
        }:
            halted = True
            halt_reason = trial.error_category
        if halted:
            break
    return {
        "manifest_id": manifest["manifest_id"],
        "run_id": run_id,
        "planned": len(plan),
        "recorded": recorded,
        "already_recorded": already_recorded,
        "contexts_created": contexts_created,
        "halted": halted,
        "halt_reason": halt_reason,
        "pii_persisted": halt_reason == "PII_PERSISTED_OR_UNSAFE_ARTIFACT",
        "candidate_state_changed": halt_reason == "CANDIDATE_STATE_CHANGED",
        "auto_submit_detected": halt_reason == "UNINTENDED_SUBMISSION",
        "submitted_count_auto": 0,
    }


def launch_pilot_browser(playwright: Any, browser_name: str) -> tuple[Any, str]:
    if browser_name == "chrome":
        try:
            return playwright.chromium.launch(channel="chrome", headless=False), "chrome"
        except Exception:
            pass
    return playwright.chromium.launch(headless=False), "chromium"
