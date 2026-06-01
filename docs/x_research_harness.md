# X Research Harness

X上の話題を調査し、主張分析とnote記事素材を生成する最小ハーネスです。

## 実行

```powershell
py scripts/run_x_research_harness.py --query "AI駆動開発 Codex サブエージェント レビュー" --mode note --mock
```

### provider を使う

```powershell
py scripts/run_x_research_harness.py --query "AI駆動開発 Codex サブエージェント レビュー" --mode note --provider hermes
```

`--mock` を付けた場合は必ず mock 実行になります。`--provider hermes` は実接続です。

### Hermes 診断

```powershell
$env:X_RESEARCH_HERMES_COMMAND="wsl hermes chat -q"
py scripts/check_hermes_x_search.py
```

### WSL2 で Hermes を入れる流れ

1. WSL2 を有効化する
2. Linux 側で `hermes` を導入する
3. `wsl hermes chat -q` が手動で動くか確認する
4. `X_RESEARCH_HERMES_COMMAND` を PowerShell で設定する

### PowerShell 環境変数

```powershell
$env:X_RESEARCH_HERMES_COMMAND="wsl hermes chat -q"
$env:X_RESEARCH_HERMES_TIMEOUT_SEC="120"
```

## 出力

`data/research/x_harness/YYYYMMDD/{slug}/` に以下を保存します。

- `run_plan.json`
- `raw_x_results.json`
- `claim_analysis.json`
- `note_material.md`
- `sources.csv`
- `run_report.json`

## 安全ルール

- Hermes 実接続は provider = hermes の時だけ使います。
- X投稿、いいね、リポスト、フォロー、DM送信、自動投稿はしません。
- APIキー、token、メールアドレスは保存・ログ出力しない前提でサニタイズします。

## 失敗時の見方

- `status: failed` は実接続側の失敗です。
- `reason` と `error_type` を見ます。
- `timeout` は時間切れです。
- `hermes_not_found` はコマンド未導入です。
- `xai_auth_missing` は認証不足です。
- `invalid_json` は Hermes の返答整形を見直します。
