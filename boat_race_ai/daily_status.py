from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.daily_status import build_daily_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize daily boat race operation status")
    parser.add_argument("--date", default=None, help="Target date in YYYY-MM-DD")
    parser.add_argument("--no-write", action="store_true", help="Do not write daily_status.json")
    args = parser.parse_args()
    status = build_daily_status(args.date, project_root=PROJECT_ROOT, write_file=not args.no_write)
    predictions = status["predictions"]
    settlement = status["settlement"]
    profitability = status["profitability"]
    timing = status["timing"]
    print(
        "date={date} next_action={next_action} predictions={races} races/{rows} rows missing_odds={missing_odds}".format(
            date=status["target_date"],
            next_action=status["next_action"],
            races=predictions.get("races", 0),
            rows=predictions.get("rows", 0),
            missing_odds=predictions.get("missing_win_odds_rows", 0),
        )
    )
    print(
        "settlement exists={exists} settled_races={settled} profitability={decision} live_allowed={allowed} candidates={candidates}".format(
            exists=settlement.get("exists", False),
            settled=settlement.get("settled_races", 0),
            decision=profitability.get("decision"),
            allowed=profitability.get("live_betting_allowed"),
            candidates=profitability.get("candidate_conditions_count", 0),
        )
    )
    print(
        "profitability_history days={days} min_days_remaining={remaining} blocker={blocker} rejected={rejected}/{total}".format(
            days=profitability.get("history_days", 0),
            remaining=profitability.get("min_days_remaining"),
            blocker=profitability.get("dominant_failed_gate"),
            rejected=profitability.get("rejected_count"),
            total=profitability.get("total_slices"),
        )
    )
    print(
        "timing now={now} odds_after={odds_after} night_after={night_after}".format(
            now=timing.get("current_time"),
            odds_after=timing.get("odds_refresh_after"),
            night_after=timing.get("night_settlement_after"),
        )
    )
    print(f"reason={status.get('next_action_reason')}")
    if status.get("next_command"):
        print(f"next_command={status['next_command']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
