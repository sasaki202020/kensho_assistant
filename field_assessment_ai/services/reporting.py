from __future__ import annotations

from html import escape
from typing import Any

from .common import LEGAL_DISCLAIMER, format_price, join_html_list, value_range_to_text


def _unique_by_code(notices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for notice in notices:
        code = str(notice.get("code") or notice.get("title") or len(unique))
        if code in seen:
            continue
        seen.add(code)
        unique.append(notice)
    return unique


def _build_rows(items: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        estimate = item.get("estimate") or {}
        analysis = item.get("analysis") or {}
        market_memo = item.get("market_memo") or {}
        rows.append(
            {
                "item_name": item.get("item", {}).get("name"),
                "category": item.get("item", {}).get("category"),
                "rank_candidate": estimate.get("rank_candidate") or (analysis.get("rank_candidates") or [None])[0],
                "value_range": value_range_to_text(analysis.get("estimated_value_range")),
                "purchase_estimate": estimate.get("purchase_estimate"),
                "final_estimate_guide": estimate.get("final_estimate_guide"),
                "kind": kind,
                "market_keyword": market_memo.get("search_keyword"),
                "notes": item.get("notes") or [],
            }
        )
    return rows


def build_report_payload(
    job: dict[str, Any],
    item_snapshots: list[dict[str, Any]],
    job_estimate: dict[str, Any],
    *,
    title: str,
    format: str = "json",
) -> dict[str, Any]:
    legal_notices: list[dict[str, Any]] = []
    for snapshot in item_snapshots:
        legal_notices.extend(snapshot.get("analysis", {}).get("legal_notices", []))
        legal_notices.extend(snapshot.get("legal_notices", []))
    if job_estimate.get("legal_notices"):
        legal_notices.extend(job_estimate["legal_notices"])
    legal_notices = _unique_by_code(legal_notices)

    reusable_candidates = []
    purchase_candidates = []
    disposal_attention = []
    estimate_applied_content = []

    for snapshot in item_snapshots:
        item = snapshot.get("item") or {}
        analysis = snapshot.get("analysis") or {}
        estimate = snapshot.get("estimate") or {}
        market_memo = snapshot.get("market_memo") or {}
        rank = estimate.get("rank_candidate") or (analysis.get("rank_candidates") or [None])[0]
        row = {
            "item_id": item.get("id"),
            "item_name": item.get("name"),
            "category": item.get("category"),
            "rank_candidate": rank,
            "value_range": analysis.get("estimated_value_range"),
            "purchase_estimate": estimate.get("purchase_estimate"),
            "final_estimate_guide": estimate.get("final_estimate_guide"),
            "search_keyword": market_memo.get("search_keyword"),
        }
        estimate_applied_content.append(row)
        if rank in {"A", "B", "C"}:
            reusable_candidates.append(row)
            if estimate.get("purchase_estimate", 0) > 0:
                purchase_candidates.append(row)
        if rank in {"D", "E", "F"} or snapshot.get("safety_notices"):
            disposal_attention.append(
                {
                    **row,
                    "safety_notices": snapshot.get("safety_notices") or [],
                }
            )

    summary = {
        "item_count": len(item_snapshots),
        "reusable_count": len(reusable_candidates),
        "purchase_count": len(purchase_candidates),
        "disposal_count": len(disposal_attention),
        "final_estimate_guide": job_estimate.get("final_estimate_guide"),
        "resale_estimate_min": job_estimate.get("resale_estimate_min"),
        "resale_estimate_max": job_estimate.get("resale_estimate_max"),
        "purchase_estimate": job_estimate.get("purchase_estimate"),
        "work_fee_estimate": job_estimate.get("work_fee_estimate"),
        "disposal_fee_estimate": job_estimate.get("disposal_fee_estimate"),
        "discount_possible_amount": job_estimate.get("discount_possible_amount"),
        "rank_candidate": job_estimate.get("rank_candidate"),
    }

    content_json = {
        "report_type": "customer_draft",
        "job": job,
        "summary": summary,
        "reusable_candidates": reusable_candidates,
        "purchase_candidates": purchase_candidates,
        "disposal_attention": disposal_attention,
        "estimate_applied_content": estimate_applied_content,
        "legal_notices": legal_notices,
        "disclaimer": LEGAL_DISCLAIMER,
        "format": format,
    }
    html = render_report_html(content_json)
    summary_text = (
        f"再販売候補 {len(reusable_candidates)}件 / "
        f"買取候補 {len(purchase_candidates)}件 / "
        f"注意品 {len(disposal_attention)}件 / "
        f"最終見積り目安 {format_price(summary.get('final_estimate_guide'))}"
    )

    return {
        "title": title,
        "summary_text": summary_text,
        "content_json": content_json,
        "content_html": html,
        "legal_notices": legal_notices,
        "summary": summary,
    }


def _render_section(title: str, body_html: str) -> str:
    return f"""
    <section class="card">
      <h2>{escape(title)}</h2>
      {body_html}
    </section>
    """


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    row_html = ""
    for row in rows:
        cells = "".join(f"<td>{cell}</td>" for cell in row)
        row_html += f"<tr>{cells}</tr>"
    return f"""
    <table>
      <thead><tr>{header_html}</tr></thead>
      <tbody>{row_html}</tbody>
    </table>
    """


def render_report_html(payload: dict[str, Any]) -> str:
    job = payload.get("job") or {}
    summary = payload.get("summary") or {}
    reusable = payload.get("reusable_candidates") or []
    purchase = payload.get("purchase_candidates") or []
    disposal = payload.get("disposal_attention") or []
    estimate_applied_content = payload.get("estimate_applied_content") or []
    legal_notices = payload.get("legal_notices") or []
    disclaimer = payload.get("disclaimer") or LEGAL_DISCLAIMER

    reusable_rows = [[
        escape(str(row.get("item_name") or "")),
        escape(str(row.get("category") or "")),
        escape(str(row.get("rank_candidate") or "")),
        escape(format_price(row.get("purchase_estimate"))),
        escape(format_price(row.get("final_estimate_guide"))),
    ] for row in reusable]

    purchase_rows = [[
        escape(str(row.get("item_name") or "")),
        escape(str(row.get("category") or "")),
        escape(str(row.get("rank_candidate") or "")),
        escape(format_price(row.get("purchase_estimate"))),
        escape(format_price(row.get("final_estimate_guide"))),
    ] for row in purchase]

    disposal_rows = [[
        escape(str(row.get("item_name") or "")),
        escape(str(row.get("category") or "")),
        escape(str(row.get("rank_candidate") or "")),
        escape(" / ".join((notice.get("title") or "" for notice in row.get("safety_notices") or [])) or "なし"),
    ] for row in disposal]

    estimate_rows = [[
        escape(str(row.get("item_name") or "")),
        escape(str(row.get("category") or "")),
        escape(str(row.get("rank_candidate") or "")),
        escape(value_range_to_text(row.get("value_range")) if isinstance(row.get("value_range"), dict) else str(row.get("value_range") or "未設定")),
        escape(format_price(row.get("purchase_estimate"))),
        escape(format_price(row.get("final_estimate_guide"))),
    ] for row in estimate_applied_content]

    legal_rows = [[
        escape(str(notice.get("severity") or "")),
        escape(str(notice.get("title") or "")),
        escape(str(notice.get("message") or "")),
    ] for notice in legal_notices]

    html = f"""
    <html lang="ja">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>{escape(payload.get("title") or "現場査定AI レポート")}</title>
        <style>
          :root {{
            color-scheme: light;
            --bg: #0f172a;
            --card: #111827;
            --text: #e5e7eb;
            --muted: #94a3b8;
            --line: #243244;
            --accent: #22c55e;
            --warn: #f59e0b;
          }}
          body {{
            margin: 0;
            font-family: "Yu Gothic UI", "Segoe UI", sans-serif;
            background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%);
            color: #0f172a;
          }}
          .page {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 32px 20px 56px;
          }}
          .hero {{
            background: #0f172a;
            color: white;
            border-radius: 20px;
            padding: 28px;
            box-shadow: 0 20px 60px rgba(15, 23, 42, 0.16);
          }}
          .hero h1 {{
            margin: 0 0 8px;
            font-size: 32px;
          }}
          .hero p {{
            margin: 6px 0 0;
            color: #cbd5e1;
          }}
          .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 14px;
            margin-top: 18px;
          }}
          .metric {{
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 16px;
            padding: 16px;
          }}
          .metric .label {{
            color: #cbd5e1;
            font-size: 12px;
            letter-spacing: 0.04em;
          }}
          .metric .value {{
            font-size: 24px;
            margin-top: 8px;
            font-weight: 700;
          }}
          .card {{
            background: rgba(255, 255, 255, 0.84);
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 18px;
            padding: 20px;
            margin-top: 16px;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
          }}
          .card h2 {{
            margin: 0 0 12px;
            font-size: 20px;
          }}
          table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
          }}
          th, td {{
            border-bottom: 1px solid #e2e8f0;
            padding: 10px 8px;
            text-align: left;
            vertical-align: top;
          }}
          th {{
            color: #334155;
            background: #f8fafc;
            font-weight: 600;
          }}
          .notice {{
            background: #fff7ed;
            border-left: 4px solid #f59e0b;
            padding: 12px 14px;
            margin-top: 10px;
            border-radius: 10px;
          }}
          .muted {{
            color: #475569;
          }}
        </style>
      </head>
      <body>
        <div class="page">
          <div class="hero">
            <div class="muted">お客様向けレポート下書き</div>
            <h1>{escape(payload.get("title") or "現場査定AI レポート")}</h1>
            <p>{escape(job.get("title") or "")}</p>
            <div class="grid">
              <div class="metric"><div class="label">再販売候補</div><div class="value">{summary.get("reusable_count", 0)}件</div></div>
              <div class="metric"><div class="label">買取候補</div><div class="value">{summary.get("purchase_count", 0)}件</div></div>
              <div class="metric"><div class="label">注意品</div><div class="value">{summary.get("disposal_count", 0)}件</div></div>
              <div class="metric"><div class="label">最終見積り目安</div><div class="value">{escape(format_price(summary.get("final_estimate_guide")))} </div></div>
            </div>
          </div>
          {_render_section("リユース候補", _render_table(["商品名", "カテゴリ", "ランク候補", "買取見込み", "見積り目安"], reusable_rows) if reusable_rows else "<p>なし</p>")}
          {_render_section("買取候補", _render_table(["商品名", "カテゴリ", "ランク候補", "買取見込み", "見積り目安"], purchase_rows) if purchase_rows else "<p>なし</p>")}
          {_render_section("処分・注意品", _render_table(["商品名", "カテゴリ", "ランク候補", "注意点"], disposal_rows) if disposal_rows else "<p>なし</p>")}
          {_render_section("見積もりに反映した内容", _render_table(["商品名", "カテゴリ", "ランク候補", "価値レンジ", "買取見込み", "見積り目安"], estimate_rows) if estimate_rows else "<p>なし</p>")}
          {_render_section("法令・注意", _render_table(["重要度", "件名", "内容"], legal_rows) if legal_rows else "<p>なし</p>")}
          <div class="notice">
            <strong>注意:</strong> {escape(disclaimer)}
          </div>
        </div>
      </body>
    </html>
    """
    return html
