from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .autopilot_shared import (
    LeadRecord,
    compact_text,
    digest_text,
    ensure_dir,
    safe_company_dir_name,
    today_key,
    write_csv_rows,
    write_json,
    write_text,
)
from .crm import build_crm_row, write_crm_csv
from .estimate_generator import build_estimate_markdown
from .lead_finder import find_leads, save_generated_leads
from .marketplace_writer import build_chrome_command, write_marketplace_helper
from .pdf_generator import write_customer_pdf
from .proposal_generator import build_proposal_text
from .screenshotter import capture_screenshots

LEADS_SCORED_COLUMNS = [
    "company_name",
    "industry",
    "area",
    "website_url",
    "contact_url",
    "source_url",
    "source_type",
    "confidence",
    "status",
    "score",
    "rank",
    "primary_weakness",
    "good_points",
    "top_fixes",
    "proposal_preview",
    "estimate_plan",
    "proposal_path",
    "estimate_path",
    "fix_plan_path",
    "report_path",
    "marketplace_command",
]


def _extract_contact_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        text = anchor.get_text(" ", strip=True)
        if not href:
            continue
        if "contact" not in href.casefold() and not re.search(r"お問い合わせ|問合せ|予約|相談|Contact", text, re.I):
            continue
        resolved = urljoin(base_url, href)
        if resolved not in links:
            links.append(resolved)
    return links


