# Kensho Assistant Standalone Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a standalone, reproducible kensho assistant that safely prepares one real application up to human review without automatic submission.

**Architecture:** Copy the verified source through an explicit allowlist into an independent repository. Keep `assisted_session` authoritative, expose confirmed profile fragments through a one-shot loopback bridge, and use the extension only as an ephemeral browser adapter. Prove each gate before moving to the next.

**Tech Stack:** Python 3.12, pytest, Flask, Playwright local fixtures, Chrome Manifest V3, Node built-in test runner, PowerShell.

## Global Constraints

- Do not modify or delete the migration source or the parent Git repository.
- Do not copy `.git`, `profile.enc`, `.env`, cookies, browser profiles, operational data, histories, logs, screenshots, traces, caches, temporary files, `node_modules`, or `.venv`.
- Do not automate final submit, confirmation navigation, consent, CAPTCHA, login, or SNS actions.
- Keep `submitted_count_auto=0` and `auto_submit_detected=0`.
- Bind the extension bridge only to `127.0.0.1` on a separate port and accept POST only.
- Do not run Phase B before Phase A passes.
- Do not push Git commits.

---

### Task 1: Allowlisted Standalone Copy

**Files:**
- Create: `scripts/migrate_standalone_allowlist.ps1`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `docs/MIGRATION_AUDIT.md`
- Copy: `app/`, `tests/`, `samples/`, `scripts/`, `docs/`, `extension/`, `pilot/`, `ui/`, `web/`, `config/`, Python entrypoints, dependency definitions, `README.md`, `AGENTS.md`, `MIGRATION_PROVENANCE.md`
- Copy: `data/pilot/manifests/5site-pilot-v1.json`

**Interfaces:**
- Consumes: verified source path and SHA-256 inventory.
- Produces: `Invoke-KenshoAllowlistedMigration -Source <path> -Destination <path>` and a machine-readable copied-file inventory.

- [ ] **Step 1: Write migration-policy tests**

Add `tests/test_standalone_migration.py` with tests that assert allowed roots are copied, denied names are rejected at every depth, only `5site-pilot-v1.json` is copied from `data`, and the destination contains no absolute source path.

- [ ] **Step 2: Run the tests and verify RED**

Run: `py -3.12 -m pytest tests/test_standalone_migration.py -v`

Expected: collection fails because the migration script or policy module is absent.

- [ ] **Step 3: Implement the explicit allowlist**

The script must define exact top-level directory and file arrays, walk only those entries, reject any path segment matching the denylist, hash every copied file, and abort if the destination is non-empty except for the approved design and plan documents.

- [ ] **Step 4: Execute migration once**

Run from the destination:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\migrate_standalone_allowlist.ps1 `
  -Source 'C:\Users\goo10\OneDrive\ドキュメント\New project\archive\retired_kensho_assistant_20260801\kensho_assistant' `
  -Destination 'C:\Users\goo10\Projects\kensho_assistant'
```

Expected: copied inventory contains only allowlisted files and records SHA-256 values.

- [ ] **Step 5: Verify source and destination hashes**

Compare every copied inventory row. Require zero missing files, zero hash mismatches, and zero denied-path hits. Record `STANDALONE_COPY_VERIFIED` in `docs/MIGRATION_AUDIT.md`.

- [ ] **Step 6: Initialize standalone Git and commit explicitly**

Run `git init`, set local identity only from an existing global identity, stage explicit allowlisted paths, and commit with `chore: establish standalone kensho baseline`. Do not use `git add .` or push.

### Task 2: External Profile Path

**Files:**
- Modify: `app/paths.py`
- Modify: `app/profile_manager.py`
- Modify: `README.md`
- Modify: `.env.example`
- Test: `tests/test_profile_manager.py`

**Interfaces:**
- Produces: `resolve_profile_path(env: Mapping[str, str] | None = None) -> Path`.
- Default: `%LOCALAPPDATA%\kensho_assistant\profile.enc`.
- Override: `KENSHO_PROFILE_PATH`.

- [ ] **Step 1: Add failing path-resolution tests**

Test explicit environment override, default LocalAppData resolution, missing LocalAppData fail-closed behavior, and proof that the repository `config/profile.enc` is never selected.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `py -3.12 -m pytest tests/test_profile_manager.py -v`

- [ ] **Step 3: Implement minimal path resolution**

Resolve and normalize the environment path, create only its parent directory during explicit profile-save operations, and avoid logging the resolved filename when handling errors.

- [ ] **Step 4: Verify fictional-profile round trip**

Use `tmp_path` and fictional values. Assert encrypted round trip, no plaintext repository artifacts, and no production profile read.

- [ ] **Step 5: Run profile and privacy tests**

Run: `py -3.12 -m pytest tests/test_profile_manager.py tests/test_privacy_guard.py -v`

### Task 3: Extension Installation Identity and Double-Activation Guard

**Files:**
- Modify: `extension/service-worker.js`
- Modify: `extension/content/overlay.js`
- Modify: `extension/shared/messages.js`
- Modify: `extension/README.md`
- Create: `docs/EXTENSION_STANDALONE_INSTALL.md`
- Test: `extension/tests/unit.test.cjs`
- Test: `tests/test_extension_mvp.py`

**Interfaces:**
- Produces: `GET_EXTENSION_ID`, `EXTENSION_INSTANCE_HELLO`, and `DUPLICATE_EXTENSION_BLOCKED` messages.
- Exposes: non-PII `chrome.runtime.id`, extension version, and active-instance count.

- [ ] **Step 1: Add failing duplicate-instance tests**

Model two extension roots on the same document and assert both fill controls are disabled, the submit guard remains active, and no profile request is issued.

- [ ] **Step 2: Run extension tests and verify RED**

Run: `npm test -- --runInBand`

- [ ] **Step 3: Implement deterministic instance handshake**

Broadcast only extension ID and version through a DOM event, detect a different ID, set `data-kensho-duplicate-extension=true`, clear session profile, and block analyze/fill while preserving the guard.

- [ ] **Step 4: Document manual loading**

Document `chrome://extensions`, Developer mode, Load unpacked from `C:\Users\goo10\Projects\kensho_assistant\extension`, recording the new ID, re-granting site permissions, and manually disabling the old extension.

