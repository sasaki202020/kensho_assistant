# RELEASE NOTES v0.4.3

## 追加内容

- `main.py agent-status generate` を追加し、`data/agent_status/agent_status.json` を安全に生成できるようにした
- `main.py agent-status run --task ...` を追加し、ローカル安全チェックの結果を JSON に更新できるようにした
- AI担当者タブは JSON 結果表示のまま維持し、sample JSON と本番生成 JSON を分離した
- 生成 JSON には PII を含めず、自動送信や X 自動操作は追加していない

## 運用メモ

- `agent-status generate` で更新した JSON を `/ai-agents` で確認する
- `agent-status run` は外部送信なしでローカル安全チェックの結果を更新する
- `profile.enc` は読まない
- `submitted_count_auto` は 0 のまま維持する
