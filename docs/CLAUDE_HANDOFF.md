# Claude handoff: non-submit real-site pilot

Updated: 2026-09-30 JST

## Source of truth

Read [AGENTS.md](../AGENTS.md), [GOAL_NON_SUBMIT_PILOT.md](GOAL_NON_SUBMIT_PILOT.md), and [EXTENSION_REAL_SITE_TEST_RUNBOOK.md](EXTENSION_REAL_SITE_TEST_RUNBOOK.md) before changing or running anything. The older `CODEX_HANDOFF.md` contains obsolete test counts and is not the current status record.

The project assists with contest entry and stops before final submission. Only the person may submit. CAPTCHA, login, SNS actions, and consent remain manual. Do not read real profiles, `.env`, cookies, or browser profiles for the pilot.

応募規約の自動入力制限は [HIGH_VALUE_RULES.md](HIGH_VALUE_RULES.md#自動入力に関する規約) を参照。フォーム診断で本文を保存せず `terms_policy` の判定・時刻のみ追加し、キューの `terms_automation_restricted` が真なら既存の `queue_prepare_block_reason` 経由で準備・候補読込・拡張機能capability発行を `terms_prohibit_automation` で除外する。期限・手動送信済みの判定順序と手動応募記録は維持する。`uncertain` はUIで注意表示するがブロックしない。未診断の旧レコードと本文取得失敗は規約確認済みとみなさず、実サイト・別ページ・画像の規約の検証は未実施。`codex/terms-automation-check` の変更では `app/assisted_session.py`、`app/browser_manager.py`、`extension/` を変更しない。

## Verified baseline

- Branch before this handoff: `codex/high-value-kensho-v1`
- Code HEAD before this handoff: `81e71fc6842db5e61ccb887db36f8cbf72abbd82`
- Source worktree was clean before adding this document. Recheck Git state after checkout.
- Extension version: `0.2.0`; dedicated build SHA-256 observed on 2026-09-26: `24999e6b09c18d7b62ba413f1dd1200c81a7d5388ca87349c72db7a58a3b7fd8`. Verify the current build before using it.
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
