# Claude handoff: non-submit real-site pilot

## 2026-09-30 runtime-origin制御

固定専用build SHA-256: `98094656368acd5a0dccaf42685b1711853431dc997d526f6656adbc60cc8767`。

作業ブランチ`codex/runtime-origin-gating`、base `006a0cb`。専用ビルドはorigin一覧に依存せず、
HTTPS全体とテストfixture用loopback HTTPのホスト権限を固定する。静的content scriptは持たない。
通常sessionはキューで本人が承認した候補のresolved entry originを1つだけ有効化し、
pilotは本人が書いたmanifestのoriginを1つだけ有効化する。どちらも`origin_policy`の拒否を優先する。
worker特権evaluateの設定と登録読み戻しが一致するまで候補へ遷移しない。
未設定・解除後は注入ゼロ。候補切替・終了・異常時は旧登録と一時プロフィール/capabilityを消去する。
通常インストール版のoptional権限フロー、送信ガード、本人の規約確認・認証・最終送信は維持する。

`config/approved_origins.json`は互換ファイルとして残すがビルド・注入判定には使わない。
旧`approved_origins_path`引数は呼び出し互換性のため受け付けるが内容を読まない。
pilotの`config_sha256/config_unchanged`は有効origin policyのhashを表す。
実サイト検証・pushは実施せず、loopback fixtureと非loopback DNS遮断で検証する。
詳細は[security model](EXTENSION_SECURITY_MODEL.md)と[runbook](EXTENSION_REAL_SITE_TEST_RUNBOOK.md)が正本。
この変更は過去の実サイト承認やpilot fingerprintを引き継がない。以下の過去build hashは履歴である。

Updated: 2026-09-30 JST

## 通常assisted session（worktree `codex/assist-integration`）

今回のbase commit: `a8e31b8`。前回（base `684d24d`）は通常assisted sessionに値なしの永続テンプレートを追加した。SSOTは`data/form_templates.json`で、承認から180日以内かつ専用拡張version/build SHA-256一致のものだけを新しい一時プロファイルへseedする。前回の変更では拡張側コード・送信ガード・Phase 5A経路を変更していない。初回の人の欄対応承認と入力後検証合格が保存条件で、再利用時は既存パネル操作と厳格なbinding検証を通して入力する。内容衝突は上書きせず`conflict`をsessionへ記録する。失効CLIと安全条件は[runbook](EXTENSION_REAL_SITE_TEST_RUNBOOK.md)と[security model](EXTENSION_SECURITY_MODEL.md)を参照。

新規ストアテスト、実Chromiumの新規プロファイル再利用・条件不一致・検証不合格テスト、pilotのストアAPI呼び出し禁止とSHA-256不変確認で回帰を検証する。実サイト検証は行わない。専用ビルドを更新したら全チェックを再実行し、承認を再取得する。

統合試験で、通常session UUID内の7桁数字が既存の郵便番号マスクにより変形し、bridge bindingが拒否される不具合を再現した。通常sessionの32桁hex UUIDだけを保持し、pilot有効時の処理は従来どおりとする。旧専用buildハッシュは改行コード依存のため失効。このcommitで再計算（下記）。

2026-09-30 パートA: `.js/.json/.html/.css/.md/.txt`のビルド出力とハッシュ入力をCRLF→LFへ正規化し、`extension/** text eol=lf`を指定した。このcommitで再計算した専用build SHA-256: `a0bda86a44479f14ac528417fabcbfcb4fefd7eb9778b37a86eefe73d3e8f880`。source再ビルド照合と起動時snapshot照合は同じ`build_hash()`を使用する。CRLF/LF一致、1文字差・バイナリ差の検出、バイナリ保持と既存build/verify系をローカル検証（`10 passed in 17.64s`）。実サイト承認・pilot fingerprintの更新を意味しない。

2026-09-30 パートB: 通常sessionの入力後検証成功時だけ「送信前確認」を表示する。実際に入力した欄のラベルと既存マスク、未入力必須欄（ラジオ群・同意・アンケート・選択・生年月日を含む）のラベルと一時枠線、スクロール操作、規約リンクと候補の値なしbool警告を追加した。rollback/clearでstyle属性の有無と内容を完全復元する。ChromiumのCSSOMによる空style再生成もloopbackで再現して対処した。送信・同意ボタン、送信ガード、手動送信後の進行は変更しない。pilotへのAPI応答は従来どおりで、確認パネルと枠線の非表示を回帰試験で確認する。最新専用build SHA-256はこのcommitで再計算: `5c99b0c5312779370ca8d4ba51f49694f3af27e77a5ac2dd084c06e9ab4d4930`。旧buildに束縛された通常テンプレートは再承認が必要。実サイトや本人プロフィールでの確認は行わない。

