from __future__ import annotations

import json
from html import escape
from jinja2 import Template

from .config import AppSettings
from .services.common import (
    CONSUMER_DISCLAIMER,
    CONSUMER_HOTLINE_NOTICE,
    FLYER_ALERT_PHRASES,
    ITEM_CATEGORY_GUIDANCE,
)


_DEFAULT_REFUSAL = "今日はこの場で決めず、家族と確認してから判断します。"

_MVP_TEMPLATE = Template(
    """
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{{ app_name }} | {{ page_title }}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      color-scheme: light;
      --bg: #f4efe7;
      --bg-strong: #fbf7f2;
      --panel: rgba(255, 255, 255, 0.88);
      --panel-strong: rgba(255, 255, 255, 0.96);
      --line: rgba(61, 74, 92, 0.12);
      --line-strong: rgba(25, 35, 49, 0.2);
      --text: #17202b;
      --muted: #5f6d7d;
      --accent: #1f5ef2;
      --accent-strong: #1749bf;
      --accent-soft: rgba(31, 94, 242, 0.12);
      --warn: #d97706;
      --warn-soft: rgba(217, 119, 6, 0.14);
      --danger: #b42318;
      --danger-soft: rgba(180, 35, 24, 0.13);
      --ok: #0f9d58;
      --ok-soft: rgba(15, 157, 88, 0.13);
      --shadow: 0 22px 60px rgba(17, 24, 39, 0.08);
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
      font-family: "IBM Plex Sans JP", "Yu Gothic UI", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 15% 14%, rgba(31, 94, 242, 0.12), transparent 25%),
        radial-gradient(circle at 90% 2%, rgba(217, 119, 6, 0.10), transparent 22%),
        linear-gradient(180deg, #f8f3eb 0%, var(--bg) 100%);
    }

    a { color: inherit; }
    button, input, select, textarea { font: inherit; }

    .page {
      width: min(100%, 720px);
      margin: 0 auto;
      padding: 16px 16px 112px;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 4px 2px 16px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }

    .brand-mark {
      width: 46px;
      height: 46px;
      border-radius: 16px;
      display: grid;
      place-items: center;
      flex: 0 0 auto;
      background: linear-gradient(180deg, rgba(31, 94, 242, 0.96), rgba(23, 73, 191, 0.92));
      color: white;
      font-family: "Space Grotesk", sans-serif;
      font-weight: 700;
      letter-spacing: 0.08em;
      box-shadow: 0 18px 34px rgba(31, 94, 242, 0.18);
    }

    .brand-copy h1,
    .brand-copy p,
    .eyebrow,
    .page-title,
    .section-title,
    .card-title,
    .card-copy,
    .helper,
    .muted {
      margin: 0;
    }

    .brand-copy h1 {
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 1rem;
      letter-spacing: 0.03em;
      line-height: 1.35;
    }

    .brand-copy p {
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.5;
      margin-top: 2px;
    }

    .top-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.78);
      color: var(--text);
      text-decoration: none;
      font-size: 0.86rem;
      font-weight: 600;
      box-shadow: 0 10px 22px rgba(15, 23, 42, 0.04);
    }

    .hero,
    .section-card,
    .result-card,
    .stack-card,
    .notice-card,
    .copy-card {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
    }

    .hero {
      padding: 22px 18px 18px;
      overflow: hidden;
      position: relative;
    }

    .hero::after {
      content: "";
      position: absolute;
      inset: auto -20px -56px auto;
      width: 172px;
      height: 172px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(31, 94, 242, 0.13), rgba(31, 94, 242, 0.02) 64%, transparent 70%);
      pointer-events: none;
    }

    .eyebrow {
      color: var(--accent-strong);
      font-size: 0.75rem;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      margin-bottom: 8px;
      font-weight: 700;
    }

    .page-title {
      font-size: clamp(1.88rem, 4vw, 2.6rem);
      line-height: 1.18;
      letter-spacing: -0.03em;
      font-weight: 800;
      max-width: 12ch;
    }

    .hero-copy {
      margin-top: 12px;
      font-size: 1rem;
      line-height: 1.85;
      color: var(--text);
      max-width: 36ch;
    }

    .hero-subcopy {
      margin-top: 10px;
      font-size: 0.93rem;
      line-height: 1.75;
      color: var(--muted);
    }

    .hero-meta {
      display: grid;
      gap: 8px;
      margin-top: 14px;
    }

    .hero-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 36px;
      width: fit-content;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.64);
      color: var(--muted);
      font-size: 0.8rem;
    }

    .hero-pill strong { color: var(--text); }

    .home-grid {
      display: grid;
      gap: 12px;
      margin-top: 18px;
    }

    .home-button {
      display: grid;
      gap: 4px;
      width: 100%;
      min-height: 92px;
      padding: 16px 16px 15px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.92));
      color: var(--text);
      text-decoration: none;
      text-align: left;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
    }

    .home-button .title {
      font-size: 1.1rem;
      line-height: 1.3;
      font-weight: 800;
      letter-spacing: -0.02em;
    }

    .home-button .sub {
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.6;
    }

    .home-button.primary {
      background: linear-gradient(180deg, rgba(31, 94, 242, 0.11), rgba(255, 255, 255, 0.95));
      border-color: rgba(31, 94, 242, 0.18);
    }

    .home-note {
      margin-top: 16px;
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.72);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.75;
    }

    .section-card,
    .stack-card,
    .result-card,
    .notice-card,
    .copy-card {
      margin-top: 14px;
      padding: 18px;
    }

    .section-head,
    .card-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }

    .section-title,
    .card-title {
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 1.02rem;
      letter-spacing: 0.03em;
      line-height: 1.3;
      font-weight: 700;
    }

    .helper {
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.6;
    }

    .field-grid {
      display: grid;
      gap: 12px;
    }

    .field {
      display: grid;
      gap: 7px;
    }

    .field label {
      font-size: 0.9rem;
      font-weight: 600;
      line-height: 1.4;
    }

    .field input,
    .field select,
    .field textarea {
      width: 100%;
      border: 1px solid rgba(64, 76, 92, 0.18);
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.96);
      color: var(--text);
      min-height: 48px;
      padding: 12px 14px;
      outline: none;
      transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
    }

    .field textarea {
      min-height: 108px;
      resize: vertical;
      line-height: 1.7;
    }

    .field input:focus,
    .field select:focus,
    .field textarea:focus {
      border-color: rgba(31, 94, 242, 0.48);
      box-shadow: 0 0 0 4px rgba(31, 94, 242, 0.1);
    }

    .field small {
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.5;
    }

    .toggle-list {
      display: grid;
      gap: 10px;
      margin-top: 8px;
    }

    .toggle {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid rgba(64, 76, 92, 0.14);
      background: rgba(255, 255, 255, 0.74);
      line-height: 1.55;
      font-size: 0.92rem;
    }

    .toggle input {
      width: 18px;
      height: 18px;
      margin-top: 2px;
      flex: 0 0 auto;
    }

    .chip-list {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid rgba(64, 76, 92, 0.12);
      background: rgba(255, 255, 255, 0.8);
      color: var(--muted);
      font-size: 0.8rem;
      white-space: nowrap;
    }

    .chip strong {
      color: var(--text);
      margin-right: 6px;
    }

    .warning-band {
      margin-top: 12px;
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(217, 119, 6, 0.09);
      border: 1px solid rgba(217, 119, 6, 0.18);
      color: #8a5600;
      line-height: 1.7;
      font-size: 0.9rem;
    }

    .warning-band strong {
      display: block;
      margin-bottom: 4px;
      font-size: 0.92rem;
      color: #6c4300;
    }

    .guidance-list,
    .stack-list,
    .plain-list {
      margin: 0;
      padding-left: 18px;
      color: var(--text);
      line-height: 1.7;
    }

    .guidance-list li,
    .stack-list li,
    .plain-list li {
      margin: 6px 0;
    }

    .form-actions {
      display: grid;
      gap: 10px;
      margin-top: 16px;
    }

    .primary-button,
    .secondary-button,
    .link-button,
    .bottom-button,
    .copy-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 48px;
      width: 100%;
      padding: 0 14px;
      border-radius: 16px;
      border: 1px solid transparent;
      cursor: pointer;
      font-weight: 700;
      letter-spacing: 0.01em;
      text-decoration: none;
      transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease, border-color 120ms ease;
    }

    .primary-button,
    .bottom-button.primary {
      background: linear-gradient(180deg, var(--accent), var(--accent-strong));
      color: white;
      box-shadow: 0 14px 26px rgba(31, 94, 242, 0.18);
    }

    .secondary-button,
    .bottom-button.secondary {
      background: rgba(255, 255, 255, 0.92);
      color: var(--text);
      border-color: rgba(64, 76, 92, 0.14);
    }

    .primary-button:hover,
    .secondary-button:hover,
    .link-button:hover,
    .bottom-button:hover,
    .copy-button:hover {
      transform: translateY(-1px);
    }

    .section-stack {
      display: grid;
      gap: 14px;
    }

    .result-card {
      padding-bottom: 16px;
    }

    .result-badge-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }

    .result-chip {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 11px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 700;
      border: 1px solid transparent;
    }

    .result-chip.low { background: var(--ok-soft); color: #0b6d3c; border-color: rgba(15, 157, 88, 0.16); }
    .result-chip.medium { background: var(--warn-soft); color: #8a5600; border-color: rgba(217, 119, 6, 0.18); }
    .result-chip.high { background: var(--danger-soft); color: #8f2417; border-color: rgba(180, 35, 24, 0.18); }
    .result-chip.verdict { background: rgba(31, 94, 242, 0.12); color: var(--accent-strong); border-color: rgba(31, 94, 242, 0.16); }

    .result-headline {
      font-size: clamp(1.48rem, 4vw, 2rem);
      line-height: 1.25;
      letter-spacing: -0.02em;
      margin: 8px 0 8px;
      font-weight: 800;
    }

    .result-copy {
      font-size: 0.98rem;
      line-height: 1.82;
      color: var(--text);
      margin: 0;
    }

    .result-meta {
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }

    .meta-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .meta-pill {
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 11px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.82);
      border: 1px solid rgba(64, 76, 92, 0.12);
      color: var(--muted);
      font-size: 0.8rem;
    }

    .meta-pill strong {
      color: var(--text);
      margin-left: 6px;
    }

    .step-card {
      padding: 18px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background: var(--panel-strong);
      box-shadow: var(--shadow);
    }

    .step-card h3 {
      margin: 0 0 12px;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 1.02rem;
      letter-spacing: 0.02em;
    }

    .copy-card {
      background: var(--panel-strong);
    }

    .copy-row {
      display: grid;
      gap: 12px;
    }

    .copy-text {
      font-size: 0.97rem;
      line-height: 1.78;
      margin: 0;
      white-space: pre-wrap;
    }

    .copy-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .copy-button {
      width: auto;
      min-width: 104px;
      padding-inline: 16px;
      border-color: rgba(31, 94, 242, 0.16);
      background: rgba(31, 94, 242, 0.12);
      color: var(--accent-strong);
    }

    .copy-button.secondary {
      background: rgba(255, 255, 255, 0.84);
      color: var(--text);
      border-color: rgba(64, 76, 92, 0.14);
    }

    .link-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .link-pill {
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid rgba(31, 94, 242, 0.16);
      background: rgba(31, 94, 242, 0.08);
      color: var(--accent-strong);
      text-decoration: none;
      font-size: 0.84rem;
      font-weight: 700;
      line-height: 1.2;
    }

    .info-grid {
      display: grid;
      gap: 10px;
    }

    .info-card {
      padding: 14px 15px;
      border-radius: 18px;
      border: 1px solid rgba(64, 76, 92, 0.12);
      background: rgba(255, 255, 255, 0.85);
    }

    .info-top {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: flex-start;
      margin-bottom: 8px;
    }

    .info-category {
      font-size: 0.75rem;
      letter-spacing: 0.08em;
      color: var(--accent-strong);
      text-transform: uppercase;
      font-weight: 700;
    }

    .info-card h4 {
      margin: 0;
      font-size: 0.98rem;
      line-height: 1.5;
    }

    .info-card p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.7;
    }

    .notice-card.prominent {
      border-color: rgba(180, 35, 24, 0.2);
      background: rgba(180, 35, 24, 0.06);
    }

    .notice-card strong,
    .notice-card .notice-title {
      display: block;
      margin-bottom: 6px;
      font-size: 0.95rem;
      line-height: 1.5;
      font-weight: 800;
    }

    .notice-card p {
      margin: 0;
      color: var(--text);
      line-height: 1.75;
      font-size: 0.93rem;
    }

    .confidence-box {
      display: grid;
      gap: 12px;
    }

    .score-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }

    .score-track {
      position: relative;
      height: 12px;
      border-radius: 999px;
      background: rgba(64, 76, 92, 0.08);
      overflow: hidden;
    }

    .score-fill {
      position: absolute;
      inset: 0 auto 0 0;
      width: var(--score, 0%);
      border-radius: inherit;
      background: linear-gradient(90deg, rgba(31, 94, 242, 0.9), rgba(15, 157, 88, 0.9));
    }

    .toast {
      position: fixed;
      left: 50%;
      bottom: 18px;
      transform: translateX(-50%) translateY(8px);
      opacity: 0;
      z-index: 30;
      max-width: calc(100vw - 28px);
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(17, 24, 39, 0.95);
      color: white;
      font-size: 0.9rem;
      line-height: 1.55;
      box-shadow: 0 18px 48px rgba(15, 23, 42, 0.22);
      pointer-events: none;
      transition: opacity 180ms ease, transform 180ms ease;
    }

    .toast.show {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }

    .bottom-bar {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      z-index: 28;
      padding: 12px 12px max(12px, env(safe-area-inset-bottom));
      background: linear-gradient(180deg, rgba(244, 239, 231, 0.08), rgba(244, 239, 231, 0.96) 26%, rgba(244, 239, 231, 0.98));
      border-top: 1px solid rgba(64, 76, 92, 0.12);
      backdrop-filter: blur(12px);
    }

    .bottom-inner {
      width: min(100%, 720px);
      margin: 0 auto;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    .bottom-button {
      min-height: 48px;
      font-size: 0.84rem;
      padding: 0 10px;
      border-radius: 16px;
    }

    .bottom-button.warn {
      background: linear-gradient(180deg, rgba(180, 35, 24, 0.92), rgba(143, 28, 20, 0.96));
      color: white;
      box-shadow: 0 14px 26px rgba(180, 35, 24, 0.16);
    }

    .bottom-button.secondary {
      background: rgba(255, 255, 255, 0.88);
      color: var(--text);
      border-color: rgba(64, 76, 92, 0.14);
    }

    .empty-state {
      padding: 18px;
      border-radius: 16px;
      border: 1px dashed rgba(64, 76, 92, 0.2);
      background: rgba(255, 255, 255, 0.72);
      color: var(--muted);
      line-height: 1.75;
      font-size: 0.93rem;
    }

    .muted {
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.7;
    }

    .hidden { display: none !important; }

    @media (min-width: 720px) {
      .page {
        padding-top: 20px;
        padding-bottom: 120px;
      }

      .home-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }

      .field-grid.two-col {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (prefers-reduced-motion: reduce) {
      html { scroll-behavior: auto; }
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
      }
    }
  </style>
</head>
<body data-page="{{ page_key }}" data-check-type="{{ check_type or '' }}">
  <main class="page">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">SC</div>
        <div class="brand-copy">
          <h1>{{ app_name }}</h1>
          <p>{{ page_subtitle }}</p>
        </div>
      </div>
      <a class="top-link" href="{{ top_link_href }}">{{ top_link_label }}</a>
    </header>

    {{ body_html | safe }}
  </main>

  <div class="bottom-bar hidden" id="bottomBar" aria-label="下部固定アクション">
    <div class="bottom-inner">
    <button type="button" class="bottom-button primary" id="copyRefusalBottomButton">断り文例をコピー</button>
    <button type="button" class="bottom-button secondary" id="scrollMarketButton">相場リンクを見る</button>
    <button type="button" class="bottom-button secondary" id="scrollHotlineButton">188を見る</button>
    </div>
  </div>

  <div class="toast" id="toast" role="status" aria-live="polite"></div>

  <script>
    const API_BASE = {{ api_prefix_json }};
    const PAGE_KEY = {{ page_key_json }};
    const RESULT_ROUTE = {{ result_route_json }};
    const INITIAL_CHECK_TYPE = {{ check_type_json }};
    const INITIAL_CHECK_ID = {{ check_id_json }};
    const ITEM_GUIDANCE = {{ item_guidance_json }};
    const MARKET_LINK_LABELS = {{ market_link_labels_json }};
    const CHECK_TYPE_LABELS = {{ check_type_labels_json }};
    const RESULT_HEADLINES = {{ result_headlines_json }};
    const RESULT_RECOMMENDATIONS = {{ result_recommendations_json }};
    const DEFAULT_REFUSAL = {{ default_refusal_json }};
    const DEFAULT_HOTLINE = {{ default_hotline_json }};
    const DEFAULT_DISCLAIMER = {{ default_disclaimer_json }};

    const toast = document.getElementById("toast");
    const bottomBar = document.getElementById("bottomBar");
    const copyRefusalBottomButton = document.getElementById("copyRefusalBottomButton");
    const scrollMarketButton = document.getElementById("scrollMarketButton");
    const scrollHotlineButton = document.getElementById("scrollHotlineButton");

    let toastTimer = null;

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[char] || char));
    }

    function showToast(message) {
      if (!toast) return;
      toast.textContent = message;
      toast.classList.add("show");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast.classList.remove("show"), 1600);
    }

    function firstSentence(value) {
      const text = String(value ?? "").trim();
      if (!text) return "";
      const sentence = text.split(/[。！？]/)[0].trim();
      return sentence || text;
    }

    function riskLabelFromVerdict(verdict) {
      return {
        "問題なさそう": "低",
        "確認推奨": "中",
        "即決注意": "中",
        "相談推奨": "高",
      }[verdict] || "中";
    }

    function formatMoney(value) {
      if (value === null || value === undefined || value === "") return "未入力";
      const numeric = Number(value);
      if (Number.isNaN(numeric)) return String(value);
      return `${new Intl.NumberFormat("ja-JP").format(numeric)}円`;
    }

    function getLastCheck() {
      try {
        const raw = localStorage.getItem("sellBeforeCheck:last");
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed?.check_type || !parsed?.check_id) return null;
        return parsed;
      } catch (_) {
        return null;
      }
    }

    function setLastCheck(checkType, checkId) {
      try {
        localStorage.setItem("sellBeforeCheck:last", JSON.stringify({ check_type: checkType, check_id: checkId }));
      } catch (_) {
        // storage may be blocked; ignore
      }
    }

    function scrollToElement(id) {
      const element = document.getElementById(id);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }

    function copyText(text, message) {
      const payload = String(text ?? "").trim();
      if (!payload) {
        showToast("コピーする文例がありません");
        return Promise.resolve();
      }
      return navigator.clipboard.writeText(payload)
        .then(() => showToast(message || "コピーしました"))
        .catch(() => showToast("コピーに失敗しました"));
    }

    async function postJson(path, payload) {
      const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        let detail = `${path} (${response.status})`;
        try {
          const errorJson = await response.json();
          if (errorJson?.detail) {
            detail = Array.isArray(errorJson.detail)
              ? errorJson.detail.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join(" / ")
              : String(errorJson.detail);
          }
        } catch (_) {
          // ignore
        }
        throw new Error(detail);
      }
      return response.json();
    }

    async function fetchJson(path) {
      const response = await fetch(`${API_BASE}${path}`);
      if (!response.ok) {
        throw new Error(`${path} (${response.status})`);
      }
      return response.json();
    }

    function readText(form, name) {
      const field = form.querySelector(`[name="${name}"]`);
      const value = field && typeof field.value === "string" ? field.value.trim() : "";
      return value || null;
    }

    function readNumber(form, name) {
      const value = readText(form, name);
      if (!value) return null;
      const numeric = Number(String(value).replace(/[^\\d-]/g, ""));
      return Number.isFinite(numeric) ? numeric : null;
    }

    function readBoolean(form, name) {
      const field = form.querySelector(`[name="${name}"]`);
      return Boolean(field && field.checked);
    }

    function buildFlyerPayload(form) {
      return {
        company_name: readText(form, "company_name"),
        phone_number: readText(form, "phone_number"),
        flyer_text: readText(form, "flyer_text"),
        outcall_fee_text: readBoolean(form, "outcall_fee_present") ? "出張費無料" : null,
        cancellation_fee_text: readBoolean(form, "cancellation_fee_present") ? "キャンセル料無料" : null,
        high_price_text: readBoolean(form, "high_price_present") ? "高価買取" : null,
        same_day_cash_text: readBoolean(form, "same_day_cash_present") ? "即日現金化" : null,
        inducement_text: readBoolean(form, "inducement_present") ? "貴金属・時計・ブランド品も査定" : null,
        memo: readText(form, "memo"),
      };
    }

    function buildItemPayload(form) {
      return {
        item_category: readText(form, "item_category"),
        item_name: readText(form, "item_name"),
        brand: readText(form, "brand"),
        model_number: readText(form, "model_number"),
        condition_note: readText(form, "condition_note"),
        accessories: readText(form, "accessories"),
        offered_price: readNumber(form, "offered_price"),
        market_memo: readText(form, "market_memo"),
        additional_photo_requests: readText(form, "additional_photo_requests"),
        check_points: readText(form, "check_points"),
        memo: readText(form, "memo"),
      };
    }

    function buildQuotePayload(form) {
      return {
        offered_price: readNumber(form, "offered_price"),
        work_fee: readNumber(form, "work_fee"),
        disposal_fee: readNumber(form, "disposal_fee"),
        outcall_fee: readNumber(form, "outcall_fee"),
        appraisal_fee: readNumber(form, "appraisal_fee"),
        cancellation_fee: readNumber(form, "cancellation_fee"),
        home_appliance_recycling_fee: readText(form, "home_appliance_recycling_fee"),
        additional_charge_conditions: readText(form, "additional_charge_conditions"),
        package_price: readNumber(form, "package_price"),
        same_day_extra_charge: readNumber(form, "same_day_extra_charge"),
        estimate_sheet_present: readBoolean(form, "estimate_sheet_present"),
        memo: readText(form, "memo"),
      };
    }

    async function submitForm(type, form) {
      const submitButton = form.querySelector('button[type="submit"]');
      const status = form.querySelector("[data-form-status]");
      const payload = type === "flyer" ? buildFlyerPayload(form) : type === "item" ? buildItemPayload(form) : buildQuotePayload(form);
      if (submitButton) submitButton.disabled = true;
      if (status) status.textContent = "保存中...";
      try {
        const created = await postJson(`/${type}-checks`, payload);
        setLastCheck(type, created.id);
        if (status) status.textContent = "保存しました。結果を開きます。";
        window.location.href = `${RESULT_ROUTE}?check_type=${encodeURIComponent(type)}&check_id=${encodeURIComponent(created.id)}`;
      } catch (error) {
        console.error(error);
        if (status) status.textContent = `保存に失敗しました: ${error.message}`;
        showToast("保存に失敗しました");
      } finally {
        if (submitButton) submitButton.disabled = false;
      }
    }

    function guidanceForCategory(category) {
      const fallback = {
        check_points: ["商品名", "ブランド", "型番", "状態", "付属品"],
        photo_requests: ["全体写真", "型番や刻印のアップ", "付属品の写真"],
      };
      return ITEM_GUIDANCE[category] || fallback;
    }

    function renderItemGuidance() {
      const select = document.getElementById("itemCategory");
      const pointsList = document.getElementById("itemCheckPointsList");
      const photoList = document.getElementById("itemPhotoRequestsList");
      const pointsText = document.getElementById("check_points");
      const photoText = document.getElementById("additional_photo_requests");
      if (!select || !pointsList || !photoList || !pointsText || !photoText) return;

      const update = () => {
        const selected = select.value || "着物";
        const guidance = guidanceForCategory(selected);
        const points = Array.isArray(guidance.check_points) ? guidance.check_points : [];
        const photos = Array.isArray(guidance.photo_requests) ? guidance.photo_requests : [];
        pointsList.innerHTML = points.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
        photoList.innerHTML = photos.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
        pointsText.value = points.join("\\n");
        photoText.value = photos.join("\\n");
      };

      select.addEventListener("change", update);
      update();
    }

    async function loadResult() {
      const params = new URLSearchParams(window.location.search);
      const checkType = params.get("check_type") || INITIAL_CHECK_TYPE || (getLastCheck() || {}).check_type;
      const checkId = params.get("check_id") || INITIAL_CHECK_ID || (getLastCheck() || {}).check_id;

      const resultStatus = document.getElementById("resultStatus");
      const verdictChip = document.getElementById("resultVerdictChip");
      const riskChip = document.getElementById("resultRiskChip");
      const headline = document.getElementById("resultHeadline");
      const summary = document.getElementById("resultSummary");
      const recommendation = document.getElementById("resultRecommendation");
      const nextActionsList = document.getElementById("nextActionsList");
      const refusalText = document.getElementById("refusalText");
      const reasonText = document.getElementById("reasonText");
      const missingList = document.getElementById("missingList");
      const marketLinks = document.getElementById("marketLinks");
      const officialList = document.getElementById("officialList");
      const hotlineCard = document.getElementById("hotlineSection");
      const hotlineTitle = document.getElementById("hotlineTitle");
      const hotlineText = document.getElementById("hotlineText");
      const confidenceScore = document.getElementById("confidenceScore");
      const confidenceLabel = document.getElementById("confidenceLabel");
      const confidenceBar = document.getElementById("confidenceBar");
      const disclaimerText = document.getElementById("disclaimerText");
      const resultTypeLabel = document.getElementById("resultTypeLabel");
      const fallbackState = document.getElementById("resultEmptyState");

      if (!checkType || !checkId) {
        if (resultStatus) resultStatus.textContent = "まだ診断がありません。";
        if (fallbackState) fallbackState.classList.remove("hidden");
        return;
      }

      try {
        const response = await fetchJson(`/reports/${checkType}/${checkId}`);
        const report = response.content_json || {};
        setLastCheck(checkType, checkId);
        const judgement = report.judgement || "確認推奨";
        const risk = riskLabelFromVerdict(judgement);
        const headlineText = RESULT_HEADLINES[judgement] || "売る前に、少し待ってください";
        const recommendationText = RESULT_RECOMMENDATIONS[judgement] || "契約前に条件を確認してください";
        const nextActions = Array.isArray(report.next_actions) ? report.next_actions.slice(0, 4) : [];
        const missingInfo = Array.isArray(report.missing_info) ? report.missing_info.slice(0, 4) : [];
        const officialInfos = Array.isArray(report.official_infos) ? report.official_infos.slice(0, 3) : [];
        const marketLinksData = report.market_links || {};
        const confidence = report.confidence || {};
        const refusal = report.refusal_phrase || DEFAULT_REFUSAL;
        const hotline = report.hotline_notice || DEFAULT_HOTLINE;
        const disclaimer = report.disclaimer || DEFAULT_DISCLAIMER;
        const reason = String(report.reason || "").trim();
        const firstReason = firstSentence(reason);

        if (verdictChip) verdictChip.textContent = judgement;
        if (riskChip) riskChip.textContent = `危険度 ${risk}`;
        if (headline) headline.textContent = headlineText;
        if (summary) summary.textContent = firstReason || "売る前に、条件と証拠を整理してから判断できます。";
        if (recommendation) recommendation.textContent = `おすすめ行動: ${recommendationText}`;
        if (nextActionsList) {
          nextActionsList.innerHTML = nextActions.length
            ? nextActions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
            : [
                "今日はその場で決めず、家族に見せてから判断する",
                "見積書や明細は紙かメールで受け取る",
                "写真や条件を残してから進める",
              ].map((item) => `<li>${escapeHtml(item)}</li>`).join("");
        }
        if (refusalText) refusalText.textContent = refusal;
        if (reasonText) reasonText.textContent = reason || "情報が足りないため、まずは追加確認をおすすめします。";
        if (missingList) {
          missingList.innerHTML = missingInfo.length
            ? missingInfo.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
            : "<li>不足情報はありません。</li>";
        }
        if (marketLinks) {
          const entries = Object.entries(marketLinksData);
          marketLinks.innerHTML = entries.length
            ? entries.map(([key, url]) => {
                const label = MARKET_LINK_LABELS[key] || key;
                return `<a class="link-pill" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
              }).join("")
            : '<span class="muted">相場リンクはまだありません。</span>';
        }
        if (officialList) {
          officialList.innerHTML = officialInfos.length
            ? officialInfos.map((info) => `
                <div class="info-card">
                  <div class="info-top">
                    <span class="info-category">${escapeHtml(info.category || "official")}</span>
                    <span class="chip">参考</span>
                  </div>
                  <h4>${escapeHtml(info.title || "")}</h4>
                  <p>${escapeHtml(info.summary || "")}</p>
                </div>
              `).join("")
            : '<div class="empty-state">公式情報はまだありません。</div>';
        }
        if (hotlineTitle) hotlineTitle.textContent = "不安なときは、消費者ホットライン188に相談できます";
        if (hotlineText) hotlineText.textContent = hotline;
        if (hotlineCard) {
          hotlineCard.classList.toggle("prominent", judgement === "相談推奨");
        }
        if (confidenceScore) confidenceScore.textContent = `${Number(confidence.score ?? 0)}`;
        if (confidenceLabel) confidenceLabel.textContent = confidence.label || "low";
        if (confidenceBar) confidenceBar.style.setProperty("--score", `${Math.max(0, Math.min(100, Number(confidence.score ?? 0)))}%`);
        if (disclaimerText) disclaimerText.textContent = disclaimer;
        if (resultTypeLabel) resultTypeLabel.textContent = CHECK_TYPE_LABELS[checkType] || "診断結果";
        if (resultStatus) resultStatus.textContent = "診断結果を読み込みました。";
        if (fallbackState) fallbackState.classList.add("hidden");
        if (bottomBar) bottomBar.classList.remove("hidden");
        if (copyRefusalBottomButton) {
          copyRefusalBottomButton.disabled = !refusal;
          copyRefusalBottomButton.onclick = () => copyText(refusal, "断り文例をコピーしました");
        }
        if (scrollMarketButton) {
          scrollMarketButton.disabled = false;
          scrollMarketButton.onclick = () => scrollToElement("marketSection");
        }
        if (scrollHotlineButton) {
          scrollHotlineButton.disabled = false;
          scrollHotlineButton.onclick = () => scrollToElement("hotlineSection");
          scrollHotlineButton.classList.toggle("warn", judgement === "相談推奨");
          scrollHotlineButton.classList.toggle("secondary", judgement !== "相談推奨");
        }
      } catch (error) {
        console.error(error);
        if (resultStatus) resultStatus.textContent = "診断結果の読み込みに失敗しました。";
        if (fallbackState) fallbackState.classList.remove("hidden");
      }
    }

    const resultCopyButton = document.getElementById("copyRefusalButton");
    if (resultCopyButton) {
      resultCopyButton.addEventListener("click", () => copyText(document.getElementById("refusalText")?.textContent || "", "断り文例をコピーしました"));
    }

    const flyerForm = document.getElementById("flyerForm");
    if (flyerForm) {
      flyerForm.addEventListener("submit", (event) => {
        event.preventDefault();
        submitForm("flyer", flyerForm);
      });
    }

    const itemForm = document.getElementById("itemForm");
    if (itemForm) {
      itemForm.addEventListener("submit", (event) => {
        event.preventDefault();
        submitForm("item", itemForm);
      });
      renderItemGuidance();
    }

    const quoteForm = document.getElementById("quoteForm");
    if (quoteForm) {
      quoteForm.addEventListener("submit", (event) => {
        event.preventDefault();
        submitForm("quote", quoteForm);
      });
    }

    if (PAGE_KEY === "result") {
      loadResult();
    } else if (bottomBar) {
      bottomBar.classList.add("hidden");
    }
  </script>
</body>
</html>
    """
)


