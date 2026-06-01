# RELEASE NOTES v0.4.2-beta

## 固定内容

- `v0.4-beta` の導線を維持したまま、`あとで応募` キューを追加
- `AI担当者` タブを追加し、`agent_status.json` の JSON 結果表示モードを追加
- URL を貼るだけで候補を登録し、あとで確認・準備できるようにした
- 同一 URL の重複登録を防止する
- `submitted_count_auto` は常に 0
- 自動送信はしない
- 応募ボタンの自動クリックはしない

## 運用メモ

- `later add-url` で URL を登録する
- `later review` で確認モードへ移す
- `later prepare-fill` で既存の form_readiness / review / fill 導線へ橋渡しする
- `later mark-applied-manual` で手動応募済みを記録する
- 個人情報、ID、パスワード、メール本文は保存しない

## 配布方針

- `start_web_app.bat` を推奨起動にする
- 配布物に `.env` / `profile.json` / `profile.enc` / `logs` / `screenshots` / `data` を含めない
- 旧 ZIP や test_install は `archive/` に退避する
