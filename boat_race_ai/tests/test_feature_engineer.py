from __future__ import annotations

import pandas as pd

from src.data_processing.preprocessor import BoatRacePreprocessor
from src.features.feature_engineer import BoatRaceFeatureEngineer


def _make_frame() -> pd.DataFrame:
    rows = []
    for race_number, finish_position, win in [(1, 2, 0), (2, 1, 1)]:
        rows.append(
            {
                "race_id": f"20260601_07_{race_number:02d}",
                "race_date": "2026-06-01",
                "course_id": "07",
                "course_name": "蒲郡",
                "race_number": race_number,
                "race_title": "テスト",
                "race_class": "一般戦",
                "distance_m": 1800,
                "weather": "晴",
                "wind_speed": 2.0,
                "water_temp": 20.0,
                "wave_height": 1.0,
                "racer_id": "1001",
                "name": "テスト一",
                "age": 30,
                "weight": 52.0,
                "grade": "B1",
                "lane": 1,
                "f_count": 0,
                "l_count": 0,
                "avg_st": 0.15,
                "national_win_rate": 5.0,
                "national_2rate": 20.0,
                "national_3rate": 40.0,
                "local_win_rate": 4.0,
                "local_2rate": 18.0,
                "local_3rate": 38.0,
                "motor_no": 10,
                "motor_2rate": 30.0,
                "motor_3rate": 45.0,
                "boat_no": 11,
                "boat_2rate": 25.0,
                "boat_3rate": 35.0,
                "exhibition_time": 6.90,
                "start_time": 0.14,
                "tilt": 0.0,
                "propeller": "",
                "parts_exchange": "",
                "start_exhibition_course": 1,
                "start_exhibition_lane": 1,
                "start_exhibition_st": 0.14,
                "finish_position": finish_position,
                "race_time": "1'51\"2",
                "decision": "",
                "win": win,
                "place": int(finish_position <= 2),
                "show": int(finish_position <= 3),
                "actual_start_time": 0.14,
                "win_odds": 2.1,
                "place_odds_low": 1.1,
                "place_odds_high": 1.3,
            }
        )
    return pd.DataFrame(rows)


def test_feature_engineer_uses_shifted_history() -> None:
    raw = _make_frame()
    preprocessed = BoatRacePreprocessor().fit(raw).transform(raw)
    engineered = BoatRaceFeatureEngineer().transform(preprocessed)
    first_row = engineered.iloc[0]
    second_row = engineered.iloc[1]
    assert first_row["feat_racer_prior_starts"] == 0
    assert second_row["feat_racer_prior_starts"] == 1
    assert second_row["feat_racer_prior_win_rate"] == 0
    assert "feat_total_strength" in engineered.columns
