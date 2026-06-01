# SELF TEST LOG

## 使い方

このファイルに、実施した自己テスト結果を追記します。

## 最新記録

### 2026-05-23

- 実施者: 自分
- 実施目的: v0.4.2-beta のあとで応募キュー実運用確認
- 起動方法: `start_web_app.bat` → `http://127.0.0.1:8787`
- 確認した画面: `/queue` / `/later-queue` / `/approved` / `/approved/session` / `/entries`
- 実行したコマンド: `compileall` / `pytest` / `web_app.py --smoke-test` / `build-queue` / `approved-queue` / `browser doctor` / `later add-url` / `later list` / `later review` / `later prepare-fill` / `later mark-applied-manual` / `later skip` / `later remove`
- 結果: `submitted_count_auto = 0` のまま、送信なしで確認できた
- 気づき: URL 登録と重複警告が先に見えると、あとで応募候補をまとめやすい
- 次回やること: `later` 一覧の文言と状態表示を実運用でさらに1回見る

### 2026-05-23

- 実施者: 自分
- 実施目的: v0.4.2-beta のあとで応募キュー実運用確認
- 起動方法: `start_web_app.bat` → `http://127.0.0.1:8787`
- 確認した画面: `/queue` / `/later-queue` / `/approved` / `/approved/session` / `/entries`
- 実行したコマンド: `compileall` / `pytest` / `web_app.py --smoke-test` / `build-queue` / `approved-queue` / `browser doctor` / `later add-url` / `later list`
- 結果: `submitted_count_auto = 0` のまま、送信なしで確認できた
- 気づき: URL だけ先に登録できると、あとでまとめて見る流れが作りやすい
- 次回やること: `later review` と `later prepare-fill` の文言がさらに短くできるか見る

### 2026-05-23

- 実施者: 自分
- 実施目的: v0.4-beta 固定後の実運用最終確認
- 起動方法: `start_web_app.bat` → `http://127.0.0.1:8787`
- 確認した画面: `/queue` / `/approved` / `/approved/session` / `/entries`
- 実行したコマンド: `compileall` / `pytest` / `web_app.py --smoke-test` / `build-queue` / `approved-queue` / `browser doctor` / `entries list` / `entries win-mail-rescan`
- 結果: `submitted_count_auto = 0` のまま、送信なしで確認できた
- 気づき: 応募履歴と当選メール候補は実運用で確認しやすい
- 次回やること: 実際の応募記録を1件だけ増やして使い勝手を見る

### 2026-05-21

- 実施者: 自分
- 実施目的: v0.3-beta 固定前の導線確認
- 起動方法: `start_web_app.bat` → `http://127.0.0.1:8787`
- 確認した画面: `/queue` / `/approved` / `/approved/session`
- 実行したコマンド: `auto_scan.bat` / `build-queue` / `approved-queue` / `browser doctor`
- 結果: 送信なしで確認可能
- 気づき: `Chromeで応募準備` 後の案内は短い方が分かりやすい
- 次回やること: 迷う文言があればここに追記する

### 2026-05-23

- 実施者: 自分
- 実施目的: v0.3-beta 固定後の最終確認
- 起動方法: `start_web_app.bat` → `http://127.0.0.1:8787`
- 確認した画面: `/queue` / `/approved` / `/approved/session` / `/review` / `/security`
- 実行したコマンド: `compileall` / `pytest` / `web_app.py --smoke-test` / `build-queue` / `approved-queue` / `browser doctor`
- 結果: `submitted_count_auto = 0` のまま、送信なしで確認できた
- 気づき: 承認済みキューの表示はこのままで実運用に入れる
- 次回やること: 実運用で1日使って迷う文言だけメモする
