from __future__ import annotations

import argparse
import json
from pathlib import Path

from kensho_assistant.app.research.hermes_x_search import run_hermes_x_search_check


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check the configured Hermes X search provider")
    parser.add_argument("--command", default="", help="optional explicit Hermes command")
    parser.add_argument("--timeout-sec", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kwargs = {"timeout_sec": args.timeout_sec}
    if args.command:
        kwargs["command"] = args.command
    report = run_hermes_x_search_check(**kwargs)
    output_file = Path(str(report.get("output_file", "")))
    if output_file.is_file():
        saved = json.loads(output_file.read_text(encoding="utf-8"))
        saved["stdout_masked"] = str(saved.get("stdout", ""))
        saved["stderr_masked"] = str(saved.get("stderr", ""))
        output_file.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    print("### Hermes X Search Check")
    print(f"status: {report.get('status', 'failed')}")
    print(f"reason: {report.get('reason', 'unknown')}")
    print(f"output_file: {report.get('output_file', '')}")
    print(f"next_action: {report.get('next_action', '')}")
    return 0 if report.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
