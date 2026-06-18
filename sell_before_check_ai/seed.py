from __future__ import annotations

import argparse

from field_assessment_ai.seed import seed_sample_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed sample data for 売る前チェックAI v0.1")
    parser.add_argument("--reset", action="store_true", help="delete existing SQLite DB and uploads before seeding")
    args = parser.parse_args(argv)
    stats = seed_sample_data(reset=args.reset)
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

