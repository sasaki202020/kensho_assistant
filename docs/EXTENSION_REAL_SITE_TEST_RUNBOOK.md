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

`prepare-session`は通常運用経路であり、Webの入力権限APIは`load_profile()`を使う。
`pilot-run`は従来の`engine.run`経路で、拡張機能ブリッジを検証する代替にはならない。
どちらもPhase 5Aの実行コマンドとして使用しない。Phase 5Aは下記の`pilot-nonsubmit`だけで行う。

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

## Phase 5A実行コマンド（`pilot-nonsubmit`）

2026-09-30時点でローカルfixtureのみ合格。実サイトでは未実施であり、
`REAL_SITE_NON_SUBMIT_PASS`は未達成である。

### 事前準備

1. 常駐Webアプリを停止する。拡張機能は`127.0.0.1:8787`固定で、pilotはこのportを
   排他bindできなければ開始しない（`PilotPortInUseError`）。
   `scripts/stop_remote_ops.ps1`で停止し、タスクスケジューラ等で起動している場合はそのタスクも止める。
   （`scripts/windows/uninstall_web_resident.ps1`はこのリポジトリに存在しない。）
   `Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8787 -State Listen`が空であることを確認する。
2. worktreeをcleanにし（未追跡ファイルも不可。`data/`と`build/`はignore対象）、HEADを固定する。
3. 固定commitで専用拡張をbuildする。実行中はbuildし直さない。

```powershell
$env:PYTHONPATH='C:\Users\goo10\Projects'
py -3.13 -m kensho_assistant.scripts.build_dedicated_extension
```

   出力の`build_sha256`を記録する。pilotは`build/extension`をソースから一時再buildした結果と比較し、
   不一致なら`REFUSED`（`dedicated_extension_build_unverified`）で停止する。

### manifest（1候補だけ）

`data/pilot/manifests/<id>.json`（ignore対象。commitしない）:

```json
{
  "candidate_id": "epinard-2026-09",
  "url": "https://www.epinard.jp/presentquiz/",
  "origin": "https://www.epinard.jp",
  "campaign_period_start": "2026-09-01",
  "campaign_period_end": "2026-09-30",
  "human_verified_at": "2026-09-30T10:00:00+09:00",
  "expected_fingerprint": "（任意。前回確認したフォームfingerprint）"
}
```

- 上記以外のkeyは拒否。`url`はhttpsのみ、query・fragment・認証情報不可。`origin`は`url`と一致し、
  `config/approved_origins.json`に含まれること。当日が期間外なら拒否。
- `expected_fingerprint`を指定し、実フォームと異なれば`FORM_CHANGED_REVIEW_REQUIRED`で入力前に停止する。

### 実行

リポジトリのルートで実行する。

```powershell
$env:PYTHONPATH='C:\Users\goo10\Projects'
py -3.13 -m kensho_assistant.main pilot-nonsubmit --manifest data/pilot/manifests/<id>.json
```

portの指定オプションはない（8787固定）。処理順序と停止条件:

1. 事前条件: clean worktree・HEAD、専用buildのソース照合、`config/approved_origins.json`とmanifestの
   SHA-256を記録。不一致なら何もbindせず`REFUSED`。
2. 通常保存領域（`data/apply_queue.csv`、`data/entries/`、通常の`data/assisted_session/session.json`等）の
   SHA-256をpilot保存領域へ切り替える前に取得。
3. 8787を排他bind、pilot Webアプリ（架空プロフィールloaderだけ）を起動し`pilot_run_id`で自分のserverか確認。
4. `service_worker_network_events()`内でPlaywrightを起動し、専用拡張・新しい一時プロファイルで
   Chromiumを開く（本人のChromeプロファイル・Cookieは使わない）。遷移前に通信監視を開始。
5. 候補URLへ遷移し、パネル1個・ガード1個・`guard_verified=true`（locked/integrity/installedAtDocumentStart）を厳密確認。
   通信監視の入力前ブロック理由（Service Worker通信の観測不能、ページService Worker、外部origin iframe、
   RTC等）と、拡張機能のCAPTCHA・ログイン・iframe検出が1つでもあれば停止する。
6. パネルの「フォーム解析」「入力内容を確認」から、値を含まない欄対応表（ラベル・分類・入力種別・提案キー）を
   コンソールに表示する。**欄ごとに`y`で承認し、それ以外（空Enter含む）は入力しない。一括承認はない。**
   pilotはパネルの「高信頼の欄を一括承認」を押さない。
