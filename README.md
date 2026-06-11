# Kensho Entry Assistant v0.4.2-beta

ローカル実行型の懸賞応募補助ツールです。対象サイトは `懸賞生活 https://www.knshow.com/` です。
公開リポジトリは `https://github.com/sasaki202020/kensho_assistant` です。

> **同居プロジェクト: 売る前チェック (sell_before_check_ai)**
> 一般向けの買取トラブル防止チェックアプリと、その iOS 化一式がこのリポジトリに含まれています。
> 起動: `start_sell_before_check.bat`（または `py -3 run_sell_before_check.py`）→ `http://127.0.0.1:8788`
> iOS化・App Store 公開手順: `ios_app/README.md` と `docs/sell_before_check_ai/` を参照。
> 業者向けバックエンドは `field_assessment_ai/`（`uvicorn field_assessment_ai.app:app --port 8789`）。

## 推奨起動

1. `start_web_app.bat` をダブルクリックする
2. ブラウザで `http://127.0.0.1:8787` を開く
3. `auto_scan.bat` で候補を更新する
4. `/queue` で候補を確認する
5. `応募対象にする` で承認済みにする
6. `/approved/session` で `Chromeで応募準備` を使う
7. Chrome 上で人間確認する
8. `手動送信済み` / `保留` / `スキップ` を選ぶ
9. `/later-queue` であとで応募候補を登録する
10. `/ai-agents` で AI担当者の JSON 結果を確認する
11. `/agent-control` で AI司令塔の dry-run ジョブを確認する
12. `/entries` で応募履歴と当選メール候補を確認する

## Windows常駐

ログオン時に Web UI を自動起動したい場合は、次を実行します。管理者権限は不要です。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\install_web_resident.ps1
```

解除する場合は次を実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\uninstall_web_resident.ps1
```

常駐処理は `web_app.py` を監視し、終了したら再起動します。ログは `%LOCALAPPDATA%\KenshoAssistant\logs\web_resident.log` に出ます。

## 重要

- 応募送信はしません
- 送信ボタンの自動クリックはしません
- 最後の送信は必ず人間確認が必要です
- `submitted_count_auto` は 0 のまま維持します
- `profile.json` / `profile.enc` / `.env` / `logs` / `screenshots` / `data` は配布物に含めません
- 個人情報は実名ではなく伏せ字で表示します
- `research/x_search` は X API ではなく、xAI の `x_search` tool を使います
- 取得結果は Grok の要約なので、事実確認が必要です

## 起動コマンド

```powershell
python web_app.py
python main.py auto-scan --limit 30
python main.py build-queue --limit 30
python main.py later add-url --url "https://example.com/campaign"
python main.py later list --limit 30
python main.py agent-status generate
python main.py agent-status run --task "safe-agent-run" --mode normal
python main.py agent-status run --task "safe-agent-run" --mode release
data/agent_status/agent_run_log.jsonl に毎回の実行履歴が追記されます
python main.py entries list
python main.py browser doctor
python main.py apply dry-run --campaign-id <campaign_id>
python main.py apply dry-run-all --status PREPARED --limit 12
python main.py apply show-analysis --campaign-id <campaign_id>
python main.py apply show-check --campaign-id <campaign_id>
python main.py apply mark-submitted --campaign-id <campaign_id>
py scripts\run_x_search.py --query "懸賞 プレゼントキャンペーン 締切 今週 食品"
```

## 開発検証

- `python -m pytest -q`
- `python -m compileall kensho_assistant\app`
- `python web_app.py --smoke-test`

GitHub Actions でも同じ検証を回します。`main` は CI で守る前提です。

## X Search Tool

`scripts/run_x_search.py` は xAI の Responses API にある `x_search` tool を直接使って、X 投稿の検索と要約を保存します。

- `--note` を付けると、`反応分類` / `誤解` / `炎上ポイント` / `記事見出し案` の見出し付き Markdown で保存します
- 保存先は `data/research/x_search/YYYYMMDD/` です
- 大量収集や自動スパム用途には使わないでください

## 補助UI

`desktop_app.py` と `start_desktop_app.bat` は補助UIです。主導線は Web UI です。

## ドキュメント

- [docs/QUICK_START.md](docs/QUICK_START.md)
- [docs/BETA_TESTER_GUIDE.md](docs/BETA_TESTER_GUIDE.md)
- [docs/SELF_TEST_GUIDE.md](docs/SELF_TEST_GUIDE.md)
- [docs/SELF_TEST_LOG.md](docs/SELF_TEST_LOG.md)
- [docs/ENTRY_HISTORY_GUIDE.md](docs/ENTRY_HISTORY_GUIDE.md)
- [reports/self_test_log.md](kensho_assistant/reports/self_test_log.md)
- [RELEASE_NOTES_v0.4.2.md](RELEASE_NOTES_v0.4.2.md)
- [docs/AI_AGENT_DASHBOARD.md](docs/AI_AGENT_DASHBOARD.md)
- [docs/PRIVACY.md](docs/PRIVACY.md)
- [docs/FAQ.md](docs/FAQ.md)
- [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md)
- [docs/SELLING_PAGE_DRAFT.md](docs/SELLING_PAGE_DRAFT.md)
- [docs/ARCHIVE/](docs/ARCHIVE/)

## Autopilot

営業候補の発見から診断、スクリーンショット、PDF、提案文、見積もり、Chrome入力補助までをまとめて実行します。

### 使い方

```powershell
python -m src.autopilot --area "北九州市 小倉北区" --industry "整骨院" --limit 20
python -m src.autopilot --sample --limit 5
```

### バッチ

- `scripts/run_autopilot_sample.bat`
- `scripts/run_autopilot_daily.bat`
- `scripts/open_dashboard.bat`
- `scripts/fill_marketplace_text.bat`

### 運用メモ

- 日中の自動実行は `run_autopilot_daily.bat` をタスクスケジューラから呼び出します
- 帰宅後は `reports/index.html` と `reports/YYYYMMDD/index.html` を確認します
- Chrome入力補助は送信直前で止めます
- 送信・応募・公開は必ず人間が手動で実行します
- 法務・利用規約・掲載先規約の確認は別途必要です
