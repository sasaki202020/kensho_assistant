from __future__ import annotations

import argparse
from dataclasses import replace

from kensho_assistant.app.integrations.x_post import create_post, load_x_post_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare an explicitly confirmed X post")
    parser.add_argument("--text", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-live", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_x_post_config()
    if args.dry_run:
        config = replace(config, dry_run=True)
    result = create_post(args.text, confirm_live=args.confirm_live, config=config)
    print(f"status: {result.get('status', 'failed')}")
    print(f"reason: {result.get('reason', 'unknown')}")
    if "preview" in result:
        print(f"payload_preview: {result['preview']}")
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