- [ ] **Step 5: Run extension unit and local smoke tests**

Run `npm test -- --runInBand` and `py -3.12 scripts/run_extension_local_smoke.py`. Require one panel, one guard, ten successful reloads, and zero external requests.

### Task 4: Assisted Session Bridge and State Authority

**Files:**
- Modify: `app/assisted_session.py`
- Modify: `app/extension_bridge.py`
- Modify: `app/session_state_machine.py`
- Modify: `web/app.py`
- Modify: `extension/service-worker.js`
- Test: `tests/test_extension_bridge.py`
- Test: `tests/test_assisted_session_state_machine.py`
- Test: `tests/test_assisted_session.py`
- Test: `tests/test_web_app.py`

**Interfaces:**
- `CapabilityBridge.issue(session_id, candidate_id, origin, form_fingerprint, profile_fields, ttl_seconds) -> CapabilityMetadata`.
- `CapabilityBridge.consume(token, session_id, candidate_id, origin, form_fingerprint) -> dict[str, str]`.
- `assisted_session` remains the only persistent workflow authority.

- [ ] **Step 1: Add failing boundary tests**

Test loopback-only bind, separate port, POST-only behavior, TTL at most 60 seconds, replay rejection, expiry, origin/candidate/session/fingerprint mismatch, content-script direct-access rejection, and PII absence from URL/log/error output.

- [ ] **Step 2: Run bridge tests and verify RED where coverage is missing**

Run: `py -3.12 -m pytest tests/test_extension_bridge.py tests/test_assisted_session_state_machine.py tests/test_assisted_session.py tests/test_web_app.py -v`

- [ ] **Step 3: Implement the minimum missing bridge checks**

Keep the existing bridge if it passes. Add only missing pre-network validation, single-use token consumption, and worker-only request authentication. Never add a second application engine.

- [ ] **Step 4: Verify state transitions**

Require the path `CANDIDATE_LOCKED -> SUBMIT_GUARD_READY -> FORM_ANALYZED -> MAPPING_REVIEW_REQUIRED -> MAPPING_CONFIRMED -> FILLED -> POST_FILL_VERIFIED -> HUMAN_ACTION_REQUIRED`. Reject completion from every earlier state.

- [ ] **Step 5: Run integration tests**

Require all focused tests to pass with `submitted_count_auto=0`, no duplicate manual history, and no candidate mutation before user acknowledgement.

### Task 5: Field Mapping, Verification, and Rollback Gate

**Files:**
- Modify: `extension/content/field-matcher.js`
- Modify: `extension/content/form-filler.js`
- Modify: `extension/content/overlay.js`
- Modify: `extension/shared/form-fingerprint.js`
- Modify: `extension/shared/form-template.js`
- Test: `extension/tests/unit.test.cjs`
- Test: `tests/test_field_mapping_safety.py`
- Fixture: `tests/extension_fixtures/combined_japanese_form.html`
- Fixture: `tests/extension_fixtures/mapping_safety_form.html`

**Interfaces:**
- First-seen form returns `MAPPING_REVIEW_REQUIRED` without values.
- Changed fingerprint returns `FORM_CHANGED_REVIEW_REQUIRED` with zero fills.
- Failed verification returns `POST_FILL_VERIFICATION_FAILED_ROLLED_BACK`.
- Incomplete rollback returns `ROLLBACK_INCOMPLETE_HUMAN_REVIEW_REQUIRED`.

- [ ] **Step 1: Add or confirm failing safety fixtures**

Cover combined names, guardian/handle ambiguity, address split ambiguity, honeypots, controlled inputs, value reset, target-outside mutation, fingerprint changes, consent/prize/comment fields, and rollback failure.

- [ ] **Step 2: Run focused tests**

