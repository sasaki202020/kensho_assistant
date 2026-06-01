from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kensho_assistant.app.harness.x_research_harness import run_x_research_harness


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="X Research Harness")
    parser.add_argument("--query", required=True, help="調査クエリ")
    parser.add_argument("--mode", choices=["quick", "verify", "note", "ttp"], default="quick")
    parser.add_argument("--provider", choices=["mock", "hermes"], default=None, help="利用する provider")
    parser.add_argument("--mock", action="store_true", help="mockデータだけで実行する")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        provider = "mock" if args.mock else (args.provider or "mock")
        result = run_x_research_harness(query=args.query, mode=args.mode, mock=args.mock, provider=provider)
    except Exception as error:
        print(f"failed: {error}")
        return 1
    provider_label = provider
    run_report_path = Path(result.output_dir) / "run_report.json"
    if run_report_path.exists():
        try:
            report = json.loads(run_report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
        if isinstance(report, dict) and report.get("provider"):
            provider_label = str(report.get("provider"))
    print(f"status: {result.status}")
    print(f"provider: {provider_label}")
    print(f"output_dir: {result.output_dir}")
    return 0 if result.status == "success" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
