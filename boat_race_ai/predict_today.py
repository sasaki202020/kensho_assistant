from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import joblib
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_processing.database import BoatRaceDatabase
from src.data_processing.real_data_fetcher import RealDataFetcher
from src.utils import ensure_dir, load_yaml


def _today_text(value: str | None) -> str:
    if value:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    return date.today().strftime("%Y-%m-%d")


def main() -> int:
    parser = argparse.ArgumentParser(description="Predict today's boat race entries")
    parser.add_argument("--date", default=None, help="Target date in YYYY-MM-DD")
    parser.add_argument("--place", default=None, help="Venue name, e.g. 桐生")
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()

    config = load_yaml(PROJECT_ROOT / args.config)
    paths = config.get("paths", {}) if isinstance(config, dict) else {}
    model_path = PROJECT_ROOT / str(paths.get("model_path", "output/model_bundle.joblib"))
    raw_dir = PROJECT_ROOT / str(paths.get("raw_dir", "data/raw"))
    db_path = PROJECT_ROOT / str(paths.get("db_path", "data/boat_race.db"))
    if not model_path.exists():
        raise FileNotFoundError(f"Model bundle not found: {model_path}")

    bundle = joblib.load(model_path)
    preprocessor = bundle["preprocessor"]
    feature_engineer = bundle["feature_engineer"]
    model = bundle["model"]

    target_date = _today_text(args.date)
    db = BoatRaceDatabase(db_path)
    history = db.load_joined_frame(before_date=target_date)

    with RealDataFetcher(
        raw_dir=raw_dir,
        render_wait_ms=int(config.get("real", {}).get("render_wait_ms", 2500)),
        request_timeout_ms=int(config.get("real", {}).get("request_timeout_ms", 30000)),
        min_request_interval_sec=float(config.get("real", {}).get("min_request_interval_sec", 2.0)),
    ) as fetcher:
        target_frame = fetcher.fetch_day(
            target_date,
            place=args.place,
            include_beforeinfo=True,
            include_results=False,
            include_odds=True,
            max_courses=1 if args.place is None else None,
        )

    if target_frame.empty:
        raise RuntimeError("No target races were found for the requested date/place.")

    context = pd.concat([history, target_frame], ignore_index=True, sort=False) if not history.empty else target_frame.copy()
    processed = preprocessor.transform(context)
    engineered = feature_engineer.transform(processed)
    target_race_ids = target_frame["race_id"].astype(str).unique().tolist()
    target_rows = engineered[engineered["race_id"].astype(str).isin(target_race_ids)].copy()
    if target_rows.empty:
        raise RuntimeError("Target rows could not be prepared for prediction.")

    predicted = model.predict_frame(target_rows)
    predicted["expected_value"] = predicted["pred_prob"].astype(float) * predicted["win_odds"].astype(float)
    predicted = predicted.sort_values(["race_number", "pred_prob"], ascending=[True, False]).reset_index(drop=True)

    output_dir = ensure_dir(PROJECT_ROOT / "output" / "predictions")
    csv_name = f"prediction_{target_date}_{args.place or 'auto'}.csv"
    csv_path = output_dir / csv_name
    columns = [
        "race_date",
        "course_name",
        "race_number",
        "lane",
        "racer_id",
        "name",
        "grade",
        "pred_prob",
        "pred_rank",
        "win_odds",
        "expected_value",
    ]
    available_columns = [column for column in columns if column in predicted.columns]
    predicted[available_columns].to_csv(csv_path, index=False, encoding="utf-8-sig")

    display_columns = [column for column in ["race_number", "lane", "name", "grade", "pred_prob", "pred_rank", "win_odds", "expected_value"] if column in predicted.columns]
    for race_number, race_frame in predicted.groupby("race_number", sort=True):
        print(f"\nRace {int(race_number)}")
        print(race_frame[display_columns].to_string(index=False))

    print(f"\nCSV saved to {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
