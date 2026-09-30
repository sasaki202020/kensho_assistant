# Chrome拡張機能セキュリティモデル

## 責任境界

- Codex: 対象タブの選択、解析開始、警告の報告まで。
- Chrome拡張機能: フォーム解析、入力候補、入力、送信遮断、安全停止。
- 本人: 応募条件、規約、CAPTCHA、ログイン、最終送信。

拡張機能とCodexは、規約同意や最終送信を行わない。

## JavaScript world

MAIN worldの`submit-guard.js`は、承認したoriginへ動的content scriptとして
`document_start`に注入する。`form.submit()`、`requestSubmit()`、
JavaScriptの送信ボタン操作、submitイベントを遮断し、prototype改変を検出する。
PIIはMAIN worldへ渡さない。

ISOLATED worldの`isolated-guard.js`はclick、Enter、submitイベントを捕捉する。
フォーム解析、入力処理、ページ内状態表示もISOLATED worldで行う。

## PIIライフサイクル

正規の入力経路では、プロフィール原本はローカルアプリだけが扱う。
プレビューは固定マスクを用い、「入力を実行」の明示操作時だけ、承認済みの
項目値を一回限りのloopback bridgeから取得してcontent scriptへ渡す。
入力処理直後に参照を破棄する。旧セッションプロフィールへのfallbackは行わない。
tokenを扱う`chrome.storage.session`のアクセスレベルは`TRUSTED_CONTEXTS`とする。

local/sync storage、Web Storage、IndexedDB、HTML、ログ、スクリーンショット、
traceへPIIを保存しない。

Chrome自体はフォーム値を一時プロファイルのセッションファイルに記録する可能性がある。
専用経路は試行ごとの一時プロファイルを使い、終了時に全体を削除する。
削除後も残る場合は`dedicated_profile_cleanup_failed`で失敗とする。
ブラウザ異常終了時の残存と、通常Chromeプロファイルでの保存防止は、この削除検証と
同一視しない。実サイトPhase 5Aでは試行後の残存検査が別途必要。

## 項目確認とbridgeの接続

Web側の項目確認後、専用Service Workerから値を含まない承認情報だけを取得する。
対象URLのタブは1つに限定し、保存済みテンプレートのorigin、pathname、version、
承認日時と現在のform fingerprintを検証する。再計算で入力用のelement registryを壊さない。
`assisted_session`はそのfingerprintと承認済み項目名を入力前に記録する。
capabilityの要求項目は承認済み項目の部分集合に限定する。

control tokenとPII capabilityをtab IDだけでなくdocument IDにも束縛する。
確認後に別タブへ移った場合や、同じタブを再読み込みした場合はPIIを渡さない。
新documentは新しい項目確認が必要。候補切替時は前候補のfingerprintと承認項目を破棄する。

保存済みmappingは上書きしない。同内容の再保存では承認日時と一時的なfield IDを
同一性比較から除外し、既存の承認日時を保持する。旧templateの承認日時が空のときだけ、
本人が「欄対応を保存」を実行した際に日時を補完する。構造・割当・version変更は競合として拒否する。

## フォーム対応の安全境界

通常assisted sessionは、人の欄対応承認後、入力対象一致・無関係欄変更ゼロ・送信なしの検証が合格したテンプレートだけを`data/form_templates.json`へ原子的に保存する。欄情報は構造path、approvedProfileKey、confidenceBand、disabled、readOnlyだけで、入力値・ラベル・selector候補・fieldIdを保存しない。未知キー、origin policyで拒否されたorigin、不正な型・長さ・日時・pathを拒否する。

承認日時から180日以内、現在の専用拡張versionとbuild SHA-256一致のものだけを候補遷移前にworkerへseedし、読み戻し一致を確認する。同じorigin/pathnameの内容衝突は上書きしない（sessionに`conflict`のみ記録）。既存の厳格なmapping検証・capability binding・入力後検証・送信ガードは維持する。一致した場合だけ既存パネルの解析・確認・入力を進める。seed失敗は消去確認後に人の確認へ戻り、消去を確認できなければ安全停止する。pilotではストアAPIが`PilotIsolationError`となり、Phase 5Aはストアを使わない。

初回フォームは、候補の信頼度にかかわらず、欄ごとの人間確認が完了するまで
実PIIを入力しない。信頼度0.95以上は確認画面へ候補として表示し、0.75以上
0.95未満は人間が割り当てを承認した場合だけ入力し、0.75未満は入力しない。
同意、賞品選択、感想、応募理由、パスワード、認証コード、決済、ファイル添付などは
常に手動確認へ回す。

