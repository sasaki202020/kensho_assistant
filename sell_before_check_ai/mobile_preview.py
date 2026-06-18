from __future__ import annotations

import argparse
from html import escape
import json
import socket
import time
from pathlib import Path
from threading import Thread
from typing import Any

from jinja2 import Template

from .config import AppSettings
from .services.consumer_report_service import build_consumer_report_payload
from .services.consumer_risk_judgement_service import build_risk_judgement_context
from .services.official_info_service import default_official_info_rows
from .services.refusal_phrase_service import default_refusal_phrase_rows


PREVIEW_SCENARIO_DEFAULT = "kimono"
PREVIEW_TYPE_TO_SCENARIO = {
    "flyer": "kimono",
    "item": "mishin",
    "quote": "recovery_quote",
}

SCREENSHOT_LAYOUTS: list[dict[str, Any]] = [
    {
        "key": "iphone",
        "label": "iPhone縦",
        "shell_width": 452,
        "shell_height": 952,
        "screen_width": 393,
        "screen_height": 852,
        "device_class": "portrait",
    },
    {
        "key": "pixel",
        "label": "Pixel縦",
        "shell_width": 470,
        "shell_height": 1014,
        "screen_width": 412,
        "screen_height": 915,
        "device_class": "portrait",
    },
    {
        "key": "landscape",
        "label": "横向き",
        "shell_width": 1002,
        "shell_height": 526,
        "screen_width": 915,
        "screen_height": 412,
        "device_class": "landscape",
    },
]


def _mobile_preview_screenshot_dir(base_dir: Path | None = None) -> Path:
    target = base_dir or (Path(__file__).resolve().parent / "runtime" / "screenshots")
    target.mkdir(parents=True, exist_ok=True)
    return target


def ensure_mobile_preview_screenshot_dir(base_dir: Path | None = None) -> Path:
    return _mobile_preview_screenshot_dir(base_dir)


def _verdict_tone(verdict: str) -> str:
    return {
        "問題なさそう": "ok",
        "確認推奨": "review",
        "即決注意": "warn",
        "相談推奨": "danger",
    }.get(verdict, "review")


def _build_preview_scenarios() -> list[dict[str, Any]]:
    official_info_rows = default_official_info_rows()
    refusal_phrase_rows = default_refusal_phrase_rows()
    definitions: list[dict[str, Any]] = [
        {
            "key": "kimono",
            "label": "着物買取チラシ",
            "type": "flyer",
            "lead_headline": "高価買取より、条件確認を先に進めてください",
            "lead_recommendation": "出張費とキャンセル料を紙で残す",
            "lead_copy": "着物は証紙や落款、保管状態を見てから判断すると安心です。",
            "lead_reasons": [
                "高価買取や即日現金化の文言がある",
                "出張費・キャンセル料の条件を確認したい",
                "証紙や落款を写真で残したい",
            ],
            "payload": {
                "company_name": "サンプル着物査定",
                "phone_number": "0120-123-456",
                "flyer_text": "着物高価買取 / 出張査定無料 / 即日現金化 / 貴金属も査定",
                "outcall_fee_text": "出張費無料",
                "cancellation_fee_text": "キャンセル料無料",
                "high_price_text": "高価買取",
                "same_day_cash_text": "即日現金化",
                "inducement_text": "着物買取",
                "memo": "家族に見せてから判断したいチラシ",
            },
        },
        {
            "key": "mishin",
            "label": "ミシン買取",
            "type": "item",
            "lead_headline": "型番と付属品がそろうまで、即決しないでください",
            "lead_recommendation": "型番と動作確認をそろえて複数査定",
            "lead_copy": "JUKIのミシンは、型番・付属品・試し縫いで見え方が変わります。",
            "lead_reasons": [
                "型番が不明で相場が読みづらい",
                "フットコントローラーや説明書を確認したい",
                "試し縫いと動作確認を見てから比べたい",
            ],
            "payload": {
                "item_category": "ミシン",
                "item_name": "JUKI ミシン",
                "brand": "JUKI",
                "model_number": "不明",
                "condition_note": "動作未確認",
                "accessories": "フットコントローラーなし",
                "offered_price": 1000,
                "market_memo": "型番不明",
                "memo": "型番と付属品の確認が必要",
            },
        },
        {
            "key": "kikinzoku",
            "label": "貴金属査定",
            "type": "item",
            "lead_headline": "即決はせず、相場と複数査定で比べてください",
            "lead_recommendation": "刻印・重量・鑑定書を確認してから判断する",
            "lead_copy": "K18らしき指輪は、刻印・重量・鑑定書がそろうほど判断しやすくなります。",
            "lead_reasons": [
                "即決を求められているなら、その場で売らない",
                "相場の根拠が見えにくいので複数査定で比べたい",
                "刻印・重量・鑑定書を写真で残したい",
            ],
            "payload": {
                "item_category": "貴金属",
                "item_name": "K18らしき指輪",
                "brand": "",
                "model_number": "",
                "condition_note": "刻印未確認",
                "accessories": "",
                "offered_price": 5000,
                "market_memo": "刻印未確認",
                "memo": "真贋は断定しない前提",
            },
        },
        {
            "key": "recovery_quote",
            "label": "不用品回収見積もり",
            "type": "quote",
            "lead_headline": "追加料金の条件がそろうまで、契約は待ってください",
            "lead_recommendation": "見積書・明細を紙かメールで残す",
            "lead_copy": "軽トラックパックでも、当日追加請求や家電リサイクル費の扱いを先に確認します。",
            "lead_reasons": [
                "追加料金の条件があいまい",
                "キャンセル条件と家電リサイクル費を確認したい",
                "見積書と明細を紙かメールで残したい",
            ],
            "payload": {
                "offered_price": 9800,
                "work_fee": 0,
                "disposal_fee": 0,
                "outcall_fee": 0,
                "appraisal_fee": 0,
                "cancellation_fee": 0,
                "home_appliance_recycling_fee": "不明",
                "additional_charge_conditions": "当日追加請求あり",
                "package_price": 9800,
                "same_day_extra_charge": 80000,
                "estimate_sheet_present": False,
                "memo": "軽トラックパック9,800円",
            },
        },
    ]

    scenarios: list[dict[str, Any]] = []
    for definition in definitions:
        risk_context = build_risk_judgement_context(
            definition["type"],
            definition["payload"],
            official_info_rows,
            refusal_phrase_rows,
        )
        report = build_consumer_report_payload(
            definition["type"],
            definition["payload"],
            risk_context,
            title=definition["label"],
            format="json",
        )
        content_json = report["content_json"]
        scenarios.append(
            {
                "key": definition["key"],
                "label": definition["label"],
                "type": definition["type"],
                "lead_headline": definition["lead_headline"],
                "lead_recommendation": definition["lead_recommendation"],
                "lead_copy": definition["lead_copy"],
                "lead_reasons": definition["lead_reasons"],
                "verdict": content_json["judgement"],
                "tone": _verdict_tone(content_json["judgement"]),
                "check": definition["payload"],
                "report": content_json,
                "summary": report["summary_text"],
                "confidence_score": content_json["confidence"]["score"],
                "confidence_label": content_json["confidence"]["label"],
            }
        )
    return scenarios


def _preview_scenarios_by_key() -> dict[str, dict[str, Any]]:
    return {scenario["key"]: scenario for scenario in _build_preview_scenarios()}


def _build_mobile_preview_screenshot_targets() -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = [
        {
            "key": "live",
            "label": "本番想定 / scenarioなし",
            "scenario_key": None,
        }
    ]
    for scenario in _build_preview_scenarios():
        targets.append(
            {
                "key": scenario["key"],
                "label": scenario["label"],
                "scenario_key": scenario["key"],
            }
        )
    return targets


def _find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _wait_for_http_ready(url: str, timeout_seconds: float = 10.0) -> None:
    import urllib.request

    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - retry loop for local server startup
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"server did not become ready: {url}") from last_error


