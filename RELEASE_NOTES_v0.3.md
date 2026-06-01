# RELEASE NOTES v0.3-beta

## 固定内容

- Web UI を主導線に固定
- 応募キューを実運用導線として固定
- `/queue` と `/approved/session` を実運用導線として整理
- 承認済みキューを追加
- `Chromeで応募準備` 後の状態表示と次アクションを改善
- `submitted_count_auto` は常に 0
- `submit-approved` は使用しない
- 自動送信はしない

## 運用メモ

- 応募対象にした候補だけを `Chromeで応募準備` する
- 最後の送信は必ず人間が行う
- 規約同意、クイズ、メルマガ、CAPTCHA は自動操作しない
- 年齢・生年月日は明示許可時のみ入力補助する

## 配布方針

- `start_web_app.bat` を推奨起動にする
- 配布物に `profile.json` / `profile.enc` / `.env` / `logs` / `screenshots` / `data` を含めない
- 旧 ZIP や test_install は `archive/` に退避する
