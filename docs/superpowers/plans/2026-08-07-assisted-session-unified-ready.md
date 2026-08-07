# Assisted Session Unified Non-Submit Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `assisted_session` the single source of truth for safe, non-submitting form preparation while keeping the Chrome extension as a thin browser adapter.

**Architecture:** Add a loopback-only capability bridge owned by `assisted_session`; the bridge issues one-time, short-lived tokens bound to session, candidate, origin, and form fingerprint. Extend the existing session state with guarded transitions and a single active-candidate lock. Keep profile decryption, queue state, and manual submission records in the Python application; keep DOM analysis, ephemeral field values, verification, rollback, and submit blocking in the extension/browser layer.

**Tech Stack:** Python 3, FastAPI/stdlib HTTP boundary already used by the repository, Playwright, Chrome Manifest V3, pytest, Node test runner.

## Global Constraints

- Never click or invoke final submit, confirmation, consent, CAPTCHA, login, SNS, payment, or authentication controls.
- Keep `submitted_count_auto=0` and `auto_submit_detected=0`.
- Never persist or log profile values, cookies, tokens, URLs with query/fragment, HTML, screenshots, or browser storage exports.
- Bind the bridge to `127.0.0.1` only and keep it on a port separate from the management UI.
- Preserve existing user changes; do not reset, clean, stash, delete, commit, or push unrelated worktree changes.
- Keep candidate status and ordinary history changes limited to explicit human actions.

---

### Task 1: Define the session state machine and active-candidate lock

**Files:**
- Create: `app/session_state_machine.py`
- Modify: `app/assisted_session.py`
- Test: `tests/test_assisted_session_state_machine.py`

**Interfaces:**
- `SessionStateMachine.transition(state, event, *, session_id, candidate_id) -> dict[str, object]`
- `SessionStateMachine.lock_candidate(state, candidate_id) -> dict[str, object]`
- `SessionStateMachine.release_candidate(state, candidate_id) -> dict[str, object]`
- `SessionStateMachine.is_transition_allowed(current, event) -> bool`

- [ ] Write tests for all required states, invalid transitions, one active candidate, and a second candidate lock rejection.
- [ ] Run `py -3 -m pytest tests/test_assisted_session_state_machine.py -q` and confirm RED.
- [ ] Implement a pure transition table and lock checks without touching queue files.
- [ ] Run the focused tests and confirm GREEN.
- [ ] Integrate only session-state writes in `assisted_session.py`; preserve existing serialized fields and set `submitted_count_auto` to zero.
- [ ] Run assisted-session and web tests.

### Task 2: Add a loopback-only one-time capability bridge

**Files:**
- Create: `app/extension_bridge.py`
- Modify: `app/assisted_session.py`, `app/paths.py`
- Test: `tests/test_extension_bridge.py`

**Interfaces:**
- `CapabilityBridge.issue(*, session_id, candidate_id, origin, fingerprint, payload) -> dict[str, object]`
- `CapabilityBridge.consume(*, token, session_id, candidate_id, origin, fingerprint) -> dict[str, object]`
- `CapabilityBridge.start() -> tuple[str, int]`
- `CapabilityBridge.stop() -> None`

- [ ] Write tests for valid use, TTL expiry, token reuse, wrong origin, wrong candidate, wrong session, wrong fingerprint, URL/query exclusion, and redacted errors.
- [ ] Run the focused bridge tests and confirm RED.
- [ ] Implement token records in process memory with a maximum 60-second TTL, constant-time token comparison, single consumption, and no request/response logging.
- [ ] Implement the HTTP endpoint on `127.0.0.1` only; reject non-POST, missing token, malformed origin, query/fragment-bearing URLs, and unknown payload fields.
- [ ] Run focused bridge tests and confirm GREEN.

### Task 3: Connect the bridge to assisted-session lifecycle

**Files:**
- Modify: `app/assisted_session.py`, `web/app.py`
- Test: `tests/test_assisted_session_bridge_lifecycle.py`, `tests/test_web_app.py`

**Interfaces:**
- `issue_extension_capability(session_id, candidate_id, origin, fingerprint) -> dict[str, object]`
- `consume_extension_capability(...) -> dict[str, object]`
- `GET /api/session/extension-capability/status` returns only non-PII status.