_MOBILE_PREVIEW_TEMPLATE = Template(
    """
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{{ app_name }} | スマホ導線</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #050b12;
      --panel: rgba(12, 18, 26, 0.94);
      --panel-strong: rgba(17, 24, 34, 0.98);
      --panel-soft: rgba(255, 255, 255, 0.04);
      --line: rgba(148, 163, 184, 0.18);
      --line-strong: rgba(215, 166, 74, 0.25);
      --text: #eef2f7;
      --muted: #9aa7b8;
      --muted-strong: #cbd5e1;
      --accent: #4fa3ff;
      --accent-soft: rgba(79, 163, 255, 0.15);
      --warn: #f3c44f;
      --warn-soft: rgba(243, 196, 79, 0.15);
      --danger: #f66d6d;
      --danger-soft: rgba(246, 109, 109, 0.17);
      --success: #5ed09a;
      --success-soft: rgba(94, 208, 154, 0.15);
      --shadow: 0 22px 70px rgba(2, 6, 23, 0.5);
      --radius-xl: 28px;
      --radius-lg: 22px;
      --radius-md: 16px;
      --radius-sm: 12px;
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at 15% 10%, rgba(79, 163, 255, 0.12), transparent 20%),
        radial-gradient(circle at 85% 14%, rgba(215, 166, 74, 0.16), transparent 22%),
        linear-gradient(180deg, #04080d 0%, #08111a 46%, #0b1320 100%);
      font-family: "IBM Plex Sans JP", "Yu Gothic UI", "Segoe UI", sans-serif;
      letter-spacing: 0.01em;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
      background-size: 64px 64px;
      mask-image: radial-gradient(circle at center, black 44%, transparent 100%);
      opacity: 0.55;
    }

    a { color: inherit; }
    button, input { font: inherit; }

    .page {
      position: relative;
      z-index: 1;
      width: min(100%, 430px);
      margin: 0 auto;
      padding: 16px 16px 124px;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 6px 0 14px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }

    .brand-mark {
      width: 44px;
      height: 44px;
      border-radius: 16px;
      display: grid;
      place-items: center;
      background: linear-gradient(180deg, rgba(79, 163, 255, 0.95), rgba(255, 255, 255, 0.08));
      color: #08111a;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-weight: 700;
      letter-spacing: 0.08em;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35);
      flex: none;
    }

    .brand-copy {
      min-width: 0;
    }

    .eyebrow {
      margin: 0 0 3px;
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }

    .brand-copy h1 {
      margin: 0;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 1rem;
      letter-spacing: 0.04em;
      line-height: 1.15;
    }

    .ghost-link {
      min-height: 44px;
      padding: 0 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
      color: var(--muted-strong);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
      font-size: 0.85rem;
      white-space: nowrap;
    }

    .card {
      display: grid;
      gap: 14px;
      padding: 18px;
      border-radius: var(--radius-xl);
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }

    .scenario-card {
      gap: 12px;
      border-color: rgba(215, 166, 74, 0.22);
      background: linear-gradient(180deg, rgba(14, 20, 30, 0.96), rgba(10, 16, 24, 0.96));
    }

    .scenario-note {
      margin: 0;
      color: var(--muted-strong);
      font-size: 0.86rem;
      line-height: 1.65;
    }

    .scenario-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .scenario-button {
      min-height: 68px;
      padding: 12px 12px 11px;
      text-align: left;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text);
      cursor: pointer;
      display: grid;
      gap: 4px;
      align-content: center;
      transition: transform 140ms ease, filter 140ms ease, border-color 140ms ease, background 140ms ease;
    }

    .scenario-button.ok { border-color: rgba(94, 208, 154, 0.16); }
    .scenario-button.review { border-color: rgba(243, 196, 79, 0.22); }
    .scenario-button.warn { border-color: rgba(246, 109, 109, 0.22); }
    .scenario-button.danger { border-color: rgba(246, 109, 109, 0.32); }

    .scenario-button.active {
      background: linear-gradient(180deg, rgba(79, 163, 255, 0.2), rgba(79, 163, 255, 0.08));
      border-color: rgba(79, 163, 255, 0.46);
      box-shadow: 0 0 0 4px rgba(79, 163, 255, 0.08);
    }

    .scenario-button .scenario-title {
      font-size: 0.92rem;
      font-weight: 800;
      line-height: 1.35;
      letter-spacing: 0.01em;
    }

    .scenario-button .scenario-verdict {
      color: var(--muted-strong);
      font-size: 0.74rem;
      line-height: 1.2;
      letter-spacing: 0.03em;
    }

    .lead-card {
      position: relative;
      overflow: hidden;
      background:
        radial-gradient(circle at 100% 0%, rgba(79, 163, 255, 0.12), transparent 28%),
        linear-gradient(180deg, rgba(15, 23, 35, 0.96), rgba(10, 16, 26, 0.96));
      border-color: rgba(79, 163, 255, 0.18);
    }

    .lead-top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }

    .lead-stack {
      display: grid;
      gap: 8px;
      min-width: 0;
    }

    .lead-risk {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(243, 196, 79, 0.22);
      background: rgba(243, 196, 79, 0.1);
      color: #ffe29b;
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      white-space: nowrap;
    }

    .lead-headline {
      margin: 0;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: clamp(1.8rem, 7vw, 2.35rem);
      line-height: 1.08;
      letter-spacing: -0.03em;
      text-wrap: balance;
    }

    .lead-copy {
      margin: 0;
      color: var(--muted-strong);
      font-size: 1rem;
      line-height: 1.85;
      text-wrap: pretty;
    }

    .lead-meta {
      display: grid;
      gap: 8px;
      padding: 14px 15px;
      border-radius: 18px;
      border: 1px solid rgba(79, 163, 255, 0.16);
      background: rgba(79, 163, 255, 0.08);
    }

    .lead-meta strong {
      font-size: 1rem;
      line-height: 1.6;
      color: var(--text);
    }

    .lead-reasons {
      margin: 0;
      padding: 0 0 0 20px;
      display: grid;
      gap: 8px;
      color: var(--text);
      font-size: 0.96rem;
      line-height: 1.7;
    }

    .lead-reasons li {
      overflow-wrap: anywhere;
    }

    .hero-note {
      display: grid;
      gap: 8px;
      padding: 14px 15px;
      border-radius: 18px;
      border: 1px solid rgba(79, 163, 255, 0.16);
      background: rgba(79, 163, 255, 0.08);
      color: var(--muted-strong);
      font-size: 0.93rem;
      line-height: 1.7;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
      color: var(--muted-strong);
      font-size: 0.78rem;
      white-space: nowrap;
    }

    .pill strong {
      color: var(--text);
      font-weight: 700;
    }

    .home-actions {
      display: grid;
      gap: 10px;
    }

    .home-button {
      min-height: 64px;
      padding: 12px 14px;
      display: grid;
      gap: 4px;
      text-align: left;
      border-radius: 18px;
      border: 1px solid rgba(79, 163, 255, 0.22);
      background: linear-gradient(180deg, rgba(79, 163, 255, 0.96), rgba(32, 105, 204, 0.96));
      color: white;
      cursor: pointer;
      box-shadow: 0 16px 28px rgba(19, 67, 139, 0.34);
      transition: transform 140ms ease, filter 140ms ease, box-shadow 140ms ease;
    }

    .home-button:hover,
    .home-button:focus-visible,
    .scenario-button:hover,
    .scenario-button:focus-visible,
    .bottom-button:hover,
    .bottom-button:focus-visible,
    .copy-button:hover,
    .copy-button:focus-visible,
    .chip-link:hover,
    .chip-link:focus-visible {
      transform: translateY(-1px);
      filter: brightness(1.03);
    }

    .home-button.active {
      border-color: rgba(255, 255, 255, 0.35);
      box-shadow: 0 0 0 4px rgba(79, 163, 255, 0.12), 0 16px 28px rgba(19, 67, 139, 0.34);
    }

    .home-button .title {
      font-size: 1.02rem;
      font-weight: 800;
      letter-spacing: 0.01em;
    }

    .home-button .sub {
      font-size: 0.84rem;
      color: rgba(255, 255, 255, 0.86);
      line-height: 1.4;
    }

    .main-section {
      margin-top: 16px;
      display: grid;
      gap: 12px;
    }

    .section-head {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 12px;
      padding: 2px 2px 0;
    }

    .section-head h3 {
      margin: 0;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 1rem;
      letter-spacing: 0.04em;
    }

    .section-head p {
      margin: 0;
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.5;
      text-align: right;
    }

    .result-card,
    .detail-card {
      display: grid;
      gap: 14px;
      padding: 18px;
      border-radius: 22px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }

    .result-card {
      border-color: rgba(79, 163, 255, 0.18);
    }

    .result-card.review { border-color: rgba(243, 196, 79, 0.26); }
    .result-card.warn { border-color: rgba(246, 109, 109, 0.24); }
    .result-card.danger { border-color: rgba(246, 109, 109, 0.38); }
    .result-card.ok { border-color: rgba(94, 208, 154, 0.24); }

    .result-top {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 12px;
    }

    .result-chip {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.01em;
      white-space: nowrap;
    }

    .result-chip.ok {
      background: var(--success-soft);
      color: #aaf0cf;
      border: 1px solid rgba(94, 208, 154, 0.24);
    }

    .result-chip.review {
      background: var(--warn-soft);
      color: #ffe29b;
      border: 1px solid rgba(243, 196, 79, 0.24);
    }

    .result-chip.warn {
      background: rgba(247, 154, 72, 0.16);
      color: #ffc9a5;
      border: 1px solid rgba(246, 109, 109, 0.16);
    }

    .result-chip.danger {
      background: var(--danger-soft);
      color: #ffb8b8;
      border: 1px solid rgba(246, 109, 109, 0.34);
    }

    .result-kind {
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.4;
      text-align: right;
    }

    .result-card h4 {
      margin: 0;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: clamp(1.55rem, 7vw, 2rem);
      line-height: 1.08;
      letter-spacing: -0.03em;
      text-wrap: balance;
    }

    .result-conclusion {
      display: grid;
      gap: 10px;
      padding: 4px 0 2px;
    }

    .result-conclusion h4 {
      font-size: clamp(1.72rem, 7vw, 2.1rem);
    }

    .result-meta {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      flex-wrap: wrap;
    }

    .risk-pill {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(243, 196, 79, 0.22);
      background: rgba(243, 196, 79, 0.1);
      color: #ffe29b;
      font-size: 0.8rem;
      font-weight: 800;
      letter-spacing: 0.04em;
    }

    .recommend-pill {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(79, 163, 255, 0.22);
      background: rgba(79, 163, 255, 0.1);
      color: #d8ebff;
      font-size: 0.8rem;
      font-weight: 700;
      line-height: 1.3;
    }

    .result-summary {
      margin: 0;
      color: var(--muted-strong);
      font-size: 0.98rem;
      line-height: 1.8;
      text-wrap: pretty;
    }

    .action-card {
      display: grid;
      gap: 10px;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid rgba(79, 163, 255, 0.18);
      background: rgba(79, 163, 255, 0.08);
    }

    .section-label {
      margin: 0;
      color: var(--muted);
      font-size: 0.75rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }

    .check-list {
      margin: 0;
      padding: 0 0 0 20px;
      display: grid;
      gap: 8px;
      color: var(--text);
      font-size: 0.96rem;
      line-height: 1.7;
    }

    .check-list li {
      overflow-wrap: anywhere;
    }

    .reason-list {
      margin: 0;
      padding: 0 0 0 20px;
      display: grid;
      gap: 8px;
      color: var(--text);
      font-size: 0.96rem;
      line-height: 1.7;
    }

    .reason-list li {
      overflow-wrap: anywhere;
    }

    .detail-title {
      margin: 0;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 0.98rem;
      letter-spacing: 0.03em;
    }

    .copy-shell {
      display: grid;
      gap: 12px;
    }

    .copy-text {
      margin: 0;
      padding: 14px 15px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
      font-size: 0.98rem;
      line-height: 1.9;
      white-space: pre-line;
    }

    .copy-button,
    .chip-link,
    .bottom-button {
      min-height: 44px;
      border-radius: 14px;
      border: 1px solid rgba(79, 163, 255, 0.22);
      background: rgba(79, 163, 255, 0.14);
      color: #d8ebff;
      cursor: pointer;
      transition: transform 140ms ease, filter 140ms ease, background 140ms ease;
    }

    .copy-button {
      padding: 0 14px;
      font-weight: 700;
    }

    .chip-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0 14px;
      text-decoration: none;
      font-size: 0.88rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .button-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .info-list {
      display: grid;
      gap: 10px;
    }

    .info-item {
      display: grid;
      gap: 6px;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
    }

    .info-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }

    .info-category {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid rgba(148, 163, 184, 0.22);
      background: rgba(255, 255, 255, 0.03);
      color: var(--muted-strong);
      font-size: 0.75rem;
    }

    .info-item h5 {
      margin: 0;
      font-size: 0.95rem;
      line-height: 1.6;
    }

    .info-item p {
      margin: 0;
      color: var(--muted);
      font-size: 0.85rem;
      line-height: 1.7;
    }

    .notice-card {
      display: grid;
      gap: 10px;
      padding: 14px 15px;
      border-radius: 18px;
      border: 1px solid rgba(246, 109, 109, 0.22);
      background: rgba(246, 109, 109, 0.08);
    }

    .notice-card strong {
      font-size: 1rem;
    }

    .notice-card p {
      margin: 0;
      color: var(--muted-strong);
      font-size: 0.92rem;
      line-height: 1.75;
    }

    .notice-card.prominent {
      border-color: rgba(246, 109, 109, 0.42);
      background: rgba(246, 109, 109, 0.14);
    }

    .muted-text {
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.75;
    }

    .key-value-list {
      display: grid;
      gap: 10px;
    }

    .key-value {
      display: grid;
      gap: 4px;
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
    }

    .key-value .key {
      color: var(--muted);
      font-size: 0.74rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .key-value .value {
      color: var(--text);
      font-size: 0.94rem;
      line-height: 1.7;
      overflow-wrap: anywhere;
    }

    .bottom-bar {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      z-index: 20;
      padding: 10px 12px calc(env(safe-area-inset-bottom) + 12px);
      background: linear-gradient(180deg, rgba(4, 8, 13, 0.08), rgba(4, 8, 13, 0.94) 28%, rgba(4, 8, 13, 0.98));
      backdrop-filter: blur(16px);
      border-top: 1px solid rgba(148, 163, 184, 0.16);
    }

    .bottom-inner {
      width: min(100%, 430px);
      margin: 0 auto;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .bottom-button {
      padding: 0 10px;
      text-align: center;
      font-weight: 800;
      font-size: 0.84rem;
      line-height: 1.2;
      color: white;
      background: linear-gradient(180deg, rgba(79, 163, 255, 0.96), rgba(32, 105, 204, 0.96));
      box-shadow: 0 12px 22px rgba(19, 67, 139, 0.32);
    }

    .bottom-button.secondary {
      border-color: rgba(148, 163, 184, 0.2);
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      box-shadow: 0 10px 18px rgba(2, 6, 23, 0.18);
    }

    .bottom-button.warn {
      border-color: rgba(246, 109, 109, 0.28);
      background: linear-gradient(180deg, rgba(246, 109, 109, 0.92), rgba(176, 38, 38, 0.92));
      box-shadow: 0 12px 22px rgba(139, 19, 38, 0.2);
    }

    .toast {
      position: fixed;
      left: 50%;
      top: 16px;
      z-index: 30;
      max-width: calc(100vw - 32px);
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(10, 16, 24, 0.96);
      border: 1px solid rgba(148, 163, 184, 0.18);
      color: var(--text);
      box-shadow: var(--shadow);
      transform: translate(-50%, -8px);
      opacity: 0;
      transition: opacity 180ms ease, transform 180ms ease;
      pointer-events: none;
      font-size: 0.88rem;
      line-height: 1.5;
    }

    .toast.show {
      opacity: 1;
      transform: translate(-50%, 0);
    }

    .hidden { display: none !important; }

    @media (min-width: 700px) {
      .page {
        padding-top: 22px;
        padding-bottom: 132px;
      }
    }
  </style>
</head>
<body>
  <main class="page">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">SC</div>
        <div class="brand-copy">
          <p class="eyebrow">mobile flow</p>
          <h1>{{ app_name }}</h1>
        </div>
      </div>
      <a class="ghost-link" href="/dashboard">ダッシュボード</a>
    </header>

    {% if preview_mode %}
    <section class="card scenario-card" aria-label="診断シナリオ">
      <p class="section-label">レビュー用シナリオ</p>
      <p class="scenario-note">目視レビューしやすいように、即決を避ける代表シナリオを切り替えられます。</p>
      <div class="scenario-grid" id="scenarioButtons" role="tablist" aria-label="診断シナリオの切り替え">
        {% for scenario in preview_scenarios %}
        <button
          type="button"
          class="scenario-button {{ scenario.tone }}{% if scenario.key == active_preview_scenario_key %} active{% endif %}"
          data-scenario="{{ scenario.key }}"
          aria-pressed="{% if scenario.key == active_preview_scenario_key %}true{% else %}false{% endif %}"
        >
          <span class="scenario-title">{{ scenario.label }}</span>
          <span class="scenario-verdict">{{ scenario.verdict }}</span>
        </button>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    <section class="card lead-card" aria-label="結論カード">
      <div class="lead-top">
        <div class="lead-stack">
          <p class="section-label">結論</p>
          <div class="pill">Home <strong id="leadModeText">1分で確認できます</strong></div>
        </div>
        <span class="lead-risk" id="leadRisk">危険度 中</span>
      </div>
      <h2 class="lead-headline" id="leadHeadline">このまま売るのは少し待ってください</h2>
      <p class="lead-copy" id="leadCopy">売る前に確認したいポイントを整理しました。契約前に条件を見て、家族と比べながら進められます。</p>
      <div class="lead-meta">
        <span class="section-label">おすすめ行動</span>
        <strong id="leadRecommendation">契約せず、条件を紙で残してください</strong>
      </div>
      <ul class="lead-reasons" id="leadReasons">
        <li>今日中の即決を求められても、その場で決めない</li>
        <li>査定額の根拠や内訳を紙で確認する</li>
        <li>キャンセル条件と追加費用を見落とさない</li>
      </ul>
      <div class="hero-note">
        <span>家族に見せながら、落ち着いて比べやすい画面です。</span>
        <span>証拠になる写真や見積書は、あとから見返せる形で残してください。</span>
      </div>
      <div class="home-actions" id="homeActions" aria-label="主要ボタン">
        <button type="button" class="home-button active" data-select-type="flyer">
          <span class="title">チラシをチェック</span>
          <span class="sub">気になる文言と条件を先に確認する</span>
        </button>
        <button type="button" class="home-button" data-select-type="item">
          <span class="title">商品をチェック</span>
          <span class="sub">着物・ミシン・貴金属を比べて見る</span>
        </button>
        <button type="button" class="home-button" data-select-type="quote">
          <span class="title">見積もりをチェック</span>
          <span class="sub">追加料金やキャンセル条件を確認する</span>
        </button>
      </div>
    </section>

    <section class="main-section" id="resultSection" aria-label="診断結果画面">
      <div class="section-head">
        <h3>診断結果</h3>
        <p id="selectedLabel">チラシチェック</p>
      </div>

      <article class="result-card review" id="resultCard">
        <div class="muted-text">読み込み中です。</div>
      </article>

      <section class="detail-card" id="reasonCard">
        <h4 class="detail-title">理由</h4>
        <ul class="reason-list" id="reasonList">
          <li>読み込み中です。</li>
        </ul>
      </section>

      <section class="detail-card" id="refusalCard">
        <h4 class="detail-title">断り文例</h4>
        <div class="copy-shell">
          <p class="copy-text" id="refusalText">読み込み中です。</p>
          <div class="button-row">
            <button type="button" class="copy-button" id="copyRefusalButton">コピー</button>
          </div>
        </div>
      </section>

      <section class="detail-card" id="hotlineCard">
        <h4 class="detail-title">188相談案内</h4>
        <div class="notice-card" id="hotlineNoticeCard">
          <strong>不安なときは、消費者ホットライン188に相談できます</strong>
          <p id="hotlineText">読み込み中です。</p>
        </div>
      </section>

      <section class="detail-card" id="marketCard">
        <h4 class="detail-title">相場リンク</h4>
        <div class="button-row" id="marketLinks">
          <span class="muted-text">読み込み中です。</span>
        </div>
      </section>

      <section class="detail-card" id="officialCard">
        <h4 class="detail-title">公式情報の見出し</h4>
        <div class="info-list" id="officialList">
          <span class="muted-text">読み込み中です。</span>
        </div>
      </section>

      <section class="detail-card" id="inputCard">
        <h4 class="detail-title">入力内容</h4>
        <div class="key-value-list" id="inputList">
          <span class="muted-text">読み込み中です。</span>
        </div>
      </section>
    </section>
  </main>

  <div class="bottom-bar hidden" id="bottomBar" aria-label="下部固定アクション">
    <div class="bottom-inner">
      <button type="button" class="bottom-button" id="copyRefusalBottomButton">断り文例をコピー</button>
      <button type="button" class="bottom-button secondary" id="secondaryActionButton">家族に共有</button>
    </div>
  </div>

  <div class="toast" id="toast" role="status" aria-live="polite"></div>

  <script>
    const API_BASE = {{ api_prefix_json }};
    const INITIAL_TYPE = {{ selected_type_json }};
    const PREVIEW_SCENARIOS = {{ preview_scenarios_json }};
    const PREVIEW_DEFAULT_SCENARIO = {{ preview_default_scenario_json }};
    const INITIAL_PREVIEW_SCENARIO = {{ active_preview_scenario_json }};
    const TYPE_TO_SCENARIO = {{ type_to_scenario_json }};
    const TYPE_LABELS = {
      flyer: "チラシチェック",
      item: "商品チェック",
      quote: "見積もりチェック",
    };
    const DEFAULT_REFUSAL = "今日はこの場で決めず、家族と確認してから判断します。";
    const DEFAULT_HOTLINE = "不安なときは、消費者ホットライン188に相談できます。";
    const DEFAULT_DISCLAIMER = "相場や判定は参考です。法律判断や真贋の断定は行いません。";
    const LEAD_COPY_BY_TYPE = {
      flyer: {
        headline: "このまま売るのは少し待ってください",
        copy: "チラシの文言だけで決めず、条件と連絡先を先に整理しましょう。",
        recommendation: "出張費とキャンセル料を紙で残す",
        reasons: [
          "高価買取や即日現金化の文言を確認する",
          "業者名と電話番号を控える",
          "条件があいまいなら家族に見せる",
        ],
      },
      item: {
        headline: "型番と付属品がそろうまで、即決しないでください",
        copy: "着物・ミシン・貴金属は、相場と状態で見え方が変わります。",
        recommendation: "型番や刻印をそろえて複数査定",
        reasons: [
          "商品名や型番を写真で残す",
          "付属品や状態をそろえて見比べる",
          "相場が不明なら複数査定にする",
        ],
      },
      quote: {
        headline: "追加料金の条件がそろうまで、契約は待ってください",
        copy: "見積書の内訳やキャンセル条件を先に確認しましょう。",
        recommendation: "見積書と明細を紙かメールで残す",
        reasons: [
          "追加料金の条件を確認する",
          "キャンセル条件と家電リサイクル費を見る",
          "当日追加請求がないか書面で残す",
        ],
      },
    };
    const VERDICT_COPY_BY_TYPE = {
      flyer: {
        "問題なさそう": {
          headline: "今のところ大きな不安は見えません",
          copy: "必要な情報はそろっているため、条件を残して進めましょう。",
          recommendation: "条件を紙かメールで残して進める",
          reasons: [
            "条件を書面で残す",
            "不明点はその場で質問する",
            "迷ったら家族と見直す",
          ],
        },
        "確認推奨": {
          headline: "その場で進める前に、条件をもう一度確認してください",
          copy: "見えていない条件が残っているため、急がず比べるのが安全です。",
          recommendation: "条件を紙で確認してから進める",
          reasons: [
            "内訳や根拠を紙で残す",
            "不足している情報を埋める",
            "家族にも見てもらう",
          ],
        },
        "即決注意": {
          headline: "契約は急がず、複数で比べてください",
          copy: "その場で決める前に、相場と条件をもう一度並べましょう。",
          recommendation: "契約せず、複数査定で比べる",
          reasons: [
            "今日中の即決を求められても急がない",
            "相場の根拠を確認する",
            "家族と見比べてから判断する",
          ],
        },
        "相談推奨": {
          headline: "今日はこの場で決めず、家族と188で確認してください",
          copy: "不安が強いときは、いったん止めて相談するほうが安全です。",
          recommendation: "契約せず、家族と相談して188へ",
          reasons: [
            "追加条件やキャンセル条件を確認する",
            "証拠になる書面や写真を残す",
            "不安なときは188へ相談する",
          ],
        },
      },
      item: {
        "問題なさそう": {
          headline: "今のところ大きな不安は見えません",
          copy: "必要な付属品や状態が見えているなら、条件を残して進めましょう。",
          recommendation: "条件を紙かメールで残して進める",
          reasons: [
            "付属品と状態を紙で残す",
            "不明点はその場で質問する",
            "迷ったら家族と見直す",
          ],
        },
        "確認推奨": {
          headline: "その場で進める前に、型番と状態を確認してください",
          copy: "型番や付属品が見えにくいと、相場の判断がぶれやすくなります。",
          recommendation: "型番と付属品をそろえてから比べる",
          reasons: [
            "型番と付属品を写真で残す",
            "動作確認や状態を見直す",
            "家族に見せて複数査定で比べる",
          ],
        },
        "即決注意": {
          headline: "契約は急がず、複数で比べてください",
          copy: "型番や付属品が足りないまま進めると、相場が読みづらくなります。",
          recommendation: "契約せず、複数査定で比べる",
          reasons: [
            "今日中の即決を求められても急がない",
            "型番や付属品を確認する",
            "家族と見比べてから判断する",
          ],
        },
        "相談推奨": {
          headline: "今日はこの場で決めず、家族と188で確認してください",
          copy: "真贋や相場の見え方が弱いときは、いったん止めて相談するほうが安全です。",
          recommendation: "契約せず、家族と相談して188へ",
          reasons: [
            "真贋や相場の根拠を確認する",
            "証拠になる書面や写真を残す",
            "不安なときは188へ相談する",
          ],
        },
      },
      quote: {
        "問題なさそう": {
          headline: "今のところ大きな不安は見えません",
          copy: "内訳が明確なら、条件を残して進めましょう。",
          recommendation: "条件を紙かメールで残して進める",
          reasons: [
            "見積書と明細を残す",
            "不明点はその場で質問する",
            "迷ったら家族と見直す",
          ],
        },
        "確認推奨": {
          headline: "追加料金の条件を、先に確認してください",
          copy: "見積書の内訳やキャンセル条件が見えてから判断すると安心です。",
          recommendation: "見積書と明細を紙かメールで残す",
          reasons: [
            "追加料金の条件を確認する",
            "キャンセル条件と家電リサイクル費を見る",
            "見積書を持ち帰って比べる",
          ],
        },
        "即決注意": {
          headline: "契約は急がず、内訳をそろえて比べてください",
          copy: "当日追加請求や不明瞭な内訳があるなら、すぐ決めないほうが安全です。",
          recommendation: "契約せず、明細をそろえて比べる",
          reasons: [
            "当日追加請求の有無を確認する",
            "家電リサイクル費とキャンセル条件を見る",
            "見積書と明細を紙で残す",
          ],
        },
        "相談推奨": {
          headline: "今日はこの場で決めず、家族と188で確認してください",
          copy: "追加料金や条件の不明点が残るときは、いったん止めて相談するほうが安全です。",
          recommendation: "契約せず、家族と相談して188へ",
          reasons: [
            "追加条件やキャンセル条件を確認する",
            "見積書と明細を紙かメールで残す",
            "不安なときは188へ相談する",
          ],
        },
      },
    };
    const VERDICT_CLASS = {
      "問題なさそう": "ok",
      "確認推奨": "review",
      "即決注意": "warn",
      "相談推奨": "danger",
    };

    const state = {
      selectedType: INITIAL_TYPE,
      checks: { flyer: null, item: null, quote: null },
      report: null,
      reportResponse: null,
      previewScenarioKey: INITIAL_PREVIEW_SCENARIO,
      previewMode: Boolean(INITIAL_PREVIEW_SCENARIO),
    };

    const homeButtons = Array.from(document.querySelectorAll("[data-select-type]"));
    const scenarioButtons = Array.from(document.querySelectorAll("[data-scenario]"));
    const resultSection = document.getElementById("resultSection");
    const resultCard = document.getElementById("resultCard");
    const reasonList = document.getElementById("reasonList");
    const leadModeText = document.getElementById("leadModeText");
    const leadRisk = document.getElementById("leadRisk");
    const leadHeadline = document.getElementById("leadHeadline");
    const leadCopy = document.getElementById("leadCopy");
    const leadRecommendation = document.getElementById("leadRecommendation");
    const leadReasons = document.getElementById("leadReasons");
    const refusalText = document.getElementById("refusalText");
    const hotlineText = document.getElementById("hotlineText");
    const hotlineNoticeCard = document.getElementById("hotlineNoticeCard");
    const marketLinks = document.getElementById("marketLinks");
    const officialList = document.getElementById("officialList");
    const inputList = document.getElementById("inputList");
    const selectedLabel = document.getElementById("selectedLabel");
    const bottomBar = document.getElementById("bottomBar");
    const secondaryActionButton = document.getElementById("secondaryActionButton");
    const toast = document.getElementById("toast");

    let toastTimer = null;

    function escapeHtml(value) {
      const htmlMap = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      };
      return String(value ?? "").replace(/[&<>"']/g, (char) => htmlMap[char] || char);
    }

    function latest(list) {
      return Array.isArray(list) && list.length ? list[0] : null;
    }

    function showToast(message) {
      toast.textContent = message;
      toast.classList.add("show");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast.classList.remove("show"), 1800);
    }

    function formatMoney(value) {
      if (value === null || value === undefined || value === "") return "未入力";
      const numeric = Number(value);
      if (Number.isNaN(numeric)) return String(value);
      return `${new Intl.NumberFormat("ja-JP").format(numeric)}円`;
    }

    function scrollToSection(id) {
      const element = document.getElementById(id);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }

    function riskLabelFromVerdict(verdict) {
      return {
        "問題なさそう": "低",
        "確認推奨": "中",
        "即決注意": "中",
        "相談推奨": "高",
      }[verdict] || "中";
    }

    function firstSentence(value) {
      const text = String(value ?? "").trim();
      if (!text) {
        return "";
      }
      const sentence = text.split(/[。！？]/)[0].trim();
      return sentence || text;
    }

    function dedupeTexts(values) {
      return Array.from(new Set((values || []).map((value) => String(value).trim()).filter(Boolean)));
    }

    function currentTemplate() {
      const previewScenario = state.previewScenarioKey ? PREVIEW_SCENARIOS[state.previewScenarioKey] : null;
      if (previewScenario) {
        return {
          headline: previewScenario.lead_headline || "このまま売るのは少し待ってください",
          copy: previewScenario.lead_copy || "売る前に確認したいポイントを整理しました。",
          recommendation: previewScenario.lead_recommendation || "契約せず、条件を紙で残してください",
          reasons: Array.isArray(previewScenario.lead_reasons) ? previewScenario.lead_reasons.slice(0, 3) : [],
        };
      }

      const verdict = state.report?.judgement || "";
      const verdictTemplate = (VERDICT_COPY_BY_TYPE[state.selectedType] || {})[verdict];
      if (verdictTemplate) {
        return {
          headline: verdictTemplate.headline,
          copy: verdictTemplate.copy,
          recommendation: verdictTemplate.recommendation,
          reasons: Array.isArray(verdictTemplate.reasons) ? verdictTemplate.reasons.slice(0, 3) : [],
        };
      }

      const typeTemplate = LEAD_COPY_BY_TYPE[state.selectedType] || LEAD_COPY_BY_TYPE.flyer;
      return {
        headline: typeTemplate.headline,
        copy: typeTemplate.copy,
        recommendation: typeTemplate.recommendation,
        reasons: Array.isArray(typeTemplate.reasons) ? typeTemplate.reasons.slice(0, 3) : [],
      };
    }

    function leadModeLabel() {
      if (state.previewScenarioKey) {
        return "レビュー用シナリオ";
      }
      return hasLiveData() ? "最新の診断" : "本番想定のライブ表示";
    }

    function renderLeadCard() {
      const template = currentTemplate();
      const verdict = state.report?.judgement || (state.previewScenarioKey ? PREVIEW_SCENARIOS[state.previewScenarioKey]?.verdict : "") || "";
      const risk = (state.report || state.previewScenarioKey) ? riskLabelFromVerdict(verdict || "確認推奨") : "中";
      leadModeText.textContent = leadModeLabel();
      leadRisk.textContent = `危険度 ${risk}`;
      leadHeadline.textContent = template.headline;
      leadCopy.textContent = template.copy;
      leadRecommendation.textContent = template.recommendation;
      const reasons = template.reasons.length ? template.reasons : (LEAD_COPY_BY_TYPE[state.selectedType] || LEAD_COPY_BY_TYPE.flyer).reasons;
      leadReasons.innerHTML = reasons.slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    }

    function updateSecondaryAction() {
      const verdict = state.report?.judgement || (state.previewScenarioKey ? PREVIEW_SCENARIOS[state.previewScenarioKey]?.verdict : "") || "";
      if (verdict === "相談推奨") {
        secondaryActionButton.textContent = "188を見る";
        secondaryActionButton.classList.remove("secondary");
        secondaryActionButton.classList.add("warn");
        secondaryActionButton.dataset.action = "hotline";
        return;
      }
      secondaryActionButton.textContent = "家族に共有";
      secondaryActionButton.classList.add("secondary");
      secondaryActionButton.classList.remove("warn");
      secondaryActionButton.dataset.action = "share";
    }

    function setActiveButtons() {
      homeButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.selectType === state.selectedType);
      });
      const activeScenarioKey = state.previewScenarioKey || (state.previewMode ? PREVIEW_DEFAULT_SCENARIO : null);
      scenarioButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.scenario === activeScenarioKey);
        button.setAttribute("aria-pressed", button.dataset.scenario === activeScenarioKey ? "true" : "false");
      });
      const scenario = state.previewScenarioKey ? PREVIEW_SCENARIOS[state.previewScenarioKey] : null;
      const confidence = state.report?.confidence || {};
      const confidenceScore = Number(confidence.score ?? 0);
      const confidenceLabel = confidence.label || "";
      if (scenario) {
        selectedLabel.textContent = `${scenario.label} · ${TYPE_LABELS[state.selectedType] || "チェック"} / 信頼度 ${confidenceScore}${confidenceLabel ? ` / ${confidenceLabel}` : ""}`;
      } else if (hasLiveData() && state.report) {
        selectedLabel.textContent = `${TYPE_LABELS[state.selectedType] || "チェック"} · 信頼度 ${confidenceScore}${confidenceLabel ? ` / ${confidenceLabel}` : ""}`;
      } else {
        selectedLabel.textContent = `本番想定のライブ表示 · ${TYPE_LABELS[state.selectedType] || "チェック"}`;
      }
      renderLeadCard();
      updateSecondaryAction();
    }

    function buildDetailReasonItems() {
      const previewScenario = state.previewScenarioKey ? PREVIEW_SCENARIOS[state.previewScenarioKey] : null;
      if (previewScenario && Array.isArray(previewScenario.lead_reasons) && previewScenario.lead_reasons.length) {
        return previewScenario.lead_reasons.slice(0, 3);
      }

      const check = state.checks[state.selectedType];
      const report = state.report || {};
      if (!check) {
        return [
          "Home の3つから選ぶと、判定と断り文例が出ます。",
          "写真や見積書を見ながら、落ち着いて比べてください。",
          "迷ったら家族に見せてから判断してください。",
        ];
      }

      const category = String(check.item_category || "");
      if (state.selectedType === "quote" || category === "不用品回収対象品") {
        return [
          "追加料金の条件があいまい",
          "キャンセル条件と家電リサイクル費を確認する",
          "見積書と明細を紙かメールで残す",
        ];
      }
      if (state.selectedType === "item" && category === "貴金属") {
        return [
          "即決を求められても、その場で売らない",
          "相場の根拠が見えにくいので複数査定で比べる",
          "刻印・重量・鑑定書を写真で残す",
        ];
      }
      if (state.selectedType === "item" && category === "ミシン") {
        return [
          "型番と付属品を確認する",
          "動作確認や試し縫いを見直す",
          "複数査定で比べる",
        ];
      }
      if (state.selectedType === "item" && category === "着物") {
        return [
          "証紙・落款・作家名を確認する",
          "保管状態とシミ・カビを写真で残す",
          "家族と見比べてから判断する",
        ];
      }
      if (state.selectedType === "flyer") {
        return [
          "高価買取や即日現金化の文言を確認する",
          "出張費とキャンセル料を確認する",
          "業者名と電話番号を控える",
        ];
      }

      const detailReasons = [];
      const reason = firstSentence(report.reason);
      if (reason) {
        detailReasons.push(reason);
      }
      const missingInfo = Array.isArray(report.missing_info) ? report.missing_info : [];
      missingInfo.slice(0, 2).forEach((item) => detailReasons.push(`${item}の確認が必要`));
      const nextActions = Array.isArray(report.next_actions) ? report.next_actions : [];
      nextActions.slice(0, 1).forEach((item) => detailReasons.push(item));
      return dedupeTexts(detailReasons).slice(0, 3);
    }

    function hasLiveData() {
      return Boolean(state.checks.flyer || state.checks.item || state.checks.quote);
    }

    function getScenarioByKey(key) {
      return PREVIEW_SCENARIOS[key] || PREVIEW_SCENARIOS[PREVIEW_DEFAULT_SCENARIO];
    }

    function syncScenarioQuery(key) {
      const url = new URL(window.location.href);
      if (key) {
        url.searchParams.set("scenario", key);
      } else {
        url.searchParams.delete("scenario");
      }
      window.history.replaceState({}, "", url);
    }

    function applyPreviewScenario(key, { scroll = false, updateUrl = true } = {}) {
      const scenario = getScenarioByKey(key);
      if (!scenario) return;
      state.previewMode = true;
      state.previewScenarioKey = scenario.key;
      state.selectedType = scenario.type;
      state.checks = { flyer: null, item: null, quote: null };
      state.checks[scenario.type] = scenario.check;
      state.report = scenario.report;
      state.reportResponse = { content_json: scenario.report, summary_text: scenario.summary };
      setActiveButtons();
      renderHome();
      renderResult();
      if (updateUrl) {
        syncScenarioQuery(scenario.key);
      }
      if (scroll) {
        scrollToSection("resultSection");
      }
    }

    function marketLinksHtml(links) {
      const entries = Object.entries(links || {});
      if (!entries.length) {
        return '<span class="muted-text">相場リンクはまだありません。</span>';
      }
      return entries.map(([label, url]) => `
        <a class="chip-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>
      `).join("");
    }

    function officialInfosHtml(infos) {
      const list = Array.isArray(infos) ? infos : [];
      if (!list.length) {
        return '<div class="muted-text">公式情報はまだありません。</div>';
      }
      return list.slice(0, 3).map((info) => `
        <div class="info-item">
          <div class="info-top">
            <span class="info-category">${escapeHtml(info.category || "official")}</span>
            <span class="pill">${escapeHtml((info.reference_links || []).length ? "リンクあり" : "参照のみ")}</span>
          </div>
          <h5>${escapeHtml(info.title || "")}</h5>
          <p>${escapeHtml(info.summary || "")}</p>
        </div>
      `).join("");
    }

    function inputDetailsHtml(type, check) {
      if (!check) {
        return '<div class="muted-text">まだ入力がありません。Homeの3つから始められます。</div>';
      }
      const rows = [];
      if (type === "flyer") {
        rows.push(["業者名", check.company_name || "未入力"]);
        rows.push(["電話番号", check.phone_number || "未入力"]);
        rows.push(["チラシ文言", check.flyer_text || "未入力"]);
        rows.push(["出張費", check.outcall_fee_text || "未入力"]);
        rows.push(["キャンセル料", check.cancellation_fee_text || "未入力"]);
        rows.push(["高価買取", check.high_price_text || "未入力"]);
        rows.push(["即日現金化", check.same_day_cash_text || "未入力"]);
        rows.push(["誘導文言", check.inducement_text || "未入力"]);
      } else if (type === "item") {
        rows.push(["商品カテゴリ", check.item_category || "未入力"]);
        rows.push(["商品名", check.item_name || "未入力"]);
        rows.push(["ブランド", check.brand || "未入力"]);
        rows.push(["型番", check.model_number || "不明"]);
        rows.push(["状態", check.condition_note || "未入力"]);
        rows.push(["付属品", check.accessories || "未入力"]);
        rows.push(["業者提示額", formatMoney(check.offered_price)]);
        rows.push(["相場メモ", check.market_memo || "未入力"]);
        rows.push(["確認ポイント", check.check_points_text || "未入力"]);
      } else {
        rows.push(["業者提示額", formatMoney(check.offered_price)]);
        rows.push(["作業費", formatMoney(check.work_fee)]);
        rows.push(["処分費", formatMoney(check.disposal_fee)]);
        rows.push(["出張費", formatMoney(check.outcall_fee)]);
        rows.push(["査定料", formatMoney(check.appraisal_fee)]);
        rows.push(["キャンセル料", formatMoney(check.cancellation_fee)]);
        rows.push(["家電リサイクル料金", check.home_appliance_recycling_fee || "未入力"]);
        rows.push(["追加料金条件", check.additional_charge_conditions || "未入力"]);
        rows.push(["パック料金", formatMoney(check.package_price)]);
        rows.push(["当日追加請求", formatMoney(check.same_day_extra_charge)]);
        rows.push(["見積書・明細", check.estimate_sheet_present ? "あり" : "なし"]);
      }
      return rows.map(([key, value]) => `
        <div class="key-value">
          <div class="key">${escapeHtml(key)}</div>
          <div class="value">${escapeHtml(value)}</div>
        </div>
      `).join("");
    }

    async function fetchJson(path) {
      const response = await fetch(`${API_BASE}${path}`);
      if (!response.ok) {
        throw new Error(`${path} (${response.status})`);
      }
      return response.json();
    }

    async function loadChecks() {
      const [flyers, items, quotes] = await Promise.all([
        fetchJson("/flyer-checks").catch(() => []),
        fetchJson("/item-checks").catch(() => []),
        fetchJson("/quote-checks").catch(() => []),
      ]);

      state.checks.flyer = latest(flyers);
      state.checks.item = latest(items);
      state.checks.quote = latest(quotes);
    }

    function chooseInitialType() {
      const hasSelected = Boolean(state.checks[state.selectedType]);
      if (hasSelected) {
        return state.selectedType;
      }
      return ["quote", "item", "flyer"].find((type) => Boolean(state.checks[type])) || "flyer";
    }

    async function loadReportForSelected() {
      const check = state.checks[state.selectedType];
      if (!check) {
        state.report = null;
        state.reportResponse = null;
        return;
      }
      const response = await fetchJson(`/reports/${state.selectedType}/${check.id}`);
      state.reportResponse = response;
      state.report = response.content_json || null;
    }

    function renderHome() {
      setActiveButtons();
    }

    function renderResult() {
      const check = state.checks[state.selectedType];
      const report = state.report || {};
      const previewScenario = state.previewScenarioKey ? PREVIEW_SCENARIOS[state.previewScenarioKey] : null;
      const verdict = report.judgement || "確認推奨";
      const tone = VERDICT_CLASS[verdict] || "review";
      const nextActions = Array.isArray(report.next_actions) ? report.next_actions : [];
      const reasonItems = buildDetailReasonItems();
      const refusal = report.refusal_phrase || DEFAULT_REFUSAL;
      const hotline = report.hotline_notice || DEFAULT_HOTLINE;
      const disclaimer = report.disclaimer || DEFAULT_DISCLAIMER;
      const marketLinkData = report.market_links || {};
      const officialInfos = Array.isArray(report.official_infos) ? report.official_infos : [];
      const confidence = report.confidence || {};
      const confidenceScore = Number(confidence.score ?? 0);
      const confidenceLabel = confidence.label || "unknown";
      const template = currentTemplate();
      const risk = (state.report || state.previewScenarioKey) ? riskLabelFromVerdict(verdict || "確認推奨") : "中";
      const summary = previewScenario
        ? `${previewScenario.label} · レビュー用シナリオ`
        : check
          ? `${TYPE_LABELS[state.selectedType] || state.selectedType} · ${check.company_name || check.item_name || check.item_category || check.model_number || "最新のチェック"}`
          : "まだ診断がありません。";

      if (!check) {
        resultCard.className = "result-card review";
        resultCard.innerHTML = `
          <div class="result-top">
            <span class="result-chip review">未選択</span>
            <span class="result-kind">${escapeHtml(TYPE_LABELS[state.selectedType] || "チェック")}</span>
          </div>
          <div class="result-conclusion">
            <p class="section-label">見方</p>
            <h4>Home の3つから選ぶと、判定と断り文例が出ます。</h4>
            <p class="result-summary">ここに判定・理由・断り文例・188案内が並びます。</p>
            <div class="result-meta">
              <span class="risk-pill">危険度 中</span>
              <span class="recommend-pill">まずは写真や見積書を整理する</span>
            </div>
          </div>
          <div class="action-card">
            <p class="section-label">今やること</p>
            <ul class="check-list">
              <li>Home の「チラシをチェック」「商品をチェック」「見積もりをチェック」から始める</li>
              <li>分からないところは空欄のままで進める</li>
              <li>迷ったら家族に見せてから判断する</li>
            </ul>
          </div>
          <p class="result-summary">写真や見積書を見ながら、落ち着いて順番に確認できます。</p>
        `;
        reasonList.innerHTML = `
          <li>まずは Home の3つから選んでください。</li>
          <li>写真や見積書を見ながら、落ち着いて比べてください。</li>
          <li>迷ったら家族に見せてから判断してください。</li>
        `;
        refusalText.textContent = DEFAULT_REFUSAL;
        hotlineText.textContent = DEFAULT_HOTLINE;
        hotlineNoticeCard.className = "notice-card";
        marketLinks.innerHTML = '<span class="muted-text">相場リンクはまだありません。</span>';
        officialList.innerHTML = '<div class="muted-text">公式情報はまだありません。</div>';
        inputList.innerHTML = '<div class="muted-text">入力内容はまだありません。</div>';
        bottomBar.classList.add("hidden");
        return;
      }

      const resultClass = tone === "ok" ? "ok" : tone === "danger" ? "danger" : tone === "warn" ? "warn" : "review";
      resultCard.className = `result-card ${resultClass}`;
      resultCard.innerHTML = `
        <div class="result-top">
          <span class="result-chip ${tone}">${escapeHtml(verdict)}</span>
          <span class="result-kind">${escapeHtml(TYPE_LABELS[state.selectedType] || state.selectedType)}</span>
        </div>
        <div class="result-conclusion">
          <p class="section-label">結論</p>
          <h4>${escapeHtml(template.headline)}</h4>
          <p class="result-summary">${escapeHtml(template.copy)}</p>
          <div class="result-meta">
            <span class="risk-pill">危険度 ${escapeHtml(risk)}</span>
            <span class="recommend-pill">おすすめ行動: ${escapeHtml(template.recommendation)}</span>
          </div>
        </div>
        <div class="action-card">
          <p class="section-label">今やること</p>
          <ul class="check-list">
            ${
              nextActions.length
                ? nextActions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
                : [
                    "今日はその場で決めず、家族に見せてから判断する",
                    "見積書や明細は紙かメールで受け取る",
                    "写真や条件を残してから進める",
                  ].map((item) => `<li>${escapeHtml(item)}</li>`).join("")
            }
          </ul>
        </div>
        <p class="result-summary">${escapeHtml(summary)}</p>
      `;

      reasonList.innerHTML = reasonItems.length
        ? reasonItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
        : '<li>情報が足りないため、まずは追加確認をおすすめします。</li>';
      refusalText.textContent = refusal;
      hotlineText.textContent = hotline;
      hotlineNoticeCard.className = `notice-card${verdict === "相談推奨" ? " prominent" : ""}`;
      marketLinks.innerHTML = marketLinksHtml(marketLinkData);
      officialList.innerHTML = officialInfosHtml(officialInfos);
      inputList.innerHTML = inputDetailsHtml(state.selectedType, check);

      bottomBar.classList.remove("hidden");
      const copyButton = document.getElementById("copyRefusalButton");
      copyButton.disabled = !refusal;
      document.getElementById("copyRefusalBottomButton").disabled = !refusal;
      secondaryActionButton.disabled = false;

      if (verdict === "相談推奨") {
        document.getElementById("hotlineCard").scrollMarginTop = "88px";
      }
      updateSecondaryAction();
      selectedLabel.textContent = previewScenario
        ? `${previewScenario.label} · ${TYPE_LABELS[state.selectedType] || state.selectedType} / 信頼度 ${confidenceScore}${confidenceLabel ? ` / ${confidenceLabel}` : ""}`
        : `${TYPE_LABELS[state.selectedType] || state.selectedType} · 信頼度 ${confidenceScore}${confidenceLabel ? ` / ${confidenceLabel}` : ""}`;
    }

    function copyRefusalPhrase() {
      const text = refusalText.textContent.trim();
      if (!text) {
        showToast("コピーする断り文例がありません");
        return;
      }
      navigator.clipboard.writeText(text)
        .then(() => showToast("断り文例をコピーしました"))
        .catch(() => showToast("コピーに失敗しました"));
    }

    function copyFamilyShareSummary() {
      const lines = [
        "売る前チェックAI",
        selectedLabel.textContent.trim(),
        `結論: ${leadHeadline.textContent.trim()}`,
        `おすすめ行動: ${leadRecommendation.textContent.trim()}`,
      ];
      const reasons = Array.from(leadReasons.querySelectorAll("li")).map((item) => item.textContent.trim()).filter(Boolean);
      if (reasons.length) {
        lines.push("理由:");
        reasons.slice(0, 3).forEach((item) => lines.push(`- ${item}`));
      }
      navigator.clipboard.writeText(lines.join("\\n"))
        .then(() => showToast("家族共有メモをコピーしました"))
        .catch(() => showToast("コピーに失敗しました"));
    }

    function handleSecondaryAction() {
      if (secondaryActionButton.dataset.action === "hotline") {
        scrollToSection("hotlineCard");
        return;
      }
      copyFamilyShareSummary();
    }

    async function refreshPreview({ scroll = false } = {}) {
      if (state.previewScenarioKey) {
        applyPreviewScenario(state.previewScenarioKey, { scroll, updateUrl: false });
        return;
      }
      await loadChecks();
      if (!hasLiveData()) {
        state.report = null;
        state.reportResponse = null;
        setActiveButtons();
        renderHome();
        renderResult();
        if (scroll) {
          scrollToSection("resultSection");
        }
        return;
      }
      state.selectedType = chooseInitialType();
      setActiveButtons();
      await loadReportForSelected();
      renderHome();
      renderResult();
      if (scroll) {
        scrollToSection("resultSection");
      }
    }

    homeButtons.forEach((button) => {
      button.addEventListener("click", async () => {
        const nextType = button.dataset.selectType;
        if (state.previewMode) {
          const scenarioKey = TYPE_TO_SCENARIO[nextType] || PREVIEW_DEFAULT_SCENARIO;
          applyPreviewScenario(scenarioKey, { scroll: true, updateUrl: true });
          return;
        }
        if (nextType === state.selectedType && state.report) {
          scrollToSection("resultSection");
          return;
        }
        state.selectedType = nextType;
        setActiveButtons();
        await loadReportForSelected();
        renderResult();
        scrollToSection("resultSection");
      });
    });

    scenarioButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const nextScenario = button.dataset.scenario;
        applyPreviewScenario(nextScenario, { scroll: true, updateUrl: true });
      });
    });

    document.getElementById("copyRefusalButton").addEventListener("click", copyRefusalPhrase);
    document.getElementById("copyRefusalBottomButton").addEventListener("click", copyRefusalPhrase);
    secondaryActionButton.addEventListener("click", handleSecondaryAction);

    refreshPreview();
  </script>
</body>
</html>
    """
)


