# 懸賞入力補助 Chrome拡張機能 MVP

普段使っているChromeの現在のタブで、応募フォームを解析し、入力前プレビューを表示してから基本情報を入力します。拡張機能を有効にした現在の文書では最終送信をロックします。

## 現在の範囲

- Manifest V3
- `activeTab`、`scripting`、`storage`だけを使用
- 承認したoriginだけ`optional_host_permissions`で一時許可
- 未許可originでは、拡張機能アイコンから初回許可パネルだけを表示
- 本人が「このサイトで常に有効にする」を押したoriginでは自動起動
- 外部JavaScript、CDN、リモートコードなし
- プロフィールはローカルアプリから一回限りのloopback bridgeで必要項目だけ取得
- 入力中の一時参照以外へPIIを保存せず、旧セッションプロフィール経路へfallbackしない
- 管理APIは専用Service Workerへ直接渡した60秒以内の制御tokenを必須とし、`Origin`だけでは認証しない
- 入力後の進捗は、PII capabilityを実際に消費した時だけ得られる一回限りtokenへ束縛する
- ページ右下のShadow DOMパネルから解析・入力・ロールバック
- パネル表示後にフォーム解析を自動開始し、必要な場合だけ「フォーム解析」で再解析
- CAPTCHA検出時は入力せず安全停止。CAPTCHA、確認遷移、送信は本人対応
- ログイン、認証コード検出時は入力せず安全停止
- Enter、submitイベント、`form.submit()`、`form.requestSubmit()`、送信ボタンのクリックを遮断
- 規約同意チェックボックスは操作しない
- 初回フォームは欄ごとの人間確認が必須。確認済みfingerprintと一致するテンプレートだけ再利用し、構造変更時は入力せず停止
- 入力後は対象欄・対象外欄・フォームfingerprintを再検証し、不一致時は全変更をロールバック
- `submitted_count_auto=0`
- MAIN worldは`document_start`、ISOLATED worldはイベント捕捉を担当

## Chromeへ手動読み込み

1. Chromeで`chrome://extensions/`を開く。
2. 右上の「デベロッパーモード」をオンにする。
3. 「パッケージ化されていない拡張機能を読み込む」を押す。
4. 次のフォルダーを選ぶ。

```text
<kensho_assistantリポジトリルート>\extension
```

5. 拡張機能の詳細画面で、未承認サイトへの常時アクセスがないことを確認する。

独立版は旧パスの拡張機能と別インストールとして扱います。旧版を自動削除せず、新版のIDを記録してから旧版を無効化し、必要なサイト権限を再許可してください。詳しい手順は[独立版Chrome拡張の導入](../docs/EXTENSION_STANDALONE_INSTALL.md)を参照してください。新旧が同時に動作した場合は、入力操作を無効化して一時プロフィールを消去し、送信ガードだけを維持します。

Chromeウェブストア公開やGit pushは不要です。

## プロフィール境界

プロフィール原本は`assisted_session`側だけが扱います。確認済みテンプレートと
form fingerprintが一致した後、Service Workerが必要な項目名だけを要求し、
`127.0.0.1`の一回限りcapability bridgeから取得します。

- オプション画面にPII入力欄はありません。
- MAIN worldへPIIを渡しません。
- `storage.local`、`storage.sync`、LocalStorage、IndexedDBへ保存しません。
- bridgeが利用できない場合は旧経路へ切り替えず安全停止します。
- 入力後検証、ロールバック、セッション消去時にcontent script側参照を破棄します。
- ページ内パネルには固定のマスク表現だけを表示します。

## ローカル確認

Chromeツールバーを操作せず自動確認する場合は、次を実行します。専用の一時Chromeプロファイルと一時的なlocalhost専用ビルドを使用し、終了時に削除します。通常の拡張機能権限は変更しません。

```powershell
py -3 scripts\run_extension_local_smoke.py
```

このスモークはフォーム解析、ダミー情報の入力、ロールバック、送信遮断、セッション消去、外部通信0件を確認します。画面を表示して確認する場合だけ`--headed`を追加します。

手動で確認する場合は、外部サイトを使わず、リポジトリルートでローカルHTTPサーバーを起動します。

