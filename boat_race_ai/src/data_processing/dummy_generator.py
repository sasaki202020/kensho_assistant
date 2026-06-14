from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from ..constants import COURSE_ID_TO_NAME, GRADE_ORDER, WEATHER_CATEGORIES
from ..utils import race_id_for


@dataclass
class DummyDataGenerator:
    seed: int = 20260613

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self._racer_pool = self._build_racer_pool()

    def _build_racer_pool(self) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for racer_id in range(1001, 1181):
            base_skill = float(self.rng.normal(0.0, 1.0))
            home_course = f"{int(self.rng.integers(1, 25)):02d}"
            grade = self.rng.choice(GRADE_ORDER, p=[0.18, 0.2, 0.42, 0.2])
            rows.append(
                {
                    "racer_id": str(racer_id),
                    "name": f"Racer {racer_id}",
                    "age": int(self.rng.integers(20, 58)),
                    "weight": round(float(self.rng.uniform(49.0, 57.5)), 1),
                    "grade": grade,
                    "skill": base_skill,
                    "home_course": home_course,
                }
            )
        return pd.DataFrame(rows)

    def generate(
        self,
        n_races: int,
        start_date: str | datetime | pd.Timestamp = "2026-06-01",
        course_ids: Iterable[str | int] | None = None,
    ) -> pd.DataFrame:
        course_ids = [f"{int(c):02d}" for c in (course_ids or sorted(COURSE_ID_TO_NAME.keys()))]
        start_dt = pd.to_datetime(start_date).to_pydatetime()
        records: list[dict[str, object]] = []
        for race_idx in range(n_races):
            day_offset = race_idx // (len(course_ids) * 12)
            within_day = race_idx % (len(course_ids) * 12)
            course_id = course_ids[(within_day // 12) % len(course_ids)]
            race_number = within_day % 12 + 1
            race_date = (start_dt + timedelta(days=day_offset)).date()
            race_title = f"Dummy Cup {race_idx % 5 + 1}"
            race_class = self.rng.choice(["一般戦", "G3", "G2", "G1"], p=[0.6, 0.2, 0.1, 0.1])
            distance_m = 1800
            weather = self.rng.choice(WEATHER_CATEGORIES[:4])
            wind_speed = round(float(self.rng.uniform(0.0, 8.0)), 1)
            water_temp = round(float(self.rng.uniform(12.0, 30.0)), 1)
            wave_height = round(float(self.rng.uniform(0.0, 5.0)), 1)

            sampled = self._racer_pool.sample(n=6, replace=False, random_state=int(self.rng.integers(0, 1_000_000)))
            sampled = sampled.copy().reset_index(drop=True)
            sampled["lane"] = np.arange(1, 7)

            lane_adv = {lane: (7 - lane) * 0.18 for lane in range(1, 7)}
            raw_scores = []
            for _, row in sampled.iterrows():
                grade_bonus = {"A1": 0.9, "A2": 0.6, "B1": 0.25, "B2": 0.0}.get(str(row["grade"]), 0.0)
                weather_penalty = {"雨": -0.15, "雪": -0.1, "曇": -0.05, "くもり": -0.05}.get(str(weather), 0.0)
                skill = float(row["skill"]) + grade_bonus + lane_adv[int(row["lane"])]
                skill += 0.03 * (57.0 - float(row["weight"])) + weather_penalty
                skill += float(self.rng.normal(0.0, 0.35))
                raw_scores.append(skill)

            order = np.argsort(raw_scores)[::-1]
            finish_positions = np.empty(6, dtype=int)
            finish_positions[order] = np.arange(1, 7)

            market_logits = np.array(raw_scores) + self.rng.normal(0.0, 0.15, size=6)
            market_probs = np.exp(market_logits - market_logits.max())
            market_probs = market_probs / market_probs.sum()
            odds = np.clip(1.0 / np.maximum(market_probs, 0.03) * 0.9, 1.0, 25.0)

            for row_idx, row in sampled.iterrows():
                lane = int(row["lane"])
                finish_position = int(finish_positions[row_idx])
                record = {
                    "race_id": race_id_for(race_date, course_id, race_number),
                    "race_date": pd.to_datetime(race_date),
                    "course_id": course_id,
                    "course_name": COURSE_ID_TO_NAME.get(course_id, ""),
                    "race_number": race_number,
                    "race_title": race_title,
                    "race_class": race_class,
                    "distance_m": distance_m,
                    "weather": weather,
                    "wind_speed": wind_speed,
                    "water_temp": water_temp,
                    "wave_height": wave_height,
                    "racer_id": str(row["racer_id"]),
                    "name": row["name"],
                    "age": int(row["age"]),
                    "weight": float(row["weight"]),
                    "grade": row["grade"],
                    "lane": lane,
                    "f_count": int(self.rng.integers(0, 5)),
                    "l_count": int(self.rng.integers(0, 5)),
                    "avg_st": round(float(self.rng.uniform(0.12, 0.22)), 2),
                    "national_win_rate": round(float(self.rng.uniform(2.0, 8.5)), 2),
                    "national_2rate": round(float(self.rng.uniform(10.0, 40.0)), 2),
                    "national_3rate": round(float(self.rng.uniform(20.0, 60.0)), 2),
                    "local_win_rate": round(float(self.rng.uniform(1.0, 8.0)), 2),
                    "local_2rate": round(float(self.rng.uniform(8.0, 42.0)), 2),
                    "local_3rate": round(float(self.rng.uniform(18.0, 62.0)), 2),
                    "motor_no": int(self.rng.integers(1, 100)),
                    "motor_2rate": round(float(self.rng.uniform(20.0, 55.0)), 2),
                    "motor_3rate": round(float(self.rng.uniform(30.0, 65.0)), 2),
                    "boat_no": int(self.rng.integers(1, 100)),
                    "boat_2rate": round(float(self.rng.uniform(20.0, 55.0)), 2),
                    "boat_3rate": round(float(self.rng.uniform(30.0, 65.0)), 2),
                    "exhibition_time": round(float(self.rng.uniform(6.50, 7.40)), 2),
                    "start_time": round(float(self.rng.uniform(0.05, 0.25)), 2),
                    "tilt": round(float(self.rng.uniform(-0.5, 0.5)), 1),
                    "propeller": "",
                    "parts_exchange": "",
                    "start_exhibition_course": lane,
                    "start_exhibition_lane": lane,
                    "start_exhibition_st": round(float(self.rng.uniform(0.05, 0.25)), 2),
                    "finish_position": finish_position,
                    "race_time": f"1'{50 + finish_position:02d}\"{finish_position}",
                    "decision": "差し" if finish_position == 1 and lane != 1 else "",
                    "win": int(finish_position == 1),
                    "place": int(finish_position <= 2),
                    "show": int(finish_position <= 3),
                    "actual_start_time": round(float(self.rng.uniform(0.05, 0.25)), 2),
                    "win_odds": round(float(odds[row_idx]), 1),
                    "place_odds_low": round(max(1.0, float(odds[row_idx]) * 0.45), 1),
                    "place_odds_high": round(max(1.0, float(odds[row_idx]) * 0.75), 1),
                }
                records.append(record)
        frame = pd.DataFrame(records)
        frame["race_date"] = pd.to_datetime(frame["race_date"])
        return frame.sort_values(["race_date", "course_id", "race_number", "lane"]).reset_index(drop=True)
