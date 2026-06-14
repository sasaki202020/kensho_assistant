from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src import daily_ops


class FakePreprocessor:
    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        return frame.copy()


class ImputingFakePreprocessor:
    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        output = frame.copy()
        output["win_odds"] = 7.3
        return output


class FakeFeatureEngineer:
    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        output = frame.copy()
        output["feat_lane"] = pd.to_numeric(output["lane"], errors="coerce").fillna(0)
        return output


class FakeModel:
    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        output = frame.copy()
        output["pred_prob"] = (7 - pd.to_numeric(output["lane"], errors="coerce").fillna(6)) / 21
        output["pred_rank"] = output.groupby("race_id")["pred_prob"].rank(method="first", ascending=False)
        return output


class FakeFetcher:
    def __init__(self, _config: dict, _project_root: Path) -> None:
        self.target_date = "2026-06-13"

    def __enter__(self) -> "FakeFetcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def discover_course_ids(self, _date_text: str, limit: int | None = None) -> list[str]:
        if limit is not None:
            return ["07"][:limit]
        return ["07"]

    def fetch_day(self, date_text: str, **_kwargs) -> pd.DataFrame:
        records = []
        for race_number in range(1, 13):
            for lane in range(1, 7):
                records.append(
                    {
                        "race_date": pd.to_datetime(date_text),
                        "course_id": "07",
                        "course_name": "蒲郡",
                        "race_id": f"20260613_07_{race_number:02d}",
                        "race_number": race_number,
                        "lane": lane,
                        "racer_id": f"10{race_number}{lane}",
                        "name": f"テスト{race_number}{lane}",
                        "grade": "A1" if lane == 1 else "B1",
                        "age": 30,
                        "weight": 50.0,
                        "win_odds": float(lane + 1),
                    }
                )
        return pd.DataFrame(records)

    def fetch_race(self, date_text: str, _course_id: str, race_number: int, **_kwargs) -> pd.DataFrame:
        frame = self.fetch_day(date_text)
        return frame[frame["race_number"] == race_number].copy()

    def fetch_results_day(self, date_text: str, **_kwargs) -> pd.DataFrame:
        records = []
        for race_number in range(1, 13):
            for lane in range(1, 7):
                records.append(
                    {
                        "race_date": pd.to_datetime(date_text),
                        "course_id": "07",
                        "course_name": "蒲郡",
                        "race_id": f"20260613_07_{race_number:02d}",
                        "race_number": race_number,
                        "lane": lane,
                        "finish_position": lane,
                        "win": int(lane == 1),
                        "place": int(lane <= 2),
                        "show": int(lane <= 3),
                    }
                )
        return pd.DataFrame(records)

    def fetch_result_race_with_status(self, date_text: str, _course_id: str, race_number: int):
        frame = self.fetch_results_day(date_text)
        frame = frame[frame["race_number"] == race_number].copy()
        frame["result_status"] = "settled"
        frame["unavailable_reason"] = ""
        return frame, {
            "stage": "night_fetch",
            "course_id": "07",
            "race_number": race_number,
            "race_id": f"20260613_07_{race_number:02d}",
            "status": "settled",
            "unavailable_reason": "",
            "message": "result parsed",
        }

    def fetch_odds_race(self, date_text: str, _course_id: str, race_number: int, **_kwargs) -> pd.DataFrame:
        records = []
        for lane in range(1, 7):
            records.append(
                {
                    "race_date": pd.to_datetime(date_text),
                    "course_id": "07",
                    "course_name": "蒲郡",
                    "race_id": f"20260613_07_{race_number:02d}",
                    "race_number": race_number,
                    "lane": lane,
                    "win_odds": float(10 + race_number + lane),
                }
            )
        return pd.DataFrame(records)


class MissingOddsFetcher(FakeFetcher):
    def fetch_day(self, date_text: str, **_kwargs) -> pd.DataFrame:
        frame = super().fetch_day(date_text, **_kwargs)
        return frame.drop(columns=["win_odds"])


