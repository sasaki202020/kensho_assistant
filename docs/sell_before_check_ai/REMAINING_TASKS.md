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

- [ ] iOS実機でのUI微調整（Dynamic Type、ダークモード対応は未実装）
- [ ] 履歴一覧画面（現在は件数表示と削除のみ。必要なら追加）
- [ ] ルール辞書の拡充（実際の相談事例に基づくキーワード追加）
- [ ] App Store スクリーンショットの本番撮影（シミュレータ）

## 残タスク（人間にしかできないもの）

1. **Apple Developer Program 登録**（99 USD/年、D-U-N-S不要の個人登録可、承認まで数日）
2. **App Store Connect アカウント設定**（有料販売する場合は契約・税務・銀行口座も）
3. **バンドルIDの決定** — `capacitor.config.json` の `appId`（現在は仮の `jp.example.sellbeforecheck`）
4. **プライバシーポリシーの公開URL** — `PRIVACY_POLICY.md` を GitHub Pages 等で公開
5. **サポートURL** — `SUPPORT.md` を同様に公開し、連絡先メールを記載
6. **販売価格の決定** — 推奨: 無料で公開しレビューを集める → 将来 買い切り(¥300-500) or 機能追加で検討
7. **Macでのビルド・スクリーンショット確認** — `ios_app/README.md` の手順で Xcode ビルド
8. **TestFlight で家族・知人テスト** → フィードバック反映 → 審査提出

## ローカル版（C:\Users\goo10\OneDrive\ドキュメント\New project）との関係

このブランチの実装は、GitHub に元プロジェクトが見つからなかったため、
タスク仕様（URL構成・4段階判定・画面一覧）に基づく新規実装です。
ローカルに既存の `sell_before_check_ai` / `field_assessment_ai` がある場合は、
そちらを別ブランチで push してもらえれば差分を統合できます。
