from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.daily_ops import refresh_daily_odds, run_morning, run_night
from src.daily_status import build_daily_status
from src.daily_verify import verify_daily_artifacts
from src.profitability_analysis import AnalysisPaths, run_analysis


def should_skip_phase(phase: str, status: dict, *, ignore_schedule: bool = False) -> tuple[bool, str]:
    next_action = status.get("next_action")
    reason = status.get("next_action_reason") or "No status reason available."
    if phase == "odds":
        if status.get("settlement", {}).get("exists"):
            return True, "Settlement already exists; do not update predictions after settlement."
        if next_action == "run_morning":
            return True, "Morning predictions are missing; run morning first."
        if next_action == "run_night_after_results":
            return True, "Settlement window has arrived; run night before refreshing odds."
        if next_action == "wait_for_odds_refresh" and not ignore_schedule:
            return True, reason
    if phase == "night":
        if next_action == "run_morning":
            return True, "Morning predictions are missing; run morning first."
        if next_action in {"wait_for_odds_refresh", "wait_for_night_settlement"} and not ignore_schedule:
            return True, reason
        if next_action == "run_odds_refresh":
            return True, "Official odds refresh is still pending; run odds first."
    return False, ""


def print_verify(stage: str, target_date: str | None) -> dict:
    result = verify_daily_artifacts(target_date, project_root=PROJECT_ROOT, stage=stage, write_file=True)
    print(
        "verify stage={stage} status={status} missing={missing}/{checked}".format(
            stage=stage,
            status=result["status"],
            missing=result["missing_count"],
            checked=result["checked_count"],
        )
    )
    if result.get("verify_json"):
        print(f"verify_json={result['verify_json']}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run daily boat race operations")
    parser.add_argument("--date", default=None, help="Target date in YYYY-MM-DD")
    parser.add_argument("--phase", choices=["morning", "odds", "night", "full"], default="morning")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate morning predictions")
    parser.add_argument("--force-refresh", action="store_true", help="Refetch official odds HTML during odds refresh")
    parser.add_argument("--max-courses", type=int, default=None, help="Limit active courses for smoke tests")
    parser.add_argument("--bankroll-yen", type=int, default=None, help="Bankroll used by shadow profitability guard")
    parser.add_argument("--min-sample", type=int, default=100, help="Minimum settled bets required by profitability gates")
    parser.add_argument("--min-days", type=int, default=3, help="Minimum distinct days required by profitability gates")
    parser.add_argument("--min-roi-pct", type=float, default=105.0, help="Minimum ROI percent required by profitability gates")
    parser.add_argument("--min-positive-day-rate", type=float, default=0.5, help="Minimum share of profitable days required by shadow profitability gates")
    parser.add_argument("--min-daily-roi-floor-pct", type=float, default=80.0, help="Minimum worst-day ROI percent required by shadow profitability gates")
    parser.add_argument("--ignore-schedule", action="store_true", help="Run odds/night even when daily_status says the scheduled window has not arrived")
    parser.add_argument("--no-verify", action="store_true", help="Do not write verify_<stage>.json after completed phases")
    parser.add_argument("--no-status", action="store_true", help="Do not refresh daily_status.json after the run")
    args = parser.parse_args()
    if args.phase in {"morning", "full"}:
        morning = run_morning(
            args.date,
            config_path=args.config,
            project_root=PROJECT_ROOT,
            overwrite=args.overwrite,
            max_courses=args.max_courses,
        )
        print(f"morning status={morning['status']} races={morning['races']} rows={morning['rows']}")
        if not args.no_verify:
            print_verify("morning", args.date)
    if args.phase in {"odds", "full"}:
        status = build_daily_status(args.date, project_root=PROJECT_ROOT)
        skip, skip_reason = should_skip_phase("odds", status, ignore_schedule=args.ignore_schedule)
        if skip:
            print(f"odds skipped reason={skip_reason}")
        else:
            odds = refresh_daily_odds(
                args.date,
                config_path=args.config,
                project_root=PROJECT_ROOT,
                force_refresh=args.force_refresh,
            )
            print(
                "odds status={status} available={available}/{rows}".format(
                    status=odds["status"],
                    available=odds["odds_available_rows"],
                    rows=odds["rows"],
                )
            )
            if not args.no_verify:
                print_verify("odds", args.date)
    if args.phase in {"night", "full"}:
        status = build_daily_status(args.date, project_root=PROJECT_ROOT)
        skip, skip_reason = should_skip_phase("night", status, ignore_schedule=args.ignore_schedule)
        if skip:
            print(f"night skipped reason={skip_reason}")
        else:
            night = run_night(args.date, config_path=args.config, project_root=PROJECT_ROOT)
            print(f"night status={night['status']} settled={night['races_settled']}/{night['races_predicted']}")
            analysis = run_analysis(
                AnalysisPaths(
                    current_daily_root=PROJECT_ROOT / "output" / "daily",
                    legacy_daily_root=None,
                    output_dir=PROJECT_ROOT / "output" / "analysis" / "profitability",
                ),
                min_sample=args.min_sample,
                min_days=args.min_days,
                min_roi_pct=args.min_roi_pct,
                min_positive_day_rate=args.min_positive_day_rate,
                min_daily_roi_floor_pct=args.min_daily_roi_floor_pct,
                bankroll_yen=args.bankroll_yen,
                target_date=args.date,
            )
            recommendation = analysis["recommendation"]
            print(
                "profitability decision={decision} live_betting_allowed={allowed}".format(
                    decision=recommendation["decision"],
                    allowed=recommendation["live_betting_allowed"],
                )
            )
            if not args.no_verify:
                print_verify("night", args.date)
                print_verify("analysis", args.date)
    if not args.no_status:
        status = build_daily_status(args.date, project_root=PROJECT_ROOT)
        print(f"daily_status next_action={status['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