class ResultPayoutOnlyFetcher(MissingOddsFetcher):
    def fetch_result_race_with_status(self, date_text: str, _course_id: str, race_number: int):
        frame = self.fetch_results_day(date_text)
        frame = frame[frame["race_number"] == race_number].copy()
        frame["result_status"] = "settled"
        frame["unavailable_reason"] = ""
        frame["win_odds"] = pd.NA
        frame.loc[frame["win"] == 1, "win_odds"] = 2.5
        return frame, {
            "stage": "night_fetch",
            "course_id": "07",
            "race_number": race_number,
            "race_id": f"20260613_07_{race_number:02d}",
            "status": "settled",
            "unavailable_reason": "",
            "message": "result parsed",
        }


class UnavailableResultFetcher(FakeFetcher):
    def fetch_result_race_with_status(self, date_text: str, _course_id: str, race_number: int):
        if race_number == 1:
            return super().fetch_result_race_with_status(date_text, _course_id, race_number)
        return pd.DataFrame(), {
            "stage": "night_fetch",
            "course_id": "07",
            "race_number": race_number,
            "race_id": f"20260613_07_{race_number:02d}",
            "status": "unavailable",
            "unavailable_reason": "result_unpublished",
            "message": "result_unpublished",
        }


def _write_config(root: Path) -> Path:
    config = root / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "paths:",
                "  raw_dir: data/raw",
                "  db_path: data/boat_race.db",
                "  model_path: model_bundle.joblib",
                "real:",
                "  min_request_interval_sec: 2.0",
            ]
        ),
        encoding="utf-8",
    )
    (root / "model_bundle.joblib").write_text("placeholder", encoding="utf-8")
    return config


def _patch_bundle(monkeypatch) -> None:
    monkeypatch.setattr(
        daily_ops.joblib,
        "load",
        lambda _path: {
            "preprocessor": FakePreprocessor(),
            "feature_engineer": FakeFeatureEngineer(),
            "model": FakeModel(),
        },
    )


def _patch_imputing_bundle(monkeypatch) -> None:
    monkeypatch.setattr(
        daily_ops.joblib,
        "load",
        lambda _path: {
            "preprocessor": ImputingFakePreprocessor(),
            "feature_engineer": FakeFeatureEngineer(),
            "model": FakeModel(),
        },
    )


def test_daily_morning_writes_predictions_and_preserves_rerun(tmp_path: Path, monkeypatch) -> None:
    config = _write_config(tmp_path)
    _patch_bundle(monkeypatch)
    first = daily_ops.run_morning(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=FakeFetcher,
    )
    predictions = tmp_path / "output" / "daily" / "2026-06-13" / "predictions.csv"
    assert first["status"] == "ok"
    assert predictions.exists()
    before = predictions.read_text(encoding="utf-8-sig")
    second = daily_ops.run_morning(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=FakeFetcher,
    )
    assert second["status"] == "exists"
    assert second["courses"] == 1
    assert predictions.read_text(encoding="utf-8-sig") == before


def test_daily_morning_does_not_output_imputed_odds(tmp_path: Path, monkeypatch) -> None:
    config = _write_config(tmp_path)
    _patch_imputing_bundle(monkeypatch)

    daily_ops.run_morning(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=MissingOddsFetcher,
    )

    predictions = pd.read_csv(tmp_path / "output" / "daily" / "2026-06-13" / "predictions.csv")
    assert "win_odds" in predictions.columns
    assert "expected_value" in predictions.columns
    assert predictions["win_odds"].isna().all()
    assert predictions["expected_value"].isna().all()


