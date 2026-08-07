# 5サイト pilot 実行手順

## 前提

- 対象リポジトリ: `C:\Users\goo10\OneDrive\ドキュメント\New project\kensho_assistant`
- pilotは固定した5サイトを各3回、合計15試行する。
- 自動送信、CAPTCHA処理、ログイン、規約同意は行わない。
- 3回の検証では応募を送信しない。重複応募を避けるため、最終送信はpilot外で本人が1回だけ行う。
- Playwright traceとスクリーンショット保存は無効のまま使用する。

## 1. 自宅PCで起動

PowerShellで親ディレクトリへ移動し、事前監査後にWebアプリを起動する。

```powershell
Set-Location 'C:\Users\goo10\OneDrive\ドキュメント\New project'
py -3 -m kensho_assistant.pilot.preflight
py -3 -m kensho_assistant.run_web
```

`READY_FOR_5_SITE_PILOT`以外なら起動後のpilot操作へ進まない。

## 2. Tailscale Serve確認

```powershell
tailscale status
tailscale serve status
```

一般公開のFunnel、ルーターのポート開放、`0.0.0.0`へのbindは使用しない。Tailscale Serveの転送先が`http://127.0.0.1:8787`であることを確認する。

## 3. Chrome Remote Desktop確認

Chrome Remote Desktopアプリで自宅PCがオンラインと表示され、本人の端末から接続できることを確認する。pilot開始前に、画面操作と切断後の再接続ができることを確認する。

## 4. build fingerprint確認

```powershell
py -3 -m kensho_assistant.pilot.build_fingerprint `
  --manifest kensho_assistant\data\pilot\manifests\5site-pilot-v1.json `
  --candidates kensho_assistant\data\pilot\manifests\5site-candidates-v1.json
```

出力値が`5site-pilot-v1.json`の`build_fingerprint_sha256`と一致しない場合は停止する。

## 5. commit SHA確認

```powershell
git -C kensho_assistant rev-parse HEAD
git -C kensho_assistant status --short
```

`pilot_commit`と対象commitが一致し、pilot対象ファイルに未コミット差分がないことを確認する。

## 6. 1試行目を開始

マニフェストを検証してからpilotを開始する。

```powershell
py -3 -m kensho_assistant.main pilot-manifest validate `
  --manifest kensho_assistant\data\pilot\manifests\5site-pilot-v1.json
py -3 -m kensho_assistant.main pilot-run `
  --manifest kensho_assistant\data\pilot\manifests\5site-pilot-v1.json `
  --browser chrome
```

`--keep-open`は使用しない。各試行では新しいbrowser contextを使用し、終了時に閉じる。

## 7. 入力結果の確認

値を記録せず、次を項目単位で確認する。

- 候補と提供元、賞品、キャンペーン名が一致している
- 氏名、住所、電話、メール等が正しい種類の欄に入っている
- 未解決項目と人間操作が画面に明示されている
- 最終送信または安全に判別できないボタンの直前で停止している
- 入力値がログ、HTML、画像、traceへ保存されていない

## 8. CAPTCHA・ログイン時

自動処理せず、`CAPTCHA_REQUIRED`または`LOGIN_REQUIRED`として停止する。本人が手動継続する場合も、その試行では送信せず、手動介入ありとして記録する。

## 9. 最終送信

pilot中は押さない。実応募を行う場合はpilot完了後、本人が応募条件と入力内容を確認し、対象サイト上で1回だけ押す。アシスタントは最終送信を実行しない。

## 10. 送信しない検証の終了

送信直前で停止したことを確認し、試行を終了する。ブラウザcontextを閉じ、Cookie、Local Storage、Session Storageを次試行へ引き継がない。

## 11. 「送信済み・次へ」

pilotでは使用しない。実応募を本人が完了した場合だけ通常運用画面から1回押す。再読み込みや古い画面からの重複操作は行わない。

## 12. 事後検査

15試行後に次を確認する。

```powershell
py -3 -m kensho_assistant.pilot.preflight
py -3 -m kensho_assistant.main trial-report `
  --manifest-id 5site-pilot-v1 `
  --require-trials 15 `
  --require-sites 5
```

以下がすべて0であることを確認する。

- `submitted_count_auto`
- 自動送信検出数
- PII検出数
- 候補状態差分
- 通常履歴差分

## 13. エラー時の安全停止

次のいずれかを検出した時点で残りの試行を停止する。

- 意図しない送信または送信済み画面への遷移
- 個人情報の保存
- 候補状態または通常履歴の変更
- 誤った項目への入力
- 無限待機、過剰アクセス、原因不明エラー
- traceまたはスクリーンショット保存の有効化

原因を修正した場合、同じ固定ビルドのpilot結果として継続せず、ビルドを再固定して15試行を最初から行う。

## 14. 次の試行へ進む条件

現在の試行が安全に終了し、送信なし、PII保存なし、状態変更なし、browser context終了を確認した場合だけ次へ進む。受付状態が未確認、終了済み、候補不一致の場合は結果を置き換えず、そのまま記録する。