def _hero_note_html() -> str:
    return """
    <section class="hero">
      <p class="eyebrow">売る前チェックAI</p>
      <h2 class="page-title">その場で売る前に、まず写真でチェック。</h2>
      <p class="hero-copy">着物・ミシン・貴金属・不用品回収で、安く買い叩かれないための確認アプリ。</p>
      <p class="hero-subcopy">1分で確認できます。高齢の親を心配する家族にも、そのまま見せやすい文言で整えています。</p>
      <div class="hero-meta">
        <span class="hero-pill">まずは <strong>チラシ</strong> / <strong>商品</strong> / <strong>見積もり</strong> の3つから</span>
        <span class="hero-pill">自動出品なし / 自動購入なし / 自動ログインなし / スクレイピングなし</span>
      </div>
      <div class="home-grid" aria-label="主要導線">
        <a class="home-button primary" href="/flyer-check">
          <span class="title">チラシをチェック</span>
          <span class="sub">気になる文言と条件を先に見ます</span>
        </a>
        <a class="home-button" href="/item-check">
          <span class="title">商品をチェック</span>
          <span class="sub">着物・ミシン・貴金属を落ち着いて確認します</span>
        </a>
        <a class="home-button" href="/quote-check">
          <span class="title">見積もりをチェック</span>
          <span class="sub">追加料金やキャンセル条件を見直します</span>
        </a>
      </div>
      <div class="home-note">
        売る前に迷ったら、家族に見せてから判断してください。<br>
        ここで見るのは参考の整理です。正確な査定額、真贋、法律判断は断定しません。
      </div>
    </section>
    """


