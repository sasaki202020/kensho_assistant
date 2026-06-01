# X Research Harness

このハーネスは、X API ではなく xAI の `x_search` 系を使う調査・分析ツールです。
通常は `--mock` で動かし、Hermes 実接続は `--provider hermes` で切り替えます。

## まずこれだけ

PowerShell で:

```powershell
cd "C:\Users\goo10\OneDrive\ドキュメント\New project"
powershell -ExecutionPolicy Bypass -File scripts\setup_hermes_wsl.ps1
```

その後、WSL2 Ubuntu で:

```bash
hermes model
hermes auth add xai-oauth
hermes tools
```

`hermes tools` で `x_search` を ON にしてください。

最後に PowerShell で:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test_hermes_provider.ps1
```

成功したら:

```powershell
py -3 scripts\run_x_research_harness.py --query "調べたいテーマ" --mode note --provider hermes
```

## 目的

- query を受け取る
- mode を受け取る
- mock の X 投稿データを使う
- 主張を分析する
- 怪しい点、誇張表現、確認不足を抽出する
- note 記事素材を Markdown で出力する
- `sources.csv` と `run_report.json` を保存する

## モード

- `quick`
- `verify`
- `note`
- `ttp`

## 出力先

`data/research/x_harness/YYYYMMDD/{slug}/`

## 出力ファイル

- `run_plan.json`
- `raw_x_results.json`
- `claim_analysis.json`
- `note_material.md`
- `sources.csv`
- `run_report.json`

## CLI

```powershell
py scripts/run_x_research_harness.py --query "AI駆動開発 Codex サブエージェント レビュー" --mode note --mock
```

Hermes 実接続は次の形で使います。

```powershell
$env:X_RESEARCH_HERMES_COMMAND="wsl -d Ubuntu -- /home/goo10/.local/bin/hermes chat -q"
py scripts/check_hermes_x_search.py
py scripts/run_x_research_harness.py --query "AI駆動開発 Codex サブエージェント レビュー" --mode note --provider hermes
```

## note 出力

`--mode note` では、調査メモとして次の観点をまとめます。

- 反応分類
- 誤解
- 炎上ポイント
- 記事見出し案

## 誇張フラグ

以下の表現があれば、`exaggeration_flags` に入れます。

- 完全自動
- 誰でもできる
- 寝ている間に稼げる
- API不要
- 無料で無限
- 絶対
- 公式が発表
- 激変
- 最強
- これだけでOK

## 注意

- Hermes 実接続は `--provider hermes` のときだけ実行します
- X 投稿、いいね、リポスト、フォロー、DM 送信はしません
- 自動投稿もしません
- 認証情報、API キー、token は保存しません
- ログに個人情報や token は出しません
- Hermes の取得結果は Grok/x_search の要約なので、公開前は事実確認が必要です

## Hermes 実接続前の診断

1. WSL2 側で Hermes を入れる
2. `hermes model` を確認する
3. `hermes auth add xai-oauth` を実行する
4. `hermes tools` で `x_search` を有効化する
5. Windows PowerShell で環境変数を設定して診断する

```powershell
$env:X_RESEARCH_HERMES_COMMAND="wsl -d Ubuntu -- /home/goo10/.local/bin/hermes chat -q"
py scripts/check_hermes_x_search.py
```

失敗時の見方:

- `wsl_not_found`
- `hermes_not_found`
- `xai_auth_missing`
- `x_search_disabled`
- `timeout`
- `invalid_json`
- `empty_result`

実接続が通ったら、次を実行します。

```powershell
py scripts/run_x_research_harness.py --query "AI駆動開発 Codex サブエージェント レビュー" --mode note --provider hermes
```
