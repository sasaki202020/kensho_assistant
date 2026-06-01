# RELEASE NOTES v0.4.5

## 追加
- `agent-status run` のたびに `data/agent_status/agent_run_log.jsonl` へ安全な実行履歴を追記するようにした。
- 実行モード、起動担当、警告・失敗理由、release_allowed 判定、安全フラグを記録できるようにした。

## 安全
- 自動送信なし
- submit / click 系の応募実行なし
- `profile.enc` 非読込
- PII なし
- `submitted_count_auto = 0` 維持
