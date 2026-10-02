# Claude引継ぎ：kensho

確認日: 2026-10-02。プロジェクト資料・Git・実行設定だけを読み取り調査。アプリ、取引、投稿、collector、runnerは起動していない。

場所: `%USERPROFILE%\projects\kensho_assistant`。追加前branch: `codex/high-value-kensho-v1`、HEAD: `dc86f67835ad546821c8a9830765710bc1409f11`。

## 目標・完了範囲・次の作業

懸賞候補の収集・審査・承認、応募準備、Chrome拡張の入力補助、送信直前チェックを支援する。最終送信は人間。目標 `REAL_SITE_NON_SUBMIT_PASS` は未達。
直近commit `dc86f67835ad546821c8a9830765710bc1409f11` はPhase 5A knshow手動遷移の非送信pilot対応。`docs/GOAL_NON_SUBMIT_PILOT.md`、`docs/CLAUDE_HANDOFF.md` の10/1節を参照。応募先未確定リンクをorigin未設定の可視ブラウザへ開き、本人が確認画面を通過するのを最大300秒待ち、最初の外部着地だけ審査する。別origin移動、拒否origin、規約禁止で安全停止。
資料上の検証は関連98 PASS、全Python907 PASS、Node48 PASS、Web smokeとpreflight成功。今回は文書のみのため再実行していない。preflightは実サイト成功ではない。古い `docs/CODEX_HANDOFF.md` / SELF_TEST_LOGの228件等を最新テスト数として扱わない。
次は `docs/EXTENSION_REAL_SITE_TEST_RUNBOOK.md` と `docs/EXTENSION_SECURITY_MODEL.md` で固定commit/build fingerprint・候補規約・本人承認を確認し、明示承認された1件の架空値・非送信試験。今回はアプリ・ブラウザ・pilotを起動していない。

## AGENTS・Skills・承認境界

AGENTS.mdを確認。最終送信、CAPTCHA/ログイン/規約同意/SNSの自動操作とチャレンジ回避は禁止。submitted_count_auto=0、個人情報/Cookie/認証情報/入力値を記録しない。profile.encは読まず、正式保存先は `%LOCALAPPDATA%/kensho_assistant/profile.enc`。pilotは通常候補/履歴/テンプレートストアを変えない。実サイトは固定commit/fingerprintと本人の候補・mapping・origin承認が必要。pushは別承認。`.agents/skills` はこのrepoには見当たらない。

## automation・Windows Task

ローカルCodex automation.toml一覧にはkensho_assistantを対象とする登録は見当たらない。Codexアプリregistry・他ホストは未確認。
Windows Taskの名前とActionを読取り、kensho_assistantを直接参照するTaskは見当たらない。関連候補 `ContestHunterDaily` は毎日09:00（設定offsetなし）、Ready、最終結果1。Actionを復号すると `%USERPROFILE%/kennsyou/scheduled_run.bat` で別場所。これを本repoの自動実行と断定しない。`auto_scan.bat` 等のファイル存在と登録/稼働は別。既存Taskを起動・変更しない。

## 未解決・保留

実サイト互換性・初回mapping・query必須ページの再遷移は未証明。過去の別作業checkoutを指すdocsのパスは履歴であり、現在の作業先は冒頭と下記Git一覧。pilot用worktreeの証拠を保全する。最終送信は自動化しない。
## Git状態・ブランチ・worktreeの保全

以下は追加前の実測。全既存変更・未追跡・worktree・branchは保全。破棄許可の根拠はない。remote一覧はfetchせずローカル参照を確認しただけで、現在のサーバ状態は未確認。

ブランチ一覧（氏名や認証値は転載しない）：

```text
* codex/high-value-kensho-v1                           dc86f67 Support human navigation for knshow non-submit pilots
+ codex/pilot-5site-v1                                 99d4889 pilot: include safe diagnostic form candidates
  codex/standalone-completion                          bd28f51 test: verify standalone kensho baseline
  remotes/origin/HEAD                                  -> origin/main
  remotes/origin/claude/boat-race-ai-production-vrorsv 9925740 Add profitability gate analysis for daily runs
  remotes/origin/claude/boatrace-repo-structure-e0g5wk a396412 Prepare boatrace-ai standalone: add scripts, remove staging dependency, replace production with research
  remotes/origin/claude/claude-md-docs-b8rxbm          b84b9f1 Add CLAUDE.md handoff for Kensho Entry Assistant
  remotes/origin/claude/kensho-codex-handoff-eq7469    ab57b15 Record verified select→apply state and remaining manual step in handoff
  remotes/origin/claude/pc-file-organization-9ygedp    a2cc606 Add pc_organizer general-purpose file-organization tool
  remotes/origin/claude/sell-before-check-ios-k2axrs   f345e33 Add field_assessment_ai and sell_before_check_ai MVPs
  remotes/origin/codex/boat-race-ai-daily-ops-handoff  0257cd8 Treat zero official odds as unavailable
  remotes/origin/codex/high-value-kensho-v1            dc86f67 Support human navigation for knshow non-submit pilots
  remotes/origin/main                                  2249ba9 Refine pre-submit audit and UI
```

worktree一覧：

```text
worktree %USERPROFILE%/projects/kensho_assistant
HEAD dc86f67835ad546821c8a9830765710bc1409f11
branch refs/heads/codex/high-value-kensho-v1

worktree %USERPROFILE%/projects/kensho_assistant/.worktrees/pilot-5site-v1
HEAD 99d4889b196404efc019e66ce2b083b1c65fb7e8
branch refs/heads/codex/pilot-5site-v1

```

未commit変更: なし（追加前clean）。

意味: 競艇のcodex/research-autopilot-v1は終了研究、codex/exacta-conditional-second-v1は隔離Exacta、codex/roi-oof-v1-20261002は完了OOF、mainは共有base。kenshoのpilot-5site-v1は別pilot作業、standalone-completionとremote refsは履歴/参照で、破棄判断は未確認。SoundOn mainはローカル進捗、別Claude branchは履歴。各repoに存在するものだけを上記一覧で判断する。

今回の追加予定は docs/HANDOFF_CLAUDE.md と、CLAUDE.mdがなければその2行参照ファイルだけ。既存CLAUDE.mdは未編集。追加文書だけをpath指定でcommitし、既存index/作業ツリーを混ぜない。push/reset/stash/checkout/cleanなし。前後の既存ファイルhash・git statusとcommit差分で文書追加以外の保全を確認する。コードテストは実行していない。
