# Goal: 実サイト1件の安全な応募準備

## 対象と境界

- 正本: `C:\Users\goo10\Projects\kensho_assistant`
- ゴール: `REAL_SITE_NON_SUBMIT_PASS`
- 最終送信、確認画面への遷移、規約同意、CAPTCHA、ログインは自動操作しない。
- 本人プロフィールを使わず、試行ごとに一意な架空センチネルを使う。
- 包括的な作業許可を、初回項目対応の本人承認の代わりにしない。
- 実サイトpilotは同一のclean commit・拡張機能ハッシュで実施する。

## 今回の修正範囲

保存済みキューは作成時点の情報であるため、表示・セッション候補選択・個別準備の
入口で期限切れと手動送信済みを再確認する。元キューの削除や書き換えは行わない。
既存CLIでもプロフィール復号より前に拒否する。
ブラウザの起動受付は入力完了ではなく、`preparation_verified=false`とする。
旧Web入口も検査付き起動処理へ統一し、起動受付だけで次候補へ進めない。
項目対応の確認待ち後、プロフィール復号前と入力権限発行前に保存キューを再読込する。
同一候補の重複行・保存先の読込失敗も入力権限を発行しない。

期限判定は公式ページの受付状況の証明ではない。年不明、相対日付、当日の締切時刻、
応募条件が不明な候補は、実サイトpilot前に公式情報を確認する。
年がない古い締切を、翌年のキャンペーンとして自動的に再解釈しない。
絶対日付は「本日中」等の補足より優先し、明示的な期間は終了日を使う。
複数日付の意味が確定できない場合、先頭日付を締切と決めつけない。

### 2026-09-13の候補確認

