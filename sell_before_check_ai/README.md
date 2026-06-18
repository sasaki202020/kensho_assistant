# 売る前チェックAI v0.1

一般ユーザー向けの防衛用バックエンドです。訪問買取、不用品回収、出張査定の前に、チラシ・商品・見積もりをチェックして、注意点や断り文例、公式情報、相場リンクを返します。

## 起動

```powershell
py -3 -m sell_before_check_ai
```

または、ダブルクリック用に:

```powershell
start_sell_before_check_ai.bat
```

## 開くURL

- Home: `http://127.0.0.1:8002/`
- 一般ユーザー向けの実画面:
  - `http://127.0.0.1:8002/flyer-check`
  - `http://127.0.0.1:8002/item-check`
  - `http://127.0.0.1:8002/quote-check`
  - `http://127.0.0.1:8002/result`
- 管理ダッシュボード: `http://127.0.0.1:8002/dashboard`
- API Health: `http://127.0.0.1:8002/api/v0/consumer/health`
- スマホ導線レビュー: `http://127.0.0.1:8002/mobile-preview`
- 見る順番: Home → チラシチェック / 商品チェック / 見積もりチェック → 診断結果

## 実際に触れる導線

1. Home で `チラシをチェック` / `商品をチェック` / `見積もりをチェック` を選ぶ
2. 各チェック画面で入力して `診断して結果を見る` を押す
3. `/result` で判定、今やること、断り文例、相場リンク、188案内を確認する
4. 迷ったら断り文例をコピーして、その場で決めない

## mobile-preview の使い方

- `http://127.0.0.1:8002/mobile-preview` でスマホ導線を確認できます
- 何も付けない場合は、scenario なしの本番想定ライブ表示が開きます
- 実画面レビューは `view` パラメータで切り替えられます
  - `?view=home`
  - `?view=flyer`
  - `?view=item`
  - `?view=quote`
  - `?view=result`
- 診断シナリオの切り替えは次の URL パラメータで行えます
  - `?scenario=kimono`
  - `?scenario=mishin`
  - `?scenario=kikinzoku`
  - `?scenario=recovery_quote`
- 診断結果では、まず「今やること」が一番上に出ます
- 断り文例、相場リンク、188案内はその下で確認できます

## スクショ保存

Playwright を使って、scenario なしのライブ表示とレビュー用シナリオのスクショを保存できます。

```powershell
py -3 -m sell_before_check_ai.mobile_preview --save-screenshots
```

保存先:

- `sell_before_check_ai/runtime/screenshots/`

保存対象:

- `mobile_preview_iphone_live.png`
- `mobile_preview_iphone_kimono.png`
- `mobile_preview_iphone_mishin.png`
- `mobile_preview_iphone_kikinzoku.png`
- `mobile_preview_iphone_recovery_quote.png`
- `mobile_preview_pixel_live.png`
- `mobile_preview_pixel_kimono.png`
- `mobile_preview_pixel_mishin.png`
- `mobile_preview_pixel_kikinzoku.png`
- `mobile_preview_pixel_recovery_quote.png`
- `mobile_preview_landscape_live.png`
- `mobile_preview_landscape_kimono.png`
- `mobile_preview_landscape_mishin.png`
- `mobile_preview_landscape_kikinzoku.png`
- `mobile_preview_landscape_recovery_quote.png`

必要なものが足りない場合は、次を実行してください。

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m playwright install chromium
```

## 実画面のスクショ確認

`/mobile-preview` から実画面を確認する場合は、次のように切り替えます。

- `http://127.0.0.1:8002/mobile-preview?view=home`
- `http://127.0.0.1:8002/mobile-preview?view=flyer`
- `http://127.0.0.1:8002/mobile-preview?view=item`
- `http://127.0.0.1:8002/mobile-preview?view=quote`
- `http://127.0.0.1:8002/mobile-preview?view=result`

レビュー用に iPhone 枠つきで見たいときは、`view` 付き URL を開いてから目視確認してください。

## サンプル投入

```powershell
py -3 -m sell_before_check_ai.seed --reset
```

## 注意

- 自動出品はしません
- 自動購入はしません
- 自動ログインはしません
- スクレイピングはしません
- 法令適合や査定結果を保証しません
- 188 相談案内を常に表示します
