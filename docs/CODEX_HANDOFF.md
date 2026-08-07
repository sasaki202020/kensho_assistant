# Codex Handoff

この文書は `kensho_assistant` の引き継ぎ用メモです。
次の担当者がまず読む前提で、現状、入口、制約、確認手順だけをまとめています。

## 目的

`kensho_assistant` は、懸賞生活 `knshow.com` を起点に候補を集め、応募準備、送信直前チェック、履歴管理までを支援するローカルツールです。
重要なのは「入力補助」であって、実サイトの自動送信はしません。

## 現在の状態

- 候補収集、分析、承認、`PREPARED` 管理、`later-queue`、応募準備、送信直前チェック、履歴管理、Web UI は接続済み
- `submitted_count_auto` は実サイトで 0 のまま維持
- `submit` / `confirm` / `complete` 系の自動クリックは実装しない
- CAPTCHA 回避、ログイン突破、SNS 応募の自動化はしない
- 個人情報はログに出さない
- `Sites` ダッシュボードで診断結果、未解決項目、AI候補、JSON、`skip_reason` を確認できる
- `later-queue` から `Sites` 診断への橋渡しは実装済み
- `kensho_harness` で `PREPARED` 案件と `later-queue` を薄く束ねる入口を追加済み

## 主要入口

- Web UI: `web_app.py`
- CLI: `main.py`
- 応募準備: `python main.py prepare --campaign-id <id> --require-user-approved`
- 送信直前チェック: `python main.py apply dry-run --campaign-id <id>`
- 複数件の確認: `python main.py apply dry-run-all --status PREPARED --limit 12`
- 後追い候補: `python main.py later list --limit 30`
- 引き継ぎ用ハーネス: `python main.py harness run --campaign-id <id> --mode dry_run`
- 同じハーネスの直呼び: `py scripts/run_kensho_harness.py --campaign-id <id> --mode dry_run`

## 重要ファイル

- `kensho_assistant/main.py`
- `kensho_assistant/app/engine.py`
- `kensho_assistant/app/auto_apply_engine.py`
- `kensho_assistant/app/form_filler.py`
- `kensho_assistant/app/pre_submit_verifier.py`
- `kensho_assistant/app/field_mapper.py`
- `kensho_assistant/app/site_templates.py`
- `kensho_assistant/app/later_queue.py`
- `kensho_assistant/app/apply_queue.py`
- `kensho_assistant/app/harness/kensho_harness.py`
- `kensho_assistant/app/harness/x_research_harness.py`
- `kensho_assistant/web/app.py`
- `kensho_assistant/web/templates/sites_dashboard.html`

## データの置き場所

- 候補: `kensho_assistant/data/campaigns.csv`
- 応募キュー: `kensho_assistant/data/apply_queue.csv`
- 送信前解析: `kensho_assistant/data/form_analysis/`
- 送信前チェック: `kensho_assistant/data/pre_submit_checks/`
- dry-run 実行履歴: `kensho_assistant/data/apply_runs/`
- later queue: `kensho_assistant/data/queue/later_apply_queue.jsonl`
- ハーネス出力: `kensho_assistant/data/research/kensho_harness/`
- 画面用スクショ: `kensho_assistant/screenshots/`

## 安全境界

- 実サイトでは自動送信しない
- submit 系ボタンは自動クリックしない
- 送信直前で止める
- `profile.enc` の中身は見ない
- 個人情報は平文ログに残さない
- `submitted_count_auto` は 0 を維持する

## 最近の確認結果

- `py -3 -m pytest kensho_assistant\tests -q -rs` -> `228 passed`
- `py -3 -m compileall kensho_assistant\app scripts\run_kensho_harness.py` -> 成功
- `py -3 web_app.py --smoke-test` -> `WEB_SMOKE_TEST_OK`
- `py -3 main.py harness run --help` -> 成功
- `py -3 scripts/run_kensho_harness.py --help` -> 成功

## 引き継ぎ時に見る順番

1. `README.md`
2. `docs/SELF_TEST_LOG.md`
3. `docs/SITES_DASHBOARD_GUIDE.md`
4. `docs/kensho_harness.md`
5. `app/harness/kensho_harness.py`
6. `main.py`

## 次にやるなら

- `Sites` の JSON 折りたたみ表示をもう少し見やすくする
- `later-queue` と `PREPARED` の横断表示を強化する
- サイト別テンプレートを増やす
- モックフォームの回帰テストを増やす

## 注意

このプロジェクトは「応募補助」が役割です。
完全自動応募には寄せず、最後は人間が確認して送信する前提を崩さないでください。
