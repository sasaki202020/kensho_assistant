# kensho_assistant

懸賞候補の確認から応募フォームの最終送信直前までを補助するローカルアプリです。
応募の確定と最終送信は必ず人間が行います。

## 安全方針

- 最終送信、CAPTCHA、ログイン、規約同意は自動化しません。
- `submitted_count_auto`は常にゼロです。
- プロフィールは暗号化された既存機構で読み込み、Git外の`%LOCALAPPDATA%\kensho_assistant\profile.enc`に保存します。
- 実名、住所、電話番号、メールアドレスをログへ保存しません。
- 画面上でプロフィールを示す必要がある場合も伏せ字で表示します。
- pilot証跡は通常履歴と分離し、候補状態を変更しません。

`KENSHO_PROFILE_PATH`を設定すると、別の絶対パスを使用できます。ただし、リポジトリ配下のパスは安全のため拒否します。実プロフィールは基準テストへ使用せず、独立ビルドの検証後に本人が登録します。

## 高額懸賞

Web UIの `/high-value` または「候補」画面の「高額懸賞を見る」から、3万円以上と価格確認待ちの候補を応募優先度順に確認できます。価格不明の高額カテゴリは推定せず、人間確認へ残します。`応募準備` は既存キューへ渡すだけで、最終送信は行いません。

ユーザーが保存した掲載一覧HTMLは、外部通信なしで取り込めます。

```powershell
py -3.12 -m kensho_assistant.main high-value import-html --source chance --html-file .\chance-list.html --source-url https://chance.com/list
py -3.12 -m kensho_assistant.main high-value list --min-value 30000 --limit 30
```

## 独立版の実行場所

この版のGitルートは`C:\Users\goo10\Projects\kensho_assistant`です。Pythonモジュールは親ディレクトリから実行します。

```powershell
Set-Location 'C:\Users\goo10\Projects'
py -3.12 -m kensho_assistant.pilot.preflight
py -3.12 -m kensho_assistant.run_web --smoke-test
py -3.12 -m kensho_assistant.run_web
```

旧OneDrive版や親Gitを実行・変更しません。実サイト確認は固定commit、fingerprint、拡張機能ID、P1事前監査を確認した後、[非送信Phase A手順](docs/EXTENSION_REAL_SITE_TEST_RUNBOOK.md)に従います。

## P1事前監査

```powershell
Set-Location 'C:\Users\goo10\Projects'
py -3.12 -m kensho_assistant.pilot.preflight
```

`READY_FOR_5_SITE_PILOT`以外の場合、実サイトpilotを開始しません。

## Chrome拡張機能MVP

`extension/`には、普段使っているChromeの現在のタブへフォーム入力補助を追加するManifest V3拡張機能があります。

役割分担:

- Codex: 候補ページを開き、ページ内パネルの解析・入力開始を指示する。
- Chrome拡張機能: フォーム解析、入力前プレビュー、明示操作による入力、ロールバック、送信防止を行う。
- 本人: 応募条件、規約、CAPTCHA、ログイン、入力内容を確認し、最終送信を行う。

Chromeへの読み込みとローカルfixtureでの確認方法は[extension/README.md](extension/README.md)を参照してください。既存Playwright経路は削除せず、拡張機能MVPと並行して保持します。
