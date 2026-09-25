# OSSフォーム入力補助の調査・採用記録

## 対象

2026-09-21、正本 `kensho_assistant`、開始HEAD
`290ee69efe8e0e4f9866f917f1573c9a696bc9db`、開始worktree clean。
外部コードは取得して読み取り確認しただけで、実行・インストール・転載していない。
比較テストは既存拡張機能をローカルChromiumで動かす。AutoContestの実行結果や
実サイトの成功率を測ったものではない。

## 固定した参照先と採否

| 参照先 | 確認revision | ライセンス確認 | 採用判断 |
| --- | --- | --- | --- |
| [AutoContest](https://github.com/AdamRiversCEO/AutoContest) | `5ce91bdc3209bc94b5b6e323ee72bd5b341eebd1` | MIT | 相対URL解決、複数情報源、重複排除、結果分類は既存実装を利用。フォーム選択と入力の危険例をローカル回帰テストへ追加 |
| [Form Filler](https://github.com/thuyydt/formfiller) | `c4121e6144e9a015cc2aaa59532eb8c79ab9caaa` | MIT | 日本語項目判定、複数の根拠、無効な選択肢の除外、Undoを参考。既存matcherとselect処理の不足を修正 |
| [Superfill](https://github.com/superfill-ai/superfill.ai) | `8f2f45117245092164406063ef033374f2b2236d` | LICENSEはself-hosted/BYOK Phase 1へのMIT適用を明記。単純な全体MIT扱いはしない | 選択肢の表示と内部値を区別する入力後検証を独自実装。プレビュー・信頼度UIは既存を維持 |
| [SweepSeeker](https://github.com/Jtekkk/contest-king) | `5798cb316ea4e93c910a5b6c9864f934346deb7a` | APIでlicense=null。許諾確認前のコード転載なし | READMEに記載された暗号化プロフィール、手動CAPTCHA、オフラインdriverの考え方は既存機能で充足 |
| [Sweepstakes Agent](https://github.com/RhythrosaLabs/sweepstakes-agent) | `54b6f3b1ca1c55df90fc9adf3e4649c51dbfff27` | MIT | README上の探索・履歴・dashboardは既存にあり重複エンジンを追加しない。LLM課金・自律送信は採用しない |
| [Typeless Forms](https://github.com/rifatshampod/Typeless-form-chrome-extension) | `c17938cc4c8ca101f86ac65a8f641e72e8d76e07` | GPL-3.0 | README上のframework対応イベントは既存native setter/input/change/blurで実装済み。コード転載・永続プロフィール保存なし |

実コードの重点確認: AutoContest.py、Form Fillerのhelpers/typeDetectionCore.ts・
clearUndo.ts・selectTypeDetection.ts、Superfillのdom-fill-verification.ts。
その他の候補はREADME・構成・license確認であり、コード全体の安全監査ではない。

## 今回反映した不足

1. autocompleteを部分一致せず、section/shipping/billing等を分離して標準の項目トークンで判定。
   `section-entry shipping name`、分割生年月日を認識し、`tel-national`を完全電話番号として扱わない。
2. placeholderや周辺文言の同義語の合算だけでは入力候補の閾値へ到達させない。
   初回mapping確認、既存confidence閾値、本人承認の要件は維持。
3. selectは表示名と内部valueを区別し、入力前に決めたoption・内部valueを入力後に検証。
   disabled option/optgroup、同名の複数候補、multiple selectは推測で選ばない。
4. 実際に入力を許可した欄だけを入力後の対象値検証へ渡す。除外欄は対象外変更検査の対象として残す。
5. 検索フォーム、応募フォーム、hidden、同意、賞品、自由記述、未知欄が混在する
   比較fixtureで、承認された標準項目2欄だけ入力し、完全rollback・通信0を検証。

実装先: `extension/content/field-matcher.js`、`extension/content/form-filler.js`。
検証先: `extension/tests/unit.test.cjs`、`tests/test_field_mapping_safety.py`。
サイト別selector、別応募エンジン、新規依存パッケージは追加しない。

## 既存機能を利用する箇所

- 相対リンク: `app/high_value/sources.py`の`urljoin`。
- 複数情報源と重複排除: `app/high_value/importer.py`、`ranking.py`。
- 候補キュー・履歴・進行状態: `app/assisted_session.py`、既存Web UI。
- 暗号化プロフィールと一回限りbridge: `app/profile_manager.py`、`app/extension_bridge.py`。
- マスクpreview・本人mapping・template: 拡張機能の既存overlayとmapping処理。
- 送信遮断・CAPTCHA停止・値の復元: 既存MAIN/ISOLATED guard、FormDetector、FormFiller。
- オフラインdriverの目的: 既存Playwright fixtureと拡張機能ローカルスモークで充足。

## AutoContestをそのまま動かさない理由

`submit_form_async`は先頭formを使い、checkboxを一律選択、radio/selectの先頭候補を使用し、
未知欄へ固定値を投入する。HTTP成功または成功風文言でSubmittedと判定し、
送信を再試行する。CAPTCHA代行、平文configへの個人情報保存も含む。
これらは測定対象となる危険例であり、本アプリの採用機能ではない。

Form Fillerのランダム選択やbooleanのyes優先、Superfillの未知selectへの直接代入、
ログへの実値返却も採用しない。原本コードの転載は0で、第三者コードの依存追加も0。

## 再現コマンド

正本ルート、インストール済み環境で実行する。

```powershell
$env:PYTHONPATH='C:\Users\goo10\Projects'
node --test extension/tests/unit.test.cjs
py -3.13 -m pytest tests/test_field_mapping_safety.py -q
py -3.13 -m pytest tests -q --tb=short
py -3.13 -m kensho_assistant.run_web --smoke-test
py -3.13 -m kensho_assistant.pilot.preflight
py -3.13 -m compileall -q app web main.py tests
git diff --check
```

全体テスト内の`test_extension_local_smoke.py`で再読込10回、worker再起動、
入力・rollback、セッション消去、送信遮断、通信センチネル検査を実施。
合格はローカル実装・検証の範囲。実サイトのPhase 5A/5Bや応募成功を意味しない。

## 今回の検証結果

- RED: autocomplete識別1件、placeholder単独の過信1件、selectの表示値・無効・重複4件を修正前に再現。
  比較fixtureで入力禁止欄の誤った対象値検証も再現した。
- GREEN: フォーム関連16 passed、Node 41 passed、Python全体598 passed / 0 failed。
- Python全体の所要時間385.21秒。websockets関連の非推奨警告2件。
- Chrome拡張ローカルスモーク: 全体テスト内でPASS。
- Web smoke: `WEB_SMOKE_TEST_OK`。
- P1 preflight: `READY_FOR_5_SITE_PILOT`。保存先分離・PII非保存・候補状態不変・送信ガードはtrue、
  `submitted_count_auto=0`、trace/screenshotはDISABLED。
- compileall・`git diff --check`: PASS。
- ローカル比較fixture: 入力2欄、完全rollback、対象外変更0、submitイベント0、通信0。
- 実プロフィール使用・実サイト入力・外部OSSの実行・commit・push: いずれも未実施。
- worktreeには今回の6ファイルの変更を残す。実サイトpilot用の固定buildとはまだ扱わない。

次の作業は、この差分をレビューして検証済みbuildへ固定すること。
実サイトpilotは既存の`GOAL_NON_SUBMIT_PILOT.md`の本人mapping確認とゲートに従う。
