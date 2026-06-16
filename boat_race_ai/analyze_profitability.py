from __future__ import annotations

import argparse
from pathlib import Path

from src.profitability_analysis import AnalysisPaths, run_analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build shadow profitability analysis from daily artifacts.")
    parser.add_argument("--date", default=None, help="Analysis date for idempotent history rows")
    parser.add_argument("--current-daily-root", default="output/daily")
    parser.add_argument(
        "--legacy-daily-root",
        default=r"C:\Users\goo10\競艇\boatrace-ai-mvp\reports\daily",
        help="Legacy boatrace-ai-mvp reports/daily path. Use empty string to disable.",
    )
    parser.add_argument("--output-dir", default="output/analysis/profitability")
    parser.add_argument("--min-sample", type=int, default=100)
    parser.add_argument("--min-days", type=int, default=3)
    parser.add_argument("--min-roi-pct", type=float, default=105.0)
    parser.add_argument("--min-positive-day-rate", type=float, default=0.5)
    parser.add_argument("--min-daily-roi-floor-pct", type=float, default=80.0)
    parser.add_argument("--bankroll-yen", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    current_daily_root = Path(args.current_daily_root)
    if not current_daily_root.is_absolute():
        current_daily_root = project_root / current_daily_root
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    legacy_daily_root = Path(args.legacy_daily_root) if args.legacy_daily_root else None
    payload = run_analysis(
        AnalysisPaths(
            current_daily_root=current_daily_root,
            legacy_daily_root=legacy_daily_root,
            output_dir=output_dir,
        ),
        min_sample=args.min_sample,
        min_days=args.min_days,
        min_roi_pct=args.min_roi_pct,
        min_positive_day_rate=args.min_positive_day_rate,
        min_daily_roi_floor_pct=args.min_daily_roi_floor_pct,
        bankroll_yen=args.bankroll_yen,
        target_date=args.date,
    )
    print(
        "analysis status={status} current_days={days} settled_rows={rows} legacy_dates={legacy_dates}".format(
            status=payload["analysis_status"],
            days=payload["current"]["days"],
            rows=payload["current"]["settled_rows"],
            legacy_dates=payload["legacy"]["unique_dates"],
        )
    )
    recommendation = payload["recommendation"]
    print(
        "profitability decision={decision} live_betting_allowed={allowed} unit_stake_yen={unit}".format(
            decision=recommendation["decision"],
            allowed=recommendation["live_betting_allowed"],
            unit=payload["bankroll_guard"]["unit_stake_yen"],
        )
    )
    print(f"output={output_dir}")


if __name__ == "__main__":
    main()
