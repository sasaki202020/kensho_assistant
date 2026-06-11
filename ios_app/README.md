# 売る前チェック iOSアプリ (Capacitor)

既存Web MVP のUI・判定ロジックを移植した、オフライン完結の静的アプリです。
サーバー不要・外部送信なしで動作します（App Store 審査でのプライバシー説明が簡潔になります）。

## 方式

- **Capacitor + 静的Web資産 (www/)** を採用
  - 既存の FastAPI MVP と同じ `rules.json` / CSS を共有（`scripts/sync_ios_assets.py` で同期）
  - 判定ロジックは `www/app.js` に移植済み（`sell_before_check_ai/logic.py` と同一仕様。同期テストあり）
  - ネイティブ層は Capacitor が生成する Xcode プロジェクトに任せ、保守対象は www/ のみ

## ローカル動作確認（Macがなくても可）

```bash
cd ios_app/www
python3 -m http.server 8790
# → http://127.0.0.1:8790 をスマホ幅で開く
```

## iOSビルド手順（Macで実行）

前提: macOS + Xcode 15以上 + Node.js 18以上

```bash
cd ios_app
npm install
python3 ../scripts/sync_ios_assets.py   # rules/CSSを最新化
npx cap add ios                          # 初回のみ: ios/ ネイティブプロジェクト生成
npx @capacitor/assets generate --ios     # assets/ からアイコン・スプラッシュ全サイズ生成
npx cap sync ios
npx cap open ios                         # Xcodeが開く
```

Xcode側:
1. Signing & Capabilities で自分の Team を選択
2. Bundle Identifier を自分のものに変更（`capacitor.config.json` の `appId` も同じ値に）
3. 実機 or シミュレータで Run

## TestFlight 配布

1. Xcode: Product > Archive
2. Organizer > Distribute App > App Store Connect > Upload
3. App Store Connect > TestFlight タブで内部テスター（自分のApple ID）を追加
4. iPhone に TestFlight アプリを入れて招待を受ける

詳細は `docs/sell_before_check_ai/APP_STORE_GUIDE.md` を参照。

## 注意

- `www/rules.js` と `www/style.css` は自動生成物。`sell_before_check_ai/` 側を直して同期スクリプトを実行する
- `appId` (`jp.example.sellbeforecheck`) は仮の値。Apple Developer Program 登録後に自分のドメインで決め直すこと