def render_mobile_preview_html(
    settings: AppSettings,
    *,
    selected_type: str | None = None,
    scenario_key: str | None = None,
) -> str:
    allowed_types = {"flyer", "item", "quote"}
    safe_selected_type = selected_type if selected_type in allowed_types else "flyer"
    preview_scenarios = _build_preview_scenarios()
    preview_scenarios_by_key = {scenario["key"]: scenario for scenario in preview_scenarios}
    safe_scenario_key = scenario_key if scenario_key in preview_scenarios_by_key else None
    if safe_scenario_key:
        safe_selected_type = preview_scenarios_by_key[safe_scenario_key]["type"]
    active_preview_scenario_key = safe_scenario_key or PREVIEW_SCENARIO_DEFAULT
    return _MOBILE_PREVIEW_TEMPLATE.render(
        app_name=settings.app_name,
        api_prefix_json=json.dumps(settings.api_prefix),
        selected_type_json=json.dumps(safe_selected_type),
        preview_mode=bool(safe_scenario_key),
        preview_scenarios=preview_scenarios,
        preview_scenarios_json=json.dumps(preview_scenarios_by_key, ensure_ascii=False),
        preview_default_scenario_json=json.dumps(PREVIEW_SCENARIO_DEFAULT),
        active_preview_scenario_json=json.dumps(safe_scenario_key),
        type_to_scenario_json=json.dumps(PREVIEW_TYPE_TO_SCENARIO, ensure_ascii=False),
        active_preview_scenario_key=active_preview_scenario_key,
    )