Run: `py -3.12 -m pytest tests/test_field_mapping_safety.py -v` and `npm test -- --runInBand`.

- [ ] **Step 3: Implement only missing safety behavior**

Retain existing behavior that already passes. Never raise confidence from placeholder or DOM position alone. Persist only PII-free template metadata.

- [ ] **Step 4: Verify local browser smoke**

Run: `py -3.12 scripts/run_extension_local_smoke.py`.

Require submit blocked, rollback complete, zero external requests, zero duplicate panels/guards, and zero auto-submit detections.

### Task 6: Standalone Baseline and Reproducible Build

**Files:**
- Create: `docs/STANDALONE_BASELINE_REPORT.md`
- Create: `docs/STANDALONE_BUILD_MANIFEST.json`
- Modify: `README.md`

**Interfaces:**
- Produces a deterministic manifest of source SHA-256 values, Python version, extension version, Git branch, Git commit, and safety-test outcomes without absolute paths or PII.

- [ ] **Step 1: Run compile and full tests**

Run:

```powershell
py -3.12 -m compileall -q app web
py -3.12 -m pytest tests -p no:cacheprovider -q --disable-warnings
npm --prefix extension test -- --runInBand
py -3.12 scripts\run_extension_local_smoke.py
py -3.12 -m kensho_assistant.run_web --smoke-test
git diff --check
```

- [ ] **Step 2: Run P1 preflight**

Run the existing offline pilot preflight command documented in `README.md`. Require `READY_FOR_5_SITE_PILOT`, `submitted_count_auto=0`, zero PII persistence, zero candidate-state diff, zero normal-history diff, trace disabled, and screenshot storage disabled.

- [ ] **Step 3: Generate and repeat the build fingerprint**

Generate it twice without file changes and require identical SHA-256 values.

- [ ] **Step 4: Record `STANDALONE_BASELINE_PASS`**

Write the exact commands and results, then commit explicit source/test/doc paths with `test: verify standalone kensho baseline`. Do not push.

### Task 7: Phase A Non-Submit Real-Site Trial

**Files:**
- Create: `docs/REAL_SITE_PHASE_A_REPORT.md`
- Modify: `docs/EXTENSION_REAL_SITE_TEST_RUNBOOK.md`

**Interfaces:**
- Consumes: fixed standalone commit, build fingerprint, fictional encrypted profile, one approved candidate.
- Produces: a non-PII Phase A run record distinct from all normal history.

- [ ] **Step 1: Confirm all prior gates**

Require `STANDALONE_BASELINE_PASS`, `ASSISTED_SESSION_INTEGRATION_PASS`, and `FIELD_MAPPING_SAFETY_PASS` before opening any external page.

- [ ] **Step 2: Start a fresh Phase A session**

Load the new unpacked extension, record its ID, ensure the old extension is disabled for that tab, grant the exact origin, and use a fictional profile only.

- [ ] **Step 3: Analyze, map, fill, verify, and rollback**

Do not click confirmation, next, consent, CAPTCHA, login, or submit controls. Require mapping review, post-fill verification, complete rollback, unchanged candidate/history stores, zero persistent PII, and `submitted_count_auto=0`.

- [ ] **Step 4: Record `REAL_SITE_NON_SUBMIT_PASS` or fail closed**

Store only field types, counts, stop reason, normalized origin/path, and pass/fail flags. Store no values, query string, HTML, screenshot, or trace.

### Task 8: Phase B Single Assisted Submission

**Files:**
- Create: `docs/SINGLE_ASSISTED_SUBMISSION_REPORT.md`

**Interfaces:**
- Consumes: passed Phase A and a separately registered human profile.
- Produces: a manual acknowledgement record only after the user submits.

- [ ] **Step 1: Require human profile registration**

The user registers a new encrypted profile at `%LOCALAPPDATA%\kensho_assistant\profile.enc`. Do not copy or inspect the old profile.

- [ ] **Step 2: Start a separate assisted session**

Use a new session and run ID. Reconfirm origin, fingerprint, extension ID, single active instance, guard status, and confirmed field mapping.

- [ ] **Step 3: Prepare the form and stop**

Fill only confirmed safe profile fields, verify them, and stop in `HUMAN_ACTION_REQUIRED`. The user alone handles consent, CAPTCHA, and final submission.

- [ ] **Step 4: Record the user's result idempotently**

Only after the user reports successful submission, accept one `送信済み・次へ` action, create one manual history row, clear ephemeral PII, release the lock, and keep `submitted_count_auto=0`.

- [ ] **Step 5: Run final regression tests**

Run the complete commands from Task 6 again. Record `SINGLE_ASSISTED_SUBMISSION_PASS` only if all tests remain green and no automatic submit was detected.

## Dependency Order

Tasks 1 through 8 are sequential at gate boundaries. Within Task 1, file inventory and denylist scanning may run in parallel. Within Task 6, Python tests, extension unit tests, and static compilation may run in parallel, but the preflight and build fingerprint run only after they pass. Phase A and Phase B never run in parallel and never share a run ID.