def _flyer_body_html() -> str:
    phrases = "".join(f"<span class=\"chip\">{escape(phrase)}</span>" for phrase in FLYER_ALERT_PHRASES)
    return f"""
    <section class="section-card">
      <div class="section-head">
        <div>
          <p class="eyebrow">チラシチェック</p>
          <h2 class="section-title">言葉だけで決めず、条件を先に確認します。</h2>
        </div>
        <a class="top-link" href="/">Home</a>
      </div>
      <p class="helper">チラシ画像はあとで追加できます。v0.1 ではまず文字入力だけで進められます。</p>
      <form id="flyerForm" class="field-grid" autocomplete="off">
        <div class="field">
          <label for="flyerText">チラシ文言</label>
          <textarea id="flyerText" name="flyer_text" placeholder="着物高価買取 / 出張査定無料 / 即日現金化"></textarea>
        </div>
        <div class="field-grid two-col">
          <div class="field">
            <label for="companyName">業者名</label>
            <input id="companyName" name="company_name" type="text" placeholder="例: サンプル訪問買取">
          </div>
          <div class="field">
            <label for="phoneNumber">電話番号</label>
            <input id="phoneNumber" name="phone_number" type="text" placeholder="例: 0120-123-456">
          </div>
        </div>
        <div class="section-card" style="padding: 14px; margin: 0;">
          <div class="card-head">
            <div>
              <h3 class="card-title">見えた文言</h3>
              <p class="helper">チェックを入れると、判定に使う言葉として保存されます。</p>
            </div>
          </div>
          <div class="toggle-list">
            <label class="toggle"><input type="checkbox" name="outcall_fee_present"> 出張費無料の記載あり</label>
            <label class="toggle"><input type="checkbox" name="cancellation_fee_present"> キャンセル料無料の記載あり</label>
            <label class="toggle"><input type="checkbox" name="high_price_present"> 高価買取の記載あり</label>
            <label class="toggle"><input type="checkbox" name="same_day_cash_present"> 即日現金化の記載あり</label>
            <label class="toggle"><input type="checkbox" name="inducement_present"> 貴金属・時計・ブランド品も査定の記載あり</label>
          </div>
          <div class="warning-band">
            <strong>注意して見る文言</strong>
            <div class="chip-list">{phrases}</div>
          </div>
        </div>
        <div class="field">
          <label for="flyerMemo">メモ</label>
          <textarea id="flyerMemo" name="memo" placeholder="家族に見せてから判断したい / 口頭の説明だけだった など"></textarea>
        </div>
        <div class="form-actions">
          <p class="helper" data-form-status>未保存です。</p>
          <button type="submit" class="primary-button">診断して結果を見る</button>
          <a class="secondary-button" href="/">Home に戻る</a>
        </div>
      </form>
    </section>
    """