7. 承認された欄だけで`MAPPING_CONFIRMED`にし（ロック済みpilot候補を使用。保存キューは読まない）、
   拡張機能の「入力を実行」で架空センチネルを入力する。
8. 入力後検証: 承認欄の値一致、対象外欄・同意checkboxの変化0、承認外の値0、遷移0、
   `submitted_count_auto=0`、自動送信検出0。
9. 拡張機能の「入力を元に戻す」（`rollback_complete`と入力前snapshot一致を確認）、
   「セッション情報を消去」、`end_pilot_session`、30秒以上の静穏待機、センチネル残存検査
   （DOM・各storage・Cookie・拡張storage・`data/pilot/runs/<run>`）、通常保存領域のhash比較、
   候補ロック解除、専用コンテキスト終了（一時プロファイル削除）。
10. `data/pilot/runs/<run>/result.json`に値を含まない証跡を保存して終了する。Phase 5Bへ進まない。

途中で停止しても、rollback・session clear・ロック解除・コンテキスト終了は必ず実行する。
最終送信、確認画面への遷移、規約同意、CAPTCHAの操作は行わない。実行中はChromiumのページを操作しない。

### 検出不能な欄（phone・postal_code）

架空値の`phone`・`postal_code`は数字だけで一意なnonceを含められず、通信・残存検査で検出できない。
既定では承認を求めずに「入力しない」に固定する（`decision=forced_skip_undetectable`）。
`--allow-undetectable`を付けた場合だけ本人承認の対象になるが、その結果は必ず`UNVERIFIED`となり、
PASSにはならない。架空プロフィールに値がないキー（都道府県・生年月日・性別等）も入力しない。

### 結果（`result.json`）

主なkey: `commit`、`extension_build_sha256`、`config_sha256`、`manifest_sha256`、`invariants_after`
（commit・clean・build・config・manifestが実行中不変）、`candidate_id`、`form_fingerprint`、
`mapping`（`label`・`field_type`・`input_type`・`proposed_profile_key`・`approved`・`decision`。値なし）、
`approved_profile_keys`、`page_state`、`prefill_blocking_reasons`、`post_fill`、`rollback`、
`session_clear`、`steps`（各段階の`PASS`/`FAIL`/`STOPPED`/`UNVERIFIED`/`NOT_RUN`）、`monitor`（通信監視の全結果）、
`residue`、`normal_store_hashes`、`submitted_count_auto=0`、`stop_reason`、`overall`。

`overall`:

- `REAL_SITE_NON_SUBMIT_PASS`: 実サイトで全段階PASS、`sentinel_network_leak=0`、
  `extension_non_loopback_requests=0`、`undetectable_fields_count=0`、残存0、通常保存領域hash一致、
  invariants不変のときだけ。
- `LOCAL_FIXTURE_NON_SUBMIT_PASS`: 同条件をローカルfixture（`127.0.0.1`）で満たした場合。実サイト合格ではない。
- `UNVERIFIED`: 未測定・不透明な通信・検出不能欄を含む。PASSではない。
- `STOPPED`: 入力前ブロック、`MAPPING_NOT_APPROVED`、`FORM_CHANGED_REVIEW_REQUIRED`等で停止。
- `FAIL`: 漏洩・残存・rollback不完全・hash差分等。

CLI終了コード: PASS=0、完了したがPASSでない=3、事前条件等で拒否=2。
nonce・入力値はファイル・ログ・標準出力のどこにも書かない。

### Service Worker通信の観測について

Playwrightは`PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS`付きでdriverを起動しないと、
拡張機能Service Workerの通信をrequestイベントとして通知しない。この変更以前の
`extension_non_loopback_requests`は、この設定なしで計測されていたため、0と表示されていても
実際には測定されていなかった（2026-09-26の読み取り診断の値を含む）。現在は
`service_worker_network_events()`で`sync_playwright()`を包み、loopback probeが観測できない場合は
`service_worker_network_unobservable`で入力前に停止し、指標は`UNVERIFIED`になる。

### ローカルfixtureでの検証方法

`tests/test_pilot_nonsubmit_e2e.py`は実Chromium・実専用build・実pilot Webアプリで上記を検証する。
拡張機能は8787固定のため、テストは一時ソースのService Workerで`http://127.0.0.1:8787`を
テスト用portへ書き換えてから専用buildする（`tests/test_assisted_extension_integration.py`と同じ方式）。
build照合はその一時ソースとの比較で行う。ChromiumにはDNS規則を渡し、loopback以外の名前解決を不可にする。
`allow_loopback_http_for_tests`・`browser_args`・短い静穏時間はテスト用のプロセス内設定で、CLIからは指定できない。

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
