from __future__ import annotations

import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml

from .constants import COURSE_NAME_TO_ID

ROOT_DIR = Path(__file__).resolve().parents[1]


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_lines(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).replace("\u3000", " ").replace("\xa0", " ")
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = clean_text(value)
    if not text:
        return default
    match = re.search(r"[-+]?(?:\d+\.\d+|\.\d+|\d+)", text)
    if not match:
        return default
    try:
        return float(match.group(0))
    except ValueError:
        return default


def parse_int(value: Any, default: int | None = None) -> int | None:
    number = parse_float(value, default=None)
    if number is None:
        return default
    return int(number)


def parse_first_float_series(values: Iterable[Any], default: float | None = None) -> list[float | None]:
    return [parse_float(value, default=default) for value in values]


def race_id_for(race_date: date | datetime | pd.Timestamp | str, course_id: str | int, race_number: int) -> str:
    if isinstance(race_date, pd.Timestamp):
        normalized = race_date.strftime("%Y%m%d")
    elif isinstance(race_date, datetime):
        normalized = race_date.strftime("%Y%m%d")
    elif isinstance(race_date, date):
        normalized = race_date.strftime("%Y%m%d")
    else:
        normalized = pd.to_datetime(race_date).strftime("%Y%m%d")
    course = f"{int(course_id):02d}" if str(course_id).isdigit() else str(course_id)
    return f"{normalized}_{course}_{int(race_number):02d}"


def normalize_course_id(value: str | int) -> str:
    text = str(value).strip()
    if text.isdigit():
        return f"{int(text):02d}"
    if text in COURSE_NAME_TO_ID:
        return COURSE_NAME_TO_ID[text]
    return text


def to_datetime_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")
