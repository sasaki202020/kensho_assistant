# Kensho Harness

`kensho_assistant` の安全な入力補助を外部からまとめて呼び出すための薄いハーネスです。
送信ボタンの自動クリックはしません。`submitted_count_auto` は 0 のまま維持します。

## 実行

```powershell
py scripts/run_kensho_harness.py --campaign-id camp-123 --mode dry_run
```

later queue から連動させる場合は次を使います。

```powershell
py scripts/run_kensho_harness.py --later-id later-123 --mode review
```

`later_apply_queue.jsonl` の特定の `later-id` を確認する流れを見たいだけなら、`--later-id` で1件だけ指定します。

`main.py` からも実行できます。

```powershell
py -3 main.py harness run --campaign-id camp-123 --mode dry_run
```

## 出力

`data/research/kensho_harness/YYYYMMDD/{slug}/` に以下を保存します。

- `run_plan.json`
- `campaign.json`
- `later_bridge.json`  `--later-id` 使用時のみ
- `dry_run_result.json`
- `form_analysis.json`
- `pre_submit_check.json`
- `run_report.json`

## 挙動

- `PREPARED` 案件は、既存の応募準備パイプラインに接続して実行します。
- `later-queue` はキャンペーンへの橋渡しだけに使います。
- `submit` / `confirm` / `complete` 系の自動処理はしません。
- 個人情報はログと保存JSONの両方でマスクします。
