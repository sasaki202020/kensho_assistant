# 外出先スマホ運用

## 安全境界

- Webアプリは`127.0.0.1:8787`だけで待ち受けます。
- Tailscale Serveだけを使用し、Funnel、ポート開放、`0.0.0.0` bindは使用しません。
- Chrome Remote Desktopは入力結果の確認と、人間による規約同意・最終送信に使用します。
- CAPTCHA、ログイン、SNS操作、規約同意、最終送信は自動化しません。
- `submitted_count_auto`は常に0です。

## 自宅PCの初期設定

### 1. 許可ユーザー

Tailscaleへログインするメールアドレスを、Windowsのユーザー環境変数へ設定します。

```powershell
[Environment]::SetEnvironmentVariable(
  "KENSHO_ALLOWED_TAILSCALE_USERS",
  "user@example.com",
  "User"
)
```

複数人を許可する場合はカンマ区切りです。設定後、新しいPowerShellを開くかWindowsへ再ログオンしてください。未設定の場合、ローカル操作は維持されますが、Tailscale識別ヘッダー付きのアクセスは403になります。

### 2. Webアプリ

```powershell
cd "C:\Users\goo10\OneDrive\ドキュメント\New project"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_remote_ops.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_remote_readiness.ps1
```

停止するときは次を実行します。他のPythonやChromeは停止しません。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop_remote_ops.ps1
```

### 3. Tailscale Serve

自宅PCとスマホを同じtailnetへ登録し、端末承認を有効にします。自宅PCで次を一度実行します。

```powershell
tailscale serve --bg http://127.0.0.1:8787
tailscale serve status
```

`serve status`に表示される`https://...ts.net`がスマホ用URLです。`tailscale funnel`は実行しません。Webアプリはloopback接続だけを受け付け、Serveが付与する`Tailscale-User-Login`を許可リストと照合します。ヘッダー値は通常ログへ保存しません。

### 4. Chrome Remote Desktop

自宅PCのChromeで`https://remotedesktop.google.com/access`を開き、リモートアクセスを設定します。強いPINとGoogleアカウントの2段階認証を使用してください。スマホにはChrome Remote Desktopアプリを入れます。

### 5. 電源設定

- 自宅PCを有線または安定したWi-Fiへ接続します。
- 外出中はスリープしない設定にします。
- Windowsへユーザーがログオンした状態を維持します。
- 画面ロック中でもChrome Remote Desktopで復帰できることを事前確認します。

## タスクスケジューラ

1. Windowsの「タスク スケジューラ」を開き、「基本タスクの作成」を選びます。
2. トリガーを「ログオン時」にします。
3. 「ユーザーがログオンしているときのみ実行する」を使用します。
4. プログラムを`powershell.exe`にします。
5. 引数を次のように指定します。

```text
-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\goo10\OneDrive\ドキュメント\New project\scripts\start_remote_ops.ps1"
```

6. 「開始」を次にします。

```text
C:\Users\goo10\OneDrive\ドキュメント\New project
```

管理者権限や「ユーザーがログオンしているかどうかにかかわらず実行する」は使用しません。登録後、一度ログオフ・ログオンし、`check_remote_readiness.ps1`で確認します。

## スマホからの操作

1. スマホでTailscaleを接続します。
2. Serveの`https://...ts.net`を開きます。
3. 懸賞アシスタントで承認済み候補の入力補助を開始します。
4. Chrome Remote Desktopへ切り替え、自宅PCのフォームを確認します。
5. CAPTCHA、規約同意、クイズ、応募条件、入力内容を人間が確認します。
6. 人間が外部サイトの最終送信を押します。
7. 完了画面を確認してから、懸賞アシスタントの「送信済み・次へ」を一度だけ押します。

## 実応募前の1件テスト

1. 自宅PCで`check_remote_readiness.ps1`が`READY`になることを確認します。
2. スマホのモバイル回線からServe URLを開きます。
3. 許可していない別のTailscaleユーザーが403になることを確認します。
4. 期限内で通常フォーム型の候補を1件だけ選びます。
5. 入力補助を開始し、Chrome Remote Desktopで入力欄を項目単位に確認します。
6. CAPTCHA、規約同意、送信ボタンが自動操作されていないことを確認します。
7. この初回テストでは外部サイトの送信を押さず、保留または停止します。
8. `/health`で`submitted_count_auto`が0のままであることを確認します。

## 判定

- `READY`: Web、Tailscale Serve、Chrome Remote Desktop、状態ファイル、ブラウザプロファイルを確認済みです。
- `DEGRADED`: Webの安全性は保たれていますが、外出先運用に必要な周辺機能が不足しています。
- `BLOCKED`: Web停止、非loopback bind、health異常、状態破損、または`submitted_count_auto`異常です。応募補助を開始しないでください。
