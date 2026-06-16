from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd


BASE_FEATURE_COLUMNS = [
    "course_id",
    "race_number",
    "lane",
    "age",
    "weight",
    "grade_code",
    "weather_code",
    "wind_speed",
    "water_temp",
    "wave_height",
    "f_count",
    "l_count",
    "avg_st",
    "national_win_rate",
    "national_2rate",
    "national_3rate",
    "local_win_rate",
    "local_2rate",
    "local_3rate",
    "motor_no",
    "motor_2rate",
    "motor_3rate",
    "boat_no",
    "boat_2rate",
    "boat_3rate",
    "exhibition_time",
    "start_time",
    "tilt",
    "start_exhibition_st",
]


def _ensure_numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        frame[column] = default
    frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(default)
    return frame[column]


def _safe_shifted_cumsum(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").shift(1).fillna(0).cumsum().fillna(0)


def _safe_shifted_mean(series: pd.Series) -> pd.Series:
    shifted = pd.to_numeric(series, errors="coerce").shift(1)
    return shifted.expanding(min_periods=1).mean().fillna(0)


@dataclass
class BoatRaceFeatureEngineer:
    feature_columns_: list[str] = field(default_factory=list)

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        frame = df.copy()
        if frame.empty:
            self.feature_columns_ = []
            return frame

        frame["race_date"] = pd.to_datetime(frame["race_date"], errors="coerce")
        if "course_id" in frame.columns:
            frame["course_id"] = frame["course_id"].astype(str).str.zfill(2)
        else:
            frame["course_id"] = "00"
        frame["racer_id"] = frame.get("racer_id", "").astype(str)
        frame["race_id"] = frame.get("race_id", "").astype(str)

        sort_columns = ["race_date", "course_id", "race_number", "lane"]
        existing_sort_columns = [column for column in sort_columns if column in frame.columns]
        frame = frame.sort_values(existing_sort_columns).reset_index(drop=True)

        for column in BASE_FEATURE_COLUMNS:
            _ensure_numeric(frame, column, default=0.0)
            frame[f"feat_{column}"] = frame[column].astype(float)

        if "win" not in frame.columns:
            frame["win"] = np.nan
        if "place" not in frame.columns:
            frame["place"] = np.nan
        if "show" not in frame.columns:
            frame["show"] = np.nan
        if "finish_position" not in frame.columns:
            frame["finish_position"] = np.nan

        racer_group = frame.groupby("racer_id", sort=False)
        race_group = frame.groupby("race_id", sort=False)
        course_group = frame.groupby(["racer_id", "course_id"], sort=False)

        frame["feat_racer_prior_starts"] = racer_group.cumcount().astype(float)
        frame["feat_racer_prior_wins"] = racer_group["win"].transform(_safe_shifted_cumsum)
        frame["feat_racer_prior_places"] = racer_group["place"].transform(_safe_shifted_cumsum)
        frame["feat_racer_prior_shows"] = racer_group["show"].transform(_safe_shifted_cumsum)
        frame["feat_racer_prior_finish_sum"] = racer_group["finish_position"].transform(_safe_shifted_cumsum)
        frame["feat_racer_prior_avg_finish"] = np.where(
            frame["feat_racer_prior_starts"] > 0,
            frame["feat_racer_prior_finish_sum"] / frame["feat_racer_prior_starts"],
            0.0,
        )
        frame["feat_racer_prior_win_rate"] = np.where(
            frame["feat_racer_prior_starts"] > 0,
            frame["feat_racer_prior_wins"] / frame["feat_racer_prior_starts"],
            0.0,
        )
        frame["feat_racer_prior_place_rate"] = np.where(
            frame["feat_racer_prior_starts"] > 0,
            frame["feat_racer_prior_places"] / frame["feat_racer_prior_starts"],
            0.0,
        )
        frame["feat_racer_prior_show_rate"] = np.where(
            frame["feat_racer_prior_starts"] > 0,
            frame["feat_racer_prior_shows"] / frame["feat_racer_prior_starts"],
            0.0,
        )
        frame["feat_racer_prior_top3_rate"] = np.where(
            frame["feat_racer_prior_starts"] > 0,
            frame["feat_racer_prior_shows"] / frame["feat_racer_prior_starts"],
            0.0,
        )
        frame["feat_racer_prior_avg_st"] = racer_group["start_time"].transform(_safe_shifted_mean)
        frame["feat_racer_prior_avg_exhibition_time"] = racer_group["exhibition_time"].transform(_safe_shifted_mean)
        frame["feat_racer_prior_days_since_last"] = racer_group["race_date"].transform(
            lambda series: series.shift(1).diff().dt.days.fillna(999).astype(float)
        )
        frame["feat_racer_course_starts"] = course_group.cumcount().astype(float)
        frame["feat_racer_course_wins"] = course_group["win"].transform(_safe_shifted_cumsum)
        frame["feat_racer_course_shows"] = course_group["show"].transform(_safe_shifted_cumsum)
        frame["feat_racer_course_win_rate"] = np.where(
            frame["feat_racer_course_starts"] > 0,
            frame["feat_racer_course_wins"] / frame["feat_racer_course_starts"],
            0.0,
        )
        frame["feat_racer_course_top3_rate"] = np.where(
            frame["feat_racer_course_starts"] > 0,
            frame["feat_racer_course_shows"] / frame["feat_racer_course_starts"],
            0.0,
        )

        frame["feat_field_strength"] = (
            0.45 * frame["feat_racer_prior_win_rate"]
            + 0.25 * frame["feat_racer_prior_top3_rate"]
            + 0.20 * frame["national_win_rate"]
            + 0.10 * frame["local_win_rate"]
        )
        frame["feat_history_strength"] = (
            0.50 * frame["feat_racer_prior_win_rate"]
            + 0.30 * frame["feat_racer_course_win_rate"]
            + 0.20 * frame["feat_racer_prior_top3_rate"]
        )

        race_mean_columns = [
            "age",
            "weight",
            "exhibition_time",
            "start_time",
            "avg_st",
            "grade_code",
            "wind_speed",
            "water_temp",
            "wave_height",
            "national_win_rate",
            "local_win_rate",
        ]
        for column in race_mean_columns:
            frame[f"feat_{column}_race_mean"] = race_group[column].transform("mean")
            frame[f"feat_{column}_diff_from_race_mean"] = frame[column] - frame[f"feat_{column}_race_mean"]
            frame[f"feat_{column}_rank_in_race"] = race_group[column].rank(method="average", ascending=True)

        frame["feat_lane_midpoint"] = frame["lane"] - 3.5
        frame["feat_lane_x_grade"] = frame["lane"] * frame["grade_code"]
        frame["feat_lane_x_exhibition"] = frame["lane"] * frame["exhibition_time"]
        frame["feat_lane_x_start"] = frame["lane"] * frame["start_time"]
        frame["feat_weight_x_grade"] = frame["weight"] * frame["grade_code"]
        frame["feat_exhibition_x_grade"] = frame["exhibition_time"] * frame["grade_code"]
        frame["feat_start_x_grade"] = frame["start_time"] * frame["grade_code"]
        frame["feat_wind_x_lane"] = frame["wind_speed"] * frame["lane"]
        frame["feat_wind_x_exhibition"] = frame["wind_speed"] * frame["exhibition_time"]
        frame["feat_environment_pressure"] = frame["wind_speed"] * frame["wave_height"]
        frame["feat_recent_strength"] = (
            0.55 * frame["feat_racer_prior_win_rate"]
            + 0.25 * frame["feat_racer_prior_place_rate"]
            + 0.20 * frame["feat_racer_prior_show_rate"]
        )

        frame["feat_total_strength"] = (
            0.30 * frame["feat_recent_strength"]
            + 0.20 * frame["feat_history_strength"]
            + 0.20 * frame["feat_field_strength"]
            + 0.15 * frame["feat_racer_prior_avg_st"]
            + 0.15 * frame["feat_racer_prior_avg_exhibition_time"]
        )

        if "feat_start_exhibition_st" in frame.columns:
            frame["feat_start_exhibition_rank"] = race_group["start_exhibition_st"].rank(method="average", ascending=True)
        else:
            frame["feat_start_exhibition_rank"] = 0.0

        frame["feat_total_field_mean"] = race_group["feat_total_strength"].transform("mean")
        frame["feat_total_field_diff"] = frame["feat_total_strength"] - frame["feat_total_field_mean"]
        frame["feat_grade_field_rank"] = race_group["grade_code"].rank(method="average", ascending=True)

        frame["feat_course_vs_local"] = frame["local_win_rate"] - frame["national_win_rate"]
        frame["feat_motor_edge"] = frame["motor_2rate"] - frame["boat_2rate"]
        frame["feat_boat_edge"] = frame["boat_3rate"] - frame["motor_3rate"]

        feature_columns = [column for column in frame.columns if column.startswith("feat_")]
        self.feature_columns_ = feature_columns
        return frame

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.transform(df)
