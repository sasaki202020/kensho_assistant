# 売る前チェック App Store 公開までの残タスク

最終更新: 2026-06-11（このブランチ時点）

## 完了済み（このリポジトリにあるもの）

- [x] FastAPI Web MVP（全導線: home → flyer/item/quote → result）
- [x] 4段階判定ロジック（ルールベース・ローカル完結・テスト付き）
- [x] スマホ幅UI（セーフエリア対応・下部タブバー・44pt以上のタップ領域）
- [x] iOSアプリ本体（Capacitor + オフライン静的アプリ `ios_app/www/`）
- [x] 必要画面すべて: Home / 3チェック / 結果 / 断り文例コピー / 相場リンク / 188案内 / 免責 / プライバシー / 設定・データ削除
- [x] アプリアイコン原版・スプラッシュ原版（`ios_app/assets/`）
- [x] App Store 説明文・キーワード等のドラフト（APP_STORE_GUIDE.md）
- [x] プライバシーポリシー文面 / 免責文 / サポートページ文面
- [x] TestFlight / App Store Connect 手順書
- [x] 審査リスク表現の排除（断定表現なし・自動テストで担保）

## 残タスク（コード側 / Claudeが続きをやれるもの）

- [x] Dynamic Type 対応（iOSの文字サイズ設定に追従。rem ベース + `-apple-system-body`）
- [x] ダークモード対応（`prefers-color-scheme: dark`。Web・iOS共通CSS）
- [x] 履歴一覧画面（`#/history`。設定画面からアクセス、端末内のみ・最大50件）
- [x] ルール辞書の拡充（v0.3.0: 特別価格・今決め・査定額アップ・古銭・記念硬貨・腕時計・毛皮 など14語追加）
- [x] GitHub ActionsでのiOSビルド〜TestFlightアップロード（Mac不要。`.github/workflows/ios-build.yml`）
- [x] Windowsだけで公開するための手順書（`WINDOWS_RELEASE_GUIDE.md`）
- [x] App Store用スクリーンショットのWindows撮影対応（1290x2796。`scripts/capture_sbc_screenshots.py`）
- [ ] iOS実機での最終UI確認（TestFlight配布後に。Dynamic Type 最大サイズ・ダークモードの表示）

## 残タスク（人間にしかできないもの / Windowsだけで可）

詳しい手順は **`WINDOWS_RELEASE_GUIDE.md`** にまとめてあります（Macは不要です）。

1. **Apple Developer Program 登録**（99 USD/年、D-U-N-S不要の個人登録可、承認まで数日）
2. **App Store Connect アカウント設定**（有料販売する場合は契約・税務・銀行口座も）
3. **バンドルIDの決定**と App ID・証明書・プロファイルの作成（ガイド手順3〜4）
4. **GitHub に Secrets/Variables を設定**し、Actions の `iOS build` を実行（ガイド手順5〜6）
5. **プライバシーポリシーの公開URL** — `PRIVACY_POLICY.md` を GitHub Pages 等で公開
6. **サポートURL** — `SUPPORT.md` を同様に公開し、連絡先メールを記載
7. **販売価格の決定** — 推奨: 無料で公開しレビューを集める → 将来 買い切り(¥300-500) or 機能追加で検討
8. **TestFlight で実機確認・家族/知人テスト** → フィードバック反映 → 審査提出

## ローカル版（C:\Users\goo10\OneDrive\ドキュメント\New project）との関係

このブランチの実装は、GitHub に元プロジェクトが見つからなかったため、
タスク仕様（URL構成・4段階判定・画面一覧）に基づく新規実装です。
ローカルに既存の `sell_before_check_ai` / `field_assessment_ai` がある場合は、
そちらを別ブランチで push してもらえれば差分を統合できます。
