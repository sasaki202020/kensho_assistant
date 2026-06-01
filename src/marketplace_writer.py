from __future__ import annotations

import argparse
import html
import json
import os
import webbrowser
from pathlib import Path

from .autopilot_shared import LeadRecord, write_json, write_text


def build_marketplace_html(lead: LeadRecord, proposal_text: str, estimate_markdown: str, report_path: str) -> str:
    safe_proposal = html.escape(proposal_text)
    safe_estimate = html.escape(estimate_markdown)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Marketplace Helper - {lead.company_name}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #f6f7fb; color: #102030; }}
    .card {{ background: #fff; border: 1px solid #d8e0ea; border-radius: 16px; padding: 18px; margin-bottom: 16px; box-shadow: 0 10px 24px rgba(16,32,48,.06); }}
    textarea {{ width: 100%; min-height: 180px; font: 14px/1.6 ui-monospace, Consolas, monospace; }}
    .hint {{ color: #55697f; font-size: 13px; }}
    .safe {{ background: #eef6ff; border-left: 4px solid #5ea7ff; padding: 12px; border-radius: 8px; }}
    button {{ display: inline-block; margin: 4px 8px 4px 0; padding: 10px 14px; border: 0; border-radius: 10px; background: #15324d; color: white; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{lead.company_name}</h1>
    <div class="hint">{lead.industry} / {lead.area}</div>
    <div class="safe">ここから先は人間が確認して手動で実行してください。</div>
    <p class="hint">送信・応募・公開・CAPTCHA回避はしません。下書きのコピーだけを助けます。</p>
    <p><a href="{report_path}" target="_blank">レポートを開く</a></p>
  </div>
  <div class="card">
    <h2>プロフィール文</h2>
    <textarea readonly>{safe_proposal}</textarea>
  </div>
  <div class="card">
    <h2>出品サービス文 / 提案補助</h2>
    <textarea readonly>{safe_estimate}</textarea>
  </div>
  <div class="card">
    <h2>添付準備メモ</h2>
    <ul>
      <li>customer_report.pdf</li>
      <li>internal_report.html</li>
      <li>screenshots/desktop.png</li>
      <li>screenshots/mobile.png</li>
      <li>screenshots/contact_area.png</li>
    </ul>
  </div>
</body>
</html>
"""


def write_marketplace_helper(
    company_dir: Path,
    lead: LeadRecord,
    proposal_text: str,
    estimate_markdown: str,
    report_path: Path,
) -> Path:
    helper_path = company_dir / "marketplace_helper.html"
    write_text(helper_path, build_marketplace_html(lead, proposal_text, estimate_markdown, report_path.as_posix()))
    payload = {
        "company_name": lead.company_name,
        "industry": lead.industry,
        "area": lead.area,
        "report_path": str(report_path),
        "helper_path": str(helper_path),
        "safe_notice": "ここから先は人間が確認して手動で実行してください。",
    }
    write_json(company_dir / "marketplace_helper.json", payload)
    return helper_path


def build_chrome_command(helper_path: Path) -> str:
    return f'start "" "{helper_path}"'


def open_helper(helper_path: Path) -> None:
    try:
        os.startfile(helper_path)  # type: ignore[attr-defined]
    except Exception:
        webbrowser.open(helper_path.as_uri())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.marketplace_writer", description="Chrome input helper")
    parser.add_argument("--open", dest="open_path", help="open helper HTML")
    parser.add_argument("--open-latest", action="store_true", help="open the latest generated helper HTML")
    parser.add_argument("--report-root", default="reports", help="report root to search")
    return parser


def _latest_helper(report_root: Path) -> Path | None:
    candidates = sorted(report_root.glob("*/companies/*/marketplace_helper.html"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.open_latest:
        helper = _latest_helper(Path(args.report_root))
        if helper:
            open_helper(helper)
            print(helper)
            return 0
        print("No helper HTML found.")
        return 1
    if args.open_path:
        open_helper(Path(args.open_path))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
