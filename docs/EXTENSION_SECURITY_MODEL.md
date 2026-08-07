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

PIIは`chrome.storage.session`にのみ保存し、アクセスレベルは
`TRUSTED_CONTEXTS`のままとする。プレビュー要求ではマスク値だけを返す。
「入力を実行」の明示操作時だけ必要なプロフィールをcontent scriptへ返し、
入力処理直後にcontent script側の参照を破棄する。trustedな
`chrome.storage.session`内の値は、複数フォームで再利用できるよう
明示的なセッション消去、Chrome終了、拡張機能の無効化・更新まで保持する。

local/sync storage、Web Storage、IndexedDB、HTML、ログ、スクリーンショット、
traceへPIIを保存しない。

## フォーム対応の安全境界

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

未知サイトでは`activeTab`のみを使う。入力補助を有効化する際は、本人操作で現在の
originだけを`optional_host_permissions`として許可する。query string、fragment、
pathnameは権限やscript IDへ保存しない。許可後はMAIN/ISOLATEDの2本を
`persistAcrossSessions=true`で動的登録し、自動再読み込み後に
`document_start`ガードを確認できた場合だけ入力する。

`onInstalled`、`onStartup`、Service Worker起動時に現在の許可originと動的登録を
再照合する。権限のない古い登録は削除し、不足登録は復元する。

`<all_urls>`の常時権限は持たない。「セッション情報を消去」はPIIだけを削除する。
「このサイトで自動起動しない」は動的登録、origin権限、PIIを順に削除し、
再読み込み後は自動注入しない。

## Side Panel移行

現在のオーバーレイは送信ロック、CAPTCHA、ログイン、安全停止の表示を担当する。
将来は解析結果、プレビュー、入力、ロールバック、セッション消去をSide Panelへ移し、
ページ内表示を危険状態だけに縮小する。5サイトpilot前に必須とはしない。

## 既知の制限

- 外部origin iframeは解析・入力せず停止する。
- 有効化前に作られたclosed Shadow DOMは解析できない。
- fetch/XHRによるサイト独自応募は対応対象外として停止する。
- ローカルfixture合格は実サイト互換性を保証しない。
