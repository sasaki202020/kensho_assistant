# Claude Code Handoff: Kensho Entry Assistant

このリポジトリは「懸賞応募補助ツール（Kensho Entry Assistant）」専用です。Claude Code は、このファイルを入口にして懸賞アシスタントの作業を再開してください。

## プロジェクト

- 公開リポジトリ: `https://github.com/sasaki202020/kensho_assistant`
- ローカル: `C:\Users\goo10\OneDrive\ドキュメント\New project\kensho_assistant`（soundon-tool と同じ親フォルダ）
- バージョン: `v0.4.2-beta`（`kensho_assistant/app/version.py`）
- 目的: 対象サイト `懸賞生活 https://www.knshow.com/` の懸賞候補を収集・分類し、安全なフォームだけを入力補助して、送信直前まで準備する
- 方針: 収集・分類・入力補助・履歴管理まで。最終送信、応募確定は必ず人間が手動で行う
- 実行形態: ローカル実行。Web UI（FastAPI, `127.0.0.1:8787`）が主導線、CLI（`python main.py ...`）が補助、デスクトップUI は補助UI

### このリポジトリの構成について（重要）

このリポジトリには系統の違う3つのコードが同居しています。**メインは `kensho_assistant/` パッケージ（懸賞アシスタント）です。** 懸賞作業では原則ここだけを触ります。

- `kensho_assistant/` … 懸賞応募アシスタント本体（このCLAUDE.mdの対象）
- `src/autopilot.py` ほか … 営業リード発見〜Chrome入力補助の Autopilot（別系統。`README.md` の Autopilot 節、`AGENTS.md` とは別タスク）
- `src/pipeline.py` / `src/publish_package.py` / `config.yaml`（`project_name: pension-video-maker`）… 年金系YouTube動画の自動生成パイプライン（`AGENTS.md` が説明している別系統）

懸賞タスクで `src/` や `config.yaml`、`project/` を変更しないこと。混在を整理する場合は別タスクに分ける。

## 絶対に守る安全ルール

- 応募の最終送信は自動で行わない。送信ボタンの自動クリックをしない
- `submit` と人間が明示入力したときだけ送信する設計（`app/submit_controller.py`）。Claude が代わりに `submit` を入力しない
- `submitted_count_auto` は常に 0 のまま維持する
- CAPTCHA、ログイン、会員登録、本人確認、年齢確認、購入必須・レシート・バーコードを伴う応募は入力補助せずブロックする（`app/safety_checker.py` / `app/product_guardrails.py`）
- X / Instagram / LINE / Facebook 連携が必要な懸賞は SNS_ACTION_REQUIRED 系として止める
- ログイン情報、Cookie、パスワード、`config/profile.json` / `profile.enc`、`.env`、`logs`、`screenshots`、`data` は配布物・コミットに含めない
- 個人情報は実名ではなく伏せ字で表示する（`app/privacy_guard.py`）
- `当選率アップ` / `必ず当たる` / `完全自動で稼げる` などの誇大表現は使わない（`app/product_guardrails.py` の disallowed_claims）
- `research/x_search` は X API ではなく xAI の `x_search` tool を使う。結果は Grok の要約なので必ず事実確認する。大量収集・自動スパム用途には使わない
- 入力補助は送信直前で止め、人間確認に渡す

## 現在地

- Web UI（FastAPI）と CLI（argparse）が動作する。Web は `127.0.0.1:8787`
- 主要画面: `/`(今日のおすすめ) `/today` `/queue` `/approved` `/search` `/mail` `/campaigns` `/review` `/security` `/later-queue`(あとで応募) `/entries`(応募履歴・当選メール) `/ai-agents`(AI担当者) `/agent-control`(AI司令塔 dry-run) `/research` `/research/x-campaigns`
- run mode は `mock` / `dry_run` / `review` の3種（既定 `dry_run`、`KENSHO_RUN_MODE` または `config/run_mode.json` で切替）。本番送信モードは存在しない
- 懸賞生活のスクレイプ、分類、安全判定、フォーム検出、フォーム入力補助、dry-run、提出前監査（pre-submit-audit）、応募履歴、当選メール候補抽出までが実装済み
- AI担当者ダッシュボード（`agent_dashboard`）と AI司令塔（`agent_control`、dry-run ジョブのみ）が実装済み
- `web_app.py --smoke-test` で主要ルートの起動スモークが通る（本番送信は人間確認が必要、`submit-approved` は出ない等を検証）
- テストは `kensho_assistant/tests` と `tests` にあり、`pytest.ini` で集約済み
- ⚠ `README.md` は GitHub Actions CI 前提と記載しているが、このチェックアウトに `.github/workflows` は存在しない。CI を追加する場合は別タスク

## 主なファイル

エントリポイント（リポジトリ直下、薄いラッパ）:
- `web_app.py`: Web UI 起動 / `--smoke-test`
- `main.py`: CLI（`kensho_assistant.main:main` を呼ぶ）
- `desktop_app.py`: 補助デスクトップUI