def _item_options_html() -> str:
    options = [
        "着物",
        "ミシン",
        "貴金属",
        "カメラ",
        "時計・ブランド品",
        "不用品回収対象品",
        "その他",
    ]
    return "\n".join(f"<option value=\"{escape(option)}\">{escape(option)}</option>" for option in options)


def _item_body_html() -> str:
    options_html = _item_options_html()
    default_guidance = guidance = ITEM_CATEGORY_GUIDANCE.get("着物", {})
    default_points = "\n".join(default_guidance.get("check_points", []))
    default_photos = "\n".join(default_guidance.get("photo_requests", []))
    return f"""
    <section class="section-card">
      <div class="section-head">
        <div>
          <p class="eyebrow">商品チェック</p>
          <h2 class="section-title">型番や刻印が見えにくいときは、即決注意に寄せます。</h2>
        </div>
        <a class="top-link" href="/">Home</a>
      </div>
      <p class="helper">カテゴリごとの確認ポイントを自動で表示します。着物・ミシン・貴金属は特に、証紙や型番、刻印を先に見ます。</p>
      <form id="itemForm" class="field-grid" autocomplete="off">
        <div class="field">
          <label for="itemCategory">商品カテゴリ</label>
          <select id="itemCategory" name="item_category">
            {options_html}
          </select>
        </div>
        <div class="field-grid two-col">
          <div class="field">
            <label for="itemName">商品名</label>
            <input id="itemName" name="item_name" type="text" placeholder="例: JUKI ミシン / K18らしき指輪">
          </div>
          <div class="field">
            <label for="itemBrand">ブランド</label>
            <input id="itemBrand" name="brand" type="text" placeholder="例: JUKI / Cartier / Canon">
          </div>
        </div>
        <div class="field-grid two-col">
          <div class="field">
            <label for="itemModel">型番</label>
            <input id="itemModel" name="model_number" type="text" placeholder="例: 不明 / 型番あり">
          </div>
          <div class="field">
            <label for="itemPrice">業者提示額</label>
            <input id="itemPrice" name="offered_price" type="number" min="0" step="1" placeholder="例: 1000">
          </div>
        </div>
        <div class="field">
          <label for="conditionNote">状態</label>
          <input id="conditionNote" name="condition_note" type="text" placeholder="例: 動作未確認 / 刻印未確認 / シミあり">
        </div>
        <div class="field">
          <label for="accessories">付属品</label>
          <input id="accessories" name="accessories" type="text" placeholder="例: フットコントローラーなし / 箱あり / 鑑定書なし">
        </div>
        <div class="section-card" style="padding: 14px; margin: 0;">
          <div class="card-head">
            <div>
              <h3 class="card-title">確認ポイント</h3>
              <p class="helper">カテゴリに応じて自動で埋めます。必要ならそのまま編集できます。</p>
            </div>
          </div>
          <ul class="guidance-list" id="itemCheckPointsList">
            {''.join(f'<li>{escape(point)}</li>' for point in default_guidance.get("check_points", []))}
          </ul>
          <textarea id="check_points" name="check_points" style="margin-top: 10px;">{escape(default_points)}</textarea>
        </div>
        <div class="section-card" style="padding: 14px; margin: 0;">
          <div class="card-head">
            <div>
              <h3 class="card-title">追加で撮るべき写真</h3>
              <p class="helper">あとで見返せるよう、必要な写真のメモを残します。</p>
            </div>
          </div>
          <ul class="guidance-list" id="itemPhotoRequestsList">
            {''.join(f'<li>{escape(point)}</li>' for point in default_guidance.get("photo_requests", []))}
          </ul>
          <textarea id="additional_photo_requests" name="additional_photo_requests" style="margin-top: 10px;">{escape(default_photos)}</textarea>
        </div>
        <div class="field">
          <label for="marketMemo">相場メモ</label>
          <textarea id="marketMemo" name="market_memo" placeholder="型番不明 / 複数査定で比べたい など"></textarea>
        </div>
        <div class="field">
          <label for="itemMemo">メモ</label>
          <textarea id="itemMemo" name="memo" placeholder="証紙あり / 落款あり / 動作確認したい など"></textarea>
        </div>
        <div class="form-actions">
          <p class="helper" data-form-status>未保存です。</p>
          <button type="submit" class="primary-button">診断して結果を見る</button>
          <a class="secondary-button" href="/">Home に戻る</a>
        </div>
      </form>
    </section>
    """


