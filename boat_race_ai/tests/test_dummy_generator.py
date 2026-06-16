from __future__ import annotations

from src.data_processing.dummy_generator import DummyDataGenerator


def test_dummy_generator_builds_expected_schema() -> None:
    frame = DummyDataGenerator(seed=7).generate(n_races=6, start_date="2026-06-01", course_ids=["07"])
    assert not frame.empty
    assert set(["race_id", "race_date", "course_id", "race_number", "lane", "win", "win_odds"]).issubset(frame.columns)
    assert frame["race_id"].nunique() == 6
    assert frame.groupby("race_id")["win"].sum().eq(1).all()
    assert frame.groupby("race_id")["lane"].nunique().eq(6).all()
    assert frame["finish_position"].between(1, 6).all()
    assert (frame["win_odds"] >= 1.0).all()