def _build_screenshot_shell_html(
    target_url: str,
    *,
    device_label: str,
    scenario_label: str,
    shell_width: int,
    shell_height: int,
    screen_width: int,
    screen_height: int,
    device_class: str = "portrait",
) -> str:
    device_class_attr = f" {device_class}" if device_class else ""
    return f"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{escape(device_label)} · {escape(scenario_label)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg-1: #050b12;
      --bg-2: #0b1320;
      --text: #eef2f7;
      --muted: #94a3b8;
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at 18% 14%, rgba(79, 163, 255, 0.12), transparent 26%),
        radial-gradient(circle at 82% 18%, rgba(215, 166, 74, 0.12), transparent 24%),
        linear-gradient(180deg, var(--bg-1), var(--bg-2) 56%, #05080c 100%);
      font-family: "IBM Plex Sans JP", "Yu Gothic UI", "Segoe UI", sans-serif;
      display: grid;
      place-items: center;
      padding: 28px 20px 36px;
    }}

    .wrap {{
      width: min(100%, {shell_width + 120}px);
      display: grid;
      gap: 14px;
      justify-items: center;
    }}

    .caption {{
      width: {shell_width}px;
      max-width: 100%;
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 0.86rem;
      line-height: 1.5;
    }}

    .caption strong {{
      color: var(--text);
      font-size: 1rem;
      letter-spacing: 0.02em;
    }}

    .device {{
      position: relative;
      width: {shell_width}px;
      height: {shell_height}px;
      padding: 18px 18px 28px;
      border-radius: 44px;
      background: linear-gradient(180deg, rgba(15, 23, 35, 0.98), rgba(4, 8, 13, 0.98));
      border: 1px solid rgba(148, 163, 184, 0.16);
      box-shadow: 0 36px 120px rgba(0, 0, 0, 0.45);
      overflow: hidden;
    }}

    .device::before {{
      content: "";
      position: absolute;
      left: 50%;
      top: 10px;
      transform: translateX(-50%);
      width: {96 if device_class == "landscape" else 128}px;
      height: {14 if device_class == "landscape" else 20}px;
      border-radius: 0 0 16px 16px;
      background: rgba(2, 6, 23, 0.76);
      box-shadow: inset 0 -1px 0 rgba(255, 255, 255, 0.08);
    }}

    .screen {{
      width: {screen_width}px;
      height: {screen_height}px;
      margin: {18 if device_class == "landscape" else 22}px auto 0;
      border-radius: {28 if device_class == "landscape" else 34}px;
      overflow: hidden;
      background: #091018;
      border: 1px solid rgba(255, 255, 255, 0.06);
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.03);
    }}

    iframe {{
      width: 100%;
      height: 100%;
      border: 0;
      display: block;
      background: #091018;
    }}

    .home-indicator {{
      position: absolute;
      left: 50%;
      bottom: 10px;
      transform: translateX(-50%);
      width: {110 if device_class == "landscape" else 134}px;
      height: 5px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.62);
      opacity: 0.72;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="caption">
      <strong>{escape(device_label)}</strong>
      <span>{escape(scenario_label)}</span>
    </div>
    <div class="device{device_class_attr}">
      <div class="screen">
        <iframe id="previewFrame" src="{escape(target_url)}" title="{escape(device_label)} {escape(scenario_label)}"></iframe>
      </div>
      <div class="home-indicator"></div>
    </div>
  </div>
</body>
</html>
    """


def render_mobile_preview_frame_html(
    target_url: str,
    *,
    device_label: str = "iPhone縦",
    scenario_label: str = "実画面レビュー",
) -> str:
    layout = SCREENSHOT_LAYOUTS[0]
    return _build_screenshot_shell_html(
        target_url,
        device_label=device_label,
        scenario_label=scenario_label,
        shell_width=int(layout["shell_width"]),
        shell_height=int(layout["shell_height"]),
        screen_width=int(layout["screen_width"]),
        screen_height=int(layout["screen_height"]),
        device_class=str(layout.get("device_class") or "portrait"),
    )


def save_mobile_preview_screenshots(
    settings: AppSettings | None = None,
    *,
    output_dir: Path | None = None,
) -> list[Path]:
    if settings is None:
        from .config import load_settings

        settings = load_settings()
    screenshot_dir = _mobile_preview_screenshot_dir(output_dir)

    from .app import create_app

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - optional dependency guard
        raise RuntimeError("Playwright が必要です。`py -3 -m pip install -r requirements.txt` を実行してください。") from exc

    import uvicorn

    host = "127.0.0.1"
    port = _find_free_port(host)
    app = create_app(settings)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", loop="asyncio", lifespan="on")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # type: ignore[assignment]

    thread = Thread(target=server.run, daemon=True)
    thread.start()

    screenshot_paths: list[Path] = []
    try:
        base_url = f"http://{host}:{port}"
        _wait_for_http_ready(f"{base_url}/mobile-preview")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1600},
                device_scale_factor=1,
                color_scheme="dark",
                locale="ja-JP",
            )
            page = context.new_page()
            for target in _build_mobile_preview_screenshot_targets():
                target_url = f"{base_url}/mobile-preview"
                if target["scenario_key"]:
                    target_url = f"{target_url}?scenario={target['scenario_key']}"
                for layout in SCREENSHOT_LAYOUTS:
                    shell_html = _build_screenshot_shell_html(
                        target_url,
                        device_label=layout["label"],
                        scenario_label=target["label"],
                        shell_width=int(layout["shell_width"]),
                        shell_height=int(layout["shell_height"]),
                        screen_width=int(layout["screen_width"]),
                        screen_height=int(layout["screen_height"]),
                        device_class=str(layout.get("device_class") or "portrait"),
                    )
                    page.set_content(shell_html, wait_until="load")
                    frame_handle = page.query_selector("#previewFrame")
                    if frame_handle is None:
                        raise RuntimeError("preview iframe が見つかりません")
                    frame = frame_handle.content_frame()
                    if frame is None:
                        raise RuntimeError("preview iframe の読み込みに失敗しました")
                    frame.wait_for_selector("#leadHeadline")
                    if target["scenario_key"]:
                        frame.wait_for_selector("#bottomBar:not(.hidden)")
                        frame.evaluate(
                            """() => {
                                const target = document.getElementById("resultSection");
                                if (target) {
                                  target.scrollIntoView({ block: "start" });
                                }
                            }"""
                        )
                    page.wait_for_timeout(220)
                    output_path = screenshot_dir / f"mobile_preview_{layout['key']}_{target['key']}.png"
                    page.screenshot(path=str(output_path), full_page=True)
                    screenshot_paths.append(output_path)
            context.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=15)

    return screenshot_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="売る前チェックAI v0.1 mobile preview helper")
    parser.add_argument(
        "--save-screenshots",
        action="store_true",
        help="レビュー用の iPhone / Pixel / 横向きスクリーンショットを保存する",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="スクリーンショットの保存先を上書きする",
    )
    args = parser.parse_args(argv)

    if not args.save_screenshots:
        parser.print_help()
        return 0

    from .config import load_settings

    settings = load_settings()
    paths = save_mobile_preview_screenshots(settings, output_dir=args.output_dir)
    for path in paths:
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