```powershell
py -3 -m http.server 8877 --bind 127.0.0.1
```

Chromeで`http://127.0.0.1:8877/tests/extension_fixtures/standard_form.html`を開きます。

1. 初回だけ拡張機能アイコンを押してパネルを表示する。
2. 「このサイトで常に有効にする」を押し、表示中originだけを許可する。
3. 自動再読み込み後、パネルが自動表示されることを確認する。
4. 自動解析済みの表示を確認する。「フォーム解析」は再解析が必要な場合だけ押す。
5. 「入力内容を確認」でマスク済みプレビューを確認する。
6. 初回フォームでは、高信頼の欄だけ「高信頼の欄を一括承認」で承認し、残りは欄ごとに
   割り当てを承認するか、「入力しない」を選ぶ。
   曖昧な欄は承認せず、マスク済みプレビューとfingerprintを確認する。
7. 必要なら「欄対応を保存」を押す。保存されるのはハッシュと構造情報だけで、PIIは保存されない。
8. 「入力を実行」を押す。
9. 規約同意が未選択のままであること、Enterと「応募する」が遮断されることを確認する。
10. 入力後に不一致があれば自動でロールバックされ、安全停止になることを確認する。
11. 「入力を元に戻す」で元の状態へ戻ることを確認する。
12. 「セッション情報を消去」でPIIだけを削除する。自動起動も解除する場合は
    「このサイトで自動起動しない」を押す。

## Codex Chrome拡張機能との併用

Codexは対象のChromeタブを開き、ページ内の固定パネルを確認します。主な操作は次の3つに限定します。

1. 「フォーム解析」
2. 「入力内容を確認」
3. 「入力を実行」

CAPTCHAがある場合も安全な基本項目だけ入力し、CAPTCHAの直前で人間へ引き継ぎます。ログイン、認証、未分類必須項目がある場合は停止理由を報告します。規約同意と最終送信は操作しません。Full CDPはMVPの通常操作には不要です。

## ページ遷移

許可済みoriginには、MAIN worldの送信ガードとISOLATED worldの操作パネルを
永続的な動的content scriptとして登録します。同じoriginの再読み込みとページ遷移では、
Chromeツールバー操作なしで自動起動します。別originへ移動した場合は注入せず、
新しいoriginで本人の明示許可が必要です。

## 安全上の制限

- 初回クリック後の文書は入力を許可しません。origin権限付与後の自動再読み込みで、
  `document_start`ガードを確認できた文書だけ入力します。
- 有効化前に作られたclosed Shadow DOMは解析できません。
- 外部originのiframeは入力せず、人間確認待ちで停止します。
- これらの制限があるため、ローカルfixture合格は実サイト互換性を保証しません。実サイトpilot前に1件ずつ非送信確認が必要です。

## テスト

```powershell
py -3 -m pytest tests\test_extension_mvp.py -q
node --test extension\tests\unit.test.cjs
```

テストはローカルHTMLだけを使用し、外部サイトへ接続しません。

### assisted_sessionとの実接続テスト

リポジトリのルートで実行します。

```powershell
$env:PYTHONPATH = Split-Path -Parent (Get-Location).Path
py -3.13 -m pytest tests/test_assisted_extension_integration.py -q
```

`run_extension_local_smoke.py`の`fixture-bridge`とは別に、実Web API、実Service Worker、
実loopback bridgeを接続して9項目の入力、入力後検証、全項目rollback、session clearを検証します。
起動・ビルド照合・一時プロファイル削除も正式な専用ブラウザ経路を使用します。
実プロフィール、実候補、通常履歴は使用せず、一時ディレクトリ内の架空データだけを使います。
候補の供給、旧Python解析境界、人間操作待ちと結果待ちはテスト用callbackです。
Web画面の人間承認操作そのもの、本番polling、実サイト互換性の合格を意味しません。

否定ケースは、フォーム変更、未承認template、version変更、重複タブ、
token配布前後の再読み込みです。いずれもプロフィール取得前に停止します。
Chrome自身の一時フォーム保存も考慮し、終了後はruntimeディレクトリが空であることと、
テスト保存領域にセンチネルがUTF-8/UTF-16LEで残らないことを確認します。