def test_refresh_daily_odds_updates_only_odds_fields(tmp_path: Path, monkeypatch) -> None:
    config = _write_config(tmp_path)
    _patch_imputing_bundle(monkeypatch)
    daily_ops.run_morning(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=MissingOddsFetcher,
    )
    before = pd.read_csv(tmp_path / "output" / "daily" / "2026-06-13" / "predictions.csv")

    result = daily_ops.refresh_daily_odds(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=FakeFetcher,
    )

    after = pd.read_csv(tmp_path / "output" / "daily" / "2026-06-13" / "predictions.csv")
    assert result["status"] == "ok"
    assert result["odds_available_rows"] == len(after)
    assert after["win_odds"].notna().all()
    assert after["expected_value"].notna().all()
    pd.testing.assert_series_equal(before["pred_prob"], after["pred_prob"], check_names=False)
    pd.testing.assert_series_equal(before["pred_rank"], after["pred_rank"], check_names=False)
    assert (tmp_path / "output" / "daily" / "2026-06-13" / "odds_refresh.csv").exists()
    assert (tmp_path / "output" / "daily" / "2026-06-13" / "odds_refresh_run.json").exists()


def test_refresh_daily_odds_refuses_after_settlement_exists(tmp_path: Path, monkeypatch) -> None:
    config = _write_config(tmp_path)
    _patch_bundle(monkeypatch)
    daily_ops.run_morning(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=FakeFetcher,
    )
    daily_ops.run_night(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=UnavailableResultFetcher,
    )

    with pytest.raises(RuntimeError, match="Settlement already exists"):
        daily_ops.refresh_daily_odds(
            "2026-06-13",
            config_path=config,
            project_root=tmp_path,
            fetcher_factory=FakeFetcher,
        )


def test_daily_night_settles_predictions_and_reports_unavailable(tmp_path: Path, monkeypatch) -> None:
    config = _write_config(tmp_path)
    _patch_bundle(monkeypatch)
    daily_ops.run_morning(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=FakeFetcher,
    )
    report = daily_ops.run_night(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=UnavailableResultFetcher,
    )
    daily_dir = tmp_path / "output" / "daily" / "2026-06-13"
    assert report["status"] == "partial"
    assert report["races_settled"] == 1
    assert "20260613_07_02" in report["unavailable_races"]
    assert len(report["unavailable_races"]) == 11
    assert report["unavailable_by_reason"] == {"result_unpublished": 11}
    assert report["unavailable_details"][0]["unavailable_reason"] == "result_unpublished"
    settlement = pd.read_csv(daily_dir / "settlement.csv")
    assert "unavailable_reason" in settlement.columns
    results = pd.read_csv(daily_dir / "results.csv")
    assert "unavailable_reason" in results.columns
    assert (daily_dir / "settlement.csv").exists()
    assert (daily_dir / "daily_report.json").exists()
    assert (tmp_path / "output" / "daily" / "rolling_summary.csv").exists()
    daily_ops.run_night(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=UnavailableResultFetcher,
    )
    rolling = pd.read_csv(tmp_path / "output" / "daily" / "rolling_summary.csv")
    assert len(rolling[rolling["target_date"].astype(str) == "2026-06-13"]) == 1


def test_daily_night_uses_result_payout_odds_without_dropping_losing_bets(tmp_path: Path, monkeypatch) -> None:
    config = _write_config(tmp_path)
    _patch_bundle(monkeypatch)
    daily_ops.run_morning(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=MissingOddsFetcher,
    )
    report = daily_ops.run_night(
        "2026-06-13",
        config_path=config,
        project_root=tmp_path,
        fetcher_factory=ResultPayoutOnlyFetcher,
    )

    settlement = pd.read_csv(tmp_path / "output" / "daily" / "2026-06-13" / "settlement.csv")
    assert settlement["win_odds"].notna().sum() == 12
    top2 = next(row for row in report["summary"] if row["strategy"] == "top2_win")
    value_filter = next(row for row in report["summary"] if row["strategy"] == "value_filter")
    assert top2["bets"] == 24
    assert top2["roi_pct"] == 125.0
    assert value_filter["bets"] == 0
