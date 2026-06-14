from __future__ import annotations

from pathlib import Path

import json
import pandas as pd

from src.profitability_analysis import (
    AnalysisPaths,
    legacy_candidate_summary,
    load_legacy_prediction_candidates,
    metric_summary,
    run_analysis,
)


def test_metric_summary_uses_odds_return() -> None:
    frame = pd.DataFrame(
        [
            {"pred_rank": 1, "pred_prob": 0.3, "expected_value": 1.2, "win_odds": 2.0, "win": 1},
            {"pred_rank": 1, "pred_prob": 0.2, "expected_value": 0.8, "win_odds": 4.0, "win": 0},
        ]
    )

    summary = metric_summary(frame, "top1_win", min_sample=10)

    assert summary["bets"] == 2
    assert summary["hit_count"] == 1
    assert summary["hit_rate"] == 0.5
    assert summary["roi_pct"] == 100.0
    assert summary["profit_units"] == 0.0
    assert summary["sample_status"] == "insufficient_sample"


def test_metric_summary_counts_losing_bets_without_odds() -> None:
    frame = pd.DataFrame(
        [
            {"pred_rank": 1, "pred_prob": 0.3, "expected_value": None, "win_odds": 2.5, "win": 1},
            {"pred_rank": 1, "pred_prob": 0.2, "expected_value": None, "win_odds": None, "win": 0},
        ]
    )

    summary = metric_summary(frame, "top1_win", min_sample=10)

    assert summary["bets"] == 2
    assert summary["hit_count"] == 1
    assert summary["hit_rate"] == 0.5
    assert summary["roi_pct"] == 125.0
    assert summary["profit_units"] == 0.5


def test_run_analysis_writes_shadow_outputs(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    day = daily / "2026-06-13"
    day.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "race_date": "2026-06-13",
                "course_id": "01",
                "race_id": "r1",
                "lane": 1,
                "pred_rank": 1,
                "pred_prob": 0.4,
                "expected_value": 1.4,
                "win_odds": 2.5,
                "win": 1,
                "result_status": "settled",
            },
            {
                "race_date": "2026-06-13",
                "course_id": "01",
                "race_id": "r1",
                "lane": 2,
                "pred_rank": 2,
                "pred_prob": 0.2,
                "expected_value": 0.9,
                "win_odds": 3.0,
                "win": 0,
                "result_status": "settled",
            },
        ]
    ).to_csv(day / "settlement.csv", index=False)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    pd.DataFrame(
        [
            {
                "date": "2026-06-13",
                "settledBetCount": 1,
                "hitCount": 1,
                "stakeAmount": 100,
                "payoutAmount": 250,
            }
        ]
    ).to_csv(legacy / "daily_summary_history.csv", index=False)

    payload = run_analysis(
        AnalysisPaths(current_daily_root=daily, legacy_daily_root=legacy, output_dir=tmp_path / "out"),
        min_sample=10,
        bankroll_yen=10000,
    )

    assert payload["analysis_status"] == "shadow_only"
    assert payload["recommendation"]["decision"] == "paper_trade_only"
    assert payload["recommendation"]["live_betting_allowed"] is False
    assert payload["bankroll_guard"]["unit_stake_yen"] == 0
    assert payload["current"]["days"] == 1
    assert payload["legacy"]["unique_dates"] == 1
    assert payload["analysis_date"] == "2026-06-13"
    assert (tmp_path / "out" / "profitability_summary.json").exists()
    assert (tmp_path / "out" / "candidate_conditions.csv").exists()
    assert (tmp_path / "out" / "candidate_conditions.json").exists()
    assert (tmp_path / "out" / "candidate_rejections.csv").exists()
    assert (tmp_path / "out" / "candidate_rejection_summary.json").exists()
    assert (tmp_path / "out" / "profitability_daily_history.csv").exists()
    assert (tmp_path / "out" / "candidate_condition_history.csv").exists()
    assert (tmp_path / "out" / "current_cli_slices.csv").exists()
    assert (tmp_path / "out" / "profitability_report.md").exists()


def test_run_analysis_extracts_only_stable_shadow_candidates(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    for index, date_text in enumerate(["2026-06-11", "2026-06-12", "2026-06-13"], start=1):
        day = daily / date_text
        day.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "race_date": date_text,
                    "course_id": "01",
                    "race_id": f"r{index}",
                    "lane": 1,
                    "pred_rank": 1,
                    "pred_prob": 0.4,
                    "expected_value": 1.4,
                    "win_odds": 2.0,
                    "win": 1,
                    "result_status": "settled",
                },
                {
                    "race_date": date_text,
                    "course_id": "01",
                    "race_id": f"r{index}",
                    "lane": 2,
                    "pred_rank": 2,
                    "pred_prob": 0.2,
                    "expected_value": 0.8,
                    "win_odds": 4.0,
                    "win": 0,
                    "result_status": "settled",
                },
            ]
        ).to_csv(day / "settlement.csv", index=False)

    payload = run_analysis(
        AnalysisPaths(current_daily_root=daily, legacy_daily_root=None, output_dir=tmp_path / "out"),
        min_sample=3,
        min_days=3,
        min_roi_pct=105.0,
        min_positive_day_rate=0.5,
        min_daily_roi_floor_pct=80.0,
        bankroll_yen=10000,
    )
    candidates = payload["candidate_conditions"]

    assert payload["recommendation"]["decision"] == "candidate_found_requires_manual_review"
    assert payload["recommendation"]["live_betting_allowed"] is True
    assert candidates
    assert all(row["candidate_status"] == "shadow_only_candidate" for row in candidates)
    assert all(row["production_adoption"] is False for row in candidates)
    assert all(row["daily_roi_days"] >= 3 for row in candidates)
    assert all(row["daily_roi_min"] >= 80.0 for row in candidates)


