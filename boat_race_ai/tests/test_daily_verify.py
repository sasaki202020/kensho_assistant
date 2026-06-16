from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.daily_ops import DailyPaths
from src.daily_verify import verify_daily_artifacts


def test_verify_daily_artifacts_accepts_complete_morning_outputs(tmp_path: Path) -> None:
    paths = DailyPaths(tmp_path, "2026-06-14")
    pd.DataFrame([{"race_id": "r1", "lane": 1}]).to_csv(paths.predictions_csv, index=False)
    paths.predictions_json.write_text("[]", encoding="utf-8")
    paths.morning_run_json.write_text("{}", encoding="utf-8")
    paths.coverage_json.write_text("{}", encoding="utf-8")

    result = verify_daily_artifacts("2026-06-14", project_root=tmp_path, stage="morning", write_file=True)

    assert result["status"] == "ok"
    assert result["missing_count"] == 0
    assert result["row_counts"]["predictions_rows"] == 1
    assert (paths.daily_dir / "verify_morning.json").exists()
    assert result["verify_json"].endswith("verify_morning.json")


def test_verify_daily_artifacts_reports_missing_night_outputs(tmp_path: Path) -> None:
    result = verify_daily_artifacts("2026-06-14", project_root=tmp_path, stage="night")

    assert result["status"] == "missing"
    assert result["missing_count"] > 0
    assert any("settlement.csv" in item["path"] for item in result["missing_artifacts"])


def test_verify_daily_artifacts_checks_analysis_outputs(tmp_path: Path) -> None:
    out = tmp_path / "output" / "analysis" / "profitability"
    out.mkdir(parents=True)
    for name in [
        "profitability_summary.json",
        "profitability_report.md",
        "profitability_daily_history.csv",
        "candidate_conditions.csv",
        "candidate_conditions.json",
        "candidate_rejections.csv",
        "candidate_rejection_summary.json",
        "candidate_condition_history.csv",
        "current_cli_slices.csv",
    ]:
        (out / name).write_text("x", encoding="utf-8")

    result = verify_daily_artifacts("2026-06-14", project_root=tmp_path, stage="analysis")

    assert result["status"] == "ok"
    assert result["checked_count"] == 9


def test_verify_daily_artifacts_detects_prediction_coverage_row_mismatch(tmp_path: Path) -> None:
    paths = DailyPaths(tmp_path, "2026-06-14")
    pd.DataFrame([{"race_id": "r1", "lane": 1}]).to_csv(paths.predictions_csv, index=False)
    paths.predictions_json.write_text("[]", encoding="utf-8")
    paths.morning_run_json.write_text("{}", encoding="utf-8")
    paths.coverage_json.write_text(json.dumps({"rows": 2}), encoding="utf-8")

    result = verify_daily_artifacts("2026-06-14", project_root=tmp_path, stage="morning")

    assert result["status"] == "invalid"
    assert result["issue_count"] == 1
    assert result["validation_issues"][0]["code"] == "predictions_coverage_row_mismatch"


def test_verify_daily_artifacts_detects_settlement_prediction_row_mismatch(tmp_path: Path) -> None:
    paths = DailyPaths(tmp_path, "2026-06-14")
    pd.DataFrame([{"race_id": "r1", "lane": 1}]).to_csv(paths.predictions_csv, index=False)
    pd.DataFrame([{"race_id": "r1", "lane": 1}, {"race_id": "r1", "lane": 2}]).to_csv(paths.settlement_csv, index=False)
    paths.results_csv.write_text("race_id,lane\nr1,1\n", encoding="utf-8")
    paths.daily_report_json.write_text(json.dumps({"target_date": "2026-06-14"}), encoding="utf-8")
    paths.daily_report_md.write_text("report", encoding="utf-8")
    paths.rolling_summary_csv.write_text("target_date\n2026-06-14\n", encoding="utf-8")

    result = verify_daily_artifacts("2026-06-14", project_root=tmp_path, stage="night")

    assert result["status"] == "invalid"
    assert result["validation_issues"][0]["code"] == "settlement_predictions_row_mismatch"
