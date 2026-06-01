# Beta Tester Guide

## まず知っておくこと

- このツールは応募送信しません
- `懸賞生活 https://www.knshow.com/` は入口です
- 自動スキャンは個人情報を使いません
- 本番送信は人間確認が必要です

## 主導線

1. `start_web_app.bat`
2. `http://127.0.0.1:8787`
3. `auto_scan.bat`
4. `/queue`
5. `Chromeで応募準備`
6. `手動送信済みにする`

## できること

- 懸賞の収集
- 応募タイプの分類
- rd リンク解決
- フォーム診断
- `REVIEW_ONLY` の確認
- `READY_FOR_FILL` の確認
- 応募キューの確認
- Web UI での応募準備

## できないこと

- 応募送信
- CAPTCHA 突破
- SNS 自動操作
- 年齢の自動入力
- 規約同意の自動チェック
- メルマガ登録の自動チェック

## 補助UI

- `start_desktop_app.bat`: 補助UI 起動
- `auto_scan.bat`: 自動スキャン
- `doctor_check.bat`: 環境確認
- `release_report.bat`: レポート出力

## 困った時

- `README.md`
- `docs/FAQ.md`
- `docs/PRIVACY.md`
- `docs/PRODUCT_SPEC.md`
