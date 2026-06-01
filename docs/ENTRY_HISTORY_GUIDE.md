# 応募履歴ガイド

`v0.4.2-beta` で固定した応募履歴・当選メール・メルマガ管理と、`あとで応募` キューの使い方です。

## 主な画面

- `/entries`
- `/mail`
- `/dashboard`

## 主なコマンド

```powershell
python main.py entries list
python main.py entries search --keyword "当選"
python main.py entries mark-applied --campaign-id <campaign_id>
python main.py entries export-csv
python main.py entries duplicates
python main.py entries win-mail-rescan
python main.py later add-url --url "https://example.com/campaign"
python main.py later list --limit 30
```

## 保存先

- 応募履歴: `data/entries/entry_history.jsonl`
- CSV出力: `data/entries/entry_history.csv`
- 当選メール候補: `data/entries/win_mail_candidates.jsonl`
- あとで応募: `data/queue/later_apply_queue.jsonl`

## 運用ルール

- 自動送信はしません
- 送信ボタンの自動クリックはしません
- CAPTCHA は突破しません
- 規約同意は自動操作しません
- 個人情報は平文で保存しません
- `submitted_count_auto` は 0 のままです

## 確認の流れ

1. `start_web_app.bat` を起動する
2. `/queue` で候補を確認する
3. 必要な案件だけ `応募対象にする`
4. `/approved/session` で `Chromeで応募準備` を使う
5. `/later-queue` であとで応募候補を登録する
6. `/entries` で応募履歴と当選メール候補を確認する
7. CSV が必要なら `entries export-csv` を使う
