from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from ..utils import ensure_dir


RACE_COLUMNS = [
    "race_id",
    "race_date",
    "course_id",
    "course_name",
    "race_number",
    "race_title",
    "race_class",
    "distance_m",
    "weather",
    "wind_speed",
    "water_temp",
    "wave_height",
]

ENTRY_COLUMNS = [
    "race_id",
    "lane",
    "racer_id",
    "name",
    "age",
    "weight",
    "grade",
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
    "propeller",
    "parts_exchange",
    "start_exhibition_course",
    "start_exhibition_lane",
    "start_exhibition_st",
]

RESULT_COLUMNS = [
    "race_id",
    "lane",
    "finish_position",
    "race_time",
    "decision",
    "win",
    "place",
    "show",
    "actual_start_time",
]

ODDS_COLUMNS = [
    "race_id",
    "lane",
    "win_odds",
    "place_odds_low",
    "place_odds_high",
]


@dataclass
class BoatRaceDatabase:
    db_path: Path | str

    def __post_init__(self) -> None:
        self.db_path = Path(self.db_path)
        ensure_dir(self.db_path.parent)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS races (
                    race_id TEXT PRIMARY KEY,
                    race_date TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    course_name TEXT,
                    race_number INTEGER NOT NULL,
                    race_title TEXT,
                    race_class TEXT,
                    distance_m INTEGER,
                    weather TEXT,
                    wind_speed REAL,
                    water_temp REAL,
                    wave_height REAL
                );

                CREATE TABLE IF NOT EXISTS entries (
                    race_id TEXT NOT NULL,
                    lane INTEGER NOT NULL,
                    racer_id TEXT,
                    name TEXT,
                    age REAL,
                    weight REAL,
                    grade TEXT,
                    f_count REAL,
                    l_count REAL,
                    avg_st REAL,
                    national_win_rate REAL,
                    national_2rate REAL,
                    national_3rate REAL,
                    local_win_rate REAL,
                    local_2rate REAL,
                    local_3rate REAL,
                    motor_no REAL,
                    motor_2rate REAL,
                    motor_3rate REAL,
                    boat_no REAL,
                    boat_2rate REAL,
                    boat_3rate REAL,
                    exhibition_time REAL,
                    start_time REAL,
                    tilt REAL,
                    propeller TEXT,
                    parts_exchange TEXT,
                    start_exhibition_course REAL,
                    start_exhibition_lane REAL,
                    start_exhibition_st REAL,
                    PRIMARY KEY (race_id, lane)
                );

                CREATE TABLE IF NOT EXISTS results (
                    race_id TEXT NOT NULL,
                    lane INTEGER NOT NULL,
                    finish_position INTEGER,
                    race_time TEXT,
                    decision TEXT,
                    win INTEGER,
                    place INTEGER,
                    show INTEGER,
                    actual_start_time REAL,
                    PRIMARY KEY (race_id, lane)
                );

                CREATE TABLE IF NOT EXISTS odds (
                    race_id TEXT NOT NULL,
                    lane INTEGER NOT NULL,
                    win_odds REAL,
                    place_odds_low REAL,
                    place_odds_high REAL,
                    PRIMARY KEY (race_id, lane)
                );
                """
            )

    def save_frame(self, table: str, frame: pd.DataFrame, key_columns: Iterable[str]) -> None:
        if frame is None or frame.empty:
            return
        clean = frame.copy()
        for column in clean.columns:
            if pd.api.types.is_datetime64_any_dtype(clean[column]):
                clean[column] = clean[column].dt.strftime("%Y-%m-%d %H:%M:%S")
        columns = list(clean.columns)
        placeholders = ", ".join(["?"] * len(columns))
        column_sql = ", ".join([f'"{column}"' for column in columns])
        sql = f"INSERT OR REPLACE INTO {table} ({column_sql}) VALUES ({placeholders})"
        rows = [tuple(None if pd.isna(value) else value for value in row) for row in clean.itertuples(index=False, name=None)]
        with self.connect() as conn:
            conn.executemany(sql, rows)
            conn.commit()

    def save_raw_frame(self, frame: pd.DataFrame) -> None:
        if frame is None or frame.empty:
            return
        def _project(columns: list[str]) -> pd.DataFrame:
            subset = frame[[column for column in columns if column in frame.columns]].copy()
            for column in columns:
                if column not in subset.columns:
                    subset[column] = None
            return subset[columns]

        races = _project(RACE_COLUMNS).drop_duplicates(subset=["race_id"]) if "race_id" in frame.columns else pd.DataFrame()
        entries = _project(ENTRY_COLUMNS) if "lane" in frame.columns else pd.DataFrame()
        results = _project(RESULT_COLUMNS) if {"finish_position", "win"}.intersection(frame.columns) else pd.DataFrame()
        odds = _project(ODDS_COLUMNS) if "win_odds" in frame.columns else pd.DataFrame()
        self.save_frame("races", races, ["race_id"])
        self.save_frame("entries", entries, ["race_id", "lane"])
        self.save_frame("results", results, ["race_id", "lane"])
        self.save_frame("odds", odds, ["race_id", "lane"])

    def load_table(self, table: str) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(f"SELECT * FROM {table}", conn)

    def load_joined_frame(self, before_date: str | None = None) -> pd.DataFrame:
        query = """
            SELECT
                r.race_id,
                r.race_date,
                r.course_id,
                r.course_name,
                r.race_number,
                r.race_title,
                r.race_class,
                r.distance_m,
                r.weather,
                r.wind_speed,
                r.water_temp,
                r.wave_height,
                e.lane,
                e.racer_id,
                e.name,
                e.age,
                e.weight,
                e.grade,
                e.f_count,
                e.l_count,
                e.avg_st,
                e.national_win_rate,
                e.national_2rate,
                e.national_3rate,
                e.local_win_rate,
                e.local_2rate,
                e.local_3rate,
                e.motor_no,
                e.motor_2rate,
                e.motor_3rate,
                e.boat_no,
                e.boat_2rate,
                e.boat_3rate,
                e.exhibition_time,
                e.start_time,
                e.tilt,
                e.propeller,
                e.parts_exchange,
                e.start_exhibition_course,
                e.start_exhibition_lane,
                e.start_exhibition_st,
                res.finish_position,
                res.race_time,
                res.decision,
                res.win,
                res.place,
                res.show,
                res.actual_start_time,
                o.win_odds,
                o.place_odds_low,
                o.place_odds_high
            FROM races r
            LEFT JOIN entries e
              ON r.race_id = e.race_id
            LEFT JOIN results res
              ON e.race_id = res.race_id AND e.lane = res.lane
            LEFT JOIN odds o
              ON e.race_id = o.race_id AND e.lane = o.lane
        """
        clauses = []
        params: list[str] = []
        if before_date is not None:
            clauses.append("DATE(r.race_date) < DATE(?)")
            params.append(before_date)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY r.race_date, r.course_id, r.race_number, e.lane"
        with self.connect() as conn:
            frame = pd.read_sql_query(query, conn, params=params)
        if not frame.empty:
            frame["race_date"] = pd.to_datetime(frame["race_date"], errors="coerce")
        return frame
