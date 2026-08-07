# Kensho Assistant v1 Completion Plan

> **Execution rule:** 実装は各Taskごとにfreshな実装サブエージェントを使い、仕様レビューとコード品質レビューを別サブエージェントで実施する。Critical/Importantを修正し、関連テスト後に全テストを実行する。

## 1. 現状

- 固定5サイト x 3回のpilot計画、trial ID、manifest ID、集計CLIは実装済み。
- 現在の確認済み基準は `322 passed`、compileall成功、Web smoke成功、送信防止・PII関連22 passed。
- 実サイトpilot、公式90試行、製品性能改善は未実施。
- 実サイト操作、最終送信、CAPTCHA回避、認証突破は対象外。
- 4系統の読み取り専用監査はすべてNO-GO。Safety AuditorはCritical 4件、Evidence/Test/Runbook Auditorはpilot前Importantを報告した。

## 2. Pilot開始判定

**NO-GO**

以下のCriticalが未解消である。

1. 送信ガードが初回遷移前、ページ遷移後、iframe、入力後再装着まで連続していない。
2. CAPTCHA・ログイン・認証等を入力後に検出する経路があり、PII入力前停止を保証できない。
3. safety stop、ガード発火、意図しない送信疑いの後も残り試行を継続する。
4. pilot runnerが実行時にdry-run engineを強制せず、送信フラグ上書きにより事故証跡を隠す可能性がある。

加えて、pilot/通常証跡の混在、manifest計画との照合不足、candidate_refのPII検査不足、実context・実ストレージ試験不足をpilot前に解消する。

## 3. Pilot前に必要な最小修正

### Task P0-1: 連続送信ガード

**対象ファイル**

- `app/submission_guard.py`
- `app/pilot_validation.py`
- `app/auto_apply_engine.py`
- `tests/test_submission_guard.py`
- `tests/test_pilot_validation.py`
- ローカル二段階mock form

**TDD**

1. context作成直後、`goto`前にguard init scriptを登録する失敗テストを追加する。
2. 遷移後document、遅延submit、iframeでclick、Enter、`submit()`、`requestSubmit()`が通信・URL遷移0件になることを実Chromiumで確認する。
3. pilotではcontext終了までguardを解除しない最小実装を行う。
4. 通常の人間送信経路は既存契約を維持し、pilot専用動作と分離する。

**合格条件**

- 自動処理開始からpilot context終了までguard空白0。
- submit関連4経路、イベント伝播、遷移後document、iframeで外部送信0。

### Task P0-2: PII入力前安全プリフライト

**対象ファイル**

- `app/auto_apply_engine.py`
- `app/pre_submit_verifier.py` または既存の安全判定helper
- `tests/test_auto_apply_engine.py`
- CAPTCHA・login・SNS・認証mock forms

**TDD**

1. CAPTCHA、ログイン、会員登録、SMS/メール認証、SNS、LINEページで全入力欄が空の失敗テストを追加する。
2. 既存検出を入力前preflightとして再利用する。
3. 該当時はterminal safety stopを返し、field mapping/fillを呼ばない。

**合格条件**

- 対象ページでPII入力0、送信0、明確な停止理由あり。

### Task P0-3: Manifest全体の即時停止

**対象ファイル**

- `app/pilot_validation.py`
- `app/real_site_trials.py`
- `tests/test_pilot_validation.py`

**TDD**

1. `SUBMIT_GUARD_TRIGGERED`、`submit_clicked`、`auto_submitted`、認証安全停止、PII検出、候補不一致後に次contextを作らない失敗テストを追加する。
2. 該当trialを安全事故または停止証跡として記録し、`halted=true`、`halt_reason`を返す。
3. KeyboardInterrupt/中断は成功trialにせず、再開可能な`INCOMPLETE`証跡として扱う。

**合格条件**

- 即時停止後の追加アクセス0。
- 停止理由と最後のtrial keyが証跡に残る。

### Task P0-4: Dry-run強制と事故フラグ保持

**対象ファイル**

- `app/pilot_validation.py`
- `app/auto_apply_engine.py`
- `tests/test_pilot_validation.py`
- `tests/test_auto_apply_engine.py`

**TDD**

1. mock/review/未知engineをpilot runnerへ渡すと開始前に拒否するテストを追加する。
2. submitフラグtrueをfalseへ上書きしないテストを追加する。
3. pilotでは`AutoApplyEngine.run_mode == "dry_run"`を実体で検証する。

