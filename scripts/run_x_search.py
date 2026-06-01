from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kensho_assistant.app.research.x_search_tool import (
    save_x_search_outputs,
    x_search_tool,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_x_search.py",
        description="xAI の x_search tool を使って X 投稿を検索し、要約と Markdown を保存する",
    )
    parser.add_argument("query", nargs="?", default="", help="検索クエリ")
    parser.add_argument("--query", dest="query_option", default="", help="検索クエリ")
    parser.add_argument("--date", default="", help="保存先日付 YYYYMMDD / YYYY-MM-DD")
    parser.add_argument("--model", default="grok-4.3", help="xAI model")
    parser.add_argument("--timeout-sec", type=int, default=120, help="xAI 呼び出しのタイムアウト秒")
    parser.add_argument("--allowed-handle", action="append", default=[], help="許可する X handle")
    parser.add_argument("--excluded-handle", action="append", default=[], help="除外する X handle")
    parser.add_argument("--from-date", default="", help="検索開始日 YYYY-MM-DD")
    parser.add_argument("--to-date", default="", help="検索終了日 YYYY-MM-DD")
    parser.add_argument("--note", action="store_true", help="note 記事向けに見出し付き Markdown で出力する")
    parser.add_argument("--image", action="store_true", help="画像付き投稿も解析する")
    parser.add_argument("--video", action="store_true", help="動画付き投稿も解析する")
    return parser


def _resolve_query(args: argparse.Namespace) -> str:
    query = (args.query_option or args.query or "").strip()
    return query


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    query = _resolve_query(args)
    if not query:
        print("query is required")
        return 2
    result = x_search_tool(
        query,
        note_mode=args.note,
        allowed_x_handles=args.allowed_handle,
        excluded_x_handles=args.excluded_handle,
        from_date=args.from_date or None,
        to_date=args.to_date or None,
        enable_image_understanding=args.image,
        enable_video_understanding=args.video,
        model=args.model,
        timeout_sec=args.timeout_sec,
    )
    result["note_mode"] = bool(args.note)
    paths = save_x_search_outputs(result, day=args.date or None)
    print(f"status: {result.get('status', 'failed')}")
    print(f"reason: {result.get('reason', '')}")
    print(f"answer_path: {paths['answer_path']}")
    print(f"response_path: {paths['response_path']}")
    print(f"run_path: {paths['run_path']}")
    if result.get("status") != "success":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