def test_run_analysis_reports_candidate_rejection_reasons(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    day = daily / "2026-06-13"
    day.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "race_date": "2026-06-13",
                "course_id": "01",
                "race_id": "r1",
                "lane": 1,
                "pred_rank": 1,
                "pred_prob": 0.4,
                "expected_value": 1.4,
                "win_odds": 2.0,
                "win": 0,
                "result_status": "settled",
            }
        ]
    ).to_csv(day / "settlement.csv", index=False)

    payload = run_analysis(
        AnalysisPaths(current_daily_root=daily, legacy_daily_root=None, output_dir=tmp_path / "out"),
        min_sample=10,
        min_days=3,
        min_roi_pct=105.0,
    )
    rejection = payload["candidate_rejection_summary"]
    rejections = pd.read_csv(tmp_path / "out" / "candidate_rejections.csv")

    assert payload["candidate_conditions"] == []
    assert rejection["rejected_count"] > 0
    assert rejection["failed_gate_counts"]["min_sample"] > 0
    assert not rejections.empty
    assert "min_sample" in ",".join(rejections["failed_gates"].dropna().astype(str).tolist())


def test_run_analysis_overwrites_stale_optional_csv_outputs(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    output = tmp_path / "out"
    output.mkdir()
    (output / "legacy_daily_summary.csv").write_text("stale,value\n1,2\n", encoding="utf-8")
    (output / "legacy_prediction_candidates.csv").write_text("stale,value\n1,2\n", encoding="utf-8")

    payload = run_analysis(
        AnalysisPaths(current_daily_root=daily, legacy_daily_root=None, output_dir=output),
        min_sample=3,
    )

    assert payload["current"]["rows"] == 0
    assert "stale" not in (output / "legacy_daily_summary.csv").read_text(encoding="utf-8")
    assert "stale" not in (output / "legacy_prediction_candidates.csv").read_text(encoding="utf-8")
    assert (output / "candidate_conditions.csv").exists()


def test_run_analysis_history_is_idempotent_by_analysis_date(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    day = daily / "2026-06-13"
    day.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "race_date": "2026-06-13",
                "course_id": "01",
                "race_id": "r1",
                "lane": 1,
                "pred_rank": 1,
                "pred_prob": 0.4,
                "expected_value": 1.4,
                "win_odds": 2.0,
                "win": 1,
                "result_status": "settled",
            }
        ]
    ).to_csv(day / "settlement.csv", index=False)

    paths = AnalysisPaths(current_daily_root=daily, legacy_daily_root=None, output_dir=tmp_path / "out")
    run_analysis(paths, min_sample=1, target_date="2026-06-13")
    run_analysis(paths, min_sample=1, target_date="2026-06-13")

    daily_history = pd.read_csv(tmp_path / "out" / "profitability_daily_history.csv")
    candidate_history = pd.read_csv(tmp_path / "out" / "candidate_condition_history.csv")

    assert len(daily_history[daily_history["analysis_date"].astype(str) == "2026-06-13"]) == 1
    assert candidate_history["analysis_date"].astype(str).nunique() <= 1


def test_load_legacy_prediction_candidates_scores_trifecta(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    payload = {
        "date": "20260613",
        "settlements": [
            {
                "date": "20260613",
                "jcd": "01",
                "venue": "桐生",
                "raceNo": 1,
                "actualTrifecta": "1-2-3",
                "trifectaPayout": 1200,
                "predictions": [
                    {"combo": "1-2-3", "decision": "WATCH", "rank": 1, "prob": 0.1},
                    {"combo": "1-3-2", "decision": "WATCH", "rank": 2, "prob": 0.05},
                ],
            }
        ],
    }
    (legacy / "20260613_summary.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    candidates = load_legacy_prediction_candidates(legacy)
    summary = legacy_candidate_summary(candidates, min_sample=10)
    rank1 = next(row for row in summary if row["strategy"] == "legacy_trifecta_rank1")

    assert len(candidates) == 2
    assert int(candidates["hit"].sum()) == 1
    assert rank1["bets"] == 1
    assert rank1["hit_count"] == 1
    assert rank1["roi_pct"] == 1200.0
