from __future__ import annotations

import argparse

from kensho_assistant.app.research.hermes_x_search import (
    research_x_campaigns,
    run_hermes_x_search_check,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research sweepstakes candidates through Hermes")
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--command", default="")
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--check-hermes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_hermes:
        kwargs = {"timeout_sec": args.timeout_sec}
        if args.command:
            kwargs["command"] = args.command
        report = run_hermes_x_search_check(**kwargs)
        return 0 if report.get("status") == "success" else 1
    if args.dry_run or args.mock:
        print("status: dry_run")
        return 0
    if not args.query:
        return 2
    result = research_x_campaigns(args.query, limit=args.limit)
    print(f"status: {result.get('status', 'failed')}")
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