**合格条件**

- dry-run以外はcontext作成前に拒否。
- 事故フラグは原値を保持し、trueなら即時停止。

### Task P1-1: Pilot証跡分離とmanifest照合

**対象ファイル**

- `app/paths.py`
- `app/real_site_trials.py`
- `app/pilot_validation.py`
- `main.py`
- `web/app.py`（通常集計からpilotを除外する最小変更のみ）
- `tests/test_real_site_trials.py`
- `tests/test_pilot_validation.py`
- `tests/test_web_app.py`

**TDD**

1. pilot証跡が通常trial/official集計へ混入しない失敗テストを追加する。
2. 保存manifestのentry/site/attempt計画と完全一致しない15件を拒否するテストを追加する。
3. duplicate trial ID、未計画entry、異なるsite IDを拒否する。
4. pilot専用append-only保存先または明示的なrecord type filterを実装する。official件数をpilotで増やせないことを優先する。

**合格条件**

- pilot 15件がofficial trial countへ影響しない。
- 保存manifestに一致する5 x 3だけが構造合格。

### Task P1-2: PIIと実状態非変更の実証

**対象ファイル**

- `app/pilot_validation.py`
- `app/privacy_guard.py`（既存helper再利用を優先）
- `tests/test_pilot_validation.py`
- `tests/test_privacy_guard.py`
- temp上のqueue/history fixture

**TDD**

1. candidate_refへメール、電話、郵便番号、生年月日、住所canaryを入れ、manifest作成/validateが拒否するテストを追加する。
2. manifest、trial、error、step、reportの全テキスト出力でcanary不在を確認する。
3. temp上の実queue CSV、entry history JSONL、session/statusをpilot前後でhash比較する。
4. 実Chromiumの別context間でCookie、Local Storage、Session Storageのcanaryが継承されないことを確認する。

**合格条件**

- PII平文0。
- 通常ストアのbefore/after hash一致。
- 15個のcontext間でstorage共有0。

### Task P1-3: Pilot証跡の無効化手順

**対象ファイル**

- `app/pilot_validation.py`
- `main.py`
- `docs/REAL_SITE_90_TRIAL_GUIDE.md`
- `tests/test_pilot_validation.py`

**TDD**

1. 失敗pilotを削除・上書きせず、無効化マーカーまたは新manifestへ隔離するテストを追加する。
2. 無効化済みmanifestを合格集計から除外する。
3. 操作はpilot証跡だけに限定し、通常履歴を変更しない。

**合格条件**

- append-onlyを維持しつつ、再測定は新manifest IDで開始できる。
- 無効化理由と時刻がPIIなしで残る。

## 4. 修正不要になった後の検証版固定手順

1. 上記pilot前TaskをすべてGREENにする。
2. 関連テスト、全テスト、compileall、Web smoke、diff checkを実行する。
3. 仕様レビューとコード品質レビューでCritical/Importantが0であることを確認する。
4. `git status --short`で対象外変更を分類し、検証版に含める変更だけを確定する。
5. 人間がレビュー後にcommitし、その40文字SHAを記録する。agentは明示依頼なしにcommit/pushしない。
6. pilot実行時はdirty worktreeまたは`git_commit_sha=unavailable`を拒否する。

## 5. 5サイト選定基準

- 固定manifest作成前に候補と実ページの提供元・賞品・受付状態を人間が確認する。
- 同一ドメイン重複なし。
- 標準単一ページ2、JavaScriptフォーム1、確認画面付き1、認証/CAPTCHA安全停止確認1を目安とする。
- ログイン突破、SNS操作、購入、レシート、規約回避が必要なサイトは入力対象にしない。安全停止の観測対象にはできる。
- pilot開始後の交換は禁止。到達不能やC判定も結果として残す。

## 6. Pilotの正確なコマンド

NO-GO修正完了後に以下を使用する。

```powershell
py -3 main.py pilot-manifest create --limit-sites 5
py -3 main.py pilot-manifest validate --manifest "<manifest-path>"
py -3 main.py pilot-run --manifest "<manifest-path>" --browser chrome
py -3 main.py trial-report --manifest-id "<manifest-id>" --require-trials 15 --require-sites 5
```

事前にqueue/history/statusの安全なhash、Git SHA、config fingerprint、ブラウザ版を保存し、実行後に再比較する。`--keep-open`は使用不可。

## 7. Pilot計測基盤の合格条件

