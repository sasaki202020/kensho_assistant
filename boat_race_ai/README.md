# 競艇AI予想システム CLI運用版

競艇の1着予測を、朝の全開催場予想と夜の答え合わせで日次運用するCLIです。実舟券購入、自動送信、外部投稿は行いません。

## 基本コマンド

```powershell
py -3.13 daily_run.py --date 2026-06-13 --phase morning
py -3.13 daily_run.py --date 2026-06-13 --phase odds --force-refresh
py -3.13 daily_run.py --date 2026-06-13 --phase night --bankroll-yen 10000
py -3.13 daily_status.py --date 2026-06-13
py -3.13 daily_verify.py --date 2026-06-13 --stage morning
```

- `--phase morning`: 当日開催場を検出し、出走表・直前情報・単勝オッズだけで予想します。結果ページは使いません。
- `--phase odds`: 保存済みの朝予想を読み、予測確率・順位を変えずに公式単勝オッズと期待値だけ更新します。
- `--phase night`: 保存済みの朝予想を読み、公式結果だけを取得して答え合わせします。予想は再生成しません。
- `--phase full`: morning の後に night を続けて実行します。
- `--overwrite`: 朝予想を明示的に作り直す場合だけ指定します。通常は既存 `predictions.csv` を壊しません。
- `--force-refresh`: `odds` 実行時に公式オッズHTMLを再取得します。深夜取得でオッズ未公開キャッシュが残っている場合に使います。
- `--max-courses N`: 検証用に開催場数を制限します。指定しない場合は検出できた全開催場を対象にします。
- `--bankroll-yen N`: 夜処理後の利益化ゲートで使う資金額です。ゲート未通過時は `unit_stake_yen=0` になります。
- `--ignore-schedule`: `daily_status` が時刻前待機を示していても `odds` / `night` を実行します。通常運用では使いません。
- `--no-verify`: 各フェーズ完了後の `verify_<stage>.json` 保存を省略します。通常運用では使いません。

`daily_status.py` は保存済み成果物だけを読み、予想・オッズ・決済・収益性の状態、候補ゼロの主因、次アクションを表示し、`daily_status.json` を出力します。
`daily_run.py` は既定で `daily_status` の時刻判定に従うため、18:00前の `odds` と21:30前の `night` は取得せずスキップします。
`daily_run.py` は完了したフェーズごとに `verify_<stage>.json` も保存します。
`daily_verify.py` は保存済み成果物だけを検査し、`morning` / `odds` / `night` / `analysis` / `full` ごとの不足ファイルや行数不整合を表示して、`output/daily/YYYY-MM-DD/verify_<stage>.json` に保存します。

## 日次出力

出力先は `output/daily/YYYY-MM-DD/` です。

- `predictions.csv` / `predictions.json`: 朝の予想。各艇の勝率、予想着順、単勝期待値を含みます。
- `morning_run.json`: 朝処理の状態。`exists` は既存予想を使用したことを示します。
- `coverage.json`: 開催場数、予想対象レース数、6艇不足、選手名・級別・単勝オッズ欠損、取得エラー理由を記録します。
- `odds_refresh.csv` / `odds_refresh_run.json`: 後続の公式オッズ更新結果。予測確率と予想着順は変更しません。
- `results.csv`: 夜に取得した公式結果。未取得レースは `result_status` と `unavailable_reason` を持つステータス行として残します。
- `settlement.csv`: 朝予想と公式結果の突合結果。未取得艇には `unavailable_reason` が入ります。
- `daily_report.md` / `daily_report.json`: 的中率、ROI、未取得レース、開催場別サマリを出します。
- `daily_status.json`: 現在の運用状態と次アクション。
- `verify_<stage>.json`: `daily_verify.py` の成果物検査結果。
- `output/daily/rolling_summary.csv`: 日付単位の累積サマリ。同じ日付を再実行しても重複行は作りません。

## 未取得理由

`unavailable_reason` は次の意味です。

- `result_unpublished`: 公式結果が未公開。
- `cancelled`: 中止。
- `postponed`: 順延。
- `no_contest`: 不成立。
- `result_table_not_found`: 結果ページはあるが、想定した結果表が見つからない。
- `fetch_error`: 取得時エラー。
- `fewer_than_6_finishers`: 6艇未満の結果。取得データは保持し、欠けた艇だけ未取得扱いにします。

## 収益化分析

予想ロジックやBUY条件は変更せず、保存済み日次データから的中率・ROI・条件別成績を集計します。

```powershell
py -3.13 analyze_profitability.py --date 2026-06-13 --bankroll-yen 10000
```

出力先は `output/analysis/profitability/` です。

- `profitability_summary.json`: 戦略別・日次データ・候補条件・失格理由の集計。
- `current_cli_slices.csv`: 場、予測確率、単勝オッズ、期待値ごとの条件別成績。
- `candidate_conditions.csv` / `candidate_conditions.json`: ROI安定ゲートを通過した候補条件。常に `shadow_only_candidate` です。
- `candidate_rejections.csv` / `candidate_rejection_summary.json`: 候補条件に落ちた理由。`min_days` や `min_sample` などの不足を見ます。
- `profitability_daily_history.csv`: 分析日ごとの収益性サマリ。同じ日付を再実行しても重複行は作りません。
- `candidate_condition_history.csv`: 候補条件だけの履歴。候補ゼロの日はヘッダーのみで、ゼロ件は `profitability_daily_history.csv` に残します。
- `legacy_daily_summary.csv`: 旧MVP `reports/daily/daily_summary_history.csv` の分析用コピー。
- `legacy_prediction_candidates.csv`: 旧MVPの保存済み予想候補と結果を使った三連単仮想検証データ。
- `profitability_report.md`: 人間が読むための要約。

この分析は `shadow_only` です。サンプルが十分に貯まるまで、本番BUY条件や予想ロジックには反映しません。

利益化ゲートは次の条件をすべて満たすまで `paper_trade_only` にします。

- 最低サンプル数: 既定 `100` ベット以上。
- 最低検証日数: 既定 `3` 日以上。
- ROI下限: 既定 `105%` 以上。
- 日別プラス率: 既定 `50%` 以上。
- 日別ROI下限: 既定 `80%` 以上。
- 戦略全体と条件別スライスの両方がゲートを通ること。

ゲート未通過時は `live_betting_allowed=false`、`unit_stake_yen=0` です。勝率だけで資金投入を増やさず、ROIと日数の安定性を優先します。

`daily_status.py` の `blocker` は、現在もっとも多い失格理由です。`blocker=min_days` の間は閾値調整ではなく、まず日次決済データを増やします。

## Windows運用

```powershell
scripts\run_daily_morning.bat --date 2026-06-13
scripts\run_daily_odds.bat --date 2026-06-13
scripts\run_daily_night.bat --date 2026-06-13 --bankroll-yen 10000
scripts\run_daily_status.bat --date 2026-06-13
scripts\run_daily_verify.bat --date 2026-06-13 --stage morning
powershell -ExecutionPolicy Bypass -File scripts\register_daily_tasks.ps1
```

`register_daily_tasks.ps1` はタスク登録コマンドを表示するだけです。実登録はユーザーが内容を確認してから手動で実行してください。
表示されるタスク案は朝予想、オッズ更新、夜答え合わせ、ステータス確認の4本です。

## 確認コマンド

```powershell
py -3.13 test_system.py
py -3.13 main.py --quick
py -3.13 main.py --source real --quick
```

`value_filter` は評価用です。現時点では本番推奨買い目ではありません。サンプル数が少ない間は、ROIだけで良否判定しないでください。
