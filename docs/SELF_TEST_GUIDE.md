# SELF TEST GUIDE

## 目的

v0.4.2-beta の主導線が壊れていないかを、自分で短く確認するための手順です。

## 主導線

1. `start_web_app.bat`
2. `http://127.0.0.1:8787`
3. `auto_scan.bat`
4. `/queue`
5. `応募対象にする`
6. `/approved/session`
7. `Chromeで応募準備`
8. `手動送信済み` / `保留` / `スキップ`
9. `/later-queue`
10. `/entries`

## 確認項目

- `auto_scan.bat` が動く
- `/queue` に候補が出る
- 1件承認できる
- `/approved/session` に出る
- Chrome で応募準備できる
- 送信せず停止できる
- 手動送信済み / 保留 / スキップ が分かりやすい
- `submitted_count_auto` が 0 のまま

## 実行コマンド

```powershell
python -m compileall kensho_assistant main.py desktop_app.py web_app.py
python -m pytest kensho_assistant/tests -q -rs
python web_app.py --smoke-test
python main.py build-queue --limit 30
python main.py approved-queue --limit 30
python main.py browser doctor
```

## 中止条件

- 送信ボタンを押しそうになったら止める
- `submit-approved` を見つけても使わない
- `profile.enc` / `profile.json` / `.env` を配布物に入れない
