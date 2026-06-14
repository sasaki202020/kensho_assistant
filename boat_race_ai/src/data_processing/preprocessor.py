from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

import numpy as np
import pandas as pd

from ..constants import GRADE_ORDER, WEATHER_CATEGORIES
from ..utils import clean_text, parse_float, to_datetime_series


NUMERIC_COLUMNS = [
    "course_id",
    "race_number",
    "wind_speed",
    "water_temp",
    "wave_height",
    "lane",
    "age",
    "weight",
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
    "start_exhibition_course",
    "start_exhibition_lane",
    "start_exhibition_st",
    "finish_position",
    "race_time_value",
    "actual_start_time",
    "win_odds",
    "place_odds_low",
    "place_odds_high",
]


def _first_numeric(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        value = text
    return parse_float(value, default=None)


@dataclass
class BoatRacePreprocessor:
    numeric_medians_: dict[str, float] = field(default_factory=dict)
    weather_categories_: list[str] = field(default_factory=list)
    grade_mapping_: dict[str, int] = field(default_factory=dict)
    fitted_: bool = False

    def fit(self, df: pd.DataFrame) -> "BoatRacePreprocessor":
        frame = df.copy()
        frame = self._base_clean(frame)
        self.numeric_medians_ = {}
        for column in NUMERIC_COLUMNS:
            if column in frame.columns:
                series = pd.to_numeric(frame[column], errors="coerce")
                median = series.median()
                if pd.isna(median):
                    median = 0.0
                self.numeric_medians_[column] = float(median)
        present_weather = [clean_text(value) for value in frame.get("weather", pd.Series(dtype=str)).dropna().unique().tolist()]
        self.weather_categories_ = [value for value in WEATHER_CATEGORIES if value in present_weather]
        for value in present_weather:
            if value not in self.weather_categories_ and value:
                self.weather_categories_.append(value)
        self.grade_mapping_ = {grade: idx + 1 for idx, grade in enumerate(GRADE_ORDER)}
        self.fitted_ = True
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.fitted_:
            raise RuntimeError("BoatRacePreprocessor.fit must be called before transform.")
        frame = self._base_clean(df.copy())
        for column in NUMERIC_COLUMNS:
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
                frame[column] = frame[column].fillna(self.numeric_medians_.get(column, 0.0))
            else:
                frame[column] = self.numeric_medians_.get(column, 0.0)
        frame["grade_code"] = frame.get("grade", "").astype(str).str.upper().map(self.grade_mapping_).fillna(0).astype(float)
        weather_map = {weather: idx + 1 for idx, weather in enumerate(self.weather_categories_)}
        frame["weather_code"] = frame.get("weather", "").astype(str).map(weather_map).fillna(0).astype(float)
        if "race_date" in frame.columns:
            frame["race_date"] = to_datetime_series(frame["race_date"])
        return frame

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.fit(df).transform(df)

    def _base_clean(self, frame: pd.DataFrame) -> pd.DataFrame:
        for column in ["race_id", "course_id", "course_name", "race_title", "race_class", "racer_id", "name", "grade", "weather", "decision", "propeller", "parts_exchange", "race_time"]:
            if column in frame.columns:
                frame[column] = frame[column].where(frame[column].notna(), None).map(clean_text)
        if "race_date" in frame.columns:
            frame["race_date"] = to_datetime_series(frame["race_date"])
        for column in frame.columns:
            if column in {"race_id", "course_name", "race_title", "race_class", "racer_id", "name", "grade", "weather", "decision", "propeller", "parts_exchange"}:
                continue
            if frame[column].dtype == "object":
                sample = frame[column].dropna().head(5).tolist()
                if any(isinstance(value, str) and re.search(r"\d", value) for value in sample):
                    frame[column] = frame[column].map(_first_numeric)
        if "race_time" in frame.columns:
            frame["race_time_value"] = frame["race_time"].map(lambda x: parse_float(x, default=np.nan))
        return frame