def _quote_body_html() -> str:
    return """
    <section class="section-card">
      <div class="section-head">
        <div>
          <p class="eyebrow">見積もりチェック</p>
          <h2 class="section-title">内訳があいまいなら、契約は急がずに確認します。</h2>
        </div>
        <a class="top-link" href="/">Home</a>
      </div>
      <p class="helper">不用品回収や出張買取の見積もりを、一般ユーザーが見やすい順番で整理します。</p>
      <form id="quoteForm" class="field-grid" autocomplete="off">
        <div class="field-grid two-col">
          <div class="field">
            <label for="quoteOfferedPrice">広告表示額</label>
            <input id="quoteOfferedPrice" name="offered_price" type="number" min="0" step="1" placeholder="例: 9800">
          </div>
          <div class="field">
            <label for="quotePackagePrice">パック料金</label>
            <input id="quotePackagePrice" name="package_price" type="number" min="0" step="1" placeholder="例: 9800">
          </div>
        </div>
        <div class="field-grid two-col">
          <div class="field">
            <label for="quoteWorkFee">作業費</label>
            <input id="quoteWorkFee" name="work_fee" type="number" min="0" step="1" placeholder="例: 0">
          </div>
          <div class="field">
            <label for="quoteDisposalFee">処分費</label>
            <input id="quoteDisposalFee" name="disposal_fee" type="number" min="0" step="1" placeholder="例: 0">
          </div>
        </div>
        <div class="field-grid two-col">
          <div class="field">
            <label for="quoteOutcallFee">出張費</label>
            <input id="quoteOutcallFee" name="outcall_fee" type="number" min="0" step="1" placeholder="例: 0">
          </div>
          <div class="field">
            <label for="quoteAppraisalFee">査定料</label>
            <input id="quoteAppraisalFee" name="appraisal_fee" type="number" min="0" step="1" placeholder="例: 0">
          </div>
        </div>
        <div class="field-grid two-col">
          <div class="field">
            <label for="quoteCancellationFee">キャンセル料</label>
            <input id="quoteCancellationFee" name="cancellation_fee" type="number" min="0" step="1" placeholder="例: 0">
          </div>
          <div class="field">
            <label for="quoteRecyclingFee">家電リサイクル料金</label>
            <input id="quoteRecyclingFee" name="home_appliance_recycling_fee" type="text" placeholder="例: 不明 / 別途">
          </div>
        </div>
        <div class="field">
          <label for="quoteSameDayExtraCharge">当日提示額 / 追加請求</label>
          <input id="quoteSameDayExtraCharge" name="same_day_extra_charge" type="number" min="0" step="1" placeholder="例: 80000">
        </div>
        <div class="field">
          <label for="quoteAdditionalConditions">追加料金条件</label>
          <textarea id="quoteAdditionalConditions" name="additional_charge_conditions" placeholder="当日追加請求あり / 見積外費用あり など"></textarea>
        </div>
        <label class="toggle"><input type="checkbox" name="estimate_sheet_present"> 見積書・明細あり</label>
        <div class="field">
          <label for="quoteMemo">メモ</label>
          <textarea id="quoteMemo" name="memo" placeholder="軽トラックパック9,800円 / 当日80,000円 など"></textarea>
        </div>
        <div class="warning-band">
          <strong>確認したいポイント</strong>
          <ul class="plain-list">
            <li>広告表示額と当日提示額の差</li>
            <li>追加料金条件の明確さ</li>
            <li>見積書と明細の有無</li>
            <li>家電リサイクル対象品の扱い</li>
          </ul>
        </div>
        <div class="form-actions">
          <p class="helper" data-form-status>未保存です。</p>
          <button type="submit" class="primary-button">診断して結果を見る</button>
          <a class="secondary-button" href="/">Home に戻る</a>
        </div>
      </form>
    </section>
    """


