from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path

import pandas as pd

from .daily_ops import DailyPaths, normalize_date, valid_win_odds, write_json

ODDS_REFRESH_AFTER = time(18, 0)
NIGHT_SETTLEMENT_AFTER = time(21, 30)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"read_error": str(exc)}


def _prediction_status(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    frame = pd.read_csv(path)
    win_odds = valid_win_odds(frame.get("win_odds"))
    expected_value = pd.to_numeric(frame.get("expected_value"), errors="coerce")
    pred_prob = pd.to_numeric(frame.get("pred_prob"), errors="coerce")
    return {
        "exists": True,
        "rows": int(len(frame)),
        "races": int(frame["race_id"].astype(str).nunique()) if "race_id" in frame.columns else 0,
        "courses": int(frame["course_id"].astype(str).str.zfill(2).nunique()) if "course_id" in frame.columns else 0,
        "missing_pred_prob_rows": int(pred_prob.isna().sum()),
        "missing_win_odds_rows": int(win_odds.isna().sum()),
        "missing_expected_value_rows": int(expected_value.isna().sum()),
    }


def _settlement_status(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    frame = pd.read_csv(path)
    settled_mask = frame.get("result_status", pd.Series(dtype=str)).astype(str).isin(["settled", "partial_result"])
    return {
        "exists": True,
        "rows": int(len(frame)),
        "races": int(frame["race_id"].astype(str).nunique()) if "race_id" in frame.columns else 0,
        "settled_races": int(frame.loc[settled_mask, "race_id"].astype(str).nunique()) if "race_id" in frame.columns else 0,
        "unavailable_rows": int((~settled_mask).sum()) if "result_status" in frame.columns else 0,
    }


def _profitability_status(project_root: Path) -> dict:
    output_dir = project_root / "output" / "analysis" / "profitability"
    path = output_dir / "profitability_summary.json"
    payload = _read_json(path)
    if not payload:
        return {"exists": False}
    recommendation = payload.get("recommendation", {})
    guard = payload.get("bankroll_guard", {})
    current = payload.get("current", {})
    candidate_conditions = payload.get("candidate_conditions", []) or []
    gates = payload.get("stability_gates", {})
    rejection = payload.get("candidate_rejection_summary") or _read_json(output_dir / "candidate_rejection_summary.json").get(
        "candidate_rejection_summary",
        {},
    )
    current_days = current.get("days")
    min_days = gates.get("min_days")
    try:
        min_days_remaining = max(0, int(min_days) - int(current_days))
    except (TypeError, ValueError):
        min_days_remaining = None
    history_days = 0
    history_rows = 0
    history_path = output_dir / "profitability_daily_history.csv"
    if history_path.exists():
        try:
            history = pd.read_csv(history_path)
            history_rows = int(len(history))
            if "analysis_date" in history.columns and not history.empty:
                history_days = int(history["analysis_date"].astype(str).nunique())
        except Exception:
            history_days = 0
            history_rows = 0
    candidate_history_rows = 0
    candidate_history_days = 0
    candidate_history_path = output_dir / "candidate_condition_history.csv"
    if candidate_history_path.exists():
        try:
            candidate_history = pd.read_csv(candidate_history_path)
            candidate_history_rows = int(len(candidate_history))
            if "analysis_date" in candidate_history.columns and not candidate_history.empty:
                candidate_history_days = int(candidate_history["analysis_date"].astype(str).nunique())
        except Exception:
            candidate_history_rows = 0
            candidate_history_days = 0
    return {
        "exists": True,
        "analysis_status": payload.get("analysis_status"),
        "analysis_date": payload.get("analysis_date"),
        "decision": recommendation.get("decision"),
        "live_betting_allowed": recommendation.get("live_betting_allowed"),
        "unit_stake_yen": guard.get("unit_stake_yen"),
        "current_days": current_days,
        "settled_rows": current.get("settled_rows"),
        "candidate_conditions_count": len(candidate_conditions),
        "candidate_history_rows": candidate_history_rows,
        "candidate_history_days": candidate_history_days,
        "history_rows": history_rows,
        "history_days": history_days,
        "min_days_remaining": min_days_remaining,
        "dominant_failed_gate": rejection.get("dominant_failed_gate"),
        "failed_gate_counts": rejection.get("failed_gate_counts", {}),
        "rejected_count": rejection.get("rejected_count"),
        "total_slices": rejection.get("total_slices"),
        "stability_gates": gates,
    }


def _timing_status(target_date: str, now: datetime) -> dict:
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    current_date = now.date()
    current_time = now.time()
    is_past_date = target < current_date
    is_future_date = target > current_date
    return {
        "current_time": now.isoformat(timespec="seconds"),
        "odds_refresh_after": ODDS_REFRESH_AFTER.strftime("%H:%M"),
        "night_settlement_after": NIGHT_SETTLEMENT_AFTER.strftime("%H:%M"),
        "is_past_date": is_past_date,
        "is_future_date": is_future_date,
        "odds_refresh_due": is_past_date or (target == current_date and current_time >= ODDS_REFRESH_AFTER),
        "night_settlement_due": is_past_date or (target == current_date and current_time >= NIGHT_SETTLEMENT_AFTER),
    }


def _next_action(
    predictions: dict,
    odds: dict,
    settlement: dict,
    profitability: dict,
    timing: dict,
) -> str:
    if timing.get("is_future_date"):
        return "wait_for_target_date"
    if not predictions.get("exists"):
        return "run_morning"
    if not settlement.get("exists") and timing.get("night_settlement_due"):
        return "run_night_after_results"
    if predictions.get("missing_win_odds_rows", 0) > 0 and not settlement.get("exists"):
        if not timing.get("odds_refresh_due"):
            return "wait_for_odds_refresh"
        return "run_odds_refresh"
    if not settlement.get("exists"):
        if not timing.get("night_settlement_due"):
            return "wait_for_night_settlement"
        return "run_night_after_results"
    if profitability.get("live_betting_allowed") is True:
        return "manual_review_candidate"
    return "paper_trade_only"


def _next_command(next_action: str, target_date: str) -> str | None:
    commands = {
        "run_morning": f"py -3.13 daily_run.py --date {target_date} --phase morning",
        "run_odds_refresh": f"py -3.13 daily_run.py --date {target_date} --phase odds --force-refresh",
        "run_night_after_results": f"py -3.13 daily_run.py --date {target_date} --phase night --bankroll-yen 10000",
        "manual_review_candidate": f"py -3.13 daily_status.py --date {target_date}",
    }
    return commands.get(next_action)


def _next_action_reason(next_action: str, predictions: dict, profitability: dict, timing: dict) -> str:
    if next_action == "wait_for_target_date":
        return "Target date is in the future."
    if next_action == "run_morning":
        return "Morning predictions are missing."
    if next_action == "wait_for_odds_refresh":
        return f"Official odds refresh is scheduled after {timing.get('odds_refresh_after')}."
    if next_action == "run_odds_refresh":
        return f"{predictions.get('missing_win_odds_rows', 0)} prediction rows still miss official win odds."
    if next_action == "wait_for_night_settlement":
        return f"Night settlement is scheduled after {timing.get('night_settlement_after')}."
    if next_action == "run_night_after_results":
        missing_odds = predictions.get("missing_win_odds_rows", 0)
        if missing_odds:
            return f"Settlement window has arrived; run night even though {missing_odds} prediction rows still miss official win odds."
        return "Settlement artifacts are missing."
    if next_action == "manual_review_candidate":
        return "Profitability gates passed numerically; manual review is required before production adoption."
    if next_action == "paper_trade_only":
        blocker = profitability.get("dominant_failed_gate")
        if blocker:
            return f"Profitability gates are not stable enough; dominant blocker is {blocker}."
        return "Profitability gates have not approved live betting."
    return "No action reason available."


def build_daily_status(
    target_date: str | None = None,
    *,
    project_root: Path,
    write_file: bool = True,
    now: datetime | None = None,
) -> dict:
    date_text = normalize_date(target_date)
    paths = DailyPaths(project_root, date_text)
    timing = _timing_status(date_text, now or datetime.now())
    predictions = _prediction_status(paths.predictions_csv)
    settlement = _settlement_status(paths.settlement_csv)
    odds = _read_json(paths.odds_refresh_run_json)
    report = _read_json(paths.daily_report_json)
    profitability = _profitability_status(project_root)
    next_action = _next_action(predictions, odds, settlement, profitability, timing)
    payload = {
        "target_date": date_text,
        "daily_dir": str(paths.daily_dir),
        "morning_run": _read_json(paths.morning_run_json),
        "coverage": _read_json(paths.coverage_json),
        "predictions": predictions,
        "odds_refresh": odds if odds else {"exists": False},
        "settlement": settlement,
        "daily_report": report if report else {"exists": False},
        "profitability": profitability,
        "timing": timing,
        "next_action": next_action,
        "next_command": _next_command(next_action, date_text),
        "next_action_reason": _next_action_reason(next_action, predictions, profitability, timing),
    }
    if write_file:
        write_json(paths.daily_dir / "daily_status.json", payload)
    return payload
