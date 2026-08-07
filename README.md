# kensho_assistant

懸賞候補の確認から応募フォームの最終送信直前までを補助するローカルアプリです。
応募の確定と最終送信は必ず人間が行います。

## 安全方針

- 最終送信、CAPTCHA、ログイン、規約同意は自動化しません。
- `submitted_count_auto`は常にゼロです。
- プロフィールは暗号化された既存機構で読み込みます。
- 実名、住所、電話番号、メールアドレスをログへ保存しません。
- 画面上でプロフィールを示す必要がある場合も伏せ字で表示します。
- pilot証跡は通常履歴と分離し、候補状態を変更しません。

## P1事前監査

```powershell
py -3 -m kensho_assistant.pilot.preflight
```

`READY_FOR_5_SITE_PILOT`以外の場合、実サイトpilotを開始しません。

## Chrome拡張機能MVP

`extension/`には、普段使っているChromeの現在のタブへフォーム入力補助を追加するManifest V3拡張機能があります。

役割分担:

- Codex: 候補ページを開き、ページ内パネルの解析・入力開始を指示する。
- Chrome拡張機能: フォーム解析、入力前プレビュー、明示操作による入力、ロールバック、送信防止を行う。
- 本人: 応募条件、規約、CAPTCHA、ログイン、入力内容を確認し、最終送信を行う。

Chromeへの読み込みとローカルfixtureでの確認方法は[extension/README.md](extension/README.md)を参照してください。既存Playwright経路は削除せず、拡張機能MVPと並行して保持します。
