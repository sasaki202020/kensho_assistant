from __future__ import annotations

from jinja2 import Template

from .config import AppSettings


_DASHBOARD_TEMPLATE = Template(
    """
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{{ app_name }} | ダッシュボード</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #070c12;
      --bg-2: #0b1118;
      --panel: rgba(15, 22, 31, 0.92);
      --panel-strong: rgba(18, 26, 36, 0.98);
      --panel-soft: rgba(255, 255, 255, 0.04);
      --line: rgba(148, 163, 184, 0.16);
      --line-strong: rgba(217, 164, 76, 0.22);
      --text: #eef2f7;
      --muted: #94a3b8;
      --muted-strong: #cbd5e1;
      --accent: #d7a64a;
      --accent-soft: rgba(215, 166, 74, 0.14);
      --warn: #fb923c;
      --warn-soft: rgba(251, 146, 60, 0.14);
      --danger: #ef4444;
      --danger-soft: rgba(239, 68, 68, 0.15);
      --ok: #34d399;
      --ok-soft: rgba(52, 211, 153, 0.13);
      --shadow: 0 24px 70px rgba(2, 6, 23, 0.55);
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
        radial-gradient(circle at 15% 20%, rgba(215, 166, 74, 0.16), transparent 24%),
        radial-gradient(circle at 82% 14%, rgba(148, 163, 184, 0.11), transparent 20%),
        linear-gradient(180deg, #05080c 0%, #091018 45%, #0b1220 100%);
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
      mask-image: radial-gradient(circle at center, black 40%, transparent 100%);
      opacity: 0.55;
    }

    a { color: inherit; }
    button, input, textarea { font: inherit; }

    .shell {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: 276px minmax(0, 1fr) 342px;
      gap: 18px;
      min-height: 100vh;
      padding: 18px;
    }

    .sidebar,
    .main,
    .rail {
      border: 1px solid var(--line);
      background: var(--panel);
      backdrop-filter: blur(14px);
      box-shadow: var(--shadow);
    }

    .sidebar {
      border-radius: var(--radius-xl);
      padding: 22px 18px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--line);
    }

    .brand-mark {
      width: 48px;
      height: 48px;
      border-radius: 16px;
      display: grid;
      place-items: center;
      background: linear-gradient(180deg, rgba(215, 166, 74, 0.95), rgba(255, 255, 255, 0.08));
      color: #10151d;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-weight: 700;
      letter-spacing: 0.08em;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35);
    }

    .brand h1 {
      margin: 0;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 1.03rem;
      letter-spacing: 0.04em;
    }

    .brand p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.5;
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
      font-weight: 600;
    }

    .status-box {
      display: grid;
      gap: 10px;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.025);
    }

    .status-box h2,
    .section-title {
      margin: 0;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      letter-spacing: 0.04em;
      font-size: 0.92rem;
    }

    .status-copy {
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.6;
      margin: 0;
    }

    .nav {
      display: grid;
      gap: 8px;
    }

    .nav button,
    .ghost-button,
    .copy-button,
    .chip-link {
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
      cursor: pointer;
      transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
    }

    .nav button {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      min-height: 46px;
      padding: 0 14px;
      text-align: left;
      font-size: 0.92rem;
    }

    .nav button:hover,
    .ghost-button:hover,
    .copy-button:hover,
    .chip-link:hover {
      transform: translateY(-1px);
      border-color: rgba(215, 166, 74, 0.34);
      background: rgba(255, 255, 255, 0.05);
    }

    .chip-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      padding: 0 14px;
      text-decoration: none;
      margin-top: 2px;
    }

    .nav button.active {
      background: linear-gradient(180deg, rgba(215, 166, 74, 0.18), rgba(255, 255, 255, 0.04));
      border-color: rgba(215, 166, 74, 0.42);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }

    .nav small {
      color: var(--muted);
      font-size: 0.76rem;
    }

    .safety-list {
      display: grid;
      gap: 8px;
      padding: 14px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.025);
    }

    .safety-list .section-title {
      margin-bottom: 4px;
    }

    .safety-list ul {
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.8;
    }

    .main {
      border-radius: var(--radius-xl);
      padding: 22px;
      display: grid;
      gap: 18px;
      min-width: 0;
    }

    .hero {
      border-radius: 26px;
      padding: 24px 24px 22px;
      border: 1px solid var(--line-strong);
      background:
        radial-gradient(circle at 75% 18%, rgba(215, 166, 74, 0.16), transparent 28%),
        linear-gradient(180deg, rgba(18, 26, 36, 0.98), rgba(11, 18, 27, 0.95));
    }

    .hero-top {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 18px;
    }

    .eyebrow {
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 0.75rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }

    .hero h2 {
      margin: 0;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: clamp(1.8rem, 2.6vw, 3rem);
      line-height: 1.05;
      letter-spacing: 0.02em;
      text-wrap: balance;
    }

    .hero p {
      margin: 12px 0 0;
      max-width: 68ch;
      color: var(--muted-strong);
      line-height: 1.75;
      font-size: 0.96rem;
    }

    .hero-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 18px;
    }

    .verdict-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-weight: 600;
    }

    .verdict-chip.ok { background: var(--ok-soft); border-color: rgba(52, 211, 153, 0.28); color: #b8f7db; }
    .verdict-chip.review { background: var(--accent-soft); border-color: rgba(215, 166, 74, 0.28); color: #ffe4af; }
    .verdict-chip.warn { background: var(--warn-soft); border-color: rgba(251, 146, 60, 0.26); color: #ffd1b2; }
    .verdict-chip.danger { background: var(--danger-soft); border-color: rgba(239, 68, 68, 0.26); color: #ffcbcb; }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }

    .metric {
      border-radius: 20px;
      padding: 16px 16px 15px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
      min-width: 0;
    }

    .metric .label {
      color: var(--muted);
      font-size: 0.74rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 8px;
    }

    .metric .value {
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 1.2rem;
      line-height: 1.2;
      margin: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .metric .hint {
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.5;
    }

    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 320px;
      gap: 18px;
      align-items: start;
    }

    .workspace-main {
      display: grid;
      gap: 14px;
      min-width: 0;
    }

    .segment-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .segment-bar button {
      min-height: 38px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
      cursor: pointer;
    }

    .segment-bar button.active {
      background: rgba(215, 166, 74, 0.16);
      border-color: rgba(215, 166, 74, 0.36);
    }

    .entry-panel {
      border-radius: 24px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
      padding: 20px;
      display: grid;
      gap: 14px;
    }

    .entry-head {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 18px;
    }

    .entry-head .report-subtitle {
      max-width: 70ch;
    }

    .entry-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .entry-tabs button {
      min-height: 38px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
      cursor: pointer;
      transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
    }

    .entry-tabs button:hover {
      transform: translateY(-1px);
      border-color: rgba(215, 166, 74, 0.34);
      background: rgba(255, 255, 255, 0.05);
    }

    .entry-tabs button.active {
      background: rgba(215, 166, 74, 0.16);
      border-color: rgba(215, 166, 74, 0.36);
    }

    .entry-note {
      margin: 0;
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.7;
    }

    .entry-form {
      display: grid;
      gap: 14px;
    }

    .entry-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .entry-field {
      display: grid;
      gap: 6px;
      min-width: 0;
    }

    .entry-field.full {
      grid-column: 1 / -1;
    }

    .entry-field label {
      color: var(--muted-strong);
      font-size: 0.8rem;
      line-height: 1.4;
    }

    .entry-field small {
      color: var(--muted);
      font-size: 0.74rem;
      line-height: 1.5;
    }

    .entry-field input,
    .entry-field textarea,
    .entry-field select {
      width: 100%;
      min-height: 44px;
      padding: 11px 12px;
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.18);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
      outline: none;
      transition: border-color 140ms ease, background 140ms ease, box-shadow 140ms ease;
    }

    .entry-field textarea {
      min-height: 86px;
      resize: vertical;
    }

    .entry-field input:focus,
    .entry-field textarea:focus,
    .entry-field select:focus {
      border-color: rgba(215, 166, 74, 0.42);
      box-shadow: 0 0 0 3px rgba(215, 166, 74, 0.12);
      background: rgba(255, 255, 255, 0.05);
    }

    .entry-field input::placeholder,
    .entry-field textarea::placeholder {
      color: rgba(148, 163, 184, 0.72);
    }

    .entry-field select {
      appearance: none;
    }

    .entry-field input[type="file"] {
      padding: 10px 12px;
    }

    .entry-field input[type="file"]::file-selector-button {
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      border-radius: 999px;
      padding: 7px 12px;
      margin-right: 12px;
      cursor: pointer;
    }

    .checkbox-line {
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 44px;
      padding: 0 2px;
      color: var(--text);
      font-size: 0.88rem;
    }

    .checkbox-line input {
      width: 18px;
      height: 18px;
      accent-color: var(--accent);
    }

    .entry-actions {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
    }

    .entry-actions .action-group {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .primary-button {
      min-height: 42px;
      padding: 0 16px;
      border-radius: 14px;
      border: 1px solid rgba(215, 166, 74, 0.5);
      background: linear-gradient(180deg, rgba(215, 166, 74, 0.95), rgba(166, 118, 24, 0.86));
      color: #10151d;
      font-weight: 700;
      cursor: pointer;
      transition: transform 140ms ease, filter 140ms ease;
    }

    .primary-button:hover {
      transform: translateY(-1px);
      filter: brightness(1.03);
    }

    .secondary-button {
      min-height: 42px;
      padding: 0 16px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
      cursor: pointer;
    }

    .form-status {
      margin: 0;
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.6;
    }

    .report-panel,
    .rail-card,
    .recent-panel {
      border-radius: 24px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
      overflow: hidden;
    }

    .report-panel {
      padding: 22px;
    }

    .report-panel.is-hot {
      box-shadow:
        0 0 0 1px rgba(215, 166, 74, 0.35),
        0 0 0 8px rgba(215, 166, 74, 0.06),
        var(--shadow);
      animation: report-pulse 1.2s ease-out;
    }

    @keyframes report-pulse {
      0% { transform: translateY(0); }
      35% { transform: translateY(-2px); }
      100% { transform: translateY(0); }
    }

    .report-head {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 18px;
    }

    .report-title {
      margin: 0;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: clamp(1.35rem, 2vw, 2rem);
      line-height: 1.15;
      text-wrap: balance;
    }

    .report-subtitle {
      margin: 10px 0 0;
      color: var(--muted-strong);
      line-height: 1.7;
      font-size: 0.95rem;
    }

    .report-badge {
      display: grid;
      gap: 4px;
      min-width: 164px;
      padding: 14px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--line);
      text-align: right;
    }

    .report-badge strong {
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 1.1rem;
    }

    .report-badge span {
      color: var(--muted);
      font-size: 0.78rem;
    }

    .divider {
      height: 1px;
      margin: 18px 0;
      background: linear-gradient(90deg, transparent, var(--line), transparent);
    }

    .evidence {
      display: grid;
      gap: 12px;
    }

    .evidence-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .evidence-row {
      min-width: 0;
      padding: 12px 13px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
    }

    .evidence-row .label {
      color: var(--muted);
      font-size: 0.76rem;
      margin-bottom: 6px;
    }

    .evidence-row .value {
      font-size: 0.92rem;
      line-height: 1.6;
      color: var(--text);
      overflow-wrap: anywhere;
    }

    .image-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .image-thumb {
      width: 88px;
      height: 88px;
      border-radius: 18px;
      border: 1px solid var(--line);
      overflow: hidden;
      background: rgba(255, 255, 255, 0.03);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }

    .image-thumb img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }

    .section-block {
      display: grid;
      gap: 10px;
    }

    .section-block h3 {
      margin: 0;
      font-size: 0.92rem;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      letter-spacing: 0.04em;
    }

    .copy-block,
    .notice-block,
    .info-block,
    .link-grid,
    .list-block {
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
      padding: 14px;
    }

    .copy-block {
      position: relative;
      display: grid;
      gap: 10px;
    }

    .copy-block blockquote {
      margin: 0;
      color: var(--text);
      line-height: 1.8;
      font-size: 0.96rem;
      padding-left: 14px;
      border-left: 3px solid rgba(215, 166, 74, 0.72);
    }

    .copy-actions {
      display: flex;
      justify-content: flex-end;
    }

    .ghost-button,
    .copy-button {
      min-height: 36px;
      padding: 0 12px;
      color: var(--text);
      font-size: 0.82rem;
    }

    .section-copy {
      margin: 0;
      color: var(--text);
      line-height: 1.8;
      font-size: 0.95rem;
    }

    .bullets {
      margin: 0;
      padding-left: 18px;
      color: var(--text);
      line-height: 1.8;
      font-size: 0.94rem;
    }

    .bullets li { margin-bottom: 6px; }

    .link-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .chip-link {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 0 12px;
      text-decoration: none;
      color: var(--text);
      font-size: 0.82rem;
      background: rgba(255, 255, 255, 0.03);
    }

    .info-list {
      display: grid;
      gap: 10px;
    }

    .info-item {
      padding: 12px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.03);
    }

    .info-item .topline {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 8px;
    }

    .info-item .category {
      color: #ffdca7;
      font-size: 0.74rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .info-item h4 {
      margin: 0;
      font-size: 0.92rem;
      line-height: 1.35;
      text-wrap: balance;
    }

    .info-item p {
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
      font-size: 0.84rem;
    }

    .rail {
      border-radius: var(--radius-xl);
      padding: 18px;
      display: grid;
      gap: 14px;
      align-content: start;
    }

    .rail-card {
      padding: 18px;
    }

    .rail-card h3 {
      margin: 0 0 10px;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 0.92rem;
      letter-spacing: 0.04em;
    }

    .gauge-wrap {
      display: grid;
      grid-template-columns: 128px minmax(0, 1fr);
      gap: 14px;
      align-items: center;
    }

    .gauge {
      width: 124px;
      height: 124px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background:
        conic-gradient(var(--accent) calc(var(--score) * 1%), rgba(255, 255, 255, 0.08) 0),
        radial-gradient(circle at center, rgba(255, 255, 255, 0.04) 0 58%, transparent 59%);
      border: 1px solid rgba(215, 166, 74, 0.28);
    }

    .gauge-core {
      width: 78px;
      height: 78px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      text-align: center;
      background: var(--panel-strong);
      border: 1px solid var(--line);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }

    .gauge-core strong {
      display: block;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 1.25rem;
      line-height: 1;
    }

    .gauge-core span {
      color: var(--muted);
      font-size: 0.72rem;
      margin-top: 2px;
    }

    .factor-list {
      margin: 0;
      padding-left: 18px;
      color: var(--muted-strong);
      line-height: 1.7;
      font-size: 0.84rem;
    }

    .help-card {
      display: grid;
      gap: 10px;
      border: 1px solid rgba(239, 68, 68, 0.28);
      background: linear-gradient(180deg, rgba(239, 68, 68, 0.12), rgba(255, 255, 255, 0.03));
    }

    .help-card p {
      margin: 0;
      line-height: 1.7;
      color: var(--muted-strong);
      font-size: 0.86rem;
    }

    .notice-block {
      border-color: rgba(251, 146, 60, 0.24);
      background: rgba(251, 146, 60, 0.08);
    }

    .notice-block strong {
      display: block;
      margin-bottom: 8px;
      color: #ffe6c7;
    }

    .recent-panel {
      padding: 18px;
    }

    .recent-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
    }

    .recent-head h3 {
      margin: 0;
      font-family: "Space Grotesk", "IBM Plex Sans JP", sans-serif;
      font-size: 0.92rem;
      letter-spacing: 0.04em;
    }

    .recent-list {
      display: grid;
      gap: 10px;
    }

    .recent-item {
      display: grid;
      gap: 8px;
      width: 100%;
      padding: 14px;
      text-align: left;
    }

    .recent-item .line1 {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .recent-item strong {
      font-size: 0.92rem;
    }

    .recent-item p {
      margin: 0;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.6;
    }

    .footer-note {
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.76rem;
      line-height: 1.7;
    }

    .empty-state,
    .loading-state {
      padding: 18px;
      border-radius: 18px;
      border: 1px dashed rgba(148, 163, 184, 0.24);
      color: var(--muted);
      line-height: 1.7;
      background: rgba(255, 255, 255, 0.02);
    }

    .hidden { display: none !important; }

    .toast {
      position: fixed;
      right: 22px;
      bottom: 22px;
      z-index: 20;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(15, 22, 31, 0.96);
      color: var(--text);
      box-shadow: var(--shadow);
      opacity: 0;
      transform: translateY(8px);
      transition: opacity 180ms ease, transform 180ms ease;
      pointer-events: none;
      max-width: min(420px, calc(100vw - 36px));
      font-size: 0.86rem;
      line-height: 1.6;
    }

    .toast.show {
      opacity: 1;
      transform: translateY(0);
    }

    @media (max-width: 1320px) {
      .shell {
        grid-template-columns: 248px minmax(0, 1fr);
      }
      .rail {
        grid-column: 1 / -1;
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
    }

    @media (max-width: 1080px) {
      .shell {
        grid-template-columns: 1fr;
      }
      .sidebar {
        order: 0;
      }
      .main {
        order: 1;
      }
      .rail {
        order: 2;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .workspace {
        grid-template-columns: 1fr;
      }
      .meta-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 760px) {
      .shell {
        padding: 12px;
        gap: 12px;
      }
      .sidebar,
      .main,
      .rail {
        border-radius: 22px;
      }
      .hero-top,
      .report-head,
      .recent-item .line1 {
        flex-direction: column;
        align-items: start;
      }
      .meta-grid,
      .entry-grid,
      .evidence-grid,
      .rail {
        grid-template-columns: 1fr;
      }
      .gauge-wrap {
        grid-template-columns: 1fr;
      }
      .report-badge {
        text-align: left;
        min-width: 0;
      }
      .entry-actions {
        flex-direction: column;
        align-items: stretch;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">SC</div>
        <div>
          <h1>{{ app_name }}</h1>
          <p>訪問買取・不用品回収の前に、焦らず確認するための防衛UI。</p>
        </div>
      </div>

      <div class="status-box">
        <span class="pill" id="apiStatus">API接続を確認中</span>
        <p class="status-copy">自動出品なし / 自動購入なし / 自動ログインなし / スクレイピングなし。</p>
        <span class="pill">API prefix <strong id="apiPrefix">{{ api_prefix }}</strong></span>
        <a class="chip-link" href="/mobile-preview">スマホ導線レビュー</a>
        <p class="status-copy">レビュー用スクショは /mobile-preview で保存できます。</p>
      </div>

      <nav class="nav" aria-label="チェックの切り替え">
        <button type="button" data-type="overview" class="active"><span>ダッシュボード</span><small>全体</small></button>
        <button type="button" data-type="flyer"><span>チラシチェック</span><small id="countFlyer">0</small></button>
        <button type="button" data-type="item"><span>商品チェック</span><small id="countItem">0</small></button>
        <button type="button" data-type="quote"><span>見積もりチェック</span><small id="countQuote">0</small></button>
        <button type="button" data-type="official"><span>公式情報</span><small id="countOfficial">0</small></button>
        <button type="button" data-type="report"><span>レポート</span><small id="countReport">0</small></button>
      </nav>

      <div class="safety-list">
        <div class="section-title">安全仕様</div>
        <ul>
          <li>特定業者を断定しない</li>
          <li>相場は参考表示のみ</li>
          <li>真贋・法律判断は断定しない</li>
          <li>188相談案内を必ず表示する</li>
        </ul>
      </div>
    </aside>

    <main class="main">
      <header class="hero">
        <div class="hero-top">
          <div>
            <div class="eyebrow">Consumer safety workbench</div>
            <h2>現場の判断を、先に止める。</h2>
            <p>チラシ・商品・見積もりのどこに危険があるかを先に見せて、<br>「今日は決めない」を言いやすくする下書き画面です。</p>
            <div class="hero-meta" id="heroMeta">
              <span class="pill">読み込み中</span>
            </div>
          </div>
          <div class="report-badge">
            <strong id="activeVerdictBadge">確認中</strong>
            <span id="activeVerdictHint">最新のチェックを読み込みます</span>
          </div>
        </div>
      </header>

      <section class="meta-grid" id="summaryMetrics">
        <div class="metric"><div class="label">判定</div><p class="value">読み込み中</p><div class="hint">最新のリスク判定</div></div>
        <div class="metric"><div class="label">信頼度</div><p class="value">--</p><div class="hint">判定の自信度</div></div>
        <div class="metric"><div class="label">不足情報</div><p class="value">--</p><div class="hint">追加確認が必要な点</div></div>
        <div class="metric"><div class="label">画像</div><p class="value">--</p><div class="hint">紐づくローカル画像</div></div>
      </section>

      <section class="workspace">
        <div class="workspace-main">
          <div class="segment-bar" id="typeTabs">
            <button type="button" class="active" data-type="overview">概要</button>
            <button type="button" data-type="flyer">チラシ</button>
            <button type="button" data-type="item">商品</button>
            <button type="button" data-type="quote">見積もり</button>
          </div>

          <section class="entry-panel" aria-label="新規登録エリア">
            <div class="entry-head">
              <div>
                <div class="eyebrow">quick intake</div>
                <h3 class="report-title">新規チェックを登録</h3>
                <p class="report-subtitle">入力して保存すると、そのまま判定・相場リンク・レポートに進みます。画像は保存後にローカルへ添付します。</p>
              </div>
              <div class="report-badge">
                <strong id="entryTypeLabel">チラシチェック</strong>
                <span>保存後に最新データへ反映</span>
              </div>
            </div>

            <div class="entry-tabs" id="entryTabs">
              <button type="button" class="active" data-entry-tab="flyer">チラシ</button>
              <button type="button" data-entry-tab="item">商品</button>
              <button type="button" data-entry-tab="quote">見積もり</button>
            </div>

            <p class="entry-note">保存前に迷ったら、空欄のままでも大丈夫です。分からないところはあとで埋められます。</p>

            <form class="entry-form" data-entry-form="flyer">
              <div class="entry-grid">
                <div class="entry-field">
                  <label for="flyer_company_name">業者名</label>
                  <input id="flyer_company_name" name="company_name" type="text" placeholder="例: サンプル訪問買取">
                </div>
                <div class="entry-field">
                  <label for="flyer_phone_number">電話番号</label>
                  <input id="flyer_phone_number" name="phone_number" type="text" placeholder="例: 03-1234-5678">
                </div>
                <div class="entry-field full">
                  <label for="flyer_flyer_text">チラシ文言</label>
                  <textarea id="flyer_flyer_text" name="flyer_text" placeholder="着物高価買取 / 出張査定無料 / 即日現金化"></textarea>
                </div>
                <div class="entry-field">
                  <label for="flyer_outcall_fee_text">出張費表記</label>
                  <input id="flyer_outcall_fee_text" name="outcall_fee_text" type="text" placeholder="例: 出張費無料">
                </div>
                <div class="entry-field">
                  <label for="flyer_cancellation_fee_text">キャンセル料表記</label>
                  <input id="flyer_cancellation_fee_text" name="cancellation_fee_text" type="text" placeholder="例: キャンセル料無料">
                </div>
                <div class="entry-field">
                  <label for="flyer_high_price_text">高価買取表記</label>
                  <input id="flyer_high_price_text" name="high_price_text" type="text" placeholder="例: 高価買取">
                </div>
                <div class="entry-field">
                  <label for="flyer_same_day_cash_text">即日現金化表記</label>
                  <input id="flyer_same_day_cash_text" name="same_day_cash_text" type="text" placeholder="例: その場で現金">
                </div>
                <div class="entry-field full">
                  <label for="flyer_inducement_text">誘導文言</label>
                  <input id="flyer_inducement_text" name="inducement_text" type="text" placeholder="例: 貴金属も査定 / ブランド品も査定">
                </div>
                <div class="entry-field full">
                  <label for="flyer_memo">メモ</label>
                  <textarea id="flyer_memo" name="memo" placeholder="気になった点や家族メモ"></textarea>
                </div>
                <div class="entry-field full">
                  <label for="flyer_images">チラシ画像</label>
                  <input id="flyer_images" name="images" type="file" accept="image/*" multiple>
                  <small>画像は登録後に順番に添付されます。</small>
                </div>
              </div>
              <div class="entry-actions">
                <p class="form-status" data-entry-status="flyer">未保存です。</p>
                <div class="action-group">
                  <button type="reset" class="secondary-button">クリア</button>
                  <button type="submit" class="primary-button">チラシを保存</button>
                </div>
              </div>
            </form>

            <form class="entry-form hidden" data-entry-form="item">
              <div class="entry-grid">
                <div class="entry-field">
                  <label for="item_item_category">商品カテゴリ</label>
                  <select id="item_item_category" name="item_category">
                    <option value="">選択してください</option>
                    <option value="着物">着物</option>
                    <option value="ミシン">ミシン</option>
                    <option value="貴金属">貴金属</option>
                    <option value="カメラ">カメラ</option>
                    <option value="時計・ブランド品">時計・ブランド品</option>
                    <option value="不用品回収対象品">不用品回収対象品</option>
                  </select>
                </div>
                <div class="entry-field">
                  <label for="item_item_name">商品名</label>
                  <input id="item_item_name" name="item_name" type="text" placeholder="例: JUKI ミシン">
                </div>
                <div class="entry-field">
                  <label for="item_brand">ブランド</label>
                  <input id="item_brand" name="brand" type="text" placeholder="例: JUKI">
                </div>
                <div class="entry-field">
                  <label for="item_model_number">型番</label>
                  <input id="item_model_number" name="model_number" type="text" placeholder="不明なら空欄でOK">
                </div>
                <div class="entry-field full">
                  <label for="item_condition_note">状態</label>
                  <textarea id="item_condition_note" name="condition_note" placeholder="動作未確認 / キズあり / 付属品欠品 など"></textarea>
                </div>
                <div class="entry-field full">
                  <label for="item_accessories">付属品</label>
                  <input id="item_accessories" name="accessories" type="text" placeholder="例: フットコントローラー、ケース、説明書">
                </div>
                <div class="entry-field">
                  <label for="item_offered_price">業者提示額</label>
                  <input id="item_offered_price" name="offered_price" type="number" min="0" step="1" placeholder="例: 1000">
                </div>
                <div class="entry-field">
                  <label for="item_market_memo">相場メモ</label>
                  <input id="item_market_memo" name="market_memo" type="text" placeholder="例: 型番不明 / 相場は幅広い">
                </div>
                <div class="entry-field full">
                  <label for="item_additional_photo_requests">追加で撮るべき写真</label>
                  <textarea id="item_additional_photo_requests" name="additional_photo_requests" placeholder="証紙、刻印、型番、裏面、通電確認など"></textarea>
                </div>
                <div class="entry-field full">
                  <label for="item_check_points">確認ポイント</label>
                  <textarea id="item_check_points" name="check_points" placeholder="着物なら証紙、ミシンなら動作確認、貴金属なら刻印..."></textarea>
                </div>
                <div class="entry-field full">
                  <label for="item_memo">メモ</label>
                  <textarea id="item_memo" name="memo" placeholder="追加で気づいたこと"></textarea>
                </div>
                <div class="entry-field full">
                  <label for="item_images">商品画像</label>
                  <input id="item_images" name="images" type="file" accept="image/*" multiple>
                  <small>箱・付属品・刻印・型番の写真があると判定しやすくなります。</small>
                </div>
              </div>
              <div class="entry-actions">
                <p class="form-status" data-entry-status="item">未保存です。</p>
                <div class="action-group">
                  <button type="reset" class="secondary-button">クリア</button>
                  <button type="submit" class="primary-button">商品を保存</button>
                </div>
              </div>
            </form>

            <form class="entry-form hidden" data-entry-form="quote">
              <div class="entry-grid">
                <div class="entry-field">
                  <label for="quote_offered_price">業者提示額</label>
                  <input id="quote_offered_price" name="offered_price" type="number" min="0" step="1" placeholder="例: 9800">
                </div>
                <div class="entry-field">
                  <label for="quote_work_fee">作業費</label>
                  <input id="quote_work_fee" name="work_fee" type="number" min="0" step="1" placeholder="例: 3000">
                </div>
                <div class="entry-field">
                  <label for="quote_disposal_fee">処分費</label>
                  <input id="quote_disposal_fee" name="disposal_fee" type="number" min="0" step="1" placeholder="例: 5000">
                </div>
                <div class="entry-field">
                  <label for="quote_outcall_fee">出張費</label>
                  <input id="quote_outcall_fee" name="outcall_fee" type="number" min="0" step="1" placeholder="例: 0">
                </div>
                <div class="entry-field">
                  <label for="quote_appraisal_fee">査定料</label>
                  <input id="quote_appraisal_fee" name="appraisal_fee" type="number" min="0" step="1" placeholder="例: 0">
                </div>
                <div class="entry-field">
                  <label for="quote_cancellation_fee">キャンセル料</label>
                  <input id="quote_cancellation_fee" name="cancellation_fee" type="number" min="0" step="1" placeholder="例: 0">
                </div>
                <div class="entry-field">
                  <label for="quote_home_appliance_recycling_fee">家電リサイクル料金</label>
                  <input id="quote_home_appliance_recycling_fee" name="home_appliance_recycling_fee" type="text" placeholder="例: 対象品の扱い不明">
                </div>
                <div class="entry-field">
                  <label for="quote_additional_charge_conditions">追加料金条件</label>
                  <input id="quote_additional_charge_conditions" name="additional_charge_conditions" type="text" placeholder="例: 当日追加請求あり">
                </div>
                <div class="entry-field">
                  <label for="quote_package_price">パック料金</label>
                  <input id="quote_package_price" name="package_price" type="number" min="0" step="1" placeholder="例: 9800">
                </div>
                <div class="entry-field">
                  <label for="quote_same_day_extra_charge">当日追加請求</label>
                  <input id="quote_same_day_extra_charge" name="same_day_extra_charge" type="number" min="0" step="1" placeholder="例: 80000">
                </div>
                <div class="entry-field full">
                  <label class="checkbox-line" for="quote_estimate_sheet_present">
                    <input id="quote_estimate_sheet_present" name="estimate_sheet_present" type="checkbox">
                    見積書・明細あり
                  </label>
                </div>
                <div class="entry-field full">
                  <label for="quote_memo">メモ</label>
                  <textarea id="quote_memo" name="memo" placeholder="軽トラックパック9,800円 / 当日80,000円など"></textarea>
                </div>
                <div class="entry-field full">
                  <label for="quote_images">見積もり画像</label>
                  <input id="quote_images" name="images" type="file" accept="image/*" multiple>
                  <small>見積書、作業明細、当日メモの写真を添付できます。</small>
                </div>
              </div>
              <div class="entry-actions">
                <p class="form-status" data-entry-status="quote">未保存です。</p>
                <div class="action-group">
                  <button type="reset" class="secondary-button">クリア</button>
                  <button type="submit" class="primary-button">見積もりを保存</button>
                </div>
              </div>
            </form>
          </section>

          <article class="report-panel" id="reportPanel">
            <div class="loading-state">最新データを読み込み中です。</div>
          </article>

          <section class="recent-panel" id="recentPanel">
            <div class="recent-head">
              <h3>最近のチェック</h3>
              <span class="pill">クリックで切り替え</span>
            </div>
            <div class="recent-list" id="recentList">
              <div class="loading-state">読み込み中...</div>
            </div>
          </section>
        </div>

        <aside class="rail">
          <section class="rail-card" id="confidenceRail">
            <h3>信頼度</h3>
            <div class="gauge-wrap">
              <div class="gauge" style="--score: 0">
                <div class="gauge-core">
                  <strong>--</strong>
                  <span>score</span>
                </div>
              </div>
              <div>
                <p class="status-copy" id="confidenceLabel">読み込み中</p>
                <ul class="factor-list" id="confidenceFactors">
                  <li>読み込み中</li>
                </ul>
              </div>
            </div>
          </section>

          <section class="rail-card" id="officialRail">
            <h3>公式情報</h3>
            <div class="info-list" id="officialList">
              <div class="loading-state">読み込み中...</div>
            </div>
          </section>

          <section class="rail-card" id="refusalRail">
            <h3>断り文例</h3>
            <div class="copy-block">
              <blockquote id="refusalPhrase">読み込み中...</blockquote>
              <div class="copy-actions">
                <button type="button" class="copy-button" id="copyRefusalButton">コピー</button>
              </div>
            </div>
          </section>

          <section class="rail-card help-card">
            <h3>188相談案内</h3>
            <p id="hotlineNotice">消費者ホットライン188へ相談できることを、いつでも見える位置に置いておきます。</p>
          </section>
        </aside>
      </section>
    </main>
  </div>

  <div class="toast" id="toast"></div>

  <script>
    const API_BASE = "{{ api_prefix }}";
    const state = {
      health: null,
      checks: { flyer: [], item: [], quote: [] },
      officialInfos: [],
      activeType: "overview",
      activeEntryType: "flyer",
      activeCheck: null,
    };

    const labels = {
      flyer: "チラシチェック",
      item: "商品チェック",
      quote: "見積もりチェック",
      overview: "ダッシュボード",
      report: "レポート",
      official: "公式情報",
    };

    const verdictClassMap = {
      "問題なさそう": "ok",
      "確認推奨": "review",
      "即決注意": "warn",
      "相談推奨": "danger",
    };

    const checkOrder = ["quote", "item", "flyer"];
    const checkPathMap = {
      flyer: "flyer-checks",
      item: "item-checks",
      quote: "quote-checks",
    };

    const htmlEscapeMap = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };

    const navButtons = Array.from(document.querySelectorAll("[data-type]"));
    const typeTabs = Array.from(document.querySelectorAll("#typeTabs [data-type]"));
    const entryTabs = Array.from(document.querySelectorAll("[data-entry-tab]"));
    const entryForms = Array.from(document.querySelectorAll("[data-entry-form]"));

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => htmlEscapeMap[char] || char);
    }

    function formatDate(value) {
      if (!value) return "日時不明";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return new Intl.DateTimeFormat("ja-JP", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
    }

    function formatMoney(value) {
      if (value === null || value === undefined || value === "") return "未入力";
      const numeric = Number(value);
      if (Number.isNaN(numeric)) return String(value);
      return `${new Intl.NumberFormat("ja-JP").format(numeric)}円`;
    }

    function latest(list) {
      return Array.isArray(list) && list.length ? list[0] : null;
    }

    function countOf(list) {
      return Array.isArray(list) ? list.length : 0;
    }

    function setActiveEntryType(type) {
      state.activeEntryType = type;
      entryTabs.forEach((button) => {
        button.classList.toggle("active", button.dataset.entryTab === type);
      });
      entryForms.forEach((form) => {
        form.classList.toggle("hidden", form.dataset.entryForm !== type);
      });
      const label = document.getElementById("entryTypeLabel");
      if (label) {
        label.textContent = labels[type] || "チェック";
      }
    }

    function entryStatusElement(type) {
      return document.querySelector(`[data-entry-status="${type}"]`);
    }

    function setEntryStatus(type, message) {
      const status = entryStatusElement(type);
      if (status) {
        status.textContent = message;
      }
    }

    function readEntryText(form, name) {
      const field = form.querySelector(`[name="${name}"]`);
      const value = field && typeof field.value === "string" ? field.value.trim() : "";
      return value || null;
    }

    function readEntryNumber(form, name) {
      const raw = readEntryText(form, name);
      if (!raw) {
        return null;
      }
      const numeric = Number(String(raw).replace(/[^\\d-]/g, ""));
      return Number.isFinite(numeric) ? numeric : null;
    }

    function readEntryBoolean(form, name) {
      const field = form.querySelector(`[name="${name}"]`);
      return Boolean(field && field.checked);
    }

    function buildEntryPayload(type, form) {
      if (type === "flyer") {
        return {
          company_name: readEntryText(form, "company_name"),
          phone_number: readEntryText(form, "phone_number"),
          flyer_text: readEntryText(form, "flyer_text"),
          outcall_fee_text: readEntryText(form, "outcall_fee_text"),
          cancellation_fee_text: readEntryText(form, "cancellation_fee_text"),
          high_price_text: readEntryText(form, "high_price_text"),
          same_day_cash_text: readEntryText(form, "same_day_cash_text"),
          inducement_text: readEntryText(form, "inducement_text"),
          memo: readEntryText(form, "memo"),
        };
      }
      if (type === "item") {
        return {
          item_category: readEntryText(form, "item_category"),
          item_name: readEntryText(form, "item_name"),
          brand: readEntryText(form, "brand"),
          model_number: readEntryText(form, "model_number"),
          condition_note: readEntryText(form, "condition_note"),
          accessories: readEntryText(form, "accessories"),
          offered_price: readEntryNumber(form, "offered_price"),
          market_memo: readEntryText(form, "market_memo"),
          additional_photo_requests: readEntryText(form, "additional_photo_requests"),
          check_points: readEntryText(form, "check_points"),
          memo: readEntryText(form, "memo"),
        };
      }
      return {
        offered_price: readEntryNumber(form, "offered_price"),
        work_fee: readEntryNumber(form, "work_fee"),
        disposal_fee: readEntryNumber(form, "disposal_fee"),
        outcall_fee: readEntryNumber(form, "outcall_fee"),
        appraisal_fee: readEntryNumber(form, "appraisal_fee"),
        cancellation_fee: readEntryNumber(form, "cancellation_fee"),
        home_appliance_recycling_fee: readEntryText(form, "home_appliance_recycling_fee"),
        additional_charge_conditions: readEntryText(form, "additional_charge_conditions"),
        package_price: readEntryNumber(form, "package_price"),
        same_day_extra_charge: readEntryNumber(form, "same_day_extra_charge"),
        estimate_sheet_present: readEntryBoolean(form, "estimate_sheet_present"),
        memo: readEntryText(form, "memo"),
      };
    }

    async function postJson(path, payload) {
      const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        let detail = `${path} (${response.status})`;
        try {
          const errorJson = await response.json();
          if (errorJson?.detail) {
            detail = Array.isArray(errorJson.detail) ? errorJson.detail.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join(" / ") : String(errorJson.detail);
          }
        } catch (_) {
          // ignore parsing failures and fall back to status text
        }
        throw new Error(detail);
      }
      return response.json();
    }

    async function uploadEntryImages(type, checkId, files) {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        const formData = new FormData();
        formData.append("check_type", type);
        formData.append("check_id", String(checkId));
        formData.append("file", file);
        formData.append("sort_order", String(index));

        const response = await fetch(`${API_BASE}/images/upload`, {
          method: "POST",
          body: formData,
        });
        if (!response.ok) {
          throw new Error(`画像アップロードに失敗しました: ${file.name}`);
        }
      }
    }

    async function submitEntryForm(type, form) {
      const submitButton = form.querySelector('button[type="submit"]');
      const fileInput = form.querySelector('input[type="file"]');
      const files = fileInput && fileInput.files ? Array.from(fileInput.files) : [];
      const payload = buildEntryPayload(type, form);

      setEntryStatus(type, "保存中...");
      if (submitButton) {
        submitButton.disabled = true;
      }

      try {
        const created = await postJson(`/${checkPathMap[type]}`, payload);
        if (files.length) {
          await uploadEntryImages(type, created.id, files);
        }
        form.reset();
        setEntryStatus(type, "保存しました。レポートへ移動しています...");
        await loadData({ focusType: type, entryType: type });
        setActiveEntryType(type);
        focusReportPanel();
        showToast(`${labels[type]}を保存しました`);
      } catch (error) {
        console.error(error);
        setEntryStatus(type, `保存に失敗しました: ${error.message}`);
        showToast("保存に失敗しました");
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
        }
      }
    }

    function reportForCheck(check) {
      const latestReport = check?.latest_report?.content_json || null;
      const latestConfidence = check?.latest_confidence_score || null;
      const latestJudgement = check?.latest_risk_judgement || null;

      if (latestReport) {
        return latestReport;
      }

      const fallbackConfidence = latestConfidence || {};
      const fallbackJudgement = latestJudgement || {};
      return {
        check: check || {},
        judgement: fallbackJudgement.judgement_result || "確認推奨",
        reason: fallbackJudgement.reason || "情報が不足しているため、まずは追加確認をおすすめします。",
        missing_info: fallbackJudgement.missing_info || [],
        next_actions: fallbackJudgement.next_actions || [],
        refusal_phrase: fallbackJudgement.refusal_phrase || "",
        market_links: fallbackJudgement.market_links || {},
        official_infos: fallbackJudgement.official_infos || [],
        hotline_notice: "消費者ホットライン188へ相談する。",
        caution_notes: fallbackJudgement.caution_notes || [],
        confidence: {
          score: fallbackConfidence.score_value || 0,
          label: fallbackConfidence.score_label || "low",
        },
        disclaimer: "相場や判定は参考です。法律判断や真贋の断定は行いません。",
      };
    }

    function checkSummary(check, type) {
      if (!check) return "データなし";
      if (type === "flyer") {
        const company = check.company_name || "業者名未入力";
        const text = check.flyer_text || check.high_price_text || "文言未入力";
        return `${company} · ${text}`;
      }
      if (type === "item") {
        const title = check.item_name || check.item_category || "商品";
        const brand = check.brand || "ブランド未入力";
        return `${title} · ${brand}`;
      }
      const price = check.package_price || check.offered_price || check.same_day_extra_charge || "金額未入力";
      return `${formatMoney(price)} / 当日追加請求の確認`;
    }

    function checkTitle(check, type) {
      if (!check) return labels[type] || "チェック";
      if (type === "flyer") return check.company_name || "チラシチェック";
      if (type === "item") return check.item_name || check.item_category || "商品チェック";
      return "見積もりチェック";
    }

    function imageHtml(check) {
      const images = Array.isArray(check?.image_refs) ? check.image_refs : [];
      if (!images.length) {
        return '<div class="empty-state">画像がまだありません。チラシ画像や商品写真をアップすると、ここに並びます。</div>';
      }
      return `
        <div class="image-strip">
          ${images.slice(0, 4).map((image) => `
            <a class="image-thumb" href="${escapeHtml(image.public_url)}" target="_blank" rel="noreferrer" title="${escapeHtml(image.original_filename || "画像")}">
              <img src="${escapeHtml(image.public_url)}" alt="${escapeHtml(image.original_filename || "画像")}">
            </a>
          `).join("")}
        </div>
      `;
    }

    function evidenceRows(check, type) {
      const rows = [];
      if (type === "flyer") {
        rows.push(["業者名", check.company_name || "未入力"]);
        rows.push(["電話番号", check.phone_number || "未入力"]);
        rows.push(["チラシ文言", check.flyer_text || "未入力"]);
        rows.push(["出張費表記", check.outcall_fee_text || "未入力"]);
        rows.push(["キャンセル料表記", check.cancellation_fee_text || "未入力"]);
        rows.push(["高価買取表記", check.high_price_text || "未入力"]);
        rows.push(["即日現金化", check.same_day_cash_text || "未入力"]);
        rows.push(["誘導文言", check.inducement_text || "未入力"]);
        rows.push(["メモ", check.memo || "未入力"]);
      } else if (type === "item") {
        rows.push(["商品カテゴリ", check.item_category || "未入力"]);
        rows.push(["商品名", check.item_name || "未入力"]);
        rows.push(["ブランド", check.brand || "未入力"]);
        rows.push(["型番", check.model_number || "不明"]);
        rows.push(["状態", check.condition_note || "未入力"]);
        rows.push(["付属品", check.accessories || "未入力"]);
        rows.push(["業者提示額", formatMoney(check.offered_price)]);
        rows.push(["相場メモ", check.market_memo || "未入力"]);
        rows.push(["追加で撮るべき写真", check.additional_photo_requests_text || "未入力"]);
        rows.push(["確認ポイント", check.check_points_text || "未入力"]);
        rows.push(["メモ", check.memo || "未入力"]);
      } else if (type === "quote") {
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
        rows.push(["メモ", check.memo || "未入力"]);
      }
      return rows;
    }

    function renderEvidence(check, type) {
      return `
        <div class="evidence">
          <div class="image-strip">${imageHtml(check)}</div>
          <div class="evidence-grid">
            ${evidenceRows(check, type).map(([label, value]) => `
              <div class="evidence-row">
                <div class="label">${escapeHtml(label)}</div>
                <div class="value">${escapeHtml(value)}</div>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    }

    function toneFor(verdict) {
      return verdictClassMap[verdict] || "review";
    }

    function renderReportPanel(type, check) {
      const report = reportForCheck(check);
      const verdict = report.judgement || "確認推奨";
      const tone = toneFor(verdict);
      const confidence = report.confidence || {};
      const confidenceScore = Number(confidence.score ?? 0);
      const confidenceLabel = confidence.label || "unknown";
      const officialInfos = Array.isArray(report.official_infos) ? report.official_infos : [];
      const missingInfo = Array.isArray(report.missing_info) ? report.missing_info : [];
      const nextActions = Array.isArray(report.next_actions) ? report.next_actions : [];
      const cautionNotes = Array.isArray(report.caution_notes) ? report.caution_notes : [];
      const marketLinks = report.market_links || {};
      const title = checkTitle(check, type);
      const summary = checkSummary(check, type);
      const createdAt = check?.created_at ? formatDate(check.created_at) : "日時不明";
      const refusalPhrase = report.refusal_phrase || "今日はこの場で決めず、家族と確認してから判断します。";
      const hotlineNotice = report.hotline_notice || "消費者ホットライン188へ相談する。";
      const disclaimer = report.disclaimer || "相場や判定は参考です。法律判断や真贋の断定は行いません。";
      const imageCount = countOf(check?.image_refs);

      document.getElementById("activeVerdictBadge").textContent = verdict;
      document.getElementById("activeVerdictHint").textContent = report.reason || "追加確認をおすすめします";

      document.getElementById("heroMeta").innerHTML = `
        <span class="verdict-chip ${tone}">${escapeHtml(verdict)}</span>
        <span class="pill">信頼度 <strong>${confidenceScore}</strong> / ${escapeHtml(confidenceLabel)}</span>
        <span class="pill">画像 <strong>${imageCount}</strong></span>
        <span class="pill">${escapeHtml(createdAt)}</span>
      `;

      const metrics = document.getElementById("summaryMetrics");
      metrics.innerHTML = `
        <div class="metric">
          <div class="label">判定</div>
          <p class="value">${escapeHtml(verdict)}</p>
          <div class="hint">${escapeHtml(summary)}</div>
        </div>
        <div class="metric">
          <div class="label">信頼度</div>
          <p class="value">${confidenceScore}</p>
          <div class="hint">${escapeHtml(confidenceLabel)}</div>
        </div>
        <div class="metric">
          <div class="label">不足情報</div>
          <p class="value">${missingInfo.length}</p>
          <div class="hint">${escapeHtml(missingInfo[0] || "なし")}</div>
        </div>
        <div class="metric">
          <div class="label">画像</div>
          <p class="value">${imageCount}</p>
          <div class="hint">ローカル保存の証拠画像</div>
        </div>
      `;

      document.getElementById("reportPanel").innerHTML = `
        <div class="report-head">
          <div>
            <div class="eyebrow">active check</div>
            <h3 class="report-title">${escapeHtml(title)}</h3>
            <p class="report-subtitle">${escapeHtml(summary)}<br>更新: ${escapeHtml(createdAt)} / チェック種別: ${escapeHtml(labels[type] || type)}</p>
          </div>
          <div class="report-badge">
            <strong class="${tone}">${escapeHtml(verdict)}</strong>
            <span>${escapeHtml(report.reason || "理由を読み込んでいます")}</span>
          </div>
        </div>

        <div class="divider"></div>

        <div class="evidence">
          <div class="section-block">
            <h3>証拠と入力内容</h3>
            ${renderEvidence(check, type)}
          </div>

          <div class="section-block">
            <h3>判定理由</h3>
            <div class="copy-block">
              <p class="section-copy">${escapeHtml(report.reason || "理由はまだありません。")}</p>
            </div>
          </div>

          <div class="section-block">
            <h3>不足情報</h3>
            <div class="list-block">
              ${missingInfo.length ? `<ul class="bullets">${missingInfo.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : '<p class="section-copy">なし</p>'}
            </div>
          </div>

          <div class="section-block">
            <h3>次にやること</h3>
            <div class="list-block">
              ${nextActions.length ? `<ul class="bullets">${nextActions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : '<p class="section-copy">なし</p>'}
            </div>
          </div>

          <div class="section-block">
            <h3>断り文例</h3>
            <div class="copy-block">
              <blockquote id="refusalPhraseMain">${escapeHtml(refusalPhrase)}</blockquote>
              <div class="copy-actions">
                <button type="button" class="copy-button" id="copyPhraseMain">コピー</button>
              </div>
            </div>
          </div>

          <div class="section-block">
            <h3>相場リンク</h3>
            <div class="link-grid">
              ${
                Object.entries(marketLinks).length
                  ? Object.entries(marketLinks).map(([name, url]) => `
                    <a class="chip-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(name)}</a>
                  `).join("")
                  : '<span class="section-copy">なし</span>'
              }
            </div>
          </div>

          <div class="section-block">
            <h3>公式情報</h3>
            <div class="info-list">
              ${
                officialInfos.length
                  ? officialInfos.slice(0, 4).map((info) => `
                    <div class="info-item">
                      <div class="topline">
                        <span class="category">${escapeHtml(info.category || "official")}</span>
                        <span class="pill">${escapeHtml((info.reference_links || []).length ? `${info.reference_links.length} links` : "参考")}</span>
                      </div>
                      <h4>${escapeHtml(info.title || "")}</h4>
                      <p>${escapeHtml(info.summary || "")}</p>
                    </div>
                  `).join("")
                  : '<div class="empty-state">公式情報はまだありません。</div>'
              }
            </div>
          </div>

          <div class="section-block">
            <h3>188相談案内</h3>
            <div class="notice-block">
              <strong>消費者ホットライン188</strong>
              <p class="section-copy">${escapeHtml(hotlineNotice)}</p>
            </div>
          </div>

          <div class="section-block">
            <h3>注意文</h3>
            <div class="notice-block">
              <strong>法令適合を保証しない</strong>
              <p class="section-copy">${escapeHtml(disclaimer)}</p>
            </div>
          </div>

          ${cautionNotes.length ? `
            <div class="section-block">
              <h3>補足メモ</h3>
              <div class="list-block">
                <ul class="bullets">${cautionNotes.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
              </div>
            </div>
          ` : ""}
        </div>
      `;

      const copyButton = document.getElementById("copyPhraseMain");
      if (copyButton) {
        copyButton.addEventListener("click", () => copyText(refusalPhrase, "断り文例をコピーしました"));
      }

      document.getElementById("confidenceRail").innerHTML = `
        <h3>信頼度</h3>
        <div class="gauge-wrap">
          <div class="gauge" style="--score: ${Math.max(0, Math.min(100, confidenceScore))}">
            <div class="gauge-core">
              <strong>${confidenceScore}</strong>
              <span>${escapeHtml(confidenceLabel)}</span>
            </div>
          </div>
          <div>
            <p class="status-copy">${escapeHtml(report.reason || "理由がまだありません。")}</p>
            <ul class="factor-list">
              ${
                (confidence.factors || []).length
                  ? confidence.factors.map((factor) => `<li>${escapeHtml(factor)}</li>`).join("")
                  : "<li>要因はまだありません</li>"
              }
            </ul>
          </div>
        </div>
      `;

      document.getElementById("officialRail").innerHTML = `
        <h3>公式情報</h3>
        <div class="info-list">
          ${
            officialInfos.length
              ? officialInfos.slice(0, 3).map((info) => `
                <div class="info-item">
                  <div class="topline">
                    <span class="category">${escapeHtml(info.category || "official")}</span>
                    <span class="pill">${escapeHtml((info.reference_links || []).length ? "参照可" : "参照なし")}</span>
                  </div>
                  <h4>${escapeHtml(info.title || "")}</h4>
                  <p>${escapeHtml(info.summary || "")}</p>
                </div>
              `).join("")
              : '<div class="empty-state">公式情報はまだありません。</div>'
          }
        </div>
      `;

      document.getElementById("refusalPhrase").textContent = refusalPhrase;
      document.getElementById("hotlineNotice").textContent = hotlineNotice;
      document.getElementById("copyRefusalButton").onclick = () => copyText(refusalPhrase, "断り文例をコピーしました");
    }

    function renderRecent() {
      const recentList = document.getElementById("recentList");
      const cards = checkOrder
        .map((type) => {
          const check = latest(state.checks[type]);
          if (!check) return null;
          const report = reportForCheck(check);
          const verdict = report.judgement || "確認推奨";
          const tone = toneFor(verdict);
          return `
            <button type="button" class="recent-item nav button ghost-button" data-open-type="${type}">
              <div class="line1">
                <strong>${escapeHtml(labels[type])}</strong>
                <span class="verdict-chip ${tone}">${escapeHtml(verdict)}</span>
              </div>
              <p>${escapeHtml(checkSummary(check, type))}</p>
            </button>
          `;
        })
        .filter(Boolean);

      recentList.innerHTML = cards.length ? cards.join("") : '<div class="empty-state">まだチェックがありません。</div>';
      Array.from(document.querySelectorAll("[data-open-type]")).forEach((button) => {
        button.addEventListener("click", () => setActiveType(button.dataset.openType));
      });
    }

    function renderTabs() {
      [...navButtons, ...typeTabs].forEach((button) => {
        const type = button.dataset.type;
        button.classList.toggle("active", type === state.activeType);
      });
    }

    function renderCounts() {
      document.getElementById("countFlyer").textContent = String(countOf(state.checks.flyer));
      document.getElementById("countItem").textContent = String(countOf(state.checks.item));
      document.getElementById("countQuote").textContent = String(countOf(state.checks.quote));
      document.getElementById("countOfficial").textContent = String(countOf(state.officialInfos));
      document.getElementById("countReport").textContent = String(
        countOf(state.checks.flyer) + countOf(state.checks.item) + countOf(state.checks.quote)
      );
    }

    function renderOverview() {
      const hasData = ["flyer", "item", "quote"].some((type) => countOf(state.checks[type]) > 0);
      if (!hasData) {
        document.getElementById("reportPanel").innerHTML = `
          <div class="empty-state">
            データをまだ読み込めませんでした。APIと seed を確認してください。
          </div>
        `;
        return;
      }
      const firstType = checkOrder.find((type) => countOf(state.checks[type]) > 0) || "flyer";
      setActiveType(firstType, { skipRenderTabs: true });
    }

    function setActiveType(type, options = {}) {
      state.activeType = type;
      state.activeCheck = type === "overview" || type === "report" || type === "official" ? null : latest(state.checks[type]);

      if (!options.preserveEntryTab && checkPathMap[type]) {
        setActiveEntryType(type);
      }

      if (!options.skipRenderTabs) {
        renderTabs();
      }

      if (type === "overview") {
        renderOverviewState();
        return;
      }
      if (type === "official") {
        renderOfficialFocus();
        return;
      }
      if (type === "report") {
        renderReportFocus();
        return;
      }
      renderReportPanel(type, state.activeCheck);
    }

    function renderOverviewState() {
      const mostRecent = checkOrder.map((type) => latest(state.checks[type])).find(Boolean);
      if (!mostRecent) {
        renderOverview();
        return;
      }
      renderReportPanel(state.checks.quote[0] ? "quote" : state.checks.item[0] ? "item" : "flyer", mostRecent);
    }

    function renderOfficialFocus() {
      const firstOfficial = state.officialInfos[0];
      const officialInfos = state.officialInfos.slice(0, 6);
      document.getElementById("reportPanel").innerHTML = `
        <div class="report-head">
          <div>
            <div class="eyebrow">official info desk</div>
            <h3 class="report-title">公式情報を先に読む</h3>
            <p class="report-subtitle">訪問購入、クーリングオフ、一般廃棄物、家電リサイクル、古物商、188 相談案内をひとまとめにした参照画面です。</p>
          </div>
          <div class="report-badge">
            <strong>${escapeHtml(countOf(state.officialInfos))}</strong>
            <span>official entries</span>
          </div>
        </div>
        <div class="divider"></div>
        <div class="info-list">
          ${
            officialInfos.length
              ? officialInfos.map((info) => `
                <div class="info-item">
                  <div class="topline">
                    <span class="category">${escapeHtml(info.category || "official")}</span>
                    <span class="pill">${escapeHtml((info.reference_links || []).length ? "リンクあり" : "リンクなし")}</span>
                  </div>
                  <h4>${escapeHtml(info.title || "")}</h4>
                  <p>${escapeHtml(info.summary || "")}</p>
                </div>
              `).join("")
              : '<div class="empty-state">公式情報がまだありません。</div>'
          }
        </div>
        ${firstOfficial ? `
          <div class="divider"></div>
          <div class="notice-block">
            <strong>いちばん上の参照</strong>
            <p class="section-copy">${escapeHtml(firstOfficial.title || "")}</p>
          </div>
        ` : ""}
      `;
    }

    function renderReportFocus() {
      const reportCheck = state.checks.quote[0] || state.checks.item[0] || state.checks.flyer[0] || null;
      if (reportCheck) {
        renderReportPanel(state.checks.quote[0] ? "quote" : state.checks.item[0] ? "item" : "flyer", reportCheck);
        return;
      }
      document.getElementById("reportPanel").innerHTML = '<div class="empty-state">レポートの元になるチェックがまだありません。</div>';
    }

    function renderHealth(health) {
      const status = health?.status || "ok";
      const service = health?.service || "{{ app_name }}";
      document.getElementById("apiStatus").innerHTML = `API <strong>${escapeHtml(status)}</strong> · ${escapeHtml(service)}`;
    }

    function copyText(text, message) {
      if (!text) {
        showToast("コピーする内容がありません");
        return;
      }
      navigator.clipboard.writeText(text)
        .then(() => showToast(message))
        .catch(() => showToast("コピーに失敗しました"));
    }

    let toastTimer = null;
    let reportFocusTimer = null;
    function showToast(message) {
      const toast = document.getElementById("toast");
      toast.textContent = message;
      toast.classList.add("show");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast.classList.remove("show"), 2000);
    }

    function focusReportPanel() {
      const panel = document.getElementById("reportPanel");
      if (!panel) {
        return;
      }
      panel.classList.add("is-hot");
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
      clearTimeout(reportFocusTimer);
      reportFocusTimer = setTimeout(() => {
        panel.classList.remove("is-hot");
      }, 1200);
    }

    async function fetchJson(path) {
      const response = await fetch(`${API_BASE}${path}`);
      if (!response.ok) {
        throw new Error(`${path} (${response.status})`);
      }
      return response.json();
    }

    async function loadData(options = {}) {
      const focusType = options.focusType || "overview";
      const entryType = options.entryType || state.activeEntryType || "flyer";
      try {
        const [health, flyers, items, quotes, officialInfos] = await Promise.all([
          fetchJson("/health"),
          fetchJson("/flyer-checks").catch(() => []),
          fetchJson("/item-checks").catch(() => []),
          fetchJson("/quote-checks").catch(() => []),
          fetchJson("/official-info").catch(() => []),
        ]);

        state.health = health;
        state.checks.flyer = Array.isArray(flyers) ? flyers : [];
        state.checks.item = Array.isArray(items) ? items : [];
        state.checks.quote = Array.isArray(quotes) ? quotes : [];
        state.officialInfos = Array.isArray(officialInfos) ? officialInfos : [];

        renderHealth(health);
        renderCounts();
        renderTabs();
        renderRecent();
        setActiveEntryType(entryType);
        setActiveType(focusType, { preserveEntryTab: true });
      } catch (error) {
        console.error(error);
        document.getElementById("apiStatus").innerHTML = 'API <strong>error</strong>';
        document.getElementById("reportPanel").innerHTML = `
          <div class="empty-state">
            データの読み込みに失敗しました。API が起動しているか確認してください。
          </div>
        `;
        showToast("データの読み込みに失敗しました");
      }
    }

    navButtons.forEach((button) => {
      button.addEventListener("click", () => setActiveType(button.dataset.type));
    });
    typeTabs.forEach((button) => {
      button.addEventListener("click", () => setActiveType(button.dataset.type));
    });
    entryTabs.forEach((button) => {
      button.addEventListener("click", () => setActiveEntryType(button.dataset.entryTab));
    });
    entryForms.forEach((form) => {
      const type = form.dataset.entryForm;
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        await submitEntryForm(type, form);
      });
      form.addEventListener("reset", () => {
        window.setTimeout(() => setEntryStatus(type, "未保存です。"), 0);
      });
    });
    document.getElementById("copyRefusalButton").addEventListener("click", () => copyText(document.getElementById("refusalPhrase").textContent, "断り文例をコピーしました"));

    loadData();
  </script>
</body>
</html>
    """
)


def render_dashboard_html(settings: AppSettings) -> str:
    return _DASHBOARD_TEMPLATE.render(
        app_name=settings.app_name,
        api_prefix=settings.api_prefix,
    )