今回の最終ローカル検証: 指定関連テスト`88 passed, 2 warnings in 243.71s (0:04:03)`、全Pythonテスト`820 passed, 2 warnings in 798.29s (0:13:18)`、Node`47 passed / 0 failed`、`WEB_SMOKE_TEST_OK`、preflight`READY_FOR_5_SITE_PILOT`、compileallとdiff check成功。警告2件はwebsocketsの既存DeprecationWarning。非loopback DNSと通信、本人プロフィール・`.env`・実ブラウザプロフィールの読取りを一時検証ガードで遮断し、loopback fixtureだけを利用した。Web smokeの一時ガード挿入は元のバイト列へ復元した。初回の全テストは既存キューCLI単体テストの未mock DNSにより`1 failed, 819 passed`となったため、同テストのDNSもfixture化（既存assert変更なし）し、全件を再実行して合格した。一時検証ファイルは成果物に含めない。実サイト検証・Git pushは行っていない。

前回のローカル検証（参考記録）: 指定関連テスト`96 passed, 2 warnings in 235.17s (0:03:55)`、全Pythonテスト`773 passed, 2 warnings in 857.83s (0:14:17)`、Node`42 passed / 0 failed`。前回は入力値のUTF-8/UTF-16検査、再利用時の欄承認呼び出しゼロ、構造/版/build/期限の不一致、seed読み戻し失敗、検証不合格時の保存禁止、pilotのストアAPI呼び出しゼロ・SHA-256不変を確認した。

## Source of truth

Read [AGENTS.md](../AGENTS.md), [GOAL_NON_SUBMIT_PILOT.md](GOAL_NON_SUBMIT_PILOT.md), and [EXTENSION_REAL_SITE_TEST_RUNBOOK.md](EXTENSION_REAL_SITE_TEST_RUNBOOK.md) before changing or running anything. The older `CODEX_HANDOFF.md` contains obsolete test counts and is not the current status record.

The project assists with contest entry and stops before final submission. Only the person may submit. CAPTCHA, login, SNS actions, and consent remain manual. Do not read real profiles, `.env`, cookies, or browser profiles for the pilot.

