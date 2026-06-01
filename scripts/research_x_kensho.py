from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kensho_assistant.app.research.hermes_x_search import (
    daily_safe_queries,
    research_x_campaigns,
    research_x_campaigns_for_queries,
    run_hermes_x_search_check,
    x_campaign_deduped_candidates_path,
    x_campaign_duplicates_path,
    x_campaign_candidates_path,
    x_campaign_csv_path,
    x_campaign_quality_report_json_path,
    x_campaign_quality_report_md_path,
    x_campaign_raw_results_path,
    x_campaign_run_path,
)


DEFAULT_QUERY = "懸賞 プレゼントキャンペーン 締切 今週 食品 日用品 子育て"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research_x_kensho.py", description="Hermes Agent 経由でX懸賞候補を収集する")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="X検索クエリ")
    parser.add_argument("--preset", choices=["daily_safe"], default="", help="検索クエリのプリセット")
    parser.add_argument("--limit", type=int, default=20, help="保存する候補数")
    parser.add_argument("--date", default="", help="保存先日付 YYYYMMDD / YYYY-MM-DD")
    parser.add_argument("--timeout-sec", type=int, default=60, help="Hermes 呼び出しのタイムアウト秒")
    parser.add_argument("--command", default="", help="KENSHO_HERMES_COMMAND の上書き")
    parser.add_argument("--check-hermes", action="store_true", help="Hermes 接続診断のみを実行する")
    parser.add_argument("--dry-run", action="store_true", help="Hermes を呼ばずに終了する")
    parser.add_argument("--mock", action="store_true", help="Hermes を呼ばずに終了する")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check_hermes:
        report = run_hermes_x_search_check(command=args.command or None, timeout_sec=args.timeout_sec)
        status = report.get("status", "failed")
        reason = report.get("reason", "unknown_error")
        output_file = report.get("output_file", "")
        next_action = (
            "Hermes 設定を確認してから再実行してください"
            if status != "success"
            else 'py scripts/research_x_kensho.py --query "懸賞 プレゼントキャンペーン 締切 今週 食品 日用品 子育て" --limit 20'
        )
        print("### Hermes X Search Check")
        print(f"status: {status}")
        print(f"reason: {reason}")
        print(f"output_file: {output_file}")
        print(f"next_action: {next_action}")
        return 0 if status == "success" else 1
    if args.dry_run or args.mock:
        if args.preset == "daily_safe":
            print("dry_run: Hermes は実行していません")
            for query in daily_safe_queries():
                print(f"- {query}")
        else:
            print("dry_run: Hermes は実行していません")
        print("next_action: --check-hermes で接続診断を実行してください")
        return 0
    if args.preset == "daily_safe":
        result = research_x_campaigns_for_queries(
            daily_safe_queries(),
            limit=args.limit,
            day=args.date or None,
            timeout_sec=args.timeout_sec,
            command=args.command or None,
            preset=args.preset,
        )
    else:
        result = research_x_campaigns(
            args.query,
            limit=args.limit,
            day=args.date or None,
            timeout_sec=args.timeout_sec,
            command=args.command or None,
        )
    run = result["run"]
    run_day = run["day"]
    print(f"candidates: {len(result['candidates'])}")
    print(f"status: {run['status']}")
    print(f"json: {x_campaign_candidates_path(run_day).resolve()}")
    print(f"deduped_json: {x_campaign_deduped_candidates_path(run_day).resolve()}")
    print(f"raw_json: {x_campaign_raw_results_path(run_day).resolve()}")
    print(f"duplicates_json: {x_campaign_duplicates_path(run_day).resolve()}")
    print(f"csv: {x_campaign_csv_path(run_day).resolve()}")
    print(f"run: {x_campaign_run_path(run_day).resolve()}")
    print(f"report_json: {x_campaign_quality_report_json_path(run_day).resolve()}")
    print(f"report_md: {x_campaign_quality_report_md_path(run_day).resolve()}")
    return 0 if run["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
