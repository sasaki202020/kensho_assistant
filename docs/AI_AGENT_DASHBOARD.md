# AI担当者ダッシュボード

`/ai-agents` は JSON 結果表示モードです。

- `data/agent_status/agent_status.json` を読み込みます
- `main.py agent-status generate` で安全に生成できます
- `main.py agent-status run --task "..."` でローカル安全チェック結果を更新できます
- `main.py agent-status run --mode normal|release` で通常モード / リリース前モードを切り替えられます
- `data/agent_status/agent_run_log.jsonl` に毎回の実行履歴が追記されます
- `AI司令塔` は `agent_control` の dry-run ジョブ用画面です
- sample JSON は本番データとして読み込みません
- 自動送信はありません
- `profile.enc` は読みません
- PII は表示・保存しません
