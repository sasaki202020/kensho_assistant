from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.daily_status import build_daily_status


def test_daily_status_waits_for_odds_refresh_window_when_predictions_miss_odds(tmp_path: Path) -> None:
    daily_dir = tmp_path / "output" / "daily" / "2026-06-14"
    daily_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "race_id": "20260614_01_01",
                "course_id": "01",
                "race_number": 1,
                "lane": 1,
                "pred_prob": 0.2,
                "pred_rank": 1,
                "win_odds": None,
                "expected_value": None,
            }
        ]
    ).to_csv(daily_dir / "predictions.csv", index=False)

    status = build_daily_status(
        "2026-06-14",
        project_root=tmp_path,
        now=datetime(2026, 6, 14, 6, 0),
    )

    assert status["predictions"]["rows"] == 1
    assert status["predictions"]["missing_win_odds_rows"] == 1
    assert status["next_action"] == "wait_for_odds_refresh"
    assert status["next_command"] is None
    assert "18:00" in status["next_action_reason"]
    assert status["timing"]["odds_refresh_due"] is False
    assert (daily_dir / "daily_status.json").exists()


def test_daily_status_treats_zero_odds_as_missing(tmp_path: Path) -> None:
    daily_dir = tmp_path / "output" / "daily" / "2026-06-14"
    daily_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "race_id": "20260614_01_01",
                "course_id": "01",
                "race_number": 1,
                "lane": 1,
                "pred_prob": 0.2,
                "pred_rank": 1,
                "win_odds": 0.0,
                "expected_value": 0.0,
            }
        ]
    ).to_csv(daily_dir / "predictions.csv", index=False)

    status = build_daily_status(
        "2026-06-14",
        project_root=tmp_path,
        now=datetime(2026, 6, 14, 6, 0),
    )

    assert status["predictions"]["missing_win_odds_rows"] == 1
    assert status["next_action"] == "wait_for_odds_refresh"


def test_daily_status_points_to_odds_refresh_after_window(tmp_path: Path) -> None:
    daily_dir = tmp_path / "output" / "daily" / "2026-06-14"
    daily_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "race_id": "20260614_01_01",
                "course_id": "01",
                "race_number": 1,
                "lane": 1,
                "pred_prob": 0.2,
                "pred_rank": 1,
                "win_odds": None,
                "expected_value": None,
            }
        ]
    ).to_csv(daily_dir / "predictions.csv", index=False)

    status = build_daily_status(
        "2026-06-14",
        project_root=tmp_path,
        now=datetime(2026, 6, 14, 18, 1),
    )

    assert status["next_action"] == "run_odds_refresh"
    assert status["next_command"] == "py -3.13 daily_run.py --date 2026-06-14 --phase odds --force-refresh"
    assert "miss official win odds" in status["next_action_reason"]
    assert status["timing"]["odds_refresh_due"] is True


def test_daily_status_waits_for_night_settlement_window(tmp_path: Path) -> None:
    daily_dir = tmp_path / "output" / "daily" / "2026-06-14"
    daily_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "race_id": "20260614_01_01",
                "course_id": "01",
                "race_number": 1,
                "lane": 1,
                "pred_prob": 0.2,
                "pred_rank": 1,
                "win_odds": 2.0,
                "expected_value": 0.4,
            }
        ]
    ).to_csv(daily_dir / "predictions.csv", index=False)

    status = build_daily_status(
        "2026-06-14",
        project_root=tmp_path,
        now=datetime(2026, 6, 14, 19, 0),
    )

    assert status["next_action"] == "wait_for_night_settlement"
    assert status["next_command"] is None
    assert "21:30" in status["next_action_reason"]
    assert status["timing"]["night_settlement_due"] is False


def test_daily_status_prioritizes_night_after_window_even_when_odds_missing(tmp_path: Path) -> None:
    daily_dir = tmp_path / "output" / "daily" / "2026-06-14"
    daily_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "race_id": "20260614_01_01",
                "course_id": "01",
                "race_number": 1,
                "lane": 1,
                "pred_prob": 0.2,
                "pred_rank": 1,
                "win_odds": None,
                "expected_value": None,
            }
        ]
    ).to_csv(daily_dir / "predictions.csv", index=False)

    status = build_daily_status(
        "2026-06-14",
        project_root=tmp_path,
        now=datetime(2026, 6, 14, 21, 31),
    )

    assert status["next_action"] == "run_night_after_results"
    assert status["next_command"] == "py -3.13 daily_run.py --date 2026-06-14 --phase night --bankroll-yen 10000"
    assert "still miss official win odds" in status["next_action_reason"]


def test_daily_status_reports_paper_trade_after_settlement(tmp_path: Path) -> None:
    daily_dir = tmp_path / "output" / "daily" / "2026-06-14"
    daily_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "race_id": "20260614_01_01",
                "course_id": "01",
                "race_number": 1,
                "lane": 1,
                "pred_prob": 0.2,
                "pred_rank": 1,
                "win_odds": 2.0,
                "expected_value": 0.4,
            }
        ]
    ).to_csv(daily_dir / "predictions.csv", index=False)
    pd.DataFrame(
        [
            {
                "race_id": "20260614_01_01",
                "lane": 1,
                "result_status": "settled",
                "win": 1,
                "win_odds": 2.0,
            }
        ]
    ).to_csv(daily_dir / "settlement.csv", index=False)
    analysis_dir = tmp_path / "output" / "analysis" / "profitability"
    analysis_dir.mkdir(parents=True)
    (analysis_dir / "profitability_summary.json").write_text(
        json.dumps(
            {
                "analysis_status": "shadow_only",
                "analysis_date": "2026-06-14",
                "recommendation": {"decision": "paper_trade_only", "live_betting_allowed": False},
                "bankroll_guard": {"unit_stake_yen": 0},
                "current": {"days": 1, "settled_rows": 1},
                "stability_gates": {"min_days": 3},
                "candidate_conditions": [],
                "candidate_rejection_summary": {
                    "total_slices": 10,
                    "rejected_count": 10,
                    "dominant_failed_gate": "min_days",
                    "failed_gate_counts": {"min_days": 10},
                },
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "analysis_date": "2026-06-14",
                "analysis_status": "shadow_only",
                "candidate_conditions_count": 0,
            }
        ]
    ).to_csv(analysis_dir / "profitability_daily_history.csv", index=False)
    pd.DataFrame(columns=["analysis_date", "condition_id"]).to_csv(
        analysis_dir / "candidate_condition_history.csv",
        index=False,
    )

    status = build_daily_status(
        "2026-06-14",
        project_root=tmp_path,
        now=datetime(2026, 6, 14, 22, 0),
    )

    assert status["settlement"]["settled_races"] == 1
    assert status["profitability"]["decision"] == "paper_trade_only"
    assert status["profitability"]["history_days"] == 1
    assert status["profitability"]["candidate_history_rows"] == 0
    assert status["profitability"]["min_days_remaining"] == 2
    assert status["profitability"]["dominant_failed_gate"] == "min_days"
    assert status["profitability"]["rejected_count"] == 10
    assert status["next_action"] == "paper_trade_only"
    assert status["next_command"] is None
    assert "min_days" in status["next_action_reason"]