懸賞アシスタント本体（`kensho_assistant/`）:
- `web/app.py`: FastAPI アプリ、全ルート、`WEB_HOST/WEB_PORT`
- `main.py`: CLI サブコマンド定義と各 `cmd_*`
- `app/knshow_scraper.py`: 懸賞生活の収集
- `app/campaign_classifier.py`: 懸賞の種別分類（`config/rules.yaml`）
- `app/safety_checker.py`: 安全判定・ブロックステータス・重複検出
- `app/product_guardrails.py`: 既定ルール・プロダクト方針・禁止表現
- `app/privacy_guard.py`: 個人情報の伏せ字化
- `app/submit_controller.py`: 送信サマリ生成と人間確認ゲート（`submit` 入力時のみ）
- `app/form_detector.py` / `form_analyzer.py` / `field_mapper.py` / `form_filler.py` / `form_readiness.py`: フォーム検出・解析・項目対応・入力補助・準備判定
- `app/auto_apply_engine.py`: mock/dry_run/review エンジン
- `app/engine.py`: dry-run / pre-submit / mark-submitted の実行
- `app/pre_submit_verifier.py`: 提出直前監査
- `app/later_queue.py`: あとで応募キュー
- `app/entry_history.py` / `entry_logger.py`: 応募履歴・当選メール候補
- `app/mail_importer.py`（`kensho_assistant/mail_importer.py`）: メール取り込み
- `app/agent_dashboard/`: AI担当者ステータス（`agent_status.json`）
- `app/agent_control/`: AI司令塔ジョブ（dry-run のみ、`jobs.jsonl`）
- `app/research_engine.py`: research 候補収集
- `app/run_mode.py`: run mode 解決
- `app/profile_manager.py`: profile 暗号化（Fernet）
- `app/browser_manager.py`: Chrome 準備（入力補助用）
- `app/paths.py`: 実行時パスの集約（`data/`, `reports/`, `screenshots/` 等）
- `scripts/run_x_search.py`: xAI `x_search` tool での X 検索・保存

ドキュメント:
- `AGENTS.md`: ※年金YouTube動画系（別系統）のルール。懸賞作業では参照しない
- `docs/QUICK_START.md` / `docs/BETA_TESTER_GUIDE.md` / `docs/SELF_TEST_GUIDE.md` / `docs/ENTRY_HISTORY_GUIDE.md`
- `docs/AI_AGENT_DASHBOARD.md` / `docs/PRODUCT_SPEC.md` / `docs/PRIVACY.md` / `docs/FAQ.md`
- `RELEASE_NOTES_v0.*.md`

## よく使うコマンド

Web UI:
```powershell
python web_app.py
# http://127.0.0.1:8787 を開く
```

CLI（懸賞アシスタント）:
```powershell
python main.py auto-scan --limit 30
python main.py build-queue --limit 30
python main.py status
python main.py approve-campaign --campaign-id <campaign_id>
python main.py approved-queue
python main.py apply dry-run --campaign-id <campaign_id>
python main.py apply pre-submit-audit --campaign-id <campaign_id>
python main.py apply dry-run-all --status PREPARED --limit 12
python main.py apply show-analysis --campaign-id <campaign_id>
python main.py apply show-check --campaign-id <campaign_id>
python main.py apply mark-submitted --campaign-id <campaign_id>
python main.py later add-url --url "https://example.com/campaign"
python main.py later list --limit 30
python main.py entries list
python main.py agent-status generate
python main.py agent-status run --task "safe-agent-run" --mode normal
python main.py browser doctor
python main.py profile check
py scripts\run_x_search.py --query "懸賞 プレゼントキャンペーン 締切 今週 食品"
```

主な CLI サブコマンド: `collect` `analyze` `fill` `prepare` `auto-apply` `apply(dry-run/pre-submit-audit/dry-run-all/show-analysis/show-check/mark-submitted)` `approve-campaign` `approved-queue` `inspect-form` `resolve-urls` `status` `agent-status(generate/run)` `report` `review` `build-queue` `entries(list/search/add/mark-applied/duplicates/export-csv/win-mail-rescan)` `later(add-url/list/review/prepare-fill/mark-applied-manual/skip/remove)` `research` `research-report` `release-report` `auto-scan` `export` `doctor` `browser doctor` `profile(check/encrypt/decrypt/rotate-key)`

## 確認コマンド

```powershell
cd "C:\Users\goo10\OneDrive\ドキュメント\New project\kensho_assistant"
python -m pytest -q
python -m compileall kensho_assistant\app
python web_app.py --smoke-test
```

`web_app.py --smoke-test` が成功すると `WEB_SMOKE_TEST_OK` を出力します。

## 次にやること

1. 人間が `python web_app.py` を起動し、`/today` `/queue` で候補を確認する
2. `/queue` で「応募対象にする」を押し、`/approved/session` で「Chromeで応募準備」を使う
3. `apply dry-run` / `apply pre-submit-audit` の結果（`data/form_analysis/`, `data/pre_submit_checks/`）を確認する
4. `field_mapper` / `form_detector` の selector・項目対応を対象フォームに合わせて最終調整する
5. 入力補助は送信直前で止める（`submit_controller` の人間確認ゲートを越えない）
6. 最終送信・応募確定は人間が手動で行い、`submitted_count_auto` は 0 のまま維持する