def _result_body_html() -> str:
    return """
    <section class="result-card" id="resultCard">
      <div class="result-badge-row">
        <span class="result-chip verdict" id="resultVerdictChip">読み込み中</span>
        <span class="result-chip medium" id="resultRiskChip">危険度 中</span>
        <span class="chip" id="resultTypeLabel">読み込み中</span>
      </div>
      <p class="eyebrow">結論</p>
      <h2 class="result-headline" id="resultHeadline">売る前に、少し待ってください</h2>
      <p class="result-copy" id="resultSummary">今やることが最初に見えるように整理します。</p>
      <div class="result-meta">
        <div class="meta-row">
          <span class="meta-pill">おすすめ行動<strong id="resultRecommendation">契約前に条件を確認してください</strong></span>
        </div>
        <div class="meta-row" id="resultStatusRow">
          <span class="meta-pill">状態<strong id="resultStatus">読み込み中</strong></span>
        </div>
      </div>
    </section>

    <section class="step-card" id="nextActionsSection">
      <h3>今やること</h3>
      <ol class="stack-list" id="nextActionsList">
        <li>読み込み中です。</li>
      </ol>
    </section>

    <section class="copy-card" id="refusalSection">
      <div class="card-head">
        <div>
          <p class="eyebrow">断り文例</p>
          <h3 class="card-title">その場で迷ったら、短く伝えて止める</h3>
        </div>
        <button type="button" class="copy-button" id="copyRefusalButton">コピー</button>
      </div>
      <div class="copy-row">
        <p class="copy-text" id="refusalText">読み込み中です。</p>
      </div>
    </section>

    <section class="step-card" id="reasonSection">
      <h3>理由</h3>
      <p class="copy-text" id="reasonText">読み込み中です。</p>
    </section>

    <section class="step-card" id="missingSection">
      <h3>不足情報</h3>
      <ul class="stack-list" id="missingList">
        <li>読み込み中です。</li>
      </ul>
    </section>

    <section class="step-card" id="marketSection">
      <h3>相場リンク</h3>
      <div class="link-grid" id="marketLinks">
        <span class="muted">読み込み中です。</span>
      </div>
      <p class="helper" style="margin-top: 10px;">検索URLのみを開きます。スクレイピングはしません。</p>
    </section>

    <section class="step-card" id="officialSection">
      <h3>公式情報・188相談案内</h3>
      <div class="info-grid" id="officialList">
        <div class="empty-state">読み込み中です。</div>
      </div>
      <div class="notice-card" id="hotlineSection" style="margin-top: 14px;">
        <span class="notice-title" id="hotlineTitle">不安なときは、消費者ホットライン188に相談できます</span>
        <p id="hotlineText">読み込み中です。</p>
      </div>
    </section>

    <section class="step-card" id="confidenceSection">
      <h3>信頼度</h3>
      <div class="confidence-box">
        <div class="score-row">
          <div>
            <strong id="confidenceScore" style="font-size: 1.5rem;">--</strong>
            <div class="helper" id="confidenceLabel">読み込み中です。</div>
          </div>
          <span class="hero-pill">参考です</span>
        </div>
        <div class="score-track" aria-hidden="true">
          <div class="score-fill" id="confidenceBar" style="--score: 0%;"></div>
        </div>
        <p class="helper" id="disclaimerText">読み込み中です。</p>
      </div>
    </section>

    <section class="step-card hidden" id="resultEmptyState">
      <p class="helper">まだ診断がありません。Home からチラシ・商品・見積もりのいずれかを開いてください。</p>
    </section>
    """


