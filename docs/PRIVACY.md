# Privacy

- 個人情報は `profile.enc` にローカル暗号化保存です
- 中央サーバーに送信しません
- 開発者・販売者にも送信しません
- ログでは値をマスクします
- スクリーンショットは既定で保存しません
- ユーザー自身で削除できます

## 保存先

- 暗号化: `kensho_assistant/config/profile.enc`
- 暗号鍵: `.env` の `KENSHO_PROFILE_KEY`

## 暗号化

- `python main.py profile encrypt` で `profile.json` を暗号化できます
- `python main.py profile check --encrypted` で暗号化ストアを確認できます
- `python main.py profile decrypt --output ...` は明示時のみ許可します
- 暗号鍵をなくすと復元できません

## ログ方針

- 氏名、住所、電話番号、メールアドレス、生年月日、郵便番号、Cookie、セッション情報、生のフォーム値は保存しません
- CLI表示、エラーメッセージ、レポート、`run.jsonl`、`notes` は必ず秘匿化します

## スクリーンショット

- 送信前スクリーンショットは既定でOFFです
- 保存する場合は個人情報が写る可能性があります
- 保存前に注意喚起し、ユーザー責任で管理してください
- v0.1 では本番送信を推奨しません
