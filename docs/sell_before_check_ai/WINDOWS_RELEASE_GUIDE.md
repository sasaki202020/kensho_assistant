# WindowsだけでApp Storeに公開する手順（Mac不要）

iOSアプリのビルドには通常Macが必要ですが、このリポジトリでは
**GitHub Actions のクラウドMac** でビルド〜TestFlightアップロードまで行えるため、
手元のパソコンはWindowsだけで公開作業を完結できます。

ワークフロー本体: `.github/workflows/ios-build.yml`

## 全体の流れ

| ステップ | 使うもの | 費用 |
|---|---|---|
| 1. Apple Developer Program 登録 | ブラウザ | 99 USD/年 |
| 2. App Store Connect APIキー作成 | ブラウザ | 無料 |
| 3. 配布証明書(.p12)の作成 | Windows + OpenSSL | 無料 |
| 4. App ID・プロファイル作成 | ブラウザ | 無料 |
| 5. GitHubにSecrets/Variables設定 | ブラウザ | 無料 |
| 6. Actionsでビルド→TestFlight | GitHubのクラウドMac | 下記参照 |
| 7. スクリーンショット撮影 | Windows + Playwright | 無料 |

GitHub Actionsの費用: **公開リポジトリなら無料**。プライベートリポジトリの場合は
無料枠(月2,000分)を消費し、macOSは10倍換算(実質200分/月)です。
1回のビルドはおおよそ10〜20分なので、月に数回のビルドなら無料枠に収まります。

## 1. Apple Developer Program 登録（ブラウザでOK）

1. https://developer.apple.com/jp/programs/enroll/ から個人で登録（D-U-N-S番号は不要）
2. 普段iPhoneで使っているApple IDでサインインし、本人確認・支払い（99 USD/年）
3. 承認まで通常1〜2日

登録後、https://developer.apple.com/account の Membership で **Team ID**（10桁英数字）を控える。

## 2. App Store Connect APIキー作成

1. https://appstoreconnect.apple.com → ユーザとアクセス → 統合 → App Store Connect API → チームキー
2. 「キーを生成」、ロールは **App Manager**
3. 控えるもの:
   - **Issuer ID**（ページ上部に表示）
   - **Key ID**
   - **AuthKey_XXXX.p8**（ダウンロードは1回しかできないので大切に保管）

## 3. 配布証明書(.p12)をWindowsで作る

Git for Windows に同梱の OpenSSL を使います（Git Bash を開いて実行）。

```bash
# 1) 秘密鍵とCSR(証明書署名要求)を作成
openssl genrsa -out dist.key 2048
openssl req -new -key dist.key -out dist.csr \
  -subj "/emailAddress=あなたのメール/CN=あなたの名前/C=JP"
```

2) https://developer.apple.com/account/resources/certificates/list で
「+」→ **Apple Distribution** を選び、`dist.csr` をアップロード → `distribution.cer` をダウンロード

```bash
# 3) .cer と秘密鍵を .p12 にまとめる（パスワードを聞かれるので決めて入力）
openssl x509 -in distribution.cer -inform DER -out dist.pem
openssl pkcs12 -export -inkey dist.key -in dist.pem -out dist.p12
# もしActions側で証明書の読み込みに失敗する場合は -legacy を付けて作り直す
```

4) GitHubに渡すため Base64 化（PowerShellで実行。クリップボードにコピーされる）

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("dist.p12")) | Set-Clipboard
```

`dist.key` と `dist.p12` は他人に渡さないこと。

## 4. App ID とプロビジョニングプロファイル作成（ブラウザ）

1. https://developer.apple.com/account/resources/identifiers/list →「+」→ App IDs → App
   - Bundle ID: **Explicit** で決める（例: `com.goo1002.sellbeforecheck`。一度決めたら変更不可）
   - Capabilities は何も追加しなくてよい（このアプリは通信・課金なし）
2. Profiles →「+」→ **App Store Connect**（Distribution）
   - 上で作ったApp IDと証明書を選択
   - プロファイル名を付ける（例: `sellbeforecheck-appstore`）→ この名前を後で使う

## 5. GitHubリポジトリに Secrets / Variables を設定

リポジトリの Settings → Secrets and variables → Actions で設定する。

**Secrets（秘密情報）:**

| 名前 | 値 |
|---|---|
| `IOS_DIST_CERT_P12_BASE64` | 手順3でBase64化した文字列 |
| `IOS_DIST_CERT_PASSWORD` | .p12作成時に決めたパスワード |
| `APPSTORE_ISSUER_ID` | 手順2のIssuer ID |
| `APPSTORE_KEY_ID` | 手順2のKey ID |
| `APPSTORE_PRIVATE_KEY` | AuthKey_XXXX.p8 をメモ帳で開いた中身全文 |

**Variables（公開してよい設定値）:**

| 名前 | 値 |
|---|---|
| `APP_BUNDLE_ID` | 手順4で決めたBundle ID |
| `APPLE_TEAM_ID` | 手順1のTeam ID |
| `IOS_PROFILE_NAME` | 手順4のプロファイル名 |

## 6. App Store Connect でアプリを作成 → Actionsでビルド

1. https://appstoreconnect.apple.com → マイApp →「+」→ 新規App
   - プラットフォーム: iOS / 名前: 売る前チェック / バンドルID: 手順4のもの / SKU: 任意（例: sellbeforecheck）
2. GitHub → Actions → **iOS build (sell_before_check)** → Run workflow
   - まず `upload_testflight` を **オフ** のまま実行し、ビルドが通ることを確認（Apple設定不要）
   - 通ったら `upload_testflight` を **オン** にして実行
3. 成功すると App Store Connect → TestFlight にビルドが現れる（処理に10〜30分かかることあり）
4. TestFlight → 内部テスト → 自分のApple IDをテスターに追加
5. iPhoneに **TestFlight** アプリを入れて招待を受け、実機で動作確認
   - ダークモード・文字サイズ（設定→画面表示と明るさ／文字サイズ）も確認

## 7. スクリーンショット（Windowsで撮影可）

シミュレータがなくても、Web版をスマホ解像度で撮影したものが使えます。

```powershell
py -3 -m pip install playwright
py -3 -m playwright install chromium
py -3 run_sell_before_check.py        # 別ウィンドウでサーバー起動
py -3 scripts/capture_sbc_screenshots.py
```

出力: `project/exports/sbc_screenshots/*.png`（1290x2796 = 6.7インチ用サイズ）。
App Store Connect の「スクリーンショット」欄にそのままアップロードできます。

## 8. 審査提出

App Store Connect でスクリーンショット・説明文（`APP_STORE_GUIDE.md` のドラフトを利用）・
プライバシーポリシーURL・サポートURLを入力し、TestFlightで確認済みのビルドを選んで提出。
詳細は `APP_STORE_GUIDE.md` を参照。

## つまずいたら

- **証明書エラー**: 手順3を `-legacy` 付きで作り直し、Secretsを更新
- **プロファイルが見つからない**: `APP_BUNDLE_ID` とプロファイルのApp IDが一致しているか、
  プロファイル種別が App Store Connect(Distribution) かを確認
- **アップロード後にTestFlightに出ない**: 処理待ちのことが多い。30分待つ。
  Apple からメールが来ていないかも確認（輸出コンプライアンス等は「暗号化なし」でOK。
  このアプリは独自の暗号化を使っていません）