def _page_shell_html(*, settings: AppSettings, page_key: str, page_title: str, page_subtitle: str, top_link_href: str, top_link_label: str, body_html: str, check_type: str | None = None, check_id: int | None = None) -> str:
    return _MVP_TEMPLATE.render(
        app_name=settings.app_name,
        page_key=page_key,
        page_title=page_title,
        page_subtitle=page_subtitle,
        top_link_href=top_link_href,
        top_link_label=top_link_label,
        body_html=body_html,
        check_type=check_type,
        api_prefix_json=json.dumps(settings.api_prefix, ensure_ascii=False),
        page_key_json=json.dumps(page_key, ensure_ascii=False),
        result_route_json=json.dumps("/result", ensure_ascii=False),
        check_type_json=json.dumps(check_type, ensure_ascii=False),
        check_id_json=json.dumps(check_id, ensure_ascii=False),
        item_guidance_json=json.dumps(ITEM_CATEGORY_GUIDANCE, ensure_ascii=False),
        market_link_labels_json=json.dumps(
            {
                "mercari": "メルカリ検索",
                "yahoo_auction": "Yahoo!オークション検索",
                "yahoo_auction_sold": "Yahoo!オークション落札相場",
                "ebay": "eBay検索",
                "ebay_sold_completed": "eBay Sold / Completed",
                "google": "Google検索",
                "specialist_buyback": "専門買取店検索",
            },
            ensure_ascii=False,
        ),
        check_type_labels_json=json.dumps(
            {
                "flyer": "チラシチェック",
                "item": "商品チェック",
                "quote": "見積もりチェック",
            },
            ensure_ascii=False,
        ),
        result_headlines_json=json.dumps(
            {
                "問題なさそう": "今のところ大きな不安は見えません",
                "確認推奨": "その場で進める前に、条件をもう一度確認してください",
                "即決注意": "契約は急がず、複数で比べてください",
                "相談推奨": "今日はこの場で決めず、家族と188で確認してください",
            },
            ensure_ascii=False,
        ),
        result_recommendations_json=json.dumps(
            {
                "問題なさそう": "条件を紙かメールで残して進める",
                "確認推奨": "条件を紙で確認してから進める",
                "即決注意": "契約せず、複数査定で比べる",
                "相談推奨": "契約せず、家族と相談して188へ",
            },
            ensure_ascii=False,
        ),
        default_refusal_json=json.dumps(_DEFAULT_REFUSAL, ensure_ascii=False),
        default_hotline_json=json.dumps(CONSUMER_HOTLINE_NOTICE, ensure_ascii=False),
        default_disclaimer_json=json.dumps(CONSUMER_DISCLAIMER, ensure_ascii=False),
    )


