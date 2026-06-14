from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.daily_ops import run_morning


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all-course morning boat race predictions")
    parser.add_argument("--date", default=None, help="Target date in YYYY-MM-DD")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate predictions even if they already exist")
    parser.add_argument("--max-courses", type=int, default=None, help="Limit active courses for smoke tests")
    args = parser.parse_args()
    result = run_morning(
        args.date,
        config_path=args.config,
        project_root=PROJECT_ROOT,
        overwrite=args.overwrite,
        max_courses=args.max_courses,
    )
    print(f"status={result['status']} races={result['races']} rows={result['rows']}")
    print(f"predictions_csv={result['predictions_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
