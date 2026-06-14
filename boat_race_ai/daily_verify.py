from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.daily_verify import verify_daily_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify saved daily boat race artifacts without fetching external data")
    parser.add_argument("--date", default=None, help="Target date in YYYY-MM-DD")
    parser.add_argument("--stage", choices=["morning", "odds", "night", "analysis", "full"], default="morning")
    parser.add_argument("--no-write", action="store_true", help="Do not write verify_<stage>.json")
    args = parser.parse_args()
    result = verify_daily_artifacts(args.date, project_root=PROJECT_ROOT, stage=args.stage, write_file=not args.no_write)
    print(
        "date={date} stage={stage} status={status} missing={missing}/{checked} issues={issues}".format(
            date=result["target_date"],
            stage=result["stage"],
            status=result["status"],
            missing=result["missing_count"],
            checked=result["checked_count"],
            issues=result["issue_count"],
        )
    )
    rows = result["row_counts"]
    print(f"rows predictions={rows.get('predictions_rows')} settlement={rows.get('settlement_rows')}")
    if result.get("verify_json"):
        print(f"verify_json={result['verify_json']}")
    for item in result["missing_artifacts"]:
        print(f"missing {item['path']}")
    for item in result["validation_issues"]:
        print(f"issue {item['code']}: {item['message']}")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