def render_consumer_home_html(settings: AppSettings) -> str:
    return _page_shell_html(
        settings=settings,
        page_key="home",
        page_title="Home",
        page_subtitle="一般ユーザー向けの確認導線",
        top_link_href="/dashboard",
        top_link_label="管理画面",
        body_html=_hero_note_html(),
    )


def render_consumer_flyer_html(settings: AppSettings) -> str:
    return _page_shell_html(
        settings=settings,
        page_key="flyer",
        page_title="チラシチェック",
        page_subtitle="条件を先に確認する",
        top_link_href="/",
        top_link_label="Home",
        body_html=_flyer_body_html(),
        check_type="flyer",
    )


def render_consumer_item_html(settings: AppSettings) -> str:
    return _page_shell_html(
        settings=settings,
        page_key="item",
        page_title="商品チェック",
        page_subtitle="型番と状態を先に確認する",
        top_link_href="/",
        top_link_label="Home",
        body_html=_item_body_html(),
        check_type="item",
    )


def render_consumer_quote_html(settings: AppSettings) -> str:
    return _page_shell_html(
        settings=settings,
        page_key="quote",
        page_title="見積もりチェック",
        page_subtitle="追加料金を先に確認する",
        top_link_href="/",
        top_link_label="Home",
        body_html=_quote_body_html(),
        check_type="quote",
    )


def render_consumer_result_html(settings: AppSettings, *, check_type: str | None = None, check_id: int | None = None) -> str:
    return _page_shell_html(
        settings=settings,
        page_key="result",
        page_title="診断結果",
        page_subtitle="今やることを先に見せる",
        top_link_href="/",
        top_link_label="Home",
        body_html=_result_body_html(),
        check_type=check_type,
        check_id=check_id,
    )