def _page_html(website_url: str) -> tuple[str, str]:
    response = requests.get(website_url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.text, response.url


def _site_diagnostics(lead: LeadRecord, *, sample_mode: bool = False) -> dict[str, Any]:
    html_text = ""
    fetched_url = lead.website_url
    if lead.website_url and not sample_mode:
        try:
            html_text, fetched_url = _page_html(lead.website_url)
        except Exception as exc:
            html_text = ""
            fetched_url = lead.website_url
            fetch_status = f"fetch_failed: {exc}"
        else:
            fetch_status = "ok"
    else:
        fetch_status = "sample_or_missing_url"

    soup = BeautifulSoup(html_text, "html.parser") if html_text else None
    title = compact_text(soup.title.get_text(" ", strip=True), 80) if soup and soup.title else ""
    description = ""
    if soup:
        description_tag = soup.select_one("meta[name='description']")
        if description_tag:
            description = compact_text(description_tag.get("content", ""), 120)
    h1s = [compact_text(node.get_text(" ", strip=True), 80) for node in soup.select("h1")[:3]] if soup else []
    h2s = [compact_text(node.get_text(" ", strip=True), 80) for node in soup.select("h2")[:4]] if soup else []
    forms = len(soup.select("form")) if soup else 0
    phone_links = [node.get("href", "") for node in soup.select("a[href^='tel:']")] if soup else []
    mail_links = [node.get("href", "") for node in soup.select("a[href^='mailto:']")] if soup else []
    viewport = bool(soup.select_one("meta[name='viewport']")) if soup else False
    structured_data = len(soup.select("script[type='application/ld+json']")) if soup else 0
    contact_links = _extract_contact_links(soup, fetched_url) if soup else []
    text_length = len(soup.get_text(" ", strip=True)) if soup else 0
    secure = fetched_url.casefold().startswith("https://")

    good_points: list[str] = []
    weak_points: list[str] = []

    if title:
        good_points.append(f"タイトルがある: {title}")
    else:
        weak_points.append("ページタイトルが見つかりにくい")
    if description:
        good_points.append("meta description がある")
    else:
        weak_points.append("説明文が薄く、検索結果で伝わりにくい")
    if viewport:
        good_points.append("viewport が設定されている")
    else:
        weak_points.append("スマホ表示の初期設定を確認したい")
    if contact_links or phone_links or mail_links:
        good_points.append("問い合わせ導線が見つかる")
    else:
        weak_points.append("問い合わせ導線が見つかりにくい")
    if forms:
        good_points.append(f"フォームが {forms} 個ある")
    else:
        weak_points.append("フォームが見つかりにくい")
    if secure:
        good_points.append("HTTPS で配信されている")
    else:
        weak_points.append("HTTPS 化の確認余地がある")
    if structured_data:
        good_points.append("構造化データがある")
    if text_length < 1200:
        weak_points.append("テキスト情報が少なく、サービス内容の説明余地がある")

    if not h1s:
        weak_points.append("H1 が見つかりにくい")

    lighthouse = _run_lighthouse_stub(lead, {
        "title": title,
        "description": description,
        "viewport": viewport,
        "contact_links": contact_links,
        "forms": forms,
        "secure": secure,
        "text_length": text_length,
        "structured_data": structured_data,
    }, sample_mode=sample_mode)

    score = _score_site(good_points, weak_points, lighthouse)
    rank = _rank_from_score(score)
    primary_weakness = weak_points[0] if weak_points else "改善余地があります"
    top_fixes = _pick_top_fixes(weak_points)
    quick_fixes = _pick_quick_fixes(weak_points)
    month_plan = _pick_month_plan(weak_points)
    contact_summary = ", ".join(contact_links[:2]) if contact_links else "問い合わせ導線の確認余地あり"

    return {
        "fetch_status": fetch_status,
        "website_url": fetched_url,
        "title": title,
        "description": description,
        "h1s": h1s,
        "h2s": h2s,
        "forms": forms,
        "phone_links": phone_links,
        "mail_links": mail_links,
        "viewport": viewport,
        "structured_data": structured_data,
        "secure": secure,
        "text_length": text_length,
        "contact_links": contact_links,
        "contact_summary": contact_summary,
        "good_points": good_points,
        "weak_points": weak_points,
        "primary_weakness": primary_weakness,
        "top_fixes": top_fixes,
        "quick_fixes": quick_fixes,
        "month_plan": month_plan,
        "lighthouse": lighthouse,
        "score": score,
        "rank": rank,
        "summary": _diagnostic_summary(score, rank, primary_weakness),
    }


def _run_lighthouse_stub(lead: LeadRecord, metrics: dict[str, Any], *, sample_mode: bool) -> dict[str, Any]:
    if sample_mode or not lead.website_url:
        return {
            "status": "unavailable",
            "note": "sample_or_missing_url",
            "performance": 0,
            "accessibility": 0,
            "best_practices": 0,
            "seo": 0,
            "score": 0,
        }
    if shutil.which("lighthouse"):
        try:
            out_dir = Path("reports") / "_tmp_lighthouse"
            out_dir.mkdir(parents=True, exist_ok=True)
            result_json = out_dir / f"{digest_text(lead.company_name, lead.website_url)}.json"
            cmd = [
                "lighthouse",
                lead.website_url,
                "--quiet",
                "--output=json",
                f"--output-path={result_json}",
                "--chrome-flags=--headless=new --disable-gpu",
            ]
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result_json.exists():
                payload = json.loads(result_json.read_text(encoding="utf-8"))
                categories = payload.get("categories", {})
                return {
                    "status": "ok",
                    "performance": round(categories.get("performance", {}).get("score", 0) * 100),
                    "accessibility": round(categories.get("accessibility", {}).get("score", 0) * 100),
                    "best_practices": round(categories.get("best-practices", {}).get("score", 0) * 100),
                    "seo": round(categories.get("seo", {}).get("score", 0) * 100),
                    "score": round(payload.get("categories", {}).get("performance", {}).get("score", 0) * 100),
                    "stderr": compact_text(completed.stderr, 120),
                }
        except Exception as exc:
            return {
                "status": f"failed: {exc}",
                "performance": 0,
                "accessibility": 0,
                "best_practices": 0,
                "seo": 0,
                "score": 0,
            }
    score = 20
    if metrics.get("title"):
        score += 12
    if metrics.get("description"):
        score += 12
    if metrics.get("viewport"):
        score += 12
    if metrics.get("contact_links"):
        score += 15
    if metrics.get("forms"):
        score += 12
    if metrics.get("secure"):
        score += 10
    if metrics.get("text_length", 0) > 1500:
        score += 8
    if metrics.get("structured_data", 0):
        score += 5
    score = min(score, 92)
    return {
        "status": "simulated",
        "performance": min(score - 4, 100),
        "accessibility": min(score + 2, 100),
        "best_practices": min(score, 100),
        "seo": min(score + 1, 100),
        "score": score,
    }


def _score_site(good_points: list[str], weak_points: list[str], lighthouse: dict[str, Any]) -> int:
    score = 35
    score += min(len(good_points) * 6, 24)
    score -= min(len(weak_points) * 4, 28)
    score += int(lighthouse.get("performance", 0)) // 10
    score += int(lighthouse.get("accessibility", 0)) // 10
    score += int(lighthouse.get("seo", 0)) // 10
    return max(0, min(score, 100))


def _rank_from_score(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def _pick_top_fixes(weak_points: list[str]) -> list[str]:
    fixes: list[str] = []
    mapping = {
        "問い合わせ導線が見つかりにくい": "問い合わせボタンを1画面目で見つけやすくする",
        "説明文が薄く、検索結果で伝わりにくい": "サービス説明と強みを1段落で明確化する",
        "スマホ表示の初期設定を確認したい": "viewport と余白を見直してスマホ幅を整える",
        "フォームが見つかりにくい": "予約・問い合わせフォームを上部に再配置する",
        "ページタイトルが見つかりにくい": "タイトルに地域名と業種名を入れる",
        "HTTPS 化の確認余地がある": "常時 HTTPS と混在コンテンツを確認する",
        "H1 が見つかりにくい": "H1 を1つに絞って訴求を整理する",
        "テキスト情報が少なく、サービス内容の説明余地がある": "料金・流れ・選ばれる理由を追加する",
    }
    for item in weak_points:
        if item in mapping and mapping[item] not in fixes:
            fixes.append(mapping[item])
    if not fixes:
        fixes.append("ファーストビューの見せ方を整える")
    return fixes[:5]


def _pick_quick_fixes(weak_points: list[str]) -> list[str]:
    quick = []
    if any("問い合わせ" in item for item in weak_points):
        quick.append("問い合わせボタンを上部に置く")
    if any("タイトル" in item for item in weak_points):
        quick.append("title を地域名入りにする")
    if any("説明文" in item for item in weak_points):
        quick.append("meta description を追記する")
    if any("スマホ" in item for item in weak_points):
        quick.append("スマホ幅の余白を詰める")
    if not quick:
        quick.append("見出しを1つ増やす")
    return quick[:4]


def _pick_month_plan(weak_points: list[str]) -> list[str]:
    plan = ["30日以内に問い合わせ導線の見直しを進める"]
    if any("説明文" in item for item in weak_points):
        plan.append("サービス紹介ページを1枚追加する")
    if any("テキスト情報" in item for item in weak_points):
        plan.append("料金・実績・FAQ を整理する")
    if any("HTTPS" in item for item in weak_points):
        plan.append("セキュリティと常時SSLの確認を行う")
    return plan[:4]


def _diagnostic_summary(score: int, rank: str, primary_weakness: str) -> str:
    return f"総合 {score} 点 / {rank} ランク。{primary_weakness}。"


def _render_list(items: list[str], *, ordered: bool = False) -> str:
    tag = "ol" if ordered else "ul"
    body = "".join(f"<li>{item}</li>" for item in items)
    return f"<{tag}>{body}</{tag}>"


def _render_screenshot_group(company_dir: Path, items: list[str]) -> str:
    body = []
    for name in items:
        path = f"screenshots/{name}"
        body.append(f'<figure><img src="{path}" alt="{name}"><figcaption>{name}</figcaption></figure>')
    return f'<div class="shots">{"".join(body)}</div>'


def _customer_html(lead: LeadRecord, diagnostics: dict[str, Any], company_dir: Path, estimate_md: str) -> str:
    score = diagnostics["score"]
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{lead.company_name} 顧客向け診断レポート</title>
  <style>
    body {{ font-family: "Yu Gothic UI", "Hiragino Kaku Gothic ProN", sans-serif; margin: 0; padding: 0; background: #f5f7fb; color: #0f1d2e; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px; }}
    .cover {{ background: linear-gradient(135deg, #0f2740, #284b73); color: white; border-radius: 24px; padding: 32px; box-shadow: 0 20px 50px rgba(0,0,0,.12); }}
    .card {{ background: white; border: 1px solid #dfe6ef; border-radius: 20px; padding: 24px; margin-top: 18px; box-shadow: 0 10px 24px rgba(16,32,48,.05); }}
    h1, h2, h3 {{ margin-top: 0; }}
    .grid {{ display: grid; grid-template-columns: 1.2fr .8fr; gap: 16px; }}
    .metric {{ font-size: 52px; font-weight: 700; margin: 0; }}
    .badge {{ display: inline-block; padding: 6px 12px; border-radius: 999px; background: rgba(255,255,255,.18); margin-right: 8px; }}
    .shots {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }}
    figure {{ margin: 0; }}
    img {{ width: 100%; border-radius: 14px; border: 1px solid #dfe6ef; }}
    figcaption {{ font-size: 12px; color: #5f6f80; margin-top: 4px; }}
    .note {{ background: #f0f5fb; padding: 14px 16px; border-radius: 12px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="cover">
      <div class="badge">{lead.industry}</div><div class="badge">{lead.area}</div>
      <h1>{lead.company_name}</h1>
      <p>顧客向けの簡易診断レポートです。断定しすぎず、改善の余地がある部分を整理しています。</p>
      <p class="metric">{score}</p>
      <p>{diagnostics["summary"]}</p>
    </div>

    <div class="card">
      <h2>診断概要</h2>
      <p>{diagnostics["summary"]}</p>
      <p>問い合わせ導線: {diagnostics["contact_summary"]}</p>
      <p>ランク: {diagnostics["rank"]}</p>
    </div>

    <div class="card">
      <h2>スクリーンショット</h2>
      {_render_screenshot_group(company_dir, ["desktop.png", "mobile.png", "contact_area.png", "competitor_1.png"])}
    </div>

    <div class="card">
      <h2>良い点</h2>
      {_render_list(diagnostics["good_points"][:5])}
    </div>

    <div class="card">
      <h2>もったいない点</h2>
      {_render_list(diagnostics["weak_points"][:5])}
    </div>

    <div class="card">
      <h2>優先改善 TOP5</h2>
      {_render_list(diagnostics["top_fixes"], ordered=True)}
    </div>

    <div class="card">
      <h2>すぐ直せる改善</h2>
      {_render_list(diagnostics["quick_fixes"])}
    </div>

    <div class="card">
      <h2>30日以内にやる改善</h2>
      {_render_list(diagnostics["month_plan"])}
    </div>

    <div class="card">
      <h2>見積もりプラン</h2>
      <pre>{estimate_md}</pre>
    </div>

    <div class="card note">
      <h2>注意書き</h2>
      <p>本レポートは改善候補の整理であり、成果を断定するものではありません。送信・応募・公開は人間が最終確認して手動で実行してください。</p>
    </div>
  </div>
</body>
</html>
"""


def _internal_html(lead: LeadRecord, diagnostics: dict[str, Any], proposal_text: str, estimate_md: str, fix_plan_md: str, raw_json: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{lead.company_name} internal report</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #eef2f7; color: #122031; }}
    pre {{ white-space: pre-wrap; background: white; border: 1px solid #d6dfe8; padding: 14px; border-radius: 12px; overflow: auto; }}
    .card {{ background: white; border: 1px solid #d6dfe8; border-radius: 14px; padding: 18px; margin-bottom: 14px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td {{ border-bottom: 1px solid #e7edf3; padding: 8px 6px; vertical-align: top; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{lead.company_name}</h1>
    <table>
      <tr><td>score</td><td>{diagnostics["score"]}</td></tr>
      <tr><td>rank</td><td>{diagnostics["rank"]}</td></tr>
      <tr><td>website</td><td>{diagnostics["website_url"]}</td></tr>
      <tr><td>contact</td><td>{diagnostics["contact_summary"]}</td></tr>
      <tr><td>lighthouse</td><td>{json.dumps(diagnostics["lighthouse"], ensure_ascii=False)}</td></tr>
    </table>
  </div>
  <div class="card">
    <h2>良い点</h2>
    <pre>{json.dumps(diagnostics["good_points"], ensure_ascii=False, indent=2)}</pre>
  </div>
  <div class="card">
    <h2>弱点</h2>
    <pre>{json.dumps(diagnostics["weak_points"], ensure_ascii=False, indent=2)}</pre>
  </div>
  <div class="card">
    <h2>proposal.txt</h2>
    <pre>{proposal_text}</pre>
  </div>
  <div class="card">
    <h2>estimate.md</h2>
    <pre>{estimate_md}</pre>
  </div>
  <div class="card">
    <h2>fix_plan.md</h2>
    <pre>{fix_plan_md}</pre>
  </div>
  <div class="card">
    <h2>raw.json</h2>
    <pre>{raw_json}</pre>
  </div>
</body>
</html>
"""


def _build_fix_plan_md(diagnostics: dict[str, Any]) -> str:
    top = diagnostics["top_fixes"]
    quick = diagnostics["quick_fixes"]
    month = diagnostics["month_plan"]
    lines = ["# fix_plan", "", "## 優先改善", *[f"- {item}" for item in top], "", "## すぐ直す", *[f"- {item}" for item in quick], "", "## 30日以内", *[f"- {item}" for item in month], "", "## 注意", "- ここから先は人間が確認して手動で実行してください。"]
    return "\n".join(lines) + "\n"


def _build_dashboard_html(run: dict[str, Any], results: list[dict[str, Any]]) -> str:
    rows = []
    for item in results:
        rows.append(
            f"<tr><td>{item['company_name']}</td><td>{item['score']}</td><td>{item['rank']}</td>"
            f"<td>{compact_text(item['primary_weakness'], 70)}</td>"
            f"<td>{compact_text(item['proposal_preview'], 100)}</td>"
            f"<td><a href=\"{item['report_relative']}\">PDF</a></td>"
            f"<td><a href=\"{item['helper_relative']}\">Chrome helper</a></td>"
            f"<td>{item['crm_status']}</td></tr>"
        )
    weakness_list = _render_list([f"{item['company_name']}: {item['primary_weakness']}" for item in results[:10]])
    command_list = _render_list([item["chrome_command"] for item in results[:5]])
    proposal_list = _render_list([compact_text(item["proposal_preview"], 160) for item in results[:5]])
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Autopilot dashboard {run['date_key']}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: linear-gradient(180deg, #f6f7fb, #eef2f7); color: #102030; }}
    .hero {{ background: #0f2740; color: white; border-radius: 22px; padding: 24px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin: 18px 0; }}
    .metric {{ background: white; border-radius: 16px; padding: 14px; border: 1px solid #d7e0ea; }}
    .metric strong {{ display: block; font-size: 28px; }}
    .card {{ background: white; border: 1px solid #d7e0ea; border-radius: 16px; padding: 18px; margin-top: 16px; box-shadow: 0 10px 24px rgba(16,32,48,.05); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid #edf2f7; vertical-align: top; }}
    th {{ background: #f7f9fc; }}
    .small {{ color: #5a6b7d; font-size: 13px; }}
    a {{ color: #1f5fa5; }}
  </style>
</head>
<body>
  <div class="hero">
    <h1>Autopilot dashboard</h1>
    <p>{run['date_key']} / {run['area']} / {run['industry']}</p>
    <p>送信・応募・公開は自動化しません。最終判断は人間確認です。</p>
  </div>
  <div class="metrics">
    <div class="metric"><span>本日の診断件数</span><strong>{run['count']}</strong></div>
    <div class="metric"><span>Aランク</span><strong>{run['rank_counts'].get('A', 0)}</strong></div>
    <div class="metric"><span>Bランク</span><strong>{run['rank_counts'].get('B', 0)}</strong></div>
    <div class="metric"><span>想定受注額合計</span><strong>{run['revenue_total']}</strong></div>
    <div class="metric"><span>CRM件数</span><strong>{run['crm_count']}</strong></div>
  </div>

  <div class="card">
    <h2>優先営業リスト</h2>
    <table>
      <thead>
        <tr>
          <th>会社名</th><th>score</th><th>rank</th><th>弱点</th><th>提案文プレビュー</th><th>PDF</th><th>Chrome入力補助</th><th>CRM</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>各社の弱点</h2>
    {weakness_list}
  </div>

  <div class="card">
    <h2>提案文プレビュー</h2>
    {proposal_list}
  </div>

  <div class="card">
    <h2>PDFリンク</h2>
    { _render_list([f"<a href='{item['report_relative']}'> {item['company_name']} </a>" for item in results]) }
  </div>

  <div class="card">
    <h2>Chrome入力補助ボタン用コマンド</h2>
    {command_list}
  </div>

  <div class="card">
    <h2>CRMステータス</h2>
    { _render_list([f"{item['company_name']}: {item['crm_status']}" for item in results]) }
  </div>

  <div class="card">
    <h2>営業候補一覧</h2>
    <p class="small">生成元: {run['generated_leads_csv']}</p>
    <p class="small">会社ディレクトリ: {run['companies_dir']}</p>
  </div>
</body>
</html>
"""
def _write_dashboard_bundle(report_dir: Path, run: dict[str, Any], results: list[dict[str, Any]]) -> tuple[Path, Path]:
    dashboard_html = _build_dashboard_html(run, results)
    daily_index = write_text(report_dir / "index.html", dashboard_html)
    root_index = write_text(report_dir.parent / "index.html", dashboard_html)
    return daily_index, root_index


def _score_to_price(score: int) -> int:
    if score >= 80:
        return 79800
    if score >= 65:
        return 29800
    return 9800


def _format_price(price: int) -> str:
    return f"JPY {price:,}"


def run_autopilot(
    *,
    area: str,
    industry: str,
    limit: int,
    lead_csv: Path | None = None,
    sample: bool = False,
    report_root: Path = Path("reports"),
    data_root: Path = Path("data"),
) -> dict[str, Any]:
    run_date = date.today()
    date_key = today_key(run_date)
    report_dir = ensure_dir(report_root / date_key)
    companies_root = ensure_dir(report_dir / "companies")
    data_root = ensure_dir(data_root)

    leads = find_leads(area, industry, limit, lead_csv=lead_csv, sample=sample)
    generated_leads_csv = data_root / f"generated_leads_{date_key}.csv"
    save_generated_leads(generated_leads_csv, leads)

    results: list[dict[str, Any]] = []
    crm_rows: list[dict[str, str]] = []
    scored_rows: list[dict[str, str]] = []
    revenue_total = 0
    rank_counts: Counter[str] = Counter()

    lead_urls = [lead.website_url for lead in leads if lead.website_url]
    for index, lead in enumerate(leads, start=1):
        company_dir = ensure_dir(companies_root / safe_company_dir_name(lead))
        competitor_urls = [url for url in lead_urls[index:index + 2] if url and url != lead.website_url]
        diagnostics = _site_diagnostics(lead, sample_mode=sample)
        screenshot_info = capture_screenshots(
            lead,
            company_dir,
            diagnostics["website_url"],
            competitor_urls=competitor_urls,
            sample_mode=sample or not bool(lead.website_url),
        )
        diagnostics["screenshot_status"] = screenshot_info["screenshot_status"]
        diagnostics["screenshots_dir"] = screenshot_info["screenshots_dir"]
        proposal_text = build_proposal_text(
            lead,
            diagnostics,
            fix_summary=diagnostics["top_fixes"][0] if diagnostics["top_fixes"] else "導線整理",
        )
        estimate_md = build_estimate_markdown(lead, diagnostics)
        fix_plan_md = _build_fix_plan_md(diagnostics)
        proposal_path = write_text(company_dir / "proposal.txt", proposal_text)
        estimate_path = write_text(company_dir / "estimate.md", estimate_md)
        fix_plan_path = write_text(company_dir / "fix_plan.md", fix_plan_md)
        raw_payload = {
            "lead": lead.to_row(),
            "diagnostics": diagnostics,
            "screenshot_status": screenshot_info["screenshot_status"],
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "sample_mode": sample,
        }
        raw_json_path = write_json(company_dir / "raw.json", raw_payload)
        customer_html_path = write_text(company_dir / "customer_report.html", _customer_html(lead, diagnostics, company_dir, estimate_md))
        internal_html_path = write_text(
            company_dir / "internal_report.html",
            _internal_html(lead, diagnostics, proposal_text, estimate_md, fix_plan_md, json.dumps(raw_payload, ensure_ascii=False, indent=2)),
        )
        pdf_path = write_customer_pdf(customer_html_path, company_dir / "customer_report.pdf", title=f"{lead.company_name} 顧客向け診断レポート")
        helper_html_path = write_marketplace_helper(company_dir, lead, proposal_text, estimate_md, Path("customer_report.pdf"))
        chrome_command = build_chrome_command(helper_html_path)
        report_relative = Path("companies") / safe_company_dir_name(lead) / "customer_report.pdf"
        helper_relative = Path("companies") / safe_company_dir_name(lead) / "marketplace_helper.html"
        score = int(diagnostics["score"])
        rank = diagnostics["rank"]
        rank_counts[rank] += 1
        revenue_total += _score_to_price(score)
        estimate_plan = _format_price(_score_to_price(score))
        crm_status = "proposal_ready" if score >= 50 else "reviewed"
        crm_rows.append(
            build_crm_row(
                lead,
                report_date=run_date,
                score=score,
                status=crm_status,
                next_action="Chrome入力補助で内容を確認して人間が手動送信",
                proposal_path=proposal_path,
                report_path=pdf_path,
                notes=diagnostics["primary_weakness"],
            )
        )
        scored_rows.append(
            {
                **lead.to_row(),
                "score": str(score),
                "rank": rank,
                "primary_weakness": diagnostics["primary_weakness"],
                "good_points": " / ".join(diagnostics["good_points"][:3]),
                "top_fixes": " / ".join(diagnostics["top_fixes"]),
                "proposal_preview": compact_text(proposal_text, 150),
                "estimate_plan": estimate_plan,
                "proposal_path": str(proposal_path),
                "estimate_path": str(estimate_path),
                "fix_plan_path": str(fix_plan_path),
                "report_path": str(pdf_path),
                "marketplace_command": chrome_command,
            }
        )
        results.append(
            {
                "company_name": lead.company_name,
                "score": score,
                "rank": rank,
                "primary_weakness": diagnostics["primary_weakness"],
                "proposal_preview": proposal_text,
                "report_relative": report_relative.as_posix(),
                "helper_relative": helper_relative.as_posix(),
                "chrome_command": chrome_command,
                "crm_status": crm_status,
            }
        )
        write_json(
            company_dir / "result_summary.json",
            {
                "company_name": lead.company_name,
                "score": score,
                "rank": rank,
                "proposal_path": str(proposal_path),
                "estimate_path": str(estimate_path),
                "fix_plan_path": str(fix_plan_path),
                "report_path": str(pdf_path),
                "marketplace_command": chrome_command,
            },
        )

    write_csv_rows(report_dir / "leads_scored.csv", scored_rows, LEADS_SCORED_COLUMNS)
    write_crm_csv(report_dir / "crm.csv", crm_rows)
    run_summary = {
        "date_key": date_key,
        "area": area,
        "industry": industry,
        "count": len(results),
        "rank_counts": dict(rank_counts),
        "revenue_total": _format_price(revenue_total),
        "crm_count": len(crm_rows),
        "generated_leads_csv": str(generated_leads_csv),
        "companies_dir": str(companies_root),
    }
    _write_dashboard_bundle(report_dir, run_summary, results)
    return {
        "report_dir": str(report_dir),
        "generated_leads_csv": str(generated_leads_csv),
        "leads_scored_csv": str(report_dir / "leads_scored.csv"),
        "crm_csv": str(report_dir / "crm.csv"),
        "results": results,
        "summary": run_summary,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.autopilot", description="Autopilot sales assistant")
    parser.add_argument("--area", default="", help="target area")
    parser.add_argument("--industry", default="", help="target industry")
    parser.add_argument("--limit", type=int, default=20, help="number of leads")
    parser.add_argument("--lead-csv", type=Path, help="manual lead CSV input")
    parser.add_argument("--sample", action="store_true", help="use built-in sample leads and local placeholders")
    parser.add_argument("--report-root", type=Path, default=Path("reports"), help="report output root")
    parser.add_argument("--data-root", type=Path, default=Path("data"), help="data output root")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.area and not args.sample:
        raise SystemExit("--area is required unless --sample is used")
    if not args.industry and not args.sample:
        raise SystemExit("--industry is required unless --sample is used")
    result = run_autopilot(
        area=args.area or "sample area",
        industry=args.industry or "sample industry",
        limit=args.limit,
        lead_csv=args.lead_csv,
        sample=args.sample,
        report_root=args.report_root,
        data_root=args.data_root,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(result["generated_leads_csv"])
    print(result["leads_scored_csv"])
    print(result["crm_csv"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
