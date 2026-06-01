# RELEASE NOTES v0.4.4

## 追加
- `data/agent_status/agent_org.json` を追加し、AI組織の定義を安全に固定した
- `main.py agent-status run --task ... --mode normal|release` を追加し、ローカル安全チェック結果を `agent_status.json` に更新できるようにした
- `/ai-agents` をチーム別表示に拡張し、通常モード / リリース前モードを切り替えられるようにした

## 安全
- 自動送信は追加していない
- submit / click による応募実行は追加していない
- X自動操作は追加していない
- `profile.enc` は読んでいない
- PII は JSON、画面、ログに出していない
- `submitted_count_auto` は 0 のまま維持する
- `safe_to_submit` は送信実行に使っていない

## 確認ポイント
- `main.py agent-status run --task "safe-agent-run" --mode normal`
- `main.py agent-status run --task "safe-agent-run" --mode release`
- `/ai-agents` でチーム別カードを確認する
- `agent_status.json` に担当者ごとの確認内容が記録されることを確認する
