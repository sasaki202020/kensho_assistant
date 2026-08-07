from __future__ import annotations

import argparse

from kensho_assistant.app.research.x_search_tool import save_x_search_outputs, x_search_tool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an X search research query")
    parser.add_argument("--query", required=True)
    parser.add_argument("--note", action="store_true")
    parser.add_argument("--date", default="")
    parser.add_argument("--timeout-sec", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = x_search_tool(args.query, note_mode=args.note, timeout_sec=args.timeout_sec)
    if result.get("status") != "success":
        print(f"status: {result.get('status', 'failed')}")
        print(f"reason: {result.get('reason', 'unknown')}")
        return 1
    paths = save_x_search_outputs(result, day=args.date or None)
    print("status: success")
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