承認済みテンプレートはoriginと正規化pathname、フォームfingerprint、構造ハッシュ、
欄の相対パス、属性・label・選択肢のハッシュ、承認したプロフィール項目だけを保存する。
入力値、label全文、HTML、query、fragmentは保存しない。pathnameにエンコード文字列、
バックスラッシュ、メール形式、長い数値が含まれる場合はテンプレートを拒否する。

入力後は対象欄の値、対象外欄、checkbox/radio/selectの状態、fingerprintを再検証する。
不一致なら変更した欄をすべて元に戻し、`POST_FILL_VERIFICATION_FAILED_ROLLED_BACK`で停止する。
ロールバック後も差分が残る場合は`ROLLBACK_INCOMPLETE_HUMAN_REVIEW_REQUIRED`として、
以後の入力を禁止する。

## Service Worker停止

Service Workerの起動ごとに新しいepochを生成する。解析時と入力時のepochが
異なる場合、古い解析結果では入力せず、「プロフィールの再読込が必要」として停止する。
重要状態をService Workerのグローバル変数へ復旧しない。

## origin権限

専用ブラウザのビルドは1つに固定する。`host_permissions`は
`https://*/*`、`http://127.0.0.1/*`、`http://localhost/*`で固定し、
`optional_host_permissions`と静的`content_scripts`を含めない。
`version_name=dedicated-runtime-origin`で通常インストール版と区別する。
`config/approved_origins.json`はビルド・注入判定・テンプレート保存に使わず、
origin設定変更ではbuild SHA-256が変わらない。ソース変更時は再ビルドと再検証が必要。

本人がキューで承認した候補のoriginだけを実行時に1つ有効化する（候補承認＝origin承認）。
`approved_by_user=true`、`APPROVED/PREPARED`、`queue_prepare_block_reason`なしの候補の
`resolved_entry_url`からoriginを求める。`origin_policy`はコード既定拒否リストと
`config/origin_denylist.json`をマージし、SNS・認証・決済の指定ドメインと全サブドメイン、
login/signin/account/auth/payを含むサブドメイン、userinfo、非標準ポートを拒否する。
HTTPSのみで、loopback HTTPは明示されたインプロセスのテスト用フラグだけで許可する。
銀行・カードの全ドメインを網羅する保証はない。規約確認と本人の判断は引き続き必要。

アクティブoriginは`chrome.storage.session`の`TRUSTED_CONTEXTS`に保存する。
Pythonは候補遷移前に期限付きworker evaluateで`setActiveOrigin`を呼び、
origin/sessionと登録内容の読み戻し一致を確認する。不一致・timeoutではブラウザを閉じ、遷移しない。
workerは`permissions.getAll()`を使わずアクティブoriginのMAIN/ISOLATEDだけを登録し、
`persistAcrossSessions=false`とする。未設定時は登録ゼロ。候補切替では旧登録をすべて解除してから
新originを登録する。解除・終了・異常時は全管理対象登録と一時プロフィール/capabilityを消去し、
消去確認不能なら専用コンテキストを閉じて一時プロファイルを削除する。

設定・解除のruntimeメッセージ経路は存在しない。content script・ページ・外部メッセージから
アクティブoriginを変更できない。content scriptの全メッセージで、送信元拡張ID・top frame・
送信元originとタブoriginの一致を確認し、非アクティブoriginへプロフィール・capability・
テンプレートを返さない。応答時にもoriginを再確認する。登録解除は既存documentのガードを
撤去しないが、旧documentからの要求を拒否し、以後のロードには注入しない。

pilotでは人が書いたmanifest自体を候補originの承認とし、同じorigin policyと固定ビルドを使う。
manifestのoriginだけを有効化し、終了時に解除する。通常テンプレートストアには触らない。

通常インストール版は従来の`activeTab`、本人操作による`optional_host_permissions`と
`permissions.request`、許可originの永続動的登録を維持する。
専用版の広いホスト権限を通常版の権限付与フローと混同しない。

## Side Panel移行

現在のオーバーレイは送信ロック、CAPTCHA、ログイン、安全停止の表示を担当する。
将来は解析結果、プレビュー、入力、ロールバック、セッション消去をSide Panelへ移し、
ページ内表示を危険状態だけに縮小する。5サイトpilot前に必須とはしない。

## 既知の制限

- 外部origin iframeは解析・入力せず停止する。
- 有効化前に作られたclosed Shadow DOMは解析できない。
- fetch/XHRによるサイト独自応募は対応対象外として停止する。
- ローカルfixture合格は実サイト互換性を保証しない。
