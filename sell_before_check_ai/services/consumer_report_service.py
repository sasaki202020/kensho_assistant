from __future__ import annotations

from html import escape
from typing import Any

from field_assessment_ai.services.common import format_price, join_html_list

from .common import CONSUMER_DISCLAIMER, CHECK_TYPE_LABELS, build_188_notice, render_link_list


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


def _official_info_rows(official_infos: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for info in official_infos:
        links = info.get("reference_links") or []
        rows.append(
            [
                escape(str(info.get("category") or "")),
                escape(str(info.get("title") or "")),
                escape(str(info.get("summary") or "")),
                escape(" / ".join(links) if links else "なし"),
            ]
        )
    return rows


def build_consumer_report_payload(
    check_type: str,
    payload: dict[str, Any],
    risk_context: dict[str, Any],
    *,
    title: str | None = None,
    format: str = "json",
) -> dict[str, Any]:
    check_label = CHECK_TYPE_LABELS.get(check_type, check_type)
    verdict = risk_context.get("judgement_result") or "確認推奨"
    official_infos = risk_context.get("official_infos") or []
    market_links = risk_context.get("market_links") or {}
    refusal_phrase = risk_context.get("refusal_phrase") or ""
    missing_info = risk_context.get("missing_info") or []
    next_actions = risk_context.get("next_actions") or []
    caution_notes = risk_context.get("caution_notes") or []
    confidence_score = risk_context.get("confidence_score") or 0
    confidence_label = risk_context.get("confidence_label") or ""
    hotline_notice = risk_context.get("hotline_notice") or "消費者ホットライン188へ相談する。"
    disclaimer = risk_context.get("disclaimer") or CONSUMER_DISCLAIMER
    report_title = title or f"{check_label}チェックレポート"

    official_info_rows = _official_info_rows(official_infos)
    market_link_html = render_link_list(market_links)
    official_info_html = _render_table(["カテゴリ", "タイトル", "要点", "参考リンク"], official_info_rows) if official_info_rows else "<p>なし</p>"

    content_json = {
        "report_type": "consumer_check",
        "check_type": check_type,
        "check_label": check_label,
        "check": payload,
        "judgement": verdict,
        "reason": risk_context.get("reason"),
        "missing_info": missing_info,
        "next_actions": next_actions,
        "refusal_phrase": refusal_phrase,
        "market_links": market_links,
        "official_infos": official_infos,
        "hotline_notice": hotline_notice,
        "caution_notes": caution_notes,
        "confidence": {
            "score": confidence_score,
            "label": confidence_label,
        },
        "disclaimer": disclaimer,
        "format": format,
    }

    html = f"""
    <html lang="ja">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>{escape(report_title)}</title>
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
            <div class="muted">売る前チェックAI レポート</div>
            <h1>{escape(report_title)}</h1>
            <p>{escape(check_label)}</p>
            <div class="grid">
              <div class="metric"><div class="label">判定</div><div class="value">{escape(str(verdict))}</div></div>
              <div class="metric"><div class="label">信頼度</div><div class="value">{confidence_score} / {escape(str(confidence_label))}</div></div>
              <div class="metric"><div class="label">不足情報</div><div class="value">{len(missing_info)}件</div></div>
              <div class="metric"><div class="label">次にやること</div><div class="value">{len(next_actions)}件</div></div>
            </div>
          </div>
          {_render_section("判定理由", f"<p>{escape(str(risk_context.get('reason') or ''))}</p>")}
          {_render_section("不足情報", join_html_list([str(value) for value in missing_info]) if missing_info else "<p>なし</p>")}
          {_render_section("次にやること", join_html_list([str(value) for value in next_actions]) if next_actions else "<p>なし</p>")}
          {_render_section("断り文例", f"<p>{escape(str(refusal_phrase or ''))}</p>")}
          {_render_section("相場リンク", market_link_html if market_links else "<p>なし</p>")}
          {_render_section("公式情報", official_info_html)}
          {_render_section("188相談案内", f"<p>{escape(str(hotline_notice))}</p>")}
          {_render_section("注意文", f"<p>{escape(str(disclaimer))}</p>")}
          {_render_section("補足メモ", join_html_list([str(value) for value in caution_notes]) if caution_notes else "<p>なし</p>")}
        </div>
      </body>
    </html>
    """

    summary_text = f"判定 {verdict} / 信頼度 {confidence_label or confidence_score} / 不足 {len(missing_info)}件"
    return {
        "title": report_title,
        "summary_text": summary_text,
        "content_json": content_json,
        "content_html": html,
        "legal_notices": [build_188_notice()],
    }
