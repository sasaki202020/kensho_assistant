# RELEASE NOTES v0.5

## 追加
- `AI司令塔` 画面を追加し、AI担当者をカード単位で dry-run 実行・停止・確認できるようにした。
- `jobs.jsonl` / `agent_status.json` / `control_events.jsonl` で安全なローカル履歴を記録するようにした。
- Web/API から `Agent Control` の status / jobs / report を確認できるようにした。

## 安全
- 自動送信なし
- submit / click / send / post / like / follow / DM 系の自動化なし
- `profile.enc` 非読込
- PII なし
- `submit_attempted=false`
- `submitted_count_auto=0`
- `safe_to_submit=false`