- 5 unique site ID、各attempt 1/2/3、合計15。
- manifest membership完全一致、duplicate trial ID/key 0。
- 全trialで同一Git SHA、app version、config fingerprint。
- 15個のfresh context、Cookie/Storage共有0。
- 通常queue/history/status hash不変。
- pilot/通常/official証跡混在0。
- PII漏えい0、意図しない送信0、即時停止違反0。
- 中断trialを成功扱いしない。

## 8. Pilot製品性能の合格条件

15試行は小標本のため、有料β判定ではなくofficial移行判断に使う。

- A: 12/15以上（80%以上）。
- A+B: 15/15（95%基準を15件へ適用すると14/15は93.3%で未達）。
- 重大な誤入力0、意図しない送信0、PII漏えい0。
- 安全停止または手動引継ぎ成功率90%以上。
- 中央処理時間90秒以内。
- UNKNOWNは原因を説明できないまま残さない。

## 9. Pilot不合格時の修正ルール

- 安全事故、PII、重大誤入力、状態変更があれば即停止し、証跡を無効化して新manifestで最初からやり直す。
- 通常のB/Cは結果として残し、途中修正しない。
- 修正対象は件数上位の共通失敗3分類のみ。サイト固有対応は行わない。
- 修正ごとにfresh実装subagent、仕様review、品質review、関連テスト、全テストを実施する。
- コード・設定・manifestを変えた場合は旧pilotと混ぜない。

## 10. Official 30サイト x 3回への拡張Task

### Task O1: Official manifest一般化

- pilotのmanifest schemaとrunnerを一般化し、30 unique sites x 3をmanifest membershipで保証する。
- pilot/officialの保存先と集計を分離する。
- 対象: `app/pilot_validation.py`を汎用validation serviceへ最小整理、`main.py`、`app/paths.py`、関連テスト。

### Task O2: Official評価ゲート

- 件数だけでなくA率、A+B率、誤送信、重大誤入力、PII、復旧率、中央値をCLI終了コードへ反映する。
- 対象: `app/real_site_trials.py`、`main.py`、`tests/test_real_site_trials.py`。

### Task O3: 人間確認結果の確定

- 自動入力直後ではなく、人間確認後に誤入力、入力保持、次操作明確性を確定する。
- 値は保存せず項目種別と成否だけを記録する。
- 対象: evaluation service、既存review UIの最小箇所、関連Web/CLIテスト。

### Task O4: Official PII証跡方針

- 実プロフィール時のスクリーンショットは既定無効を維持する。
- 必要な場合のみ明示同意、URLクエリ除去、HTML値除去、PII領域マスクを要求する。
- 対象: `submit_adapters/dry_run_submit.py`、privacy tests、ガイド。

## 11. 公式90試行の合格条件

- 30サイトすべてattempt 1/2/3、合計90、未計画trial 0。
- A率80%以上、A+B率95%以上。
- 意図しない送信、重大誤入力、PII漏えい、通常状態変更すべて0。
- timeout後の復旧または手動引継ぎ成功率90%以上。
- 中央90秒以内、p95を報告。
- UNKNOWN率を報告し、原因不明Cが残る場合は有料βNO-GO。
- 同一サイト内の判定ばらつきと上位失敗3分類を報告する。

## 12. β公開前の最低限整備

- 対応対象・非対応・安全停止理由を利用者向けに明示。
- 1件ずつ停止・再試行・保留でき、誤送信につながる自動再試行を禁止。
- pilot/official証跡のバックアップと無効化runbook。
- PII保存範囲、スクリーンショット同意、削除手順を文書化。
- 問い合わせ時に値なしで診断できるerror categoryとrun ID。
- 大規模UI刷新、サイト固有patch、完全自動送信は行わない。

## 13. 有料βの計測指標

- 1応募あたり短縮時間。
- A/B/C率、手動介入率、復旧率、UNKNOWN率。
- 1人あたり週次利用回数と翌週継続率。
- 対応サイト到達率と非対応理由上位3分類。
- 問い合わせ件数、1件あたり対応時間。
- 継続課金意思。個人情報や入力値は分析ログへ保存しない。

## 14. 完成の定義

**技術完成:** 公式90試行の構造・安全・性能基準を固定buildで満たし、全テストとレビューがGREEN。

**商品完成:** 少人数βで時間短縮、反復利用、翌週継続、問い合わせ負担、課金意思が測定され、対象範囲と価格が成立する。技術完成だけでは商品完成としない。

