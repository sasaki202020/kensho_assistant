# Claude Code 引き継ぎ: 懸賞支援

記録日: 2026-10-02 JST。対象はkensho_assistantだけ。競艇・SoundOnの契約やデータを持ち込まない。
今回の許可は文書追加とローカルcommitのみ、pushなし。実サイト・本人プロフィールは開かない。

## 1. 現在の目標・進行中作業

ゴールは `REAL_SITE_NON_SUBMIT_PASS`。現在未達成。
ローカル実装、fixtureテスト、preflight PASSと実サイト受入を区別する。

- `dc86f67`: Phase 5Aで応募先未確定の `knshow_link` を受け取り、人間の元タブ内遷移を待つ入口を実装。
- 非knshowの最初のトップレベル着地だけをorigin policy/規約で審査し、許可登録・読み戻し・reload後に既存の確認フローへ進む。
- 上限300秒、拒否origin・規約禁止・timeout・別origin遷移は入力/capability発行前に停止。
- チャレンジをclick/fill/evaluateせず、UA/stealth偽装、Cookie流用、外部突破、連続retryをしない。
- 通常キュー・履歴・候補状態・値なしテンプレートをpilotで変更しない。本人プロフィールは使わない。
- 送信ガード、origin policy、phase5a_overallを緩めず `submitted_count_auto=0`。
- 次は現在のcommitとbuild fingerprint、未期限切れ候補、個別承認を確認してPhase 5Aの人間立会いnon-submit検証。
  この文書作成依頼では実サイトpilotを開始しない。Phase 5Bや実応募へ自動で進めない。

正本入口は [AGENTS](../AGENTS.md)、[現在の詳細記録](CLAUDE_HANDOFF.md)、
[ゴール](GOAL_NON_SUBMIT_PILOT.md)、[実サイトrunbook](EXTENSION_REAL_SITE_TEST_RUNBOOK.md)、
[セキュリティ](EXTENSION_SECURITY_MODEL.md)、[high-value規則](HIGH_VALUE_RULES.md)。
旧CODEX_HANDOFFのテスト件数や実行手順を最新状態とみなさない。

## 2. Git・branch・worktree

文書追加前: branch `codex/high-value-kensho-v1`、HEAD `dc86f67835ad546821c8a9830765710bc1409f11`、
tracked/untracked差分0、staged 0。

| branch / checkout | 文書追加前HEAD | 意味・保全 |
| --- | --- | --- |
| 正本 / codex/high-value-kensho-v1 | dc86f67 | high-value、origin/規約、手動遷移、non-submitの現在の実装。保全 |
| .worktrees/pilot-5site-v1 / codex/pilot-5site-v1 | 99d4889 | 古い5-site pilotの独立checkout。cleanだが正本と同一版ではない。保全 |
| codex/standalone-completion | bd28f51 | standalone baseline確認の履歴。checkoutなし。破棄承認なし |

現在登録されたworktreeは正本とpilot-5site-v1の2つ。
既存文書の `wt-nav` / `wt-pnav` は過去の作業場所で、今回そのパスは存在しなかった。
cleanだから不要とは判断しない。安全に削除可能と確認したbranch/worktreeはない。
reset/clean/stash、一括stage、worktree削除、branch切替、pushはこの依頼に含まない。

`build/` の専用拡張やfixture等はGit対象外の場合がある。Git cloneだけでローカル検証証拠やプロフィールは移らない。
本人情報、queue/historyの内容、暗号化プロフィール、Cookieを引き継ぎ文書へコピーしない。

## 3. 自動実行

2026-10-02にローカルCodex automation登録の名前・prompt/cwd照合とWindows Taskの名前・Action照合を読み取り確認。
kensho_assistantを対象にする登録は今回の確認範囲で見当たらない。
したがって報告できる対象の自動実行名・時刻・ACTIVE/Ready状態はない。
別ホスト、未登録の手動起動プロセス、外部サービスまで停止を証明したものではない。

`pilot-nonsubmit`、Web/CLI、Chrome拡張、ハーネス、build/preflightは手動入口。
スクリプトの存在をScheduled Task登録や実サイトPASSと解釈しない。
新automation/Task/heartbeat、ブラウザ・runner手動起動、候補収集は今回行わない。

## 4. 守る規則・必要な承認

- 最終送信、応募確定、CAPTCHA、ログイン、規約同意、SNSは自動化しない。
- 個人情報、フォーム値、Cookie、認証、URL query/fragmentを永続化・ログ・文書へ出さない。
- `%LOCALAPPDATA%/kensho_assistant/profile.enc` はリポジトリへ複製せず中身を読まない。
- assisted_sessionが通常候補ロック・進行・手動送信報告の正本。pilotで通常データを更新しない。
- 本人がorigin・項目・規約を確認する。初回mapping未承認、未知/外部origin、guard異常、二重拡張起動では入力しない。
- rollback/clear・静穏待機・残存検査・hash比較・送信ロックを維持する。
- high-valueの `terms_automation_restricted` は準備/読込/capabilityを `terms_prohibit_automation` で除外。
  `uncertain`・本文取得失敗・旧未診断レコードを規約確認済みへ昇格しない。
- 個別候補・固定commit/fingerprintに対応する実サイト承認が必要。過去buildの承認を使い回さない。
- push、外部送信、権限変更、プロフィール利用、実応募、運用/自動実行変更は別承認。
- ルート [CLAUDE](../CLAUDE.md) は今回追加した指定の2参照だけで、上記境界を拡張しない。

## 5. 直近の判断・根拠

| commit | 判断・内容 |
| --- | --- |
| dc86f67 | knshowから人間の遷移を待つnon-submit pilot |
| 21e185c | challengeされたリンクの人間遷移 |
| 0b6f5f1 | 拒否originでbatch全体停止ではなく安全skip |
| 02536d4 | runtime origin policy |
| 006a0cb | pre-submit review |

[CLAUDE_HANDOFF](CLAUDE_HANDOFF.md) の2026-10-01記録は関連pytest98、全pytest907、
Node48、WEB_SMOKE_TEST_OK、READY_FOR_5_SITE_PILOT。
これは過去の固定版に対するローカル検証記録で、今回再実行した結果ではない。
preflightやfixtureからREAL_SITE_NON_SUBMIT_PASSを主張しない。

## 6. 未解決・次の安全な操作

- 実サイトPhase 5Aの新しい有効候補、規約確認、固定fingerprintへの承認と本人立会い。
- 実ページでの通信監視・mapping・POST-FILL・rollback/clear・残存ゼロを測定した合格証拠。
- 人間がchallengeを通過できない場合、迂回せず安全停止。古い・期限切れ候補を代用しない。
- 履歴中の旧branch/path/buildと現在のcheckout対応の確認。旧pilotを正本へ自動mergeしない。
- コード変更後の関連/全テスト・Web smoke・preflightは別の実装承認の範囲で実施。
  今回は文書のリンク、秘密情報、Git差分だけを検証し、コード・候補・台帳・自動実行は変更していない。

