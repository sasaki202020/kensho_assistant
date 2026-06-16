from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import joblib
import pandas as pd

from .data_processing.database import BoatRaceDatabase
from .data_processing.real_data_fetcher import RealDataFetcher
from .evaluation.backtester import BoatRaceBacktester
from .utils import ensure_dir, load_yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAILY_COLUMNS = [
    "race_date",
    "course_id",
    "course_name",
    "race_id",
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


@dataclass
class DailyPaths:
    project_root: Path
    target_date: str

    @property
    def daily_dir(self) -> Path:
        return ensure_dir(self.project_root / "output" / "daily" / self.target_date)

    @property
    def predictions_csv(self) -> Path:
        return self.daily_dir / "predictions.csv"

    @property
    def predictions_json(self) -> Path:
        return self.daily_dir / "predictions.json"

    @property
    def morning_run_json(self) -> Path:
        return self.daily_dir / "morning_run.json"

    @property
    def coverage_json(self) -> Path:
        return self.daily_dir / "coverage.json"

    @property
    def odds_refresh_csv(self) -> Path:
        return self.daily_dir / "odds_refresh.csv"

    @property
    def odds_refresh_run_json(self) -> Path:
        return self.daily_dir / "odds_refresh_run.json"

    @property
    def results_csv(self) -> Path:
        return self.daily_dir / "results.csv"

    @property
    def settlement_csv(self) -> Path:
        return self.daily_dir / "settlement.csv"

    @property
    def daily_report_json(self) -> Path:
        return self.daily_dir / "daily_report.json"

    @property
    def daily_report_md(self) -> Path:
        return self.daily_dir / "daily_report.md"

    @property
    def rolling_summary_csv(self) -> Path:
        return ensure_dir(self.project_root / "output" / "daily") / "rolling_summary.csv"


def normalize_date(value: str | None) -> str:
    return pd.to_datetime(value or date.today()).strftime("%Y-%m-%d")


def load_config(config_path: str | Path, project_root: Path = PROJECT_ROOT) -> dict:
    path = Path(config_path)
    if not path.is_absolute():
        path = project_root / path
    return load_yaml(path)


def project_path(config: dict, key: str, default: str, project_root: Path = PROJECT_ROOT) -> Path:
    paths = config.get("paths", {}) if isinstance(config, dict) else {}
    value = Path(str(paths.get(key, default)))
    return value if value.is_absolute() else project_root / value


def make_fetcher(config: dict, project_root: Path = PROJECT_ROOT) -> RealDataFetcher:
    real_cfg = config.get("real", {}) if isinstance(config, dict) else {}
    return RealDataFetcher(
        raw_dir=project_path(config, "raw_dir", "data/raw", project_root),
        render_wait_ms=int(real_cfg.get("render_wait_ms", 2500)),
        request_timeout_ms=int(real_cfg.get("request_timeout_ms", 30000)),
        min_request_interval_sec=float(real_cfg.get("min_request_interval_sec", 2.0)),
    )


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _error_reason(error: dict) -> str:
    return str(error.get("unavailable_reason") or error.get("status") or "unknown")


def errors_by_reason(errors: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for error in errors:
        reason = _error_reason(error)
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def valid_win_odds(values: object) -> pd.Series:
    odds = pd.to_numeric(values, errors="coerce")
    return odds.where(odds > 0)


def coverage_for(frame: pd.DataFrame, course_ids: list[str], errors: list[dict] | None = None) -> dict:
    errors = errors or []
    expected_races = len(course_ids) * 12
    if frame.empty:
        return {
            "status": "missing",
            "courses_requested": len(course_ids),
            "courses_observed": 0,
            "races_observed": 0,
            "expected_races": expected_races,
            "complete_races": 0,
            "rows": 0,
            "incomplete_races": [],
            "missing_name_rows": 0,
            "missing_grade_rows": 0,
            "missing_win_odds_rows": 0,
            "errors_by_reason": errors_by_reason(errors),
            "errors": errors,
        }
    race_sizes = frame.groupby("race_id")["lane"].nunique()
    incomplete = race_sizes[race_sizes != 6].index.astype(str).tolist()
    complete_races = int((race_sizes == 6).sum())
    name_series = frame.get("name", pd.Series(index=frame.index, dtype=object)).astype(str).str.strip()
    grade_series = frame.get("grade", pd.Series(index=frame.index, dtype=object)).astype(str).str.strip()
    odds_series = valid_win_odds(frame.get("win_odds", pd.Series(index=frame.index, dtype=float)))
    missing_name_rows = int((name_series == "").sum())
    missing_grade_rows = int((grade_series == "").sum())
    missing_win_odds_rows = int(odds_series.isna().sum())
    status = "ok"
    if incomplete or errors or complete_races != expected_races or missing_name_rows or missing_grade_rows or missing_win_odds_rows:
        status = "partial"
    return {
        "status": status,
        "courses_requested": len(course_ids),
        "courses_observed": int(frame["course_id"].nunique()) if "course_id" in frame.columns else 0,
        "races_observed": int(frame["race_id"].nunique()) if "race_id" in frame.columns else 0,
        "expected_races": expected_races,
        "complete_races": complete_races,
        "rows": int(len(frame)),
        "incomplete_races": incomplete,
        "missing_name_rows": missing_name_rows,
        "missing_grade_rows": missing_grade_rows,
        "missing_win_odds_rows": missing_win_odds_rows,
        "errors_by_reason": errors_by_reason(errors),
        "errors": errors,
    }


def prepare_prediction_frame(bundle: dict, history: pd.DataFrame, target_frame: pd.DataFrame) -> pd.DataFrame:
    odds_source = target_frame[["race_id", "lane"]].copy()
    if "win_odds" in target_frame.columns:
        odds_source["raw_win_odds"] = pd.to_numeric(target_frame["win_odds"], errors="coerce")
    else:
        odds_source["raw_win_odds"] = pd.NA
    context = pd.concat([history, target_frame], ignore_index=True, sort=False) if not history.empty else target_frame.copy()
    processed = bundle["preprocessor"].transform(context)
    engineered = bundle["feature_engineer"].transform(processed)
    target_race_ids = target_frame["race_id"].astype(str).unique().tolist()
    target_rows = engineered[engineered["race_id"].astype(str).isin(target_race_ids)].copy()
    if target_rows.empty:
        raise RuntimeError("Target rows could not be prepared for prediction.")
    predicted = bundle["model"].predict_frame(target_rows)
    predicted = predicted.merge(odds_source, on=["race_id", "lane"], how="left")
    predicted["win_odds"] = valid_win_odds(predicted["raw_win_odds"])
    predicted = predicted.drop(columns=["raw_win_odds"])
    predicted["expected_value"] = pd.to_numeric(predicted["pred_prob"], errors="coerce") * pd.to_numeric(predicted["win_odds"], errors="coerce")
    return predicted.sort_values(["course_id", "race_number", "pred_prob"], ascending=[True, True, False]).reset_index(drop=True)


def fetch_morning_entries(fetcher: RealDataFetcher, date_text: str, course_ids: list[str]) -> tuple[pd.DataFrame, list[dict]]:
    frames: list[pd.DataFrame] = []
    errors: list[dict] = []
    for course_id in course_ids:
        for race_number in range(1, 13):
            try:
                frame = fetcher.fetch_race(
                    date_text,
                    course_id,
                    race_number,
                    include_beforeinfo=True,
                    include_results=False,
                    include_odds=True,
                )
            except Exception as exc:
                errors.append(
                    {
                        "stage": "morning_fetch",
                        "course_id": course_id,
                        "race_number": race_number,
                        "status": "error",
                        "message": str(exc),
                    }
                )
                continue
            if frame.empty:
                errors.append(
                    {
                        "stage": "morning_fetch",
                        "course_id": course_id,
                        "race_number": race_number,
                        "status": "missing",
                        "message": "empty frame",
                    }
                )
                continue
            frames.append(frame)
    if not frames:
        return pd.DataFrame(), errors
    return pd.concat(frames, ignore_index=True), errors


def run_morning(
    target_date: str | None = None,
    *,
    config_path: str | Path = "config/config.yaml",
    project_root: Path = PROJECT_ROOT,
    overwrite: bool = False,
    max_courses: int | None = None,
    fetcher_factory: Callable[[dict, Path], RealDataFetcher] = make_fetcher,
) -> dict:
    date_text = normalize_date(target_date)
    config = load_config(config_path, project_root)
    paths = DailyPaths(project_root, date_text)
    if paths.predictions_csv.exists() and not overwrite:
        existing = pd.read_csv(paths.predictions_csv)
        payload = {
            "status": "exists",
            "operation_status": "existing_prediction_used",
            "target_date": date_text,
            "predictions_csv": str(paths.predictions_csv),
            "courses": int(existing["course_id"].nunique()) if "course_id" in existing.columns else 0,
            "rows": int(len(existing)),
            "races": int(existing["race_id"].nunique()) if "race_id" in existing.columns else 0,
        }
        write_json(paths.morning_run_json, payload)
        return payload

    model_path = project_path(config, "model_path", "output/model_bundle.joblib", project_root)
    if not model_path.exists():
        raise FileNotFoundError(f"Model bundle not found: {model_path}")
    bundle = joblib.load(model_path)
    db_path = project_path(config, "db_path", "data/boat_race.db", project_root)
    db = BoatRaceDatabase(db_path)
    history = db.load_joined_frame(before_date=date_text)
    errors: list[dict] = []

    with fetcher_factory(config, project_root) as fetcher:
        course_ids = fetcher.discover_course_ids(date_text, limit=max_courses)
        if not course_ids:
            raise RuntimeError(f"No active courses were found for {date_text}.")
        target_frame, fetch_errors = fetch_morning_entries(fetcher, date_text, course_ids)
        errors.extend(fetch_errors)

    coverage = coverage_for(target_frame, course_ids, errors)
    write_json(paths.coverage_json, coverage)
    if target_frame.empty:
        raise RuntimeError(f"No target races were found for {date_text}.")
    db.save_raw_frame(target_frame)
    predicted = prepare_prediction_frame(bundle, history, target_frame)
    output_columns = [column for column in DAILY_COLUMNS if column in predicted.columns]
    predicted[output_columns].to_csv(paths.predictions_csv, index=False, encoding="utf-8-sig")
    predicted[output_columns].to_json(paths.predictions_json, orient="records", force_ascii=False, indent=2, date_format="iso")
    payload = {
        "status": "ok" if coverage["status"] == "ok" else "partial",
        "operation_status": "completed" if coverage["status"] == "ok" else "partial_completed",
        "target_date": date_text,
        "courses": int(predicted["course_id"].nunique()),
        "races": int(predicted["race_id"].nunique()),
        "rows": int(len(predicted)),
        "predictions_csv": str(paths.predictions_csv),
        "coverage_json": str(paths.coverage_json),
    }
    write_json(paths.morning_run_json, payload)
    return payload


def refresh_daily_odds(
    target_date: str | None = None,
    *,
    config_path: str | Path = "config/config.yaml",
    project_root: Path = PROJECT_ROOT,
    force_refresh: bool = False,
    fetcher_factory: Callable[[dict, Path], RealDataFetcher] = make_fetcher,
) -> dict:
    date_text = normalize_date(target_date)
    config = load_config(config_path, project_root)
    paths = DailyPaths(project_root, date_text)
    if not paths.predictions_csv.exists():
        raise FileNotFoundError(f"Morning predictions not found: {paths.predictions_csv}")
    if paths.settlement_csv.exists():
        raise RuntimeError(f"Settlement already exists; refusing to update predictions after settlement: {paths.settlement_csv}")

    predictions = pd.read_csv(paths.predictions_csv)
    required = {"race_id", "course_id", "race_number", "lane", "pred_prob", "pred_rank"}
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise ValueError(f"Predictions file is missing required columns: {missing}")

    race_keys = (
        predictions[["course_id", "race_number", "race_id"]]
        .drop_duplicates()
        .sort_values(["course_id", "race_number"])
        .reset_index(drop=True)
    )
    odds_frames: list[pd.DataFrame] = []
    errors: list[dict] = []
    attempted_races: set[str] = set()
    with fetcher_factory(config, project_root) as fetcher:
        for row in race_keys.itertuples(index=False):
            course_id = str(row.course_id).zfill(2)
            race_number = int(row.race_number)
            race_id = str(row.race_id)
            try:
                odds = fetcher.fetch_odds_race(date_text, course_id, race_number, force_refresh=force_refresh)
                attempted_races.add(race_id)
            except Exception as exc:
                errors.append(
                    {
                        "stage": "odds_refresh",
                        "course_id": course_id,
                        "race_number": race_number,
                        "race_id": race_id,
                        "status": "error",
                        "unavailable_reason": "fetch_error",
                        "message": str(exc),
                    }
                )
                continue
            if odds.empty or "win_odds" not in odds.columns:
                errors.append(
                    {
                        "stage": "odds_refresh",
                        "course_id": course_id,
                        "race_number": race_number,
                        "race_id": race_id,
                        "status": "unavailable",
                        "unavailable_reason": "odds_unavailable",
                        "message": "win odds were unavailable",
                    }
                )
                continue
            odds_frames.append(odds[["race_id", "lane", "win_odds"]].copy())

    if "win_odds" not in predictions.columns:
        predictions["win_odds"] = pd.NA
    predictions["win_odds"] = valid_win_odds(predictions["win_odds"])
    if attempted_races:
        attempted_mask = predictions["race_id"].astype(str).isin(attempted_races)
        predictions.loc[attempted_mask, "win_odds"] = pd.NA
    if odds_frames:
        odds_all = pd.concat(odds_frames, ignore_index=True)
        odds_all["win_odds"] = valid_win_odds(odds_all["win_odds"])
        odds_all = odds_all.dropna(subset=["win_odds"]).drop_duplicates(["race_id", "lane"], keep="last")
        predictions = predictions.merge(odds_all, on=["race_id", "lane"], how="left", suffixes=("", "_official"))
        official_mask = predictions["win_odds_official"].notna()
        predictions.loc[official_mask, "win_odds"] = predictions.loc[official_mask, "win_odds_official"]
        predictions = predictions.drop(columns=["win_odds_official"])

    predictions["expected_value"] = pd.to_numeric(predictions["pred_prob"], errors="coerce") * pd.to_numeric(predictions["win_odds"], errors="coerce")
    predictions.to_csv(paths.predictions_csv, index=False, encoding="utf-8-sig")
    predictions.to_json(paths.predictions_json, orient="records", force_ascii=False, indent=2, date_format="iso")
    if odds_frames:
        pd.concat(odds_frames, ignore_index=True).to_csv(paths.odds_refresh_csv, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(columns=["race_id", "lane", "win_odds"]).to_csv(paths.odds_refresh_csv, index=False, encoding="utf-8-sig")

    available_rows = int(valid_win_odds(predictions["win_odds"]).notna().sum())
    payload = {
        "status": "ok" if available_rows == len(predictions) else "partial",
        "operation_status": "odds_refreshed" if available_rows else "odds_unavailable",
        "target_date": date_text,
        "rows": int(len(predictions)),
        "races": int(predictions["race_id"].astype(str).nunique()),
        "odds_available_rows": available_rows,
        "missing_win_odds_rows": int(valid_win_odds(predictions["win_odds"]).isna().sum()),
        "odds_refresh_csv": str(paths.odds_refresh_csv),
        "predictions_csv": str(paths.predictions_csv),
        "errors_by_reason": errors_by_reason(errors),
        "errors": errors,
    }
    write_json(paths.odds_refresh_run_json, payload)
    return payload


def _strategy_summary(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty or "win" not in frame.columns:
        return pd.DataFrame(), pd.DataFrame()
    available = frame[pd.to_numeric(frame["win"], errors="coerce").notna()].copy()
    if available.empty:
        return pd.DataFrame(), pd.DataFrame()
    return BoatRaceBacktester().evaluate(available, probability_column="pred_prob")


def fetch_night_results(fetcher: RealDataFetcher, date_text: str, course_ids: list[str]) -> tuple[pd.DataFrame, list[dict]]:
    frames: list[pd.DataFrame] = []
    errors: list[dict] = []
    for course_id in course_ids:
        for race_number in range(1, 13):
            try:
                if hasattr(fetcher, "fetch_result_race_with_status"):
                    frame, status = fetcher.fetch_result_race_with_status(date_text, course_id, race_number)
                else:
                    frame = fetcher.fetch_result_race(date_text, course_id, race_number)
                    status = {
                        "stage": "night_fetch",
                        "course_id": course_id,
                        "race_number": race_number,
                        "status": "unavailable" if frame.empty else "settled",
                        "unavailable_reason": "empty_result" if frame.empty else "",
                        "message": "empty result" if frame.empty else "result parsed",
                    }
            except Exception as exc:
                errors.append(
                    {
                        "stage": "night_fetch",
                        "course_id": course_id,
                        "race_number": race_number,
                        "race_id": f"{date_text.replace('-', '')}_{course_id}_{race_number:02d}",
                        "status": "error",
                        "unavailable_reason": "fetch_error",
                        "message": str(exc),
                    }
                )
                continue
            if frame.empty:
                status.setdefault("stage", "night_fetch")
                status.setdefault("course_id", course_id)
                status.setdefault("race_number", race_number)
                status.setdefault("status", "unavailable")
                status.setdefault("unavailable_reason", "empty_result")
                status.setdefault("message", status.get("unavailable_reason", "empty result"))
                errors.append(status)
                continue
            frames.append(frame)
    if not frames:
        return pd.DataFrame(), errors
    return pd.concat(frames, ignore_index=True), errors


def result_status_rows(fetch_errors: list[dict], date_text: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    compact_date = date_text.replace("-", "")
    for error in fetch_errors:
        course_id = str(error.get("course_id", "")).zfill(2)
        race_number = int(error.get("race_number", 0) or 0)
        race_id = str(error.get("race_id") or f"{compact_date}_{course_id}_{race_number:02d}")
        rows.append(
            {
                "race_date": pd.to_datetime(date_text),
                "course_id": course_id,
                "race_id": race_id,
                "race_number": race_number,
                "lane": pd.NA,
                "result_status": error.get("status", "unavailable"),
                "unavailable_reason": error.get("unavailable_reason", _error_reason(error)),
                "message": error.get("message", ""),
            }
        )
    return pd.DataFrame(rows)


def course_summary_for(settlement: pd.DataFrame) -> list[dict]:
    if settlement.empty:
        return []
    rows: list[dict] = []
    for course_id, group in settlement.groupby(settlement["course_id"].astype(str).str.zfill(2), sort=True):
        predicted_races = group["race_id"].astype(str).nunique()
        settled = group[group["result_status"].isin(["settled", "partial_result"])].copy()
        settled_races = settled["race_id"].astype(str).nunique()
        unavailable_races = predicted_races - settled_races
        top1 = settled[pd.to_numeric(settled.get("pred_rank"), errors="coerce") == 1].copy()
        top1_hit_rate = None
        top1_roi_pct = None
        if not top1.empty and "win" in top1.columns:
            top1["win"] = pd.to_numeric(top1["win"], errors="coerce")
            top1["win_odds"] = pd.to_numeric(top1.get("win_odds"), errors="coerce")
            top1_hit_rate = float(top1["win"].mean())
            stake = float(len(top1) * 100)
            payout = float((top1["win"] * top1["win_odds"] * 100).fillna(0).sum())
            top1_roi_pct = (payout / stake * 100) if stake else None
        rows.append(
            {
                "course_id": course_id,
                "races_predicted": int(predicted_races),
                "races_settled": int(settled_races),
                "unavailable_races": int(unavailable_races),
                "top1_hit_rate": top1_hit_rate,
                "top1_roi_pct": top1_roi_pct,
            }
        )
    return rows


def build_markdown_report(report: dict) -> str:
    lines = [
        f"# Daily Report {report['target_date']}",
        "",
        f"status: {report['status']}",
        f"courses: {report['courses']}",
        f"races_predicted: {report['races_predicted']}",
        f"races_settled: {report['races_settled']}",
        f"unavailable_races: {len(report['unavailable_races'])}",
        "",
        "sample_note: 検証中。サンプル数が少ない間はROIだけで良否判定しない。",
        "value_filter_note: value_filter は評価用。現時点では本番推奨買い目ではない。",
        "",
        "## Strategy Summary",
    ]
    if not report["summary"]:
        lines.append("No settled results.")
    else:
        for row in report["summary"]:
            lines.append(
                f"- {row['strategy']}: hit_rate={row['race_hit_rate']:.3f}, roi={row['roi_pct']:.1f}%, bets={row['bets']}"
            )
    if report["unavailable_races"]:
        lines.extend(["", "## Unavailable Races"])
        reason_map = {item["race_id"]: item.get("unavailable_reason", "unknown") for item in report.get("unavailable_details", [])}
        lines.extend(f"- {race_id}: {reason_map.get(race_id, 'unknown')}" for race_id in report["unavailable_races"])
    if report.get("course_summary"):
        lines.extend(["", "## Course Summary", "| course | predicted | settled | unavailable | top1 hit | top1 ROI |", "|---|---:|---:|---:|---:|---:|"])
        for row in report["course_summary"]:
            hit = "" if row["top1_hit_rate"] is None else f"{row['top1_hit_rate']:.3f}"
            roi = "" if row["top1_roi_pct"] is None else f"{row['top1_roi_pct']:.1f}%"
            lines.append(
                f"| {row['course_id']} | {row['races_predicted']} | {row['races_settled']} | {row['unavailable_races']} | {hit} | {roi} |"
            )
    return "\n".join(lines) + "\n"


def update_rolling_summary(paths: DailyPaths, report: dict) -> None:
    row = {
        "target_date": report["target_date"],
        "status": report["status"],
        "courses": report["courses"],
        "races_predicted": report["races_predicted"],
        "races_settled": report["races_settled"],
        "unavailable_races": len(report["unavailable_races"]),
    }
    for summary in report["summary"]:
        prefix = summary["strategy"]
        row[f"{prefix}_hit_rate"] = summary["race_hit_rate"]
        row[f"{prefix}_roi_pct"] = summary["roi_pct"]
        row[f"{prefix}_bets"] = summary["bets"]
    if paths.rolling_summary_csv.exists():
        rolling = pd.read_csv(paths.rolling_summary_csv)
        rolling = rolling[rolling["target_date"].astype(str) != report["target_date"]]
        rolling = pd.concat([rolling, pd.DataFrame([row])], ignore_index=True, sort=False)
    else:
        rolling = pd.DataFrame([row])
    rolling.sort_values("target_date").to_csv(paths.rolling_summary_csv, index=False, encoding="utf-8-sig")


def run_night(
    target_date: str | None = None,
    *,
    config_path: str | Path = "config/config.yaml",
    project_root: Path = PROJECT_ROOT,
    fetcher_factory: Callable[[dict, Path], RealDataFetcher] = make_fetcher,
) -> dict:
    date_text = normalize_date(target_date)
    config = load_config(config_path, project_root)
    paths = DailyPaths(project_root, date_text)
    if not paths.predictions_csv.exists():
        raise FileNotFoundError(f"Morning predictions not found: {paths.predictions_csv}")
    predictions = pd.read_csv(paths.predictions_csv)
    course_ids = sorted(predictions["course_id"].astype(str).str.zfill(2).unique().tolist())
    with fetcher_factory(config, project_root) as fetcher:
        if hasattr(fetcher, "fetch_result_race_with_status") or hasattr(fetcher, "fetch_result_race"):
            results, fetch_errors = fetch_night_results(fetcher, date_text, course_ids)
        elif hasattr(fetcher, "fetch_results_day"):
            results = fetcher.fetch_results_day(date_text, course_ids=course_ids, race_numbers=range(1, 13))
            fetch_errors = []
        else:
            results = fetcher.fetch_day(date_text, include_beforeinfo=False, include_results=True, include_odds=False)
            fetch_errors = []
    status_rows = result_status_rows(fetch_errors, date_text)
    if results.empty:
        results_export = status_rows
    elif status_rows.empty:
        results_export = results.copy()
    else:
        results_export = pd.concat([results, status_rows], ignore_index=True, sort=False)
    results_export.to_csv(paths.results_csv, index=False, encoding="utf-8-sig")
    reason_map = {
        str(row.get("race_id")): str(row.get("unavailable_reason") or _error_reason(row))
        for row in fetch_errors
        if row.get("race_id")
    }
    partial_reason_map: dict[str, str] = {}
    if not results.empty and {"race_id", "result_status", "unavailable_reason"}.issubset(results.columns):
        partial_rows = results[results["result_status"] == "partial_result"]
        if not partial_rows.empty:
            partial_reason_map = (
                partial_rows.groupby("race_id")["unavailable_reason"].first().fillna("").to_dict()
            )
    if results.empty:
        settlement = predictions.copy()
        settlement["result_status"] = "unavailable"
        settlement["unavailable_reason"] = settlement["race_id"].astype(str).map(reason_map).fillna("result_unavailable")
    else:
        result_columns = [
            "race_id",
            "lane",
            "finish_position",
            "win",
            "place",
            "show",
            "actual_start_time",
            "win_odds",
            "result_status",
            "unavailable_reason",
        ]
        present = [column for column in result_columns if column in results.columns]
        result_subset = results[present].copy()
        if "win_odds" in result_subset.columns:
            result_subset = result_subset.rename(columns={"win_odds": "result_win_odds"})
        settlement = predictions.merge(result_subset, on=["race_id", "lane"], how="left")
        if "result_win_odds" in settlement.columns:
            if "win_odds" not in settlement.columns:
                settlement["win_odds"] = pd.NA
            settlement["win_odds"] = pd.to_numeric(settlement["win_odds"], errors="coerce")
            settlement["result_win_odds"] = pd.to_numeric(settlement["result_win_odds"], errors="coerce")
            settlement["win_odds"] = settlement["win_odds"].where(
                settlement["win_odds"].notna(),
                settlement["result_win_odds"],
            )
        settlement["result_status"] = settlement.apply(
            lambda row: row["result_status"] if pd.notna(row.get("result_status")) else ("unavailable" if pd.isna(row.get("finish_position")) else "settled"),
            axis=1,
        )
        settlement["unavailable_reason"] = settlement.apply(
            lambda row: row["unavailable_reason"]
            if pd.notna(row.get("unavailable_reason")) and str(row.get("unavailable_reason")).strip()
            else (
                reason_map.get(str(row["race_id"]))
                or partial_reason_map.get(str(row["race_id"]))
                or "result_unavailable"
                if row["result_status"] == "unavailable"
                else ""
            ),
            axis=1,
        )
    settlement.to_csv(paths.settlement_csv, index=False, encoding="utf-8-sig")
    settled_mask = settlement["result_status"].isin(["settled", "partial_result"])
    settled_races = sorted(settlement.loc[settled_mask, "race_id"].astype(str).unique().tolist())
    predicted_races = sorted(predictions["race_id"].astype(str).unique().tolist())
    unavailable = [race_id for race_id in predicted_races if race_id not in settled_races]
    unavailable_details = [
        {"race_id": race_id, "unavailable_reason": reason_map.get(race_id, "result_unavailable")}
        for race_id in unavailable
    ]
    summary_df, detail_df = _strategy_summary(settlement)
    report = {
        "status": "ok" if not unavailable else "partial",
        "target_date": date_text,
        "courses": int(predictions["course_id"].nunique()),
        "races_predicted": int(len(predicted_races)),
        "races_settled": int(len(settled_races)),
        "rows": int(len(settlement)),
        "unavailable_races": unavailable,
        "unavailable_count": int(len(unavailable)),
        "unavailable_details": unavailable_details,
        "unavailable_by_reason": errors_by_reason(fetch_errors),
        "course_summary": course_summary_for(settlement),
        "summary": summary_df.to_dict(orient="records") if not summary_df.empty else [],
        "detail": detail_df.to_dict(orient="records") if not detail_df.empty else [],
        "errors": fetch_errors,
        "sample_note": "検証中。サンプル数が少ない間はROIだけで良否判定しない。",
        "value_filter_note": "value_filter は評価用。現時点では本番推奨買い目ではない。",
    }
    write_json(paths.daily_report_json, report)
    paths.daily_report_md.write_text(build_markdown_report(report), encoding="utf-8")
    update_rolling_summary(paths, report)
    return report
