"""Profitability-oriented analysis for daily prediction artifacts.

The module is intentionally observational. It does not change production
thresholds or generate live betting instructions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_MIN_SAMPLE = 100
DEFAULT_MIN_DAYS = 3
DEFAULT_MIN_ROI_PCT = 105.0
DEFAULT_MIN_POSITIVE_DAY_RATE = 0.5
DEFAULT_MIN_DAILY_ROI_FLOOR_PCT = 80.0

CANDIDATE_COLUMNS = [
    "condition_id",
    "strategy",
    "slice_type",
    "slice_value",
    "bets",
    "unique_days",
    "daily_roi_days",
    "hit_count",
    "hit_rate",
    "roi_pct",
    "profit_units",
    "daily_roi_min",
    "daily_roi_mean",
    "daily_roi_max",
    "daily_roi_std",
    "daily_positive_day_rate",
    "daily_bet_min",
    "sample_status",
    "candidate_status",
    "production_adoption",
    "reason",
]

SLICE_COLUMNS = [
    "strategy",
    "bets",
    "hit_count",
    "hit_rate",
    "roi_pct",
    "profit_units",
    "sample_status",
    "daily_roi_days",
    "daily_roi_mean",
    "daily_roi_min",
    "daily_roi_max",
    "daily_roi_std",
    "daily_positive_day_rate",
    "daily_bet_min",
    "slice_type",
    "slice_value",
    "unique_days",
]

LEGACY_PREDICTION_COLUMNS = [
    "date",
    "jcd",
    "venue",
    "race_no",
    "combo",
    "actual_trifecta",
    "trifecta_payout",
    "decision",
    "rank",
    "prob",
    "odds",
    "expected_value",
    "source_type",
    "hit",
    "artifact",
]

DAILY_HISTORY_COLUMNS = [
    "analysis_date",
    "analysis_run_at",
    "analysis_status",
    "decision",
    "live_betting_allowed",
    "candidate_conditions_count",
    "current_days",
    "settled_rows",
    "top1_bets",
    "top1_hit_rate",
    "top1_roi_pct",
    "top2_bets",
    "top2_hit_rate",
    "top2_roi_pct",
    "value_filter_bets",
    "value_filter_hit_rate",
    "value_filter_roi_pct",
    "min_sample",
    "min_days",
    "min_roi_pct",
    "min_positive_day_rate",
    "min_daily_roi_floor_pct",
]

CANDIDATE_HISTORY_COLUMNS = [
    "analysis_date",
    "analysis_run_at",
    *CANDIDATE_COLUMNS,
]

CANDIDATE_REJECTION_COLUMNS = [
    "condition_id",
    "strategy",
    "slice_type",
    "slice_value",
    "bets",
    "daily_roi_days",
    "roi_pct",
    "daily_positive_day_rate",
    "daily_roi_min",
    "failed_gates",
    "primary_failed_gate",
]


@dataclass(frozen=True)
class AnalysisPaths:
    current_daily_root: Path
    legacy_daily_root: Path | None
    output_dir: Path


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_current_settlements(daily_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not daily_root.exists():
        return pd.DataFrame()
    for path in sorted(daily_root.glob("*/settlement.csv")):
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        if frame.empty:
            continue
        frame["artifact_date"] = path.parent.name
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if "race_date" not in combined.columns:
        combined["race_date"] = combined["artifact_date"]
    return combined


def _selected_rows(frame: pd.DataFrame, strategy: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    data = frame.copy()
    data["pred_rank"] = pd.to_numeric(data.get("pred_rank"), errors="coerce")
    data["pred_prob"] = pd.to_numeric(data.get("pred_prob"), errors="coerce")
    data["expected_value"] = pd.to_numeric(data.get("expected_value"), errors="coerce")
    if strategy == "top1_win":
        return data[data["pred_rank"] == 1].copy()
    if strategy == "top2_win":
        return data[data["pred_rank"].isin([1, 2])].copy()
    if strategy == "value_filter":
        return data[(data["expected_value"] >= 1.0) & data["pred_prob"].notna()].copy()
    raise ValueError(f"unknown strategy: {strategy}")


def metric_summary(frame: pd.DataFrame, strategy: str, min_sample: int = DEFAULT_MIN_SAMPLE) -> dict:
    selected = _selected_rows(frame, strategy)
    if selected.empty:
        return {
            "strategy": strategy,
            "bets": 0,
            "hit_count": 0,
            "hit_rate": None,
            "roi_pct": None,
            "profit_units": 0.0,
            "sample_status": "no_sample",
        }
    selected["win"] = pd.to_numeric(selected.get("win"), errors="coerce")
    selected = selected[selected["win"].notna()].copy()
    if selected.empty:
        return {
            "strategy": strategy,
            "bets": 0,
            "hit_count": 0,
            "hit_rate": None,
            "roi_pct": None,
            "profit_units": 0.0,
            "sample_status": "no_settled_results",
        }
    selected["win"] = selected["win"].fillna(0)
    selected["win_odds"] = pd.to_numeric(selected.get("win_odds"), errors="coerce")
    bets = int(len(selected))
    if bets == 0:
        return {
            "strategy": strategy,
            "bets": 0,
            "hit_count": 0,
            "hit_rate": None,
            "roi_pct": None,
            "profit_units": 0.0,
            "sample_status": "no_odds",
        }
    payout = (selected["win"] * selected["win_odds"].fillna(0)).sum()
    hit_count = int(selected["win"].sum())
    roi_pct = float(payout / bets * 100.0)
    return {
        "strategy": strategy,
        "bets": bets,
        "hit_count": hit_count,
        "hit_rate": float(hit_count / bets),
        "roi_pct": roi_pct,
        "profit_units": float(payout - bets),
        "sample_status": "enough_sample" if bets >= min_sample else "insufficient_sample",
    }


def daily_roi_stats(frame: pd.DataFrame) -> dict:
    if frame.empty or "artifact_date" not in frame.columns:
        return {
            "daily_roi_days": 0,
            "daily_roi_mean": None,
            "daily_roi_min": None,
            "daily_roi_max": None,
            "daily_roi_std": None,
            "daily_positive_day_rate": None,
            "daily_bet_min": 0,
        }
    data = frame.copy()
    data["win"] = pd.to_numeric(data.get("win"), errors="coerce")
    data["win_odds"] = pd.to_numeric(data.get("win_odds"), errors="coerce")
    valid = data[data["win"].notna()].copy()
    if valid.empty:
        return {
            "daily_roi_days": 0,
            "daily_roi_mean": None,
            "daily_roi_min": None,
            "daily_roi_max": None,
            "daily_roi_std": None,
            "daily_positive_day_rate": None,
            "daily_bet_min": 0,
        }
    valid["win"] = valid["win"].fillna(0)
    valid["_payout"] = valid["win"] * valid["win_odds"].fillna(0)
    daily = valid.groupby(valid["artifact_date"].astype(str), dropna=False).agg(
        bets=("win", "size"),
        payout=("_payout", "sum"),
    )
    daily["roi_pct"] = daily["payout"] / daily["bets"] * 100.0
    daily["profit_units"] = daily["payout"] - daily["bets"]
    return {
        "daily_roi_days": int(len(daily)),
        "daily_roi_mean": float(daily["roi_pct"].mean()),
        "daily_roi_min": float(daily["roi_pct"].min()),
        "daily_roi_max": float(daily["roi_pct"].max()),
        "daily_roi_std": float(daily["roi_pct"].std(ddof=0)),
        "daily_positive_day_rate": float((daily["profit_units"] > 0).mean()),
        "daily_bet_min": int(daily["bets"].min()),
    }


def _bucket_series(series: pd.Series, bins: Iterable[float], labels: list[str]) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.cut(numeric, bins=list(bins), labels=labels, include_lowest=True).astype("string").fillna("missing")


def build_current_slices(frame: pd.DataFrame, min_sample: int = DEFAULT_MIN_SAMPLE) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=SLICE_COLUMNS)
    rows: list[dict] = []
    for strategy in ["top1_win", "top2_win", "value_filter"]:
        selected = _selected_rows(frame, strategy)
        if selected.empty:
            continue
        selected = selected.copy()
        selected["prob_bucket"] = _bucket_series(
            selected.get("pred_prob", pd.Series(dtype=float)),
            [0, 0.12, 0.16, 0.20, 0.30, 1.01],
            ["<=0.12", "0.12-0.16", "0.16-0.20", "0.20-0.30", ">0.30"],
        )
        selected["odds_bucket"] = _bucket_series(
            selected.get("win_odds", pd.Series(dtype=float)),
            [0, 1.5, 3, 5, 10, 30, 9999],
            ["<=1.5", "1.5-3", "3-5", "5-10", "10-30", ">30"],
        )
        selected["ev_bucket"] = _bucket_series(
            selected.get("expected_value", pd.Series(dtype=float)),
            [-999, 0.8, 1.0, 1.2, 1.6, 9999],
            ["<0.8", "0.8-1.0", "1.0-1.2", "1.2-1.6", ">1.6"],
        )
        slice_columns = ["course_id", "race_number", "lane", "prob_bucket", "odds_bucket", "ev_bucket"]
        for column in slice_columns:
            if column not in selected.columns:
                continue
            for value, group in selected.groupby(column, dropna=False):
                summary = metric_summary(group, strategy, min_sample=min_sample)
                summary.update(daily_roi_stats(group))
                summary.update(
                    {
                        "slice_type": column,
                        "slice_value": str(value),
                        "sample_status": "enough_sample"
                        if summary["bets"] >= min_sample
                        else "insufficient_sample",
                        "unique_days": int(group["artifact_date"].astype(str).nunique())
                        if "artifact_date" in group.columns
                        else 0,
                    }
                )
                rows.append(summary)
    if not rows:
        return pd.DataFrame(columns=SLICE_COLUMNS)
    return (
        pd.DataFrame(rows)
        .reindex(columns=SLICE_COLUMNS)
        .sort_values(["strategy", "slice_type", "roi_pct"], ascending=[True, True, False])
    )


def stable_candidate_conditions(
    slices: pd.DataFrame,
    *,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    min_days: int = DEFAULT_MIN_DAYS,
    min_roi_pct: float = DEFAULT_MIN_ROI_PCT,
    min_positive_day_rate: float = DEFAULT_MIN_POSITIVE_DAY_RATE,
    min_daily_roi_floor_pct: float = DEFAULT_MIN_DAILY_ROI_FLOOR_PCT,
    limit: int = 20,
) -> pd.DataFrame:
    if slices.empty:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)
    data = slices.copy()
    numeric_columns = [
        "bets",
        "unique_days",
        "daily_roi_days",
        "hit_count",
        "hit_rate",
        "roi_pct",
        "profit_units",
        "daily_roi_min",
        "daily_roi_mean",
        "daily_roi_max",
        "daily_roi_std",
        "daily_positive_day_rate",
        "daily_bet_min",
    ]
    for column in numeric_columns:
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    for column in CANDIDATE_COLUMNS:
        if column not in data.columns:
            data[column] = None
    qualified = data[
        (data["bets"] >= min_sample)
        & (data["daily_roi_days"] >= min_days)
        & (data["roi_pct"] >= min_roi_pct)
        & (data["daily_positive_day_rate"] >= min_positive_day_rate)
        & (data["daily_roi_min"] >= min_daily_roi_floor_pct)
    ].copy()
    if qualified.empty:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)
    qualified["condition_id"] = (
        qualified["strategy"].astype(str)
        + "|"
        + qualified["slice_type"].astype(str)
        + "|"
        + qualified["slice_value"].astype(str)
    )
    qualified["candidate_status"] = "shadow_only_candidate"
    qualified["production_adoption"] = False
    qualified["reason"] = "passed_sample_cross_day_roi_stability_gates"
    qualified = qualified.sort_values(
        ["roi_pct", "daily_positive_day_rate", "daily_roi_min", "bets"],
        ascending=[False, False, False, False],
    ).head(limit)
    return qualified[CANDIDATE_COLUMNS]


def candidate_rejection_diagnostics(
    slices: pd.DataFrame,
    candidate_conditions: pd.DataFrame,
    *,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    min_days: int = DEFAULT_MIN_DAYS,
    min_roi_pct: float = DEFAULT_MIN_ROI_PCT,
    min_positive_day_rate: float = DEFAULT_MIN_POSITIVE_DAY_RATE,
    min_daily_roi_floor_pct: float = DEFAULT_MIN_DAILY_ROI_FLOOR_PCT,
    limit: int = 50,
) -> tuple[dict, pd.DataFrame]:
    if slices.empty:
        return (
            {
                "total_slices": 0,
                "candidate_count": 0,
                "rejected_count": 0,
                "failed_gate_counts": {},
                "dominant_failed_gate": None,
            },
            pd.DataFrame(columns=CANDIDATE_REJECTION_COLUMNS),
        )
    data = slices.copy()
    for column in [
        "bets",
        "daily_roi_days",
        "roi_pct",
        "daily_positive_day_rate",
        "daily_roi_min",
    ]:
        data[column] = pd.to_numeric(data.get(column), errors="coerce")
    data["condition_id"] = (
        data["strategy"].astype(str)
        + "|"
        + data["slice_type"].astype(str)
        + "|"
        + data["slice_value"].astype(str)
    )
    candidate_ids = set(candidate_conditions.get("condition_id", pd.Series(dtype=str)).astype(str))
    rows: list[dict] = []
    failed_gate_counts = {
        "min_sample": 0,
        "min_days": 0,
        "min_roi_pct": 0,
        "min_positive_day_rate": 0,
        "min_daily_roi_floor_pct": 0,
    }
    for _, row in data.iterrows():
        condition_id = str(row["condition_id"])
        if condition_id in candidate_ids:
            continue
        failed: list[str] = []
        if pd.isna(row["bets"]) or float(row["bets"]) < min_sample:
            failed.append("min_sample")
        if pd.isna(row["daily_roi_days"]) or float(row["daily_roi_days"]) < min_days:
            failed.append("min_days")
        if pd.isna(row["roi_pct"]) or float(row["roi_pct"]) < min_roi_pct:
            failed.append("min_roi_pct")
        if pd.isna(row["daily_positive_day_rate"]) or float(row["daily_positive_day_rate"]) < min_positive_day_rate:
            failed.append("min_positive_day_rate")
        if pd.isna(row["daily_roi_min"]) or float(row["daily_roi_min"]) < min_daily_roi_floor_pct:
            failed.append("min_daily_roi_floor_pct")
        for gate in failed:
            failed_gate_counts[gate] += 1
        rows.append(
            {
                "condition_id": condition_id,
                "strategy": row.get("strategy"),
                "slice_type": row.get("slice_type"),
                "slice_value": row.get("slice_value"),
                "bets": row.get("bets"),
                "daily_roi_days": row.get("daily_roi_days"),
                "roi_pct": row.get("roi_pct"),
                "daily_positive_day_rate": row.get("daily_positive_day_rate"),
                "daily_roi_min": row.get("daily_roi_min"),
                "failed_gates": ",".join(failed),
                "primary_failed_gate": failed[0] if failed else None,
            }
        )
    diagnostics = pd.DataFrame(rows).reindex(columns=CANDIDATE_REJECTION_COLUMNS)
    if not diagnostics.empty:
        diagnostics["roi_pct"] = pd.to_numeric(diagnostics["roi_pct"], errors="coerce")
        diagnostics["bets"] = pd.to_numeric(diagnostics["bets"], errors="coerce").fillna(0)
        diagnostics = diagnostics.sort_values(["roi_pct", "bets"], ascending=[False, False]).head(limit)
    dominant = None
    if failed_gate_counts:
        dominant = max(failed_gate_counts.items(), key=lambda item: item[1])[0]
    return (
        {
            "total_slices": int(len(data)),
            "candidate_count": int(len(candidate_ids)),
            "rejected_count": int(len(rows)),
            "failed_gate_counts": failed_gate_counts,
            "dominant_failed_gate": dominant,
        },
        diagnostics,
    )


def load_legacy_daily_summary(legacy_daily_root: Path | None) -> pd.DataFrame:
    if legacy_daily_root is None:
        return pd.DataFrame()
    path = legacy_daily_root / "daily_summary_history.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, low_memory=False)
    if frame.empty or "date" not in frame.columns:
        return pd.DataFrame()
    numeric_columns = [
        "settledBetCount",
        "hitCount",
        "stakeAmount",
        "payoutAmount",
        "settledRoi",
        "hitRate",
        "resultReadyCount",
        "resultMissingCount",
        "betCount",
        "buyCount",
        "watchCount",
        "skipCount",
    ]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def load_legacy_prediction_candidates(legacy_daily_root: Path | None) -> pd.DataFrame:
    if legacy_daily_root is None or not legacy_daily_root.exists():
        return pd.DataFrame()
    rows: list[dict] = []
    for path in sorted(legacy_daily_root.glob("20*_summary.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for settlement in payload.get("settlements", []) or []:
            actual_combo = settlement.get("actualTrifecta")
            payout = safe_float(settlement.get("trifectaPayout"), default=0.0)
            predictions = settlement.get("predictions") or []
            if not actual_combo or not isinstance(predictions, list):
                continue
            for prediction in predictions:
                if not isinstance(prediction, dict):
                    continue
                combo = str(prediction.get("combo") or "")
                if not combo:
                    continue
                rows.append(
                    {
                        "date": str(settlement.get("date") or payload.get("date") or path.name[:8]),
                        "jcd": str(settlement.get("jcd") or payload.get("jcd") or ""),
                        "venue": settlement.get("venue"),
                        "race_no": settlement.get("raceNo") or settlement.get("rno"),
                        "combo": combo,
                        "actual_trifecta": actual_combo,
                        "trifecta_payout": payout,
                        "decision": str(prediction.get("decision") or ""),
                        "rank": safe_float(prediction.get("rank"), default=0.0),
                        "prob": safe_float(prediction.get("prob"), default=0.0),
                        "odds": safe_float(prediction.get("odds"), default=0.0),
                        "expected_value": safe_float(prediction.get("expectedValue"), default=0.0),
                        "source_type": prediction.get("sourceType") or prediction.get("source_type"),
                        "hit": 1 if combo == str(actual_combo) else 0,
                        "artifact": str(path),
                    }
                )
    if not rows:
        return pd.DataFrame(columns=LEGACY_PREDICTION_COLUMNS)
    frame = pd.DataFrame(rows)
    frame = frame.reindex(columns=LEGACY_PREDICTION_COLUMNS)
    for column in ["rank", "prob", "odds", "expected_value", "trifecta_payout", "hit"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def legacy_candidate_summary(frame: pd.DataFrame, min_sample: int = DEFAULT_MIN_SAMPLE) -> list[dict]:
    if frame.empty:
        return []
    strategies = {
        "legacy_trifecta_rank1": frame[pd.to_numeric(frame["rank"], errors="coerce") == 1],
        "legacy_trifecta_rank3": frame[pd.to_numeric(frame["rank"], errors="coerce").between(1, 3)],
        "legacy_trifecta_watch_or_buy": frame[frame["decision"].isin(["WATCH", "BUY"])],
        "legacy_trifecta_buy": frame[frame["decision"] == "BUY"],
    }
    rows: list[dict] = []
    stake_unit = 100.0
    for strategy, selected in strategies.items():
        selected = selected.copy()
        bets = int(len(selected))
        if bets == 0:
            rows.append(
                {
                    "strategy": strategy,
                    "bets": 0,
                    "hit_count": 0,
                    "hit_rate": None,
                    "roi_pct": None,
                    "profit_yen_per_100": 0.0,
                    "sample_status": "no_sample",
                }
            )
            continue
        hit_count = int(pd.to_numeric(selected["hit"], errors="coerce").fillna(0).sum())
        payout = float((selected["hit"] * selected["trifecta_payout"]).sum())
        stake = bets * stake_unit
        rows.append(
            {
                "strategy": strategy,
                "bets": bets,
                "hit_count": hit_count,
                "hit_rate": float(hit_count / bets),
                "roi_pct": float(payout / stake * 100.0) if stake > 0 else None,
                "profit_yen_per_100": float(payout - stake),
                "sample_status": "enough_sample" if bets >= min_sample else "insufficient_sample",
            }
        )
    return rows


def summarize_legacy(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {
            "available": False,
            "rows": 0,
            "unique_dates": 0,
            "settled_bet_days": 0,
            "settled_bets": 0,
            "roi_pct": None,
            "hit_rate": None,
        }
    data = frame.copy()
    settled_bets = data.get("settledBetCount", pd.Series(dtype=float)).fillna(0)
    stake = data.get("stakeAmount", pd.Series(dtype=float)).fillna(0)
    payout = data.get("payoutAmount", pd.Series(dtype=float)).fillna(0)
    hit_count = data.get("hitCount", pd.Series(dtype=float)).fillna(0)
    settled_total = float(settled_bets.sum())
    stake_total = float(stake.sum())
    payout_total = float(payout.sum())
    return {
        "available": True,
        "rows": int(len(data)),
        "unique_dates": int(data["date"].astype(str).nunique()),
        "settled_bet_days": int((settled_bets > 0).sum()),
        "settled_bets": int(settled_total),
        "stake_amount": stake_total,
        "payout_amount": payout_total,
        "roi_pct": float(payout_total / stake_total * 100.0) if stake_total > 0 else None,
        "hit_rate": float(hit_count.sum() / settled_total) if settled_total > 0 else None,
        "latest_date": str(data["date"].dropna().astype(str).max()) if data["date"].notna().any() else None,
    }


def top_slices(slices: pd.DataFrame, limit: int = 10) -> list[dict]:
    if slices.empty:
        return []
    data = slices.copy()
    data["roi_pct"] = pd.to_numeric(data["roi_pct"], errors="coerce")
    data["bets"] = pd.to_numeric(data["bets"], errors="coerce").fillna(0)
    return (
        data.sort_values(["sample_status", "roi_pct", "bets"], ascending=[True, False, False])
        .head(limit)
        .to_dict(orient="records")
    )


def recommend_actions(
    strategy_summary: list[dict],
    slices: pd.DataFrame,
    *,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    min_days: int = DEFAULT_MIN_DAYS,
    min_roi_pct: float = DEFAULT_MIN_ROI_PCT,
    min_positive_day_rate: float = DEFAULT_MIN_POSITIVE_DAY_RATE,
    min_daily_roi_floor_pct: float = DEFAULT_MIN_DAILY_ROI_FLOOR_PCT,
) -> dict:
    candidate_frame = stable_candidate_conditions(
        slices,
        min_sample=min_sample,
        min_days=min_days,
        min_roi_pct=min_roi_pct,
        min_positive_day_rate=min_positive_day_rate,
        min_daily_roi_floor_pct=min_daily_roi_floor_pct,
        limit=10,
    )
    candidates = candidate_frame.to_dict(orient="records")

    profitable_strategy = [
        row
        for row in strategy_summary
        if row.get("sample_status") == "enough_sample"
        and row.get("roi_pct") is not None
        and row["roi_pct"] >= min_roi_pct
    ]
    live_allowed = bool(candidates and profitable_strategy)
    return {
        "decision": "paper_trade_only" if not live_allowed else "candidate_found_requires_manual_review",
        "live_betting_allowed": live_allowed,
        "reason": (
            "No strategy and slice both satisfy minimum sample, cross-day, and ROI gates."
            if not live_allowed
            else "A candidate passed numeric gates, but still requires manual review before production use."
        ),
        "candidate_slices": candidates,
        "required_gates": {
            "min_sample": int(min_sample),
            "min_days": int(min_days),
            "min_roi_pct": float(min_roi_pct),
            "min_positive_day_rate": float(min_positive_day_rate),
            "min_daily_roi_floor_pct": float(min_daily_roi_floor_pct),
        },
    }


def bankroll_guard(bankroll_yen: int | None, live_allowed: bool) -> dict:
    if bankroll_yen is None or bankroll_yen <= 0:
        return {
            "bankroll_yen": None,
            "unit_stake_yen": 0,
            "max_daily_loss_yen": 0,
            "rule": "Bankroll was not provided. Use paper trading only.",
        }
    max_daily_loss = max(100, int(bankroll_yen * 0.01 // 100 * 100))
    unit = 0 if not live_allowed else max(100, int(bankroll_yen * 0.001 // 100 * 100))
    return {
        "bankroll_yen": int(bankroll_yen),
        "unit_stake_yen": int(unit),
        "max_daily_loss_yen": int(max_daily_loss),
        "rule": (
            "Live betting is blocked by profitability gates; record-only mode."
            if not live_allowed
            else "If manually approved, stop for the day when max_daily_loss_yen is reached."
        ),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_analysis_date(current: pd.DataFrame, target_date: str | None = None) -> str:
    if target_date:
        return str(target_date)
    if "artifact_date" in current.columns and current["artifact_date"].notna().any():
        return str(current["artifact_date"].dropna().astype(str).max())
    return datetime.now().date().isoformat()


def _strategy_by_name(strategy_summary: list[dict], name: str) -> dict:
    for row in strategy_summary:
        if row.get("strategy") == name:
            return row
    return {}


def _daily_history_row(payload: dict) -> dict:
    strategies = payload["current"]["strategy_summary"]
    top1 = _strategy_by_name(strategies, "top1_win")
    top2 = _strategy_by_name(strategies, "top2_win")
    value = _strategy_by_name(strategies, "value_filter")
    gates = payload["stability_gates"]
    recommendation = payload["recommendation"]
    return {
        "analysis_date": payload["analysis_date"],
        "analysis_run_at": payload["analysis_run_at"],
        "analysis_status": payload["analysis_status"],
        "decision": recommendation.get("decision"),
        "live_betting_allowed": recommendation.get("live_betting_allowed"),
        "candidate_conditions_count": len(payload.get("candidate_conditions", [])),
        "current_days": payload["current"].get("days"),
        "settled_rows": payload["current"].get("settled_rows"),
        "top1_bets": top1.get("bets", 0),
        "top1_hit_rate": top1.get("hit_rate"),
        "top1_roi_pct": top1.get("roi_pct"),
        "top2_bets": top2.get("bets", 0),
        "top2_hit_rate": top2.get("hit_rate"),
        "top2_roi_pct": top2.get("roi_pct"),
        "value_filter_bets": value.get("bets", 0),
        "value_filter_hit_rate": value.get("hit_rate"),
        "value_filter_roi_pct": value.get("roi_pct"),
        "min_sample": gates.get("min_sample"),
        "min_days": gates.get("min_days"),
        "min_roi_pct": gates.get("min_roi_pct"),
        "min_positive_day_rate": gates.get("min_positive_day_rate"),
        "min_daily_roi_floor_pct": gates.get("min_daily_roi_floor_pct"),
    }


def update_profitability_daily_history(output_dir: Path, payload: dict) -> None:
    path = output_dir / "profitability_daily_history.csv"
    row = pd.DataFrame([_daily_history_row(payload)]).reindex(columns=DAILY_HISTORY_COLUMNS)
    if path.exists():
        existing = pd.read_csv(path)
        existing = existing[existing["analysis_date"].astype(str) != str(payload["analysis_date"])]
        frame = pd.concat([existing, row], ignore_index=True, sort=False)
    else:
        frame = row
    frame = frame.reindex(columns=DAILY_HISTORY_COLUMNS)
    frame.sort_values("analysis_date").to_csv(path, index=False, encoding="utf-8-sig")


def update_candidate_condition_history(output_dir: Path, payload: dict) -> None:
    path = output_dir / "candidate_condition_history.csv"
    candidates = pd.DataFrame(payload.get("candidate_conditions", []))
    if candidates.empty:
        rows = pd.DataFrame(columns=CANDIDATE_HISTORY_COLUMNS)
    else:
        candidates.insert(0, "analysis_run_at", payload["analysis_run_at"])
        candidates.insert(0, "analysis_date", payload["analysis_date"])
        rows = candidates.reindex(columns=CANDIDATE_HISTORY_COLUMNS)
    if path.exists():
        existing = pd.read_csv(path)
        existing = existing[existing["analysis_date"].astype(str) != str(payload["analysis_date"])]
        frame = pd.concat([existing, rows], ignore_index=True, sort=False)
    else:
        frame = rows
    frame = frame.reindex(columns=CANDIDATE_HISTORY_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(["analysis_date", "roi_pct"], ascending=[True, False])
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def build_markdown_report(payload: dict) -> str:
    lines = [
        "# Profitability Analysis",
        "",
        "This report is observational. It does not change production BUY rules.",
        "",
    ]
    recommendation = payload.get("recommendation")
    if recommendation:
        lines.extend(
            [
                "## Profitability Gate",
                f"- decision: {recommendation['decision']}",
                f"- live_betting_allowed: {recommendation['live_betting_allowed']}",
                f"- reason: {recommendation['reason']}",
                "",
            ]
        )
    guard = payload.get("bankroll_guard")
    if guard:
        lines.extend(
            [
                "## Bankroll Guard",
                f"- bankroll_yen: {guard['bankroll_yen']}",
                f"- unit_stake_yen: {guard['unit_stake_yen']}",
                f"- max_daily_loss_yen: {guard['max_daily_loss_yen']}",
                f"- rule: {guard['rule']}",
                "",
            ]
        )
    lines.append("## Current CLI Daily Data")
    current = payload["current"]
    lines.extend(
        [
            f"- days: {current['days']}",
            f"- rows: {current['rows']}",
            f"- settled rows: {current['settled_rows']}",
            "",
            "## Strategy Summary",
            "| strategy | bets | hit_rate | roi_pct | profit_units | sample |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in current["strategy_summary"]:
        hit = "" if row["hit_rate"] is None else f"{row['hit_rate']:.3f}"
        roi = "" if row["roi_pct"] is None else f"{row['roi_pct']:.1f}"
        lines.append(
            f"| {row['strategy']} | {row['bets']} | {hit} | {roi} | {row['profit_units']:.1f} | {row['sample_status']} |"
        )
    lines.extend(
        [
            "",
            "## Top Candidate Slices",
            "| strategy | slice | value | bets | days | hit_rate | roi_pct | sample |",
            "|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in payload["top_slices"]:
        hit = "" if row.get("hit_rate") is None else f"{row['hit_rate']:.3f}"
        roi = "" if row.get("roi_pct") is None else f"{row['roi_pct']:.1f}"
        lines.append(
            f"| {row['strategy']} | {row['slice_type']} | {row['slice_value']} | {int(row['bets'])} | "
            f"{int(row.get('unique_days', 0))} | {hit} | {roi} | {row['sample_status']} |"
        )
    lines.extend(
        [
            "",
            "## Stable Candidate Conditions",
            "These rows are shadow-only candidates. They are not production BUY rules.",
            "",
        ]
    )
    candidates = payload.get("candidate_conditions", [])
    if not candidates:
        lines.extend(
            [
                "No stable candidate condition passed the configured gates.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "| condition | bets | days | daily_min_roi | positive_day_rate | roi_pct | status |",
                "|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for row in candidates:
            lines.append(
                f"| {row['condition_id']} | {int(row['bets'])} | {int(row['daily_roi_days'])} | "
                f"{float(row['daily_roi_min']):.1f} | {float(row['daily_positive_day_rate']):.2f} | "
                f"{float(row['roi_pct']):.1f} | {row['candidate_status']} |"
            )
    rejection = payload.get("candidate_rejection_summary", {})
    lines.extend(
        [
            "",
            "## Candidate Rejection Diagnostics",
            f"- total_slices: {rejection.get('total_slices', 0)}",
            f"- rejected_count: {rejection.get('rejected_count', 0)}",
            f"- dominant_failed_gate: {rejection.get('dominant_failed_gate')}",
            f"- failed_gate_counts: {rejection.get('failed_gate_counts', {})}",
        ]
    )
    legacy = payload["legacy"]
    lines.extend(
        [
            "",
            "## Legacy Daily Summary",
            f"- available: {legacy['available']}",
            f"- unique dates: {legacy['unique_dates']}",
            f"- settled bet days: {legacy['settled_bet_days']}",
            f"- settled bets: {legacy['settled_bets']}",
            f"- roi_pct: {'' if legacy['roi_pct'] is None else round(legacy['roi_pct'], 1)}",
            f"- hit_rate: {'' if legacy['hit_rate'] is None else round(legacy['hit_rate'], 3)}",
            "",
            "## Legacy Saved-Prediction Trifecta Simulation",
            "| strategy | bets | hit_rate | roi_pct | profit_yen_per_100 | sample |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in payload["legacy_candidate_summary"]:
        hit = "" if row["hit_rate"] is None else f"{row['hit_rate']:.3f}"
        roi = "" if row["roi_pct"] is None else f"{row['roi_pct']:.1f}"
        lines.append(
            f"| {row['strategy']} | {row['bets']} | {hit} | {roi} | {row['profit_yen_per_100']:.0f} | {row['sample_status']} |"
        )
    lines.extend(
        [
            "",
            "## Next Decision",
            "- Keep this as shadow analysis until enough settled samples are accumulated.",
            "- Do not promote any slice to production unless it has enough cross-day samples and ROI remains stable.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_analysis(
    paths: AnalysisPaths,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    min_days: int = DEFAULT_MIN_DAYS,
    min_roi_pct: float = DEFAULT_MIN_ROI_PCT,
    min_positive_day_rate: float = DEFAULT_MIN_POSITIVE_DAY_RATE,
    min_daily_roi_floor_pct: float = DEFAULT_MIN_DAILY_ROI_FLOOR_PCT,
    bankroll_yen: int | None = None,
    target_date: str | None = None,
) -> dict:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    current = load_current_settlements(paths.current_daily_root)
    settled = current[current.get("result_status", pd.Series(dtype=str)).isin(["settled", "partial_result"])].copy()
    analysis_date = resolve_analysis_date(current, target_date=target_date)
    analysis_run_at = datetime.now().isoformat(timespec="seconds")
    strategy_summary = [
        metric_summary(settled, strategy, min_sample=min_sample)
        for strategy in ["top1_win", "top2_win", "value_filter"]
    ]
    slices = build_current_slices(settled, min_sample=min_sample)
    legacy_frame = load_legacy_daily_summary(paths.legacy_daily_root)
    legacy_summary = summarize_legacy(legacy_frame)
    legacy_candidates = load_legacy_prediction_candidates(paths.legacy_daily_root)
    legacy_candidates_summary = legacy_candidate_summary(legacy_candidates, min_sample=min_sample)
    candidate_conditions = stable_candidate_conditions(
        slices,
        min_sample=min_sample,
        min_days=min_days,
        min_roi_pct=min_roi_pct,
        min_positive_day_rate=min_positive_day_rate,
        min_daily_roi_floor_pct=min_daily_roi_floor_pct,
    )
    candidate_rejection_summary, candidate_rejections = candidate_rejection_diagnostics(
        slices,
        candidate_conditions,
        min_sample=min_sample,
        min_days=min_days,
        min_roi_pct=min_roi_pct,
        min_positive_day_rate=min_positive_day_rate,
        min_daily_roi_floor_pct=min_daily_roi_floor_pct,
    )
    recommendation = recommend_actions(
        strategy_summary,
        slices,
        min_sample=min_sample,
        min_days=min_days,
        min_roi_pct=min_roi_pct,
        min_positive_day_rate=min_positive_day_rate,
        min_daily_roi_floor_pct=min_daily_roi_floor_pct,
    )
    payload = {
        "analysis_status": "shadow_only",
        "analysis_date": analysis_date,
        "analysis_run_at": analysis_run_at,
        "min_sample": int(min_sample),
        "stability_gates": {
            "min_sample": int(min_sample),
            "min_days": int(min_days),
            "min_roi_pct": float(min_roi_pct),
            "min_positive_day_rate": float(min_positive_day_rate),
            "min_daily_roi_floor_pct": float(min_daily_roi_floor_pct),
        },
        "recommendation": recommendation,
        "bankroll_guard": bankroll_guard(bankroll_yen, recommendation["live_betting_allowed"]),
        "current": {
            "daily_root": str(paths.current_daily_root),
            "days": int(current["artifact_date"].nunique()) if "artifact_date" in current.columns else 0,
            "rows": int(len(current)),
            "settled_rows": int(len(settled)),
            "strategy_summary": strategy_summary,
        },
        "legacy": legacy_summary,
        "legacy_prediction_candidates": {
            "rows": int(len(legacy_candidates)),
            "dates": int(legacy_candidates["date"].astype(str).nunique()) if not legacy_candidates.empty else 0,
        },
        "legacy_candidate_summary": legacy_candidates_summary,
        "top_slices": top_slices(slices),
        "candidate_conditions": candidate_conditions.to_dict(orient="records"),
        "candidate_rejection_summary": candidate_rejection_summary,
        "notes": [
            "ROI is the primary monetization metric; hit rate alone is insufficient.",
            "This output is for validation and does not alter prediction or BUY logic.",
        ],
    }
    write_json(paths.output_dir / "profitability_summary.json", payload)
    write_json(
        paths.output_dir / "candidate_conditions.json",
        {
            "analysis_status": "shadow_only",
            "analysis_date": payload["analysis_date"],
            "analysis_run_at": payload["analysis_run_at"],
            "stability_gates": payload["stability_gates"],
            "candidate_conditions": payload["candidate_conditions"],
            "candidate_rejection_summary": payload["candidate_rejection_summary"],
        },
    )
    write_json(
        paths.output_dir / "candidate_rejection_summary.json",
        {
            "analysis_status": "shadow_only",
            "analysis_date": payload["analysis_date"],
            "analysis_run_at": payload["analysis_run_at"],
            "stability_gates": payload["stability_gates"],
            "candidate_rejection_summary": payload["candidate_rejection_summary"],
        },
    )
    if not slices.empty:
        slices.to_csv(paths.output_dir / "current_cli_slices.csv", index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(columns=SLICE_COLUMNS).to_csv(
            paths.output_dir / "current_cli_slices.csv",
            index=False,
            encoding="utf-8-sig",
        )
    candidate_conditions.to_csv(paths.output_dir / "candidate_conditions.csv", index=False, encoding="utf-8-sig")
    candidate_rejections.to_csv(paths.output_dir / "candidate_rejections.csv", index=False, encoding="utf-8-sig")
    if not legacy_frame.empty:
        legacy_frame.to_csv(paths.output_dir / "legacy_daily_summary.csv", index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(columns=["date"]).to_csv(
            paths.output_dir / "legacy_daily_summary.csv",
            index=False,
            encoding="utf-8-sig",
        )
    if not legacy_candidates.empty:
        legacy_candidates.to_csv(paths.output_dir / "legacy_prediction_candidates.csv", index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(columns=LEGACY_PREDICTION_COLUMNS).to_csv(
            paths.output_dir / "legacy_prediction_candidates.csv",
            index=False,
            encoding="utf-8-sig",
        )
    update_profitability_daily_history(paths.output_dir, payload)
    update_candidate_condition_history(paths.output_dir, payload)
    (paths.output_dir / "profitability_report.md").write_text(build_markdown_report(payload), encoding="utf-8")
    return payload
