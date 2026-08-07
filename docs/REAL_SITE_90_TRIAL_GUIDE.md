# 実サイト90試行ガイド

## 目的

30サイトを各3回、合計90試行し、入力補助が送信直前で安全に停止できるかをA/B/Cで評価する。
応募送信、CAPTCHA突破、ログイン、SNS認証は自動化しない。

## 実行

### 5サイトpilot

実サイトpilotを開始する前に、固定5サイトを各3回測定する検証経路を確認する。

```powershell
py -3 main.py pilot-manifest create --limit-sites 5
py -3 main.py pilot-manifest validate --manifest <表示されたmanifestパス>
py -3 main.py pilot-run --manifest <表示されたmanifestパス> --browser chrome
py -3 main.py trial-report --manifest-id <manifest_id> --require-trials 15 --require-sites 5
```

- manifestにはURLや入力値を保存せず、`candidate_ref`からローカル候補を実行時に解決する。
- 各試行は新しいbrowser contextを使い、Cookie・Local Storage・Session Storageを引き継がない。
- `pilot-run`に`--keep-open`は存在せず、各試行の確認後にcontextを閉じる。
- 候補status、保留、スキップ、送信済み状態、通常応募履歴は変更しない。
- screenshot、HTML snapshot、通常dry-run成果物は保存せず、PIIを含まないpilot試行証跡だけを追記する。
- 同じ`manifest_id + entry_id + attempt_no`は再実行しても二重記録しない。
- `trial-report`は5サイトすべてにattempt 1、2、3がある場合だけ構造合格とする。

### 公式90試行

```powershell
py -3 main.py prepare-session --status APPROVED,PREPARED --limit 30 --browser chrome --keep-open --record-trials
py -3 main.py trial-report --require-trials 90 --require-sites 30
```

同じ30サイトを各3回確認する。各回は送信せず、人間引き継ぎ画面で停止してから次の試行を開始する。
`trial-report`は90試行・30サイトに達するまで非0で終了するため、検証不足を合格扱いしない。

出力先:

- `kensho_assistant/data/real_site_trials/trials.jsonl`
- `kensho_assistant/data/real_site_trials/steps.jsonl`
- `kensho_assistant/reports/real_site_trials/trial_results.csv`
- `kensho_assistant/reports/real_site_trials/trial_results.json`
- `kensho_assistant/reports/real_site_trials/trial_summary.json`

Webでは `GET /api/trial-report` から個人情報を含まない集計だけを確認できる。

## 判定

- A: 基本項目を入力し、重大な手動修正なし、3分以内、送信直前で停止。
- B: 1〜2項目の手動修正、またはCAPTCHA・ログイン・SNS認証の明確な手動引き継ぎ。
- C: 誤入力、復旧不能、3分超過、原因不明、送信危険、次の操作が不明。

リリース合格条件:

- A判定率80%以上
- A+B判定率95%以上
- 意図しない送信0件
- 重大な誤入力0件
- タイムアウト後の復旧または手動引き継ぎ成功率90%以上
- 処理時間中央値90秒以内

## 検証サイト構成

- 標準的な単一ページフォーム: 10サイト
- JavaScriptで動くフォーム: 6サイト
- 確認画面付きフォーム: 5サイト
- 複数ステップフォーム: 4サイト
- CAPTCHAまたは認証付きの手動引き継ぎ確認: 3サイト
- 明確な非対応サイト: 2サイト

簡単なフォームだけで成功率を作らず、この構成を各3回評価する。実サイトへの送信は行わない。

## エラー分類

`ELEMENT_NOT_FOUND`、`INPUT_REJECTED`、`VALUE_RESET`、`VALIDATION_FAILED`、
`DYNAMIC_FIELD_TIMEOUT`、`NAVIGATION_TIMEOUT`、`IFRAME_UNSUPPORTED`、
`LOGIN_REQUIRED`、`CAPTCHA_REQUIRED`、`SNS_AUTH_REQUIRED`、
`EMAIL_OR_SMS_AUTH_REQUIRED`、`MULTI_STEP_UNSUPPORTED`、
`SUBMIT_GUARD_TRIGGERED`、`TERMS_RESTRICTION`、
`MANUAL_JUDGMENT_REQUIRED`、`UNKNOWN`を共通分類として使用する。

## 安全性

- 自動入力中はEnter、submitイベント、submitボタン、`form.submit()`、`requestSubmit()`を遮断する。
- 人間へ画面を引き継ぐ前にガードを解除する。
- ガード作動は`SUBMIT_GUARD_TRIGGERED`として記録し、勝手に再試行しない。
- URLはハッシュ識別子だけ保存し、クエリ文字列や入力値を保存しない。
- スクリーンショットは既定で保存しない。実プロフィールでの保存は明示同意がある場合だけにする。
- タイムアウト時は入力済み画面を維持して停止し、再試行・手動継続・中止を案内する。

## 検証チェック

1. 同じサイトは同一`site_id`で3件記録される。
2. `trial_count=90`、`site_count=30`になる。
3. `unintended_submission_count=0`を確認する。
4. C判定と上位3失敗パターンを優先して共通原因を修正する。
5. サイト固有対応は共通原因で解決できない場合だけ検討する。
# P1 pilot safety preflight

実サイトpilotの前に、外部接続を行わない次の監査を必ず実行する。

```powershell
py -3 -m kensho_assistant.pilot.preflight
```

`result`が`READY_FOR_5_SITE_PILOT`でない場合はpilotを開始しない。

pilot証跡は通常履歴から分離し、次の専用領域だけへ保存する。

```text
data/pilot/
  manifests/
  runs/
  evidence/
  reports/
```

pilotではHTML、スクリーンショット、Playwright trace、browser storage stateを保存しない。
通常の候補・履歴を含む`data`領域は、pilot専用領域を除いて実行前後のSHA-256が完全一致しなければ失敗とする。