応募規約の自動入力制限は [HIGH_VALUE_RULES.md](HIGH_VALUE_RULES.md#自動入力に関する規約) を参照。フォーム診断で本文を保存せず `terms_policy` の判定・時刻のみ追加し、キューの `terms_automation_restricted` が真なら既存の `queue_prepare_block_reason` 経由で準備・候補読込・拡張機能capability発行を `terms_prohibit_automation` で除外する。期限・手動送信済みの判定順序と手動応募記録は維持する。`uncertain` はUIで注意表示するがブロックしない。未診断の旧レコードと本文取得失敗は規約確認済みとみなさず、実サイト・別ページ・画像の規約の検証は未実施。`codex/terms-automation-check` の変更では `app/assisted_session.py`、`app/browser_manager.py`、`extension/` を変更しない。

## Verified baseline

- Branch before this handoff: `codex/high-value-kensho-v1`
- Code HEAD before this handoff: `81e71fc6842db5e61ccb887db36f8cbf72abbd82`
- Source worktree was clean before adding this document. Recheck Git state after checkout.
- Extension version: `0.2.0`; 旧dedicated build SHA-256は失効。このcommitで再計算（上記）。使用前に現在のbuildを検証する。
- Local verification on 2026-09-26: Python full suite `604 passed, 2 warnings`; targeted integration `57 passed`; Node extension `41 passed`; extension local smoke, Web smoke, P1 preflight, compileall, and `git diff --check` passed. Rerun the commands listed in `GOAL_NON_SUBMIT_PILOT.md` after any implementation change.

## Real-page observations

The September 2026 campaign at `https://www.epinard.jp/presentquiz/` was used only for read-only diagnostics on 2026-09-26. HTTP status was 200. Automatic extension injection passed with one panel, one submit guard, and `guard_verified=true`. The guard reported locked, intact, installed at document start, and `submitted_count_auto=0`.

Three third-party script attempts to replace guarded browser methods were blocked. They were not successful guard modifications or submit attempts. The page made 243 normal external resource requests; extension non-loopback requests were 0 in that read-only run. No sentinel was entered, so `sentinel_network_leak=UNMEASURED_NO_SENTINEL`. The complete sanitized diagnostic remains in local ignored pilot evidence; it is not a live input result.

No candidate lock, profile consumption, live form fill, rollback, session clear, or final submission occurred on this page. `REAL_SITE_NON_SUBMIT_PASS` has **not** been achieved.

## Next work

1. Inspect the existing `assisted_session` and its extension bridge. The in-process fixture `web.create_app(profile_loader=...)` and monkeypatches in `tests/test_assisted_extension_integration.py` are test mechanisms, not a safe operational command for a real page.
2. Implement the smallest explicit pilot path that supplies only an in-memory fake profile and keeps its candidate lock, state, and audit in `data/pilot/`. Prove that the normal profile loader and normal candidate/history stores are untouched.
3. Monitor requests from before fill through rollback and session clear. Count sentinel-bearing fetch, XHR, beacon, WebSocket, validation/autosave, and submit traffic without saving payloads. Keep page traffic distinct from extension non-loopback traffic. If a channel cannot be observed, stop before fill.
4. Test locally with a fail-first fixture, then rerun the documented targeted and full checks. A code change creates a new build; freeze its commit and fingerprint before restarting Phase 5A.
5. Recheck the campaign period and conditions. Present the actual field mapping without values and obtain per-field human confirmation. Broad permission is not a mapping decision. Fill only approved fields with unique fake sentinels, verify every change, roll back, clear the session, check residue and traffic, and release the pilot lock.

Stop after Phase 5A. Do not use the real profile or begin a real submission as part of this handoff. Do not mark an unmeasured metric as zero or claim a pilot pass from local smoke tests.

## Status 2026-09-30 (branch `claude/pilot-phase5a-integration`)

The browser stage of `pilot-nonsubmit` is implemented and passes against local fixtures only
(`tests/test_pilot_nonsubmit_e2e.py`: real headless Chromium, real dedicated build, real pilot web app).
Command, manifest format, per-field mapping policy, undetectable-field policy and the evidence schema are in
[EXTENSION_REAL_SITE_TEST_RUNBOOK.md](EXTENSION_REAL_SITE_TEST_RUNBOOK.md). Finding: before this change the
extension Service Worker traffic was invisible to Playwright, so earlier `extension_non_loopback_requests=0`
values (including the 2026-09-26 read-only diagnostic) were not measurements.

No real-site Phase 5A run has happened. `REAL_SITE_NON_SUBMIT_PASS` has **not** been achieved.

## Worktree rehearsal update (2026-09-30)

Branch `codex/pilot-rehearsal` uses only local fixtures. The extension capability request now includes
only fields explicitly approved for filling. Worker evaluation is bounded so a stopped MV3 worker cannot
hold cleanup indefinitely. Pilot fill enables pre-send routing: opaque or sentinel-bearing external
requests are aborted, with separate blocked counts. A blocked sentinel attempt fails Phase 5A. During
tab shutdown, Chromium can bypass the route for an unload beacon, so page network is blocked and the
unobserved request remains UNVERIFIED. A PASS means PASS under blocking.

The Epinard-like local fixture confirms the approved subset, untouched manual fields, rollback, clear,
and zero residue. Its controlled `external.test` destination resolves only to a loopback fixture;
all other non-loopback DNS is blocked. The receiver count is checked on the server. The fake kana
values are ASCII sentinels, so leave kana unapproved on a first real-site attempt. An eight-character
hex form fingerprint could be corrupted by general phone redaction; the state save now preserves only
that exact fingerprint shape. This update does not claim `REAL_SITE_NON_SUBMIT_PASS`.
Next: merge/freeze the commit, build with `py -3.13 -m kensho_assistant.scripts.build_dedicated_extension`,
stop the resident web app, recheck one candidate's official conditions, then run
`py -3.13 -m kensho_assistant.main pilot-nonsubmit --manifest data/pilot/manifests/<id>.json` once with
per-field human confirmation. Do not proceed to Phase 5B.
