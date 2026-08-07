# Hermes X Search Setup

## 方針

- Windows ネイティブ版は Early Beta とみなし、最初は WSL2 を推奨します。
- Hermes Agent 本体は WSL2 側で導入してください。
- `KENSHO_HERMES_COMMAND` と `KENSHO_HERMES_TIMEOUT_SEC` で挙動を切り替えます。
- 認証情報、OAuth トークン、API キーはリポジトリに保存しません。
- 自動応募、自動送信、X への自動投稿、いいね、リポスト、フォロー、DM 送信は実装しません。

## 前提

- Hermes Agent が起動できること
- Hermes 側で X Search が有効化されていること
- Hermes 側の X 認証が完了していること
- `x_search` が Hermes から利用できること

## 推奨セットアップ

1. WSL2 を準備する
2. WSL2 側で Hermes Agent を導入する
3. Hermes の model を設定する
4. Hermes 側で X Search を有効化する
5. X 側の OAuth / SuperGrok 認証を Hermes 側で完了する
6. `KENSHO_HERMES_COMMAND="wsl hermes chat -q"` を設定する
7. `KENSHO_HERMES_TIMEOUT_SEC=60` を必要に応じて設定する

## kensho_assistant 側の設定

```powershell
setx KENSHO_HERMES_COMMAND "wsl hermes chat -q"
setx KENSHO_HERMES_TIMEOUT_SEC "60"
```

設定後は新しいシェルを開いてください。

## テストコマンド

```powershell
py scripts/check_hermes_x_search.py
py scripts/research_x_kensho.py --query "懸賞 プレゼントキャンペーン 締切 今週 食品 日用品 子育て" --limit 20
```

## よくある失敗

- `Hermes command not found`
  - `wsl` か `hermes` が見つかっていません。WSL2 側の導入を確認してください。
- `timeout`
  - `KENSHO_HERMES_TIMEOUT_SEC` を増やしてください。
- JSON が取れない
  - Hermes の返答が Markdown 付きでも、JSON 配列だけを返すように調整してください。
- `x_search` が使えない
  - Hermes 側で X Search 権限と認証が未設定です。

## 既存検索 CLI の補助オプション

- `py scripts/research_x_kensho.py --check-hermes` で接続診断だけを実行できます。
- `py scripts/research_x_kensho.py --dry-run` または `--mock` で Hermes を呼ばずに終了できます。

## 実装メモ

- この連携は検索・抽出・スコアリング・保存・人間確認キューまでです。
- 応募フォームへの自動送信はしません。
- 取得結果は `kensho_assistant/data/research/x/YYYYMMDD/` に保存します。

## 実機接続テスト

1. WSL2 で Hermes Agent を導入します。
2. `hermes model` で利用モデルを確認します。
3. `hermes auth add xai-oauth` で認証を済ませます。
4. `hermes tools` で X Search を有効にします。
5. Windows 側で次を実行します。

```powershell
$env:KENSHO_HERMES_COMMAND="wsl hermes chat -q"
py scripts/check_hermes_x_search.py
```

6. 成功したら次を実行します。

```powershell
py scripts/research_x_kensho.py --query "懸賞 プレゼントキャンペーン 締切 今週 食品 日用品 子育て" --limit 20
```

## 実機接続確認の見方

- `status: success` なら Hermes が実際に X 検索できています。
- `status: failed` の場合は `reason` を確認します。
- `output_file` に診断結果が保存されます。
