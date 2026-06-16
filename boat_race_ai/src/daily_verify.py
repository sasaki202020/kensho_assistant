from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .daily_ops import DailyPaths, normalize_date


def _file_status(path: Path) -> dict:
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    return {
        "path": str(path),
        "exists": exists,
        "size": int(size),
        "ok": bool(exists and size > 0),
    }


def _csv_row_count(path: Path) -> int | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return int(len(pd.read_csv(path)))
    except Exception:
        return None


def _read_json(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"read_error": str(exc)}


def _required_paths(paths: DailyPaths, stage: str, project_root: Path) -> list[Path]:
    groups = {
        "morning": [
            paths.predictions_csv,
            paths.predictions_json,
            paths.morning_run_json,
            paths.coverage_json,
        ],
        "odds": [
            paths.odds_refresh_csv,
            paths.odds_refresh_run_json,
        ],
        "night": [
            paths.results_csv,
            paths.settlement_csv,
            paths.daily_report_json,
            paths.daily_report_md,
            paths.rolling_summary_csv,
        ],
        "analysis": [
            project_root / "output" / "analysis" / "profitability" / "profitability_summary.json",
            project_root / "output" / "analysis" / "profitability" / "profitability_report.md",
            project_root / "output" / "analysis" / "profitability" / "profitability_daily_history.csv",
            project_root / "output" / "analysis" / "profitability" / "candidate_conditions.csv",
            project_root / "output" / "analysis" / "profitability" / "candidate_conditions.json",
            project_root / "output" / "analysis" / "profitability" / "candidate_rejections.csv",
            project_root / "output" / "analysis" / "profitability" / "candidate_rejection_summary.json",
            project_root / "output" / "analysis" / "profitability" / "candidate_condition_history.csv",
            project_root / "output" / "analysis" / "profitability" / "current_cli_slices.csv",
        ],
    }
    if stage == "full":
        return groups["morning"] + groups["odds"] + groups["night"] + groups["analysis"]
    if stage not in groups:
        raise ValueError(f"unknown verify stage: {stage}")
    return groups[stage]


def _validation_issues(paths: DailyPaths, stage: str, row_counts: dict) -> list[dict]:
    issues: list[dict] = []
    if stage in {"morning", "full"}:
        predictions_rows = row_counts.get("predictions_rows")
        coverage = _read_json(paths.coverage_json)
        coverage_rows = coverage.get("rows")
        if predictions_rows is None or predictions_rows <= 0:
            issues.append({"code": "predictions_empty", "message": "predictions.csv has no readable rows"})
        if coverage_rows is not None and predictions_rows is not None and int(coverage_rows) != int(predictions_rows):
            issues.append(
                {
                    "code": "predictions_coverage_row_mismatch",
                    "message": "predictions.csv row count does not match coverage.json rows",
                    "predictions_rows": int(predictions_rows),
                    "coverage_rows": int(coverage_rows),
                }
            )
    if stage in {"night", "full"}:
        settlement_rows = row_counts.get("settlement_rows")
        predictions_rows = row_counts.get("predictions_rows")
        report = _read_json(paths.daily_report_json)
        if settlement_rows is not None and predictions_rows is not None and int(settlement_rows) != int(predictions_rows):
            issues.append(
                {
                    "code": "settlement_predictions_row_mismatch",
                    "message": "settlement.csv row count does not match predictions.csv rows",
                    "settlement_rows": int(settlement_rows),
                    "predictions_rows": int(predictions_rows),
                }
            )
        if report.get("target_date") and str(report["target_date"]) != paths.target_date:
            issues.append(
                {
                    "code": "daily_report_date_mismatch",
                    "message": "daily_report.json target_date does not match requested date",
                    "report_target_date": str(report["target_date"]),
                    "target_date": paths.target_date,
                }
            )
    return issues


def verify_daily_artifacts(
    target_date: str | None = None,
    *,
    project_root: Path,
    stage: str = "morning",
    write_file: bool = False,
) -> dict:
    date_text = normalize_date(target_date)
    paths = DailyPaths(project_root, date_text)
    statuses = [_file_status(path) for path in _required_paths(paths, stage, project_root)]
    missing = [item for item in statuses if not item["ok"]]
    row_counts = {
        "predictions_rows": _csv_row_count(paths.predictions_csv),
        "settlement_rows": _csv_row_count(paths.settlement_csv),
    }
    issues = _validation_issues(paths, stage, row_counts)
    status = "ok"
    if missing:
        status = "missing"
    elif issues:
        status = "invalid"
    payload = {
        "target_date": date_text,
        "stage": stage,
        "status": status,
        "checked_count": len(statuses),
        "missing_count": len(missing),
        "issue_count": len(issues),
        "missing_artifacts": missing,
        "validation_issues": issues,
        "artifacts": statuses,
        "row_counts": row_counts,
    }
    if write_file:
        output_path = paths.daily_dir / f"verify_{stage}.json"
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["verify_json"] = str(output_path)
    return payload
