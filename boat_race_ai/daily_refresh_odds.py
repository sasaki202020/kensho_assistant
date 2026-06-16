from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.daily_ops import refresh_daily_odds


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh official win odds for saved daily predictions")
    parser.add_argument("--date", default=None, help="Target date in YYYY-MM-DD")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--force-refresh", action="store_true", help="Refetch official odds HTML instead of using cache")
    args = parser.parse_args()
    result = refresh_daily_odds(
        args.date,
        config_path=args.config,
        project_root=PROJECT_ROOT,
        force_refresh=args.force_refresh,
    )
    print(f"status={result['status']} available={result['odds_available_rows']}/{result['rows']}")
    print(f"odds_refresh_csv={result['odds_refresh_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
