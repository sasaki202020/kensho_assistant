from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import joblib
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_processing.database import BoatRaceDatabase
from src.data_processing.dummy_generator import DummyDataGenerator
from src.data_processing.preprocessor import BoatRacePreprocessor
from src.data_processing.real_data_fetcher import RealDataFetcher
from src.evaluation.backtester import BoatRaceBacktester
from src.features.feature_engineer import BoatRaceFeatureEngineer
from src.models.prediction_system import PredictionSystem
from src.utils import ensure_dir, load_yaml


def bootstrap_paths(config: dict[str, object]) -> dict[str, Path]:
    paths = config.get("paths", {}) if isinstance(config, dict) else {}
    output_dir = ensure_dir(PROJECT_ROOT / "output")
    report_dir = ensure_dir(output_dir / "reports")
    prediction_dir = ensure_dir(output_dir / "predictions")
    raw_dir = ensure_dir(PROJECT_ROOT / str(paths.get("raw_dir", "data/raw")))
    db_path = PROJECT_ROOT / str(paths.get("db_path", "data/boat_race.db"))
    model_path = output_dir / "model_bundle.joblib"
    return {
        "output_dir": output_dir,
        "report_dir": report_dir,
        "prediction_dir": prediction_dir,
        "raw_dir": raw_dir,
        "db_path": db_path,
        "model_path": model_path,
    }


def split_race_ids(frame: pd.DataFrame, test_ratio: float, valid_ratio: float) -> tuple[list[str], list[str], list[str]]:
    races = (
        frame[["race_id", "race_date", "course_id", "race_number"]]
        .drop_duplicates()
        .sort_values(["race_date", "course_id", "race_number"])
        .reset_index(drop=True)
    )
    race_ids = races["race_id"].astype(str).tolist()
    n_races = len(race_ids)
    if n_races == 0:
        return [], [], []
    if n_races < 4:
        if n_races == 1:
            return race_ids, race_ids, race_ids
        if n_races == 2:
            return race_ids[:1], race_ids[:1], race_ids[1:]
        return race_ids[:1], race_ids[1:2], race_ids[2:]
    test_size = max(1, int(round(n_races * test_ratio)))
    valid_size = max(1, int(round(n_races * valid_ratio)))
    train_size = max(1, n_races - test_size - valid_size)
    if train_size + valid_size + test_size > n_races:
        train_size = max(1, n_races - valid_size - test_size)
    if train_size + valid_size + test_size < n_races:
        train_size = n_races - valid_size - test_size
    train_ids = race_ids[:train_size]
    valid_ids = race_ids[train_size : train_size + valid_size]
    test_ids = race_ids[train_size + valid_size :]
    if not test_ids:
        test_ids = race_ids[-1:]
        valid_ids = race_ids[-2:-1] if n_races >= 2 else race_ids[-1:]
        train_ids = race_ids[: max(1, n_races - len(valid_ids) - len(test_ids))]
    return train_ids, valid_ids, test_ids


def select_rows(frame: pd.DataFrame, race_ids: list[str]) -> pd.DataFrame:
    subset = frame[frame["race_id"].astype(str).isin(race_ids)].copy()
    return subset.sort_values(["race_date", "course_id", "race_number", "lane"]).reset_index(drop=True)


def fetch_real_frame(config: dict[str, object], paths: dict[str, Path], quick: bool) -> pd.DataFrame:
    real_cfg = config.get("real", {}) if isinstance(config, dict) else {}
    today = date.today()
    end_date = today - timedelta(days=1)
    history_days = int(real_cfg.get("history_days_quick" if quick else "history_days_normal", 1))
    max_courses = int(real_cfg.get("max_courses_quick" if quick else "max_courses_normal", 1))
    include_beforeinfo = bool(real_cfg.get("include_beforeinfo_quick" if quick else "include_beforeinfo_normal", False))
    raw_frames: list[pd.DataFrame] = []
    db = BoatRaceDatabase(paths["db_path"])
    with RealDataFetcher(
        raw_dir=paths["raw_dir"],
        render_wait_ms=int(real_cfg.get("render_wait_ms", 2500)),
        request_timeout_ms=int(real_cfg.get("request_timeout_ms", 30000)),
        min_request_interval_sec=float(real_cfg.get("min_request_interval_sec", 2.0)),
    ) as fetcher:
        for offset in range(history_days):
            current_date = end_date - timedelta(days=history_days - 1 - offset)
            frame = fetcher.fetch_day(
                current_date,
                include_beforeinfo=include_beforeinfo,
                include_results=True,
                include_odds=True,
                max_courses=max_courses,
            )
            if not frame.empty:
                raw_frames.append(frame)
                db.save_raw_frame(frame)
    if not raw_frames:
        return pd.DataFrame()
    return pd.concat(raw_frames, ignore_index=True)


