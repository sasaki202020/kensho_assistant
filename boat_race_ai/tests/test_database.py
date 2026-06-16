from __future__ import annotations

from pathlib import Path

from src.data_processing.database import BoatRaceDatabase
from src.data_processing.dummy_generator import DummyDataGenerator


def test_database_roundtrip(tmp_path: Path) -> None:
    db = BoatRaceDatabase(tmp_path / "boat_race.db")
    frame = DummyDataGenerator(seed=11).generate(n_races=3, start_date="2026-06-01", course_ids=["07"])
    db.save_raw_frame(frame)
    loaded = db.load_joined_frame()
    assert not loaded.empty
    assert loaded["race_id"].nunique() == 3
    assert set(["race_id", "lane", "win", "win_odds"]).issubset(loaded.columns)