- [ ] Add tests proving session start creates one candidate lock, candidate change invalidates the prior capability, and session stop clears bridge memory.
- [ ] Run the focused lifecycle tests and confirm RED.
- [ ] Start and stop the bridge only from the existing assisted-session controller; never from a second応募 engine.
- [ ] Keep the management UI port unchanged and bind the bridge to a separate loopback port.
- [ ] Run focused lifecycle and web tests.

### Task 4: Make extension profile handoff one-shot and adapter-only

**Files:**
- Modify: `extension/service-worker.js`, `extension/shared/messages.js`, `extension/content/overlay.js`
- Test: `extension/tests/unit.test.cjs`, `tests/test_extension_bridge_contract.py`

**Interfaces:**
- Service-worker message `REQUEST_SESSION_PROFILE` returns only the approved field subset for the active token and immediately consumes it.
- Overlay action `fill` requests the one-shot payload; it never calls the bridge directly.

- [ ] Add unit tests proving content scripts cannot call the bridge directly, MAIN world receives no PII, payload is consumed once, and session clear removes the in-memory profile.
- [ ] Run `npm test -- --runInBand` and confirm RED for the new contract tests.
- [ ] Implement service-worker-only bridge access and one-shot message handling; preserve current `storage.session` access restrictions.
- [ ] Ensure overlay cleanup runs after fill, rollback, candidate change, session clear, origin disable, and extension reload.
- [ ] Run extension tests and the local smoke test.

### Task 5: Enforce post-fill state and human handoff

**Files:**
- Modify: `app/assisted_session.py`, `extension/content/form-filler.js`, `extension/content/overlay.js`
- Test: `tests/test_assisted_session_handoff.py`, `tests/test_field_mapping_safety.py`, `extension/tests/unit.test.cjs`

**Interfaces:**
- Verified fill reports `POST_FILL_VERIFIED` metadata without values.
- Any mismatch reports `ROLLBACK_REQUIRED` and stops further input.
- Human submission reporting is the only path to `USER_REPORTED_SUBMITTED` and candidate completion.

- [ ] Add tests for fingerprint changes, unrelated-field changes, controlled-input writeback, complete rollback, incomplete rollback, and no automatic navigation.
- [ ] Run focused tests and confirm RED.
- [ ] Integrate existing fingerprint, verification, rollback, and submit guard results into the state machine.
- [ ] Explicitly reject automatic clicks for `確認`, `次へ`, `確認画面へ`, `応募する`, and `送信する`.
- [ ] Run focused tests, extension tests, and full tests.

### Task 6: Add non-PII operational visibility and documentation

**Files:**
- Modify: `web/templates/approved_session.html`, `extension/README.md`, `docs/EXTENSION_SECURITY_MODEL.md`, `docs/EXTENSION_REAL_SITE_TEST_RUNBOOK.md`
- Test: `tests/test_web_app.py`, `tests/test_privacy_guard.py`

**Interfaces:**
- The UI exposes current state, candidate lock, safe stop reason, and next human action without profile values or capability tokens.

- [ ] Add tests for safe status rendering, absent data, and zero auto-submit counters.
- [ ] Implement compact status labels and next-action text only; do not display raw tokens, profile values, or full URLs with query strings.
- [ ] Document bridge binding, token lifecycle, state transitions, manual submission, and recovery.
- [ ] Run targeted tests, all Python tests, compileall, extension tests, local extension smoke, Web smoke, and `git diff --check`.

## Verification Commands

```powershell
py -3 -m pytest tests/test_assisted_session_state_machine.py tests/test_extension_bridge.py tests/test_assisted_session_bridge_lifecycle.py tests/test_assisted_session_handoff.py tests/test_field_mapping_safety.py -q
py -3 -m pytest tests -q
py -3 -m compileall app scripts main.py web_app.py desktop_app.py
npm test -- --runInBand
py -3 scripts/run_extension_local_smoke.py
py -3 -m kensho_assistant.run_web --smoke-test
git diff --check
```

## Explicit Non-Goals

- Real-site operation in this implementation pass.
- Final submission, consent, CAPTCHA, login, SNS, payment, or account creation.
- Any new candidate collection or site-specific rule engine.
- Git commit or push while the worktree contains unrelated user changes.
