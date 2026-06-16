from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.daily_ops import run_night


def main() -> int:
    parser = argparse.ArgumentParser(description="Settle saved daily boat race predictions")
    parser.add_argument("--date", default=None, help="Target date in YYYY-MM-DD")
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()
    report = run_night(args.date, config_path=args.config, project_root=PROJECT_ROOT)
    print(f"status={report['status']} settled={report['races_settled']}/{report['races_predicted']}")
    print(f"daily_report_json={PROJECT_ROOT / 'output' / 'daily' / report['target_date'] / 'daily_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