既存キュー3件のうち2件は保存された締切を過ぎていた。残り1件の
[Eucerin公式キャンペーン](https://www.kao.co.jp/eucerin/campaign/)は公式期間内だったが、
規約にプログラムによる自動応募や本人以外による入力の制限がある。
期限内であることを、自動入力試験に使用できることと同一視しない。
この候補で試験せず、入力補助と架空値による非送信検証が条件に抵触しない対象を確認する。

追加の読み取り確認では、[ホテルエピナール那須の公式プレゼントクイズ](https://www.epinard.jp/presentquiz/)に
2026-09-01から2026-09-30までの新しい回が掲載されていた。保存済みの8月分とは別候補として扱い、
古いID・承認・mappingを流用しない。標準項目はあるが、クイズ、主観アンケート、メルマガ選択は手動。
現段階はページの読み取り確認だけであり、自動入力の適合性、初回mapping、通信監視、rollbackは未検証。
次の候補確認はこの9月分から行い、条件確認と新しい候補の明示承認が済むまで入力しない。

### 自動注入診断と準備判定の修正

2026-09-13、commit `898a86f7e531c11dab5fb71bcb54753656c746b7`の固定ビルドで
エピナール那須の実ページを診断した。拡張機能version `0.2.0`、パネル1個、ガード表示1個、
入力0件・送信0件。拡張機能ビルドSHA-256は
`fc074589f4a0709a73b584d6e7e558a7c0608d438c8fa55ba4ad94e2585cf4b4`。
ツールバー操作を毎回要求する問題は、この専用経路では再現しなかった。

一方、`dedicated_extension_page_state`はガード実状態の欠落を0件として補完しており、
ガード未設置・遅延設置・不健全な状態でもPASSになり得た。ローカル実Chromiumで再現した。
修正後はMAIN worldの`locked`・`integrity`・`installedAtDocumentStart`を厳密に確認し、
未取得・不正な件数を`null`にしてfail-closedで停止する。ページ例外の本文は出力しない。
修正前の診断結果を、そのまま修正後buildのPhase 5A証跡には流用しない。

## 次の実装ゴール指示

**直近のゴールは、既存assisted_sessionを使った「架空値限定・1件・非送信」の検証経路を
ローカルで成立させること。自動応募エンジンを新設しない。**

現時点では通常のWeb入力権限APIが`load_profile()`を使い、従来の`pilot-run`は
拡張機能とは別の`engine.run`を使っている。通常経路を実サイトで起動してから
プロフィールを差し替える運用はしない。ローカル統合テストのmonkeypatchも実運用へ転用しない。

実装する場合は以下を順次行い、各段階でRED、最小変更、GREEN、独立レビューを実施する。

1. **架空プロフィールと保存先の分離**
   - 対象: `app/assisted_session.py`、`web/app.py`、既存pilot保存層、関連テスト。
   - 本人プロフィール供給元に到達しない明示的な検証用設定を追加する。暗黙fallback禁止。
   - 1候補のID・origin・fingerprintへ束縛し、lockと進行状態はpilot領域だけに保存する。
   - 失敗テスト: 本人プロフィールloader呼出0、通常候補・通常履歴の前後hash一致、
     2候補目拒否、手動送信済み操作拒否、session終了時のPII破棄。
2. **入力前から終了までの観測**
   - 対象: `app/browser_manager.py`、既存pilot安全検査層、ローカルfixtureテスト。
   - 拡張機能の非loopback送信と、サイト側へのセンチネル送信を別々に計測する。
   - POST body・URL・WebSocket payload等は値を保存せず一致検出だけ行う。
   - 通信本文が取得不能な場合も0で成功扱いせず、入力前に停止する。
   - 失敗テスト: fetch、XHR、beacon、WebSocket、autosave、validation、遷移、
     保存領域へのセンチネル残存。対象外通信の通常ページロードは漏洩件数と混同しない。
3. **ローカル統合、固定build、人間確認**
   - 対象: `tests/test_assisted_extension_integration.py`、
     `docs/EXTENSION_REAL_SITE_TEST_RUNBOOK.md`、本指示。
   - fixtureでmapping未承認時入力0、承認後の入力・POST-FILL・完全rollback・
     session clear・残存0・通常状態差分0を実測する。
   - 正確な検証CLIを文書化し、全テスト・Web smoke・P1 preflightを再実行してから固定する。
   - その後で初めて1候補の公式条件を再確認し、実際のmapping表の本人承認を求める。

候補条件確認、通信観測、保存先分離、初回mappingのいずれかが未完了なら入力しない。
UI拡張、候補収集追加、閾値緩和、サイト固有回避、最終送信はこの実装ゴールに含めない。

## 実行指示

1. Gitルート・HEAD・branch・worktreeを確認する。他プロジェクトは参照しない。
2. 下記ローカル検証を実行する。失敗したら実サイトへ進まない。
3. 修正が必要ならfail-first testから最小変更する。既存テストは削除・無効化しない。
4. 検証済み修正を許可済みのローカルcommitに固定する。pushしない。
5. 既存候補のうち1件だけ、公式ページで期間・応募条件・フォームを読み取り確認する。
   同じURLでも月替わりキャンペーンを過去の候補と同一視しない。
6. 検証専用経路がローカル合格した後、ログイン不要の標準フォームで、
   自動注入・パネル1個・送信ガード1個・`guard_verified=true`を確認する。
7. 候補ロック後にフォームfingerprintと値を含まない項目対応表を提示し、本人承認を待つ。
8. 監視可能な環境で、承認された欄だけにセンチネルを入力する。
9. 対象値の一致、対象外欄・同意・賞品状態の不変、遷移・送信なしを確認する。
10. 完全ロールバック、セッション消去、センチネル残存検査、候補ロック解放を行う。
11. 個人情報を含まない証跡を`data/pilot/`に保存する。通常履歴へ応募済みを記録しない。

## 合格条件

- commit・設定・拡張機能ハッシュが試行中に不変。
- 人間確認済みmapping、入力後検証、完全rollback、session clearがすべてPASS。
- 対象外field、規約、メルマガ、賞品選択の意図しない変更が0。
- `submitted_count_auto=0`、`auto_submit_detected=0`、最終送信なし。
- センチネルのネットワーク漏洩・永続保存が0。
- 拡張機能の非loopback送信が0。ページの通常ロード通信と区別する。
- 通常候補と応募履歴の差分が0。未測定の指標は0でなくUNVERIFIEDとする。

1つでも未確認なら合格にしない。autosave、改変、誤入力、rollback不完全で停止する。
Phase 5A合格で終了し、本人プロフィールを使うPhase 5Bへ自動で進まない。

## ローカル検証コマンド

正本ルートで実行する。

```powershell
$env:PYTHONPATH='C:\Users\goo10\Projects'
py -3.13 -m pytest tests/test_pilot_nonsubmit.py tests/test_pilot_nonsubmit_e2e.py tests/test_pilot_network_monitor.py -q
py -3.13 -m pytest tests/test_queue_prepare_safety.py tests/test_assisted_session.py tests/test_web_app.py -q
py -3.13 -m pytest tests/test_browser_manager.py tests/test_dedicated_browser.py tests/test_assisted_extension_integration.py -q
py -3.13 -m pytest tests -q --tb=short
node --test extension/tests/unit.test.cjs
py -3.13 -m kensho_assistant.run_web --smoke-test
py -3.13 -m kensho_assistant.pilot.preflight
py -3.13 -m compileall -q app web main.py tests scripts
git diff --check
```

全体テストにはChrome拡張ローカルスモークを含む。P1 preflightは一時ストレージの
自己検査であり、それだけで実サイトの通信・PII非保存を証明したとは扱わない。

## 2026-09-13 修正後のローカル検証

- 修正前RED: guard状態のユニット試験32件FAIL、および実Chromiumの欠落・遅延・早期設置試験で旧判定を確認。
- 修正後: browser manager・専用build・実ブリッジ統合の関連57件PASS。
- 全Python: 591 passed / 0 failed、426.31秒。依存ライブラリの非推奨警告2件。
- Node拡張: 39 passed / 0 failed。
- Chrome拡張ローカルスモーク: 全体テスト内でPASS。再読込10回、別pathname、worker再起動を含む。
- Web smoke: `WEB_SMOKE_TEST_OK`。
- P1 preflight: `READY_FOR_5_SITE_PILOT`。trace・screenshotはDISABLED、`submitted_count_auto=0`。
- compileall、`git diff --check`: 成功。
- 読み取り専用の独立レビュー: GO、Critical/Importantなし。
- 候補キューSHA-256は変更前と一致:
  `d243e77a7202548fd42eb237e8b2d9eb05334226a8083c95e3e0a775c4d5f5fa`。

ここまでで合格したのはローカル安全修正である。実サイトのセンチネル入力・通信漏洩検査・
rollback・残存検査は未実施であり、`REAL_SITE_NON_SUBMIT_PASS`ではない。

## 2026-09-30 エピナール型ローカルリハーサル

`tests/pilot_e2e_fixtures/epinard_like.html`でクイズ3問、氏名・フリガナ、
生年月日、住所等、メルマガ、自由記述を含む複合フォームを再現した。人間の欄別承認は
氏名・フリガナ・メール・住所の4欄だけで、capability要求は展開後の承認済み6キーだけ。
手動欄を含む対象外欄の変更0、入力後確認、完全rollback、session clear、残存0を
実Chromium・専用拡張・loopback fixtureで確認する。`external.test`はこの試験でのみ
loopback fixtureへ割り当て、他の非loopback DNSは遮断する。

入力直前からタブ終了まで非loopback要求を`BrowserContext.route`で検査し、本文を
確認できない要求とセンチネルを含む要求は送出前にabortする。成功したabortは
`blocked_opaque_requests`と`blocked_sentinel_attempts`へ別計上する。後者が1件でも
試行結果はFAIL。`sentinel_network_leak`は送出が確認されたものだけを数え、観測不能は
`UNVERIFIED`とする。Chromiumがunload時のbeaconをrouteに通知しない場合があるため、
終了直前にページのネットワークを遮断し、route未観測分を`UNVERIFIED`のまま残す。
拡張機能Service Workerの非loopback通信とWebSocketは従来の別監視を維持する。
この状態のPASSは「遮断下のPASS」であり、無遮断での無漏洩証明ではない。

8桁のフォームfingerprintが一般の電話番号マスクに誤認されるとcapability束縛が
壊れるため、拡張機能が生成する8桁hex形式に限り保存時の変形を避ける。
架空のカナ値は英数字センチネルなので、実サイト初回のカナ欄は不承認を推奨する。
今回のリハーサルは実サイトのPhase 5A合格を示さない。
このworktreeの検証コマンドは`C:\Users\goo10\Projects\wt-reh\kensho_assistant`で
`$env:PYTHONPATH='C:\Users\goo10\Projects\wt-reh'`を設定して実行する。

## 2026-09-20 検証プロフィール境界と通信計測

拡張機能capabilityのローカルfixtureは、`web.create_app(profile_loader=...)`で明示的な
インプロセスfixtureローダーを渡せる。HTTP payloadからプロフィール供給元を選ぶ経路はなく、
引数を省略した通常アプリは従来どおり暗号化プロフィールのローダーを使う。統合テストでは
実プロフィールローダーを呼ぶと失敗するようにして、架空プロフィールだけでbridgeの往復を確認する。

`scripts/run_extension_local_smoke.py`は、入力値を保存せずに、request本文・URL・WebSocket送信フレームに
fixtureセンチネルが含まれた回数を`sentinel_network_leak`として計測する。また、frameを持たない
拡張機能由来の非loopback通信を`extension_non_loopback_requests`として別計測する。いずれも
ローカルfixtureでは0でなければPASSにしない。

今回の変更で確認するのはローカルfixtureの境界だけであり、実サイトの入力・通信監視・rollback・
残存検査を完了したことを意味しない。

## 2026-09-21 入力精度と復旧性の補完

既存のassisted_sessionと拡張機能を維持し、新しい応募エンジンは追加しない。
OSS比較の採否は `OSS_FORM_ASSIST_ADOPTION.md` に記録する。外部コードの実行や依存追加はない。

今回の修正:

- autocompleteの完全なtokenで項目を判定し、placeholderの類語だけで高信頼にしない。
- selectの表示名と内部値を区別し、曖昧・無効な選択肢は入力しない。
- 入力後検証では実際に入力した欄と未入力欄を区別する。プロフィールに値がない欄は未変更を検証する。
- 入力後fingerprint確認で要素参照を作り直さず、ロールバック後の再入力を壊さない。
- 入力直前の構造変更は、プロフィール取得前に停止する。
- 入力例外時にプロフィール応答の参照を破棄し、検証付きロールバックを行う。
- worker通信の例外・無応答でもローカル復元を実施する。復元または正本への報告が未確認なら停止する。
- 個別欄の復元失敗で他の欄の復元を中断しない。復元不完全を成功扱いしない。

REDは入力例外・worker例外・無応答・復元例外の4ケース、および構造変更・再入力の2ケースで確認した。
ローカルUI試験は通信境界とguard通知をfixture化するため、それ単独で実拡張や実サイトの合格とはしない。
実ブリッジ・Chrome拡張ローカルスモークは全体テストで別に検証する。

次のゲートは引き続きPhase 5Aである。試験対象の明示、初回欄対応の本人確認、
clean buildの固定、実プロフィール・通常履歴から隔離した実行経路を揃え、
1サイトの入力・rollback・session clear・通信と残存検査を実測する。
今回のローカル改善だけで `REAL_SITE_NON_SUBMIT_PASS` や製品完成とは判定しない。

検証結果:

- フォーム・拡張UI関連: 60 passed。
- 全Python: 604 passed / 0 failed、416.34秒。依存ライブラリの非推奨警告2件。
- Node拡張: 41 passed / 0 failed。
- Chrome拡張ローカルスモーク: 全体テスト内でPASS。
- Web smoke: `WEB_SMOKE_TEST_OK`。
- P1 preflight: `READY_FOR_5_SITE_PILOT`。storage分離・PII検査・状態不変・guard検査はtrue、
  `submitted_count_auto=0`、trace/screenshotはDISABLED。
- compileall、`git diff --check`: 成功。
- 作業対象: `codex/high-value-kensho-v1`、基準HEAD `290ee69efe8e0e4f9866f917f1573c9a696bc9db`。
  今回の変更は未commitで、固定済みpilot buildではない。push・実サイト入力・応募送信は未実施。
- 公開キャンペーンページの読み取り確認は行ったが、実プロフィールは読んでいない。

## 2026-09-30 Phase 5A実行経路（ローカルfixtureのみ）

`pilot-nonsubmit`にブラウザ段階を統合した。新しい入力エンジンは追加せず、既存の
`assisted_session`、専用拡張build、拡張機能パネル（フォーム解析・入力内容を確認・入力を実行・
入力を元に戻す・セッション情報を消去）、`SentinelNetworkMonitor`、残存検査を使う。

```powershell
$env:PYTHONPATH='C:\Users\goo10\Projects'
py -3.13 -m kensho_assistant.main pilot-nonsubmit --manifest data/pilot/manifests/<id>.json
```

- 常駐Webアプリを先に停止する（`scripts/stop_remote_ops.ps1`、またはそれを起動するタスクの停止）。
  8787を排他bindできなければ開始しない。
- 事前条件（clean worktree・HEAD、専用buildのソース照合、設定・manifestのSHA-256）が満たされなければ
  何もbindせずに拒否する。実行中にbuildし直さない。
- 欄対応は欄ごとの`y`承認だけ（既定は入力しない）。一括承認はない。`phone`・`postal_code`は
  既定で入力しない。`--allow-undetectable`で許可した場合、結果は`UNVERIFIED`でありPASSにならない。
- `MAPPING_CONFIRMED`はロック済みpilot候補だけで到達する（`assisted_session.confirm_pilot_mapping`）。
  通常候補loaderと保存キューは使わない。拡張機能のテンプレートが本人承認と異なるkeyを含めば停止する。
- 証跡は`data/pilot/runs/<run>/result.json`。値・nonceは保存しない。`overall`は全指標が厳密に
  PASS/0の場合だけPASS。未測定は`UNVERIFIED`。ローカルfixtureのPASSは
  `LOCAL_FIXTURE_NON_SUBMIT_PASS`と表示し、`REAL_SITE_NON_SUBMIT_PASS`とは区別する。
- manifest形式、停止条件、証跡の詳細は[実サイト非送信確認手順](EXTENSION_REAL_SITE_TEST_RUNBOOK.md)を正本とする。

Service Worker通信の観測: Playwrightは`PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS`付きで起動しないと
拡張機能Service Workerの通信を通知しない。この変更以前の`extension_non_loopback_requests`は
この設定なしで得た値であり、測定されていなかった。現在は`service_worker_network_events()`で
`sync_playwright()`を包み、観測できなければ入力前に停止する。

ローカル検証（`tests/test_pilot_nonsubmit_e2e.py`、実Chromium・実専用build・実pilot Webアプリ）:
名前・メールだけ承認でfixture PASS（漏洩0・拡張非loopback 0・残存0・通常hash一致・実プロフィールloader呼出0）、
全欄不承認で入力0、phoneの強制不入力と`--allow-undetectable`時の`UNVERIFIED`、入力3秒後のautosaveで`FAIL`
（rollback・session clearは実施）、ページService Worker・外部origin iframeで入力権限発行前に停止、
fingerprint不一致で`FORM_CHANGED_REVIEW_REQUIRED`、Service Worker通信観測なしで入力前停止、
run directory・標準出力・標準エラーにnonceなし。

実サイトでの入力・通信監視・rollback・残存検査は未実施であり、`REAL_SITE_NON_SUBMIT_PASS`は未達成。
次は固定commitでbuildし、1候補の公式条件を再確認してから本人の欄ごと承認で1回だけ実行する。
