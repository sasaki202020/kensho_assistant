# Standalone Baseline Report

## 結論

ローカル実装・安全検証の到達点は`FIELD_MAPPING_SAFETY_PASS`です。

- `SOURCE_CANONICAL_VERIFIED`: PASS
- `STANDALONE_COPY_VERIFIED`: PASS
- `STANDALONE_BASELINE_PASS`: PASS
- `ASSISTED_SESSION_INTEGRATION_PASS`: PASS
- `FIELD_MAPPING_SAFETY_PASS`: PASS
- `REAL_SITE_NON_SUBMIT_PASS`: NOT RUN
- `SINGLE_ASSISTED_SUBMISSION_PASS`: NOT RUN

実サイトを開いていないため、製品の実サイト性能や応募成功は未検証です。

## 固定ビルド

- branch: `codex/standalone-completion`
- source commit: `745798761b8bc502260f193c41980fdf58c384b4`
- app version: `v0.4.3`
- extension version: `0.2.0`
- Python: `3.12.10`
- build fingerprint: `ee149a684b2233603537eb9434d9bcfbf86f3971ad44e538ba3ac1b4cc0cad41`
- fingerprint repeat: identical twice

`pilot_commit`とfingerprintは`data/pilot/manifests/5site-pilot-v1.json`へ記録しています。fingerprint生成時は自己参照を避けるため、この2つの証跡フィールドを空文字として正規化します。

## 実装確認

- 暗号化プロフィールの既定保存先をリポジトリ外の`%LOCALAPPDATA%\kensho_assistant\profile.enc`へ固定した。
- `assisted_session`を候補ロック、進行状態、手動送信報告の正本として維持した。
- loopback bridgeは`127.0.0.1`の別ポート、POST、60秒以下の1回限りtokenを使用する。
- tokenはsession、candidate、origin、form fingerprintへ束縛される。
- Service Workerは確認済みマッピングに必要なprofile keyだけを要求する。
- 初回項目対応、fingerprint一致、入力後検証、全ロールバックを必須にした。
- 対象外欄のvalue、checked、disabled、readOnlyも復元・再検証する。
- 復元不能時は`ROLLBACK_INCOMPLETE_HUMAN_REVIEW_REQUIRED`で以後の入力を停止する。
- 「送信済み・次へ」は`HUMAN_ACTION_REQUIRED`かつ一致するsession/candidate/operationだけを受理する。
- 新旧拡張機能の二重起動は安全停止し、一時プロフィールを消去する。

## 検証結果

- Python全体: `419 passed / 0 failed`
- Extension unit: `26 passed / 0 failed`
- compileall: PASS
- Web smoke: `WEB_SMOKE_TEST_OK`
- P1 preflight: `READY_FOR_5_SITE_PILOT`
- Extension local smoke: PASS
- reload: `10/10`
- same-origin navigation: PASS
- Service Worker restart recovery: PASS
- duplicate panel maximum: `1`
- duplicate guard maximum: `1`
- unapproved-origin injection: `0`
- external requests: `0`
- submit blocked: PASS
- `auto_submit_detected`: `0`
- `submitted_count_auto`: `0`
- `git diff --check`: PASS

## P1安全性

- PII persistence: `0`
- candidate state diff: `0`
- normal history diff: `0`
- Playwright trace: `DISABLED`
- screenshot storage: `DISABLED`
- profile内容の確認: 未実施、かつ不要
- 実サイト接続: `0`
- Git push: 未実施

## 5サイト候補

安全な移行では実運用DBをコピーしていません。5件のopaqueな`candidate_ref`と分類だけを`5site-candidates-v1.json`へ固定し、全件を`UNVERIFIED_SOURCE_NOT_IMPORTED`としました。URL、PII、応募履歴は保存していません。

この状態では実サイトpilotを開始しません。本人が対象候補を独立版へ登録し、受付状態と応募条件を確認した後に別の証跡として扱います。

## 次のゲート

最初に行う作業は、新パスの未パッケージ拡張機能をChromeへ手動読込し、旧拡張機能を無効化して、新しい拡張機能IDをローカル運用記録へ残すことです。その後だけ、架空プロフィールを使うPhase A・1サイト非送信確認へ進みます。