def fetch_dummy_frame(config: dict[str, object], quick: bool) -> pd.DataFrame:
    dummy_cfg = config.get("dummy", {}) if isinstance(config, dict) else {}
    generator = DummyDataGenerator(seed=int(dummy_cfg.get("seed", 20260613)))
    races = int(dummy_cfg.get("quick_races" if quick else "normal_races", 48 if quick else 180))
    start_date = dummy_cfg.get("start_date", "2026-06-01")
    frame = generator.generate(n_races=races, start_date=start_date)
    db = BoatRaceDatabase(PROJECT_ROOT / "data/boat_race.db")
    db.save_raw_frame(frame)
    return frame


def format_summary(summary: pd.DataFrame) -> str:
    if summary.empty:
        return "No backtest results."
    return summary.to_string(index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Boat race AI pipeline")
    parser.add_argument("--source", choices=["dummy", "real"], default="dummy")
    parser.add_argument("--quick", action="store_true", help="Use a smaller dataset")
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()

    config = load_yaml(PROJECT_ROOT / args.config)
    paths = bootstrap_paths(config)
    model_cfg = config.get("model", {}) if isinstance(config, dict) else {}

    if args.source == "dummy":
        raw_frame = fetch_dummy_frame(config, args.quick)
    else:
        raw_frame = fetch_real_frame(config, paths, args.quick)

    if raw_frame.empty:
        raise RuntimeError("No training data was collected.")

    train_ids, valid_ids, test_ids = split_race_ids(
        raw_frame,
        test_ratio=float(model_cfg.get("test_ratio", 0.2)),
        valid_ratio=float(model_cfg.get("valid_ratio", 0.2)),
    )

    train_raw = select_rows(raw_frame, train_ids)
    valid_raw = select_rows(raw_frame, valid_ids)
    test_raw = select_rows(raw_frame, test_ids)

    preprocessor = BoatRacePreprocessor().fit(train_raw)
    processed_all = preprocessor.transform(raw_frame)
    feature_engineer = BoatRaceFeatureEngineer()
    engineered_all = feature_engineer.transform(processed_all)

    train_frame = select_rows(engineered_all, train_ids)
    valid_frame = select_rows(engineered_all, valid_ids)
    test_frame = select_rows(engineered_all, test_ids)

    eval_model = PredictionSystem(
        random_state=int(model_cfg.get("random_state", 42)),
        xgb_estimators=int(model_cfg.get("xgb_estimators", 100)),
        lgbm_estimators=int(model_cfg.get("lgbm_estimators", 140)),
        rf_estimators=int(model_cfg.get("rf_estimators", 180)),
    )
    eval_model.fit(train_frame)
    test_pred = eval_model.predict_frame(test_frame)
    backtester = BoatRaceBacktester()
    summary_df, detail_df = backtester.evaluate(test_pred)

    report_dir = paths["report_dir"]
    ensure_dir(report_dir)
    summary_json = report_dir / "backtest_summary.json"
    detail_csv = report_dir / "backtest_detail.csv"
    summary_md = report_dir / "backtest_summary.md"
    summary_df.to_json(summary_json, orient="records", force_ascii=False, indent=2)
    detail_df.to_csv(detail_csv, index=False, encoding="utf-8-sig")
    summary_md.write_text(format_summary(summary_df), encoding="utf-8")

    final_preprocessor = BoatRacePreprocessor().fit(raw_frame)
    final_processed = final_preprocessor.transform(raw_frame)
    final_engineered = feature_engineer.transform(final_processed)
    final_model = PredictionSystem(
        random_state=int(model_cfg.get("random_state", 42)),
        xgb_estimators=int(model_cfg.get("xgb_estimators", 100)),
        lgbm_estimators=int(model_cfg.get("lgbm_estimators", 140)),
        rf_estimators=int(model_cfg.get("rf_estimators", 180)),
    )
    final_model.fit(final_engineered)

    bundle = {
        "preprocessor": final_preprocessor,
        "feature_engineer": feature_engineer,
        "model": final_model,
        "source": args.source,
        "created_at": pd.Timestamp.now(tz="Asia/Tokyo").isoformat(),
    }
    joblib.dump(bundle, paths["model_path"])

    results = {
        "source": args.source,
        "quick": args.quick,
        "rows": int(len(raw_frame)),
        "races": int(raw_frame["race_id"].nunique()),
        "train_races": len(train_ids),
        "valid_races": len(valid_ids),
        "test_races": len(test_ids),
        "summary": summary_df.to_dict(orient="records"),
        "model_path": str(paths["model_path"]),
    }
    (paths["output_dir"] / "run_summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(format_summary(summary_df))
    print(f"Model saved to {paths['model_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