## 15. 停止条件

- 意図しない送信または送信疑い。
- 重大誤入力、PII平文保存、通常queue/history/status変更。
- CAPTCHA、bot対策、ログイン、SNS、認証の回避が必要。
- guard空白、無限待機、過剰アクセス、重複証跡。
- Git SHA/config/manifest不一致、dirty build、候補内容不一致。
- Critical監査指摘が1件でも未解消。

## 16. Task別対象ファイル

| Task | 主対象 |
|---|---|
| P0-1 | `submission_guard.py`, `pilot_validation.py`, `auto_apply_engine.py`, guard tests |
| P0-2 | `auto_apply_engine.py`, `pre_submit_verifier.py`, mock form tests |
| P0-3 | `pilot_validation.py`, `real_site_trials.py`, pilot tests |
| P0-4 | `pilot_validation.py`, `auto_apply_engine.py`, engine tests |
| P1-1 | `paths.py`, `real_site_trials.py`, `pilot_validation.py`, `main.py`, minimal Web filter |
| P1-2 | `pilot_validation.py`, `privacy_guard.py`, pilot/privacy tests |
| P1-3 | pilot validation/CLI/guide/tests only |
| O1-O4 | manifest/report/human review/PII evidence modules listed above |

## 17. 共通テストコマンド

各Taskは対象テストを先にRED/GREENし、最後に以下を実行する。

```powershell
py -3 -m pytest kensho_assistant\tests\test_pilot_validation.py -q
py -3 -m pytest kensho_assistant\tests\test_submission_guard.py -q
py -3 -m pytest kensho_assistant\tests\test_privacy_guard.py kensho_assistant\tests\test_real_site_trials.py -q
py -3 -m pytest kensho_assistant\tests -q
py -3 -m compileall kensho_assistant main.py web_app.py
py -3 web_app.py --smoke-test
git diff --check
```

実サイトは上記すべてとレビュー完了後にだけ、順次1試行ずつ実行する。

## 18. Task依存関係

```text
P0-1 guard continuity ─┐
P0-2 preflight stop ──┼─> P0-3 manifest halt ─> P0-4 dry-run enforcement
P1-1 evidence split ──┤
P1-2 PII/state proof ─┘
P1-3 invalidation ────────────────> pilot build freeze ─> real-site pilot
real-site pilot pass ─> O1 manifest expansion ─> O2 official gate ─> official 90
O3 human confirmation ─┬─────────> paid beta readiness
O4 PII evidence policy ┘
```

## 19. 並列実行可能なTask

- 読み取り専用監査は並列可能。
- P0-1とP0-2は設計境界を先に固定すれば別subagentで並列調査可能。ただし同じ`auto_apply_engine.py`を編集するため実装統合は順次行う。
- P1-1とP1-2は書込対象を分離できる場合のみ並列実装可能。
- O2、O3、O4はO1 schema固定後、書込ファイルが重ならない単位で並列可能。
- 仕様レビューと品質レビューは実装後に並列可能。

## 20. 順次実行すべきTask

1. P0-1 連続guard。
2. P0-2 入力前preflight。
3. P0-3 即時停止。
4. P0-4 dry-run強制。
5. P1-1 証跡分離・manifest照合。
6. P1-2 実context/実ストア/PII証明。
7. P1-3 無効化runbook。
8. 全レビュー・全検証・検証版commit。
9. 実サイトpilotを1試行ずつ順次実行。
10. pilot合格後のみO1-O4、公式90試行、β準備へ進む。

## 実装サブエージェント標準手順

すべての実装Taskで以下を必須とする。

1. fresh実装subagentへ1 Taskだけ割り当てる。
2. 失敗テストを追加しREDを確認する。
3. 最小実装でGREENにする。
4. 別の仕様レビューsubagentが要求との一致を確認する。
5. 別のコード品質レビューsubagentが安全性・PII・回帰を確認する。
6. Critical/Importantを修正する。Minorはpilotに不要なら後送する。
7. 関連テスト、全テスト、compileall、Web smoke、diff checkを実行する。
8. 実サイト操作は全Task完了後に統括agentが順次実行する。

## 監査時の注意

Runbook監査subagentがread-only指示に反して`trial-report`を1回実行し、既定レポート出力を生成したと報告した。既存ファイルとの区別が確定していないため削除・復元は行わない。この成果物はpilot証跡として使用せず、検証版固定前に人間が作業ツリー差分を確認する。
