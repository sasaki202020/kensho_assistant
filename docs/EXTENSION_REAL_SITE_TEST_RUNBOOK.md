# Chrome拡張機能 実サイト非送信確認手順

この手順はローカルfixture合格後のPhase A・1サイト確認用である。架空プロフィールだけを使い、最終送信は行わない。本人プロフィールを使うPhase Bとは同じ試行にしない。

ローカルfixtureの合格結果には、通常のページ通信件数とは別に、
`sentinel_network_leak=0`（センチネルを含むrequest本文・URL・WebSocket送信フレームなし）と
`extension_non_loopback_requests=0`（Service Worker由来の非loopback通信なし）を含める。
本文・URL・フレーム内容は証跡へ保存しない。計測不能な通信経路は0ではなく未確認として扱い、
実サイト入力へ進まない。

## 事前条件

1. ブランチとcommit SHAを記録する。
2. 全テスト、Webスモーク、P1 preflightが成功していることを確認する。
3. `submitted_count_auto=0`を確認する。
4. スクリーンショットとPlaywright traceを無効にする。
5. 対象サイトの締切、応募条件、重複応募禁止を本人が確認する。

フォーム対応の事前確認:

- 初回フォームは、信頼度にかかわらず欄ごとの割り当てを人間が承認する。
- 「保護者名」「ハンドル名」「賞品」「応募理由」「感想」などは入力しない。
- 確認済みテンプレートがあっても、origin、pathname、fingerprint、送信ガード、
  PIIセッションが一致しなければ入力せず`FORM_CHANGED_REVIEW_REQUIRED`で停止する。

## 自動注入だけの診断

現在の正本では、許可済みoriginを含む固定済みの`build/extension`と、毎回新しい専用
Chromiumコンテキストを使う。既存のChromeプロファイルやCookieは読み込まない。
この経路で毎回ツールバーを押す必要はない。通常インストール版の初回権限操作と混同しない。

正本ルートで、次の既存コマンドを使う。

```powershell
py -3.13 -B scripts/run_dedicated_chrome.py --verify-only --headless --url https://www.epinard.jp/presentquiz/
```

- `config/approved_origins.json`にないorigin、query、fragmentを含むURLは拒否する。
- 固定ビルドが現在のソースと一致しなければ停止する。診断中にビルドし直さない。
- パネル1個・ガード1個だけでは不十分。`guard_verified=true`も必要。
- MAIN worldの実状態から`locked`、`integrity`、`installedAtDocumentStart`を確認する。
- 未取得・不正な検出件数は`null`であり、0として成功扱いしない。
- 終了時に専用コンテキストを閉じ、一時プロファイルを消去する。
- このコマンドは候補lock、mapping承認、プロフィール取得、入力を行わない。
  `status=PASS`は自動注入診断のPASSだけで、Phase 5A合格ではない。

未表示やガード未確認の場合は、権限・固定ビルド・注入例外を調べる。
「アイコンを押して続行」を通常の回避策にしない。

## 入力試験を開始する前の停止点

現状の`prepare-session`は通常運用経路であり、Webの入力権限APIは`load_profile()`を使う。
`pilot-run`は従来の`engine.run`経路で、拡張機能ブリッジを検証する代替にはならない。
どちらもそのままPhase 5Aの実行コマンドとして使用しない。

次の条件を満たす検証用設定・計測経路を用意し、ローカルfixtureで合格するまで入力しない。

1. 同じ`assisted_session`を使い、プロフィール供給元をメモリ上の架空値に限定する。
   本人の`.env`、`profile.enc`、ブラウザプロファイルを読み込まない。
2. 1候補のlock・進行状態・監査を`data/pilot/`に分離し、通常キュー・通常履歴を変更しない。
3. 入力前からページと拡張機能の通信を区別し、センチネル送信の有無だけを計測する。
   fetch、XHR、beacon、WebSocket、validation、autosave、submitを含める。
   本文やセンチネルそのものをログへ保存しない。未観測の通信経路はUNVERIFIEDとする。
4. rollback後にDOM・各storage・生成成果物の残存を検査できる。
5. 初回mappingの各入力対象を本人が確認する。包括的許可で代用しない。

最小実装の順序と検証項目は[ゴール指示](GOAL_NON_SUBMIT_PILOT.md)を正本とする。

## 上記条件が揃った後の1試行

1. 固定commit・設定・拡張機能ハッシュと候補の公式期間を再確認する。
2. 1候補をlockし、専用コンテキストで自動注入と実ガード状態を検証する。
3. CAPTCHA、ログイン、外部iframe、危険項目を確認し、非対応なら入力せず停止する。
4. fingerprint、判定根拠、値を含まないmapping表を本人へ提示する。
5. 本人が各割り当てを承認し、手動項目は「入力しない」とする。
6. マスク済みpreview後、承認済み欄だけに一意な架空センチネルを入力する。
7. 対象欄の一致、対象外欄・同意・賞品・遷移・送信の不変を検証する。
8. 完全rollbackとsession clearを行い、残存検査・通常ストレージ差分検査を行う。
9. 候補lockを解除し、非PIIの結果だけを保存して終了する。Phase 5Bへ進まない。

## 即時停止

- CAPTCHA、ログイン、認証、外部iframeを検出した。
- prototype改変または自動送信試行を検出した。
- 誤入力、値リセット、候補不一致がある。
- Service Worker epochが変化した。
- PIIがログ、HTML、storage、画像、traceへ残った疑いがある。

停止時も最終送信を押さず、次のサイトへ自動移動しない。
