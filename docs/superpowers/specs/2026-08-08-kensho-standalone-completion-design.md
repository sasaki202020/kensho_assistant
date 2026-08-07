# Kensho Assistant Standalone Completion Design

## Goal

Move the verified `kensho_assistant` source into an independent repository, preserve its non-submit safety boundary, and validate the assisted workflow through a local baseline and one non-submit real-site trial before any human-profile session.

## Verified Source

The source candidate is:

`C:\Users\goo10\OneDrive\ドキュメント\New project\archive\retired_kensho_assistant_20260801\kensho_assistant`

Evidence collected on 2026-08-08:

- Independent Git root at the candidate directory.
- Branch `codex/extension-mvp`.
- HEAD `7ce150bae87839859e69271ecf1b76007e120fad`.
- Extension version `0.2.0`, Manifest V3.
- Assisted session, loopback bridge, state machine, automatic content-script registration, combined Japanese-name handling, profile reuse, form fingerprinting, and submit guards are present.
- Python tests: `394 passed`.
- Extension unit tests: `24 passed`.
- Extension local smoke: PASS, ten reloads, one panel, one guard, zero external requests.
- Web smoke: `WEB_SMOKE_TEST_OK`.
- Major source SHA-256 values were unchanged before and after verification.

The current `New project\kensho_assistant` directory is not a valid source because its implementation files are absent. `C:\Users\goo10\Projects\kensho_assistant` did not exist before this migration.

## Repository Boundary

The standalone repository lives at:

`C:\Users\goo10\Projects\kensho_assistant`

The migration source is read-only. The parent repository is not modified. The standalone copy uses an explicit allowlist and never copies `.git`, profiles, cookies, browser profiles, operational databases, histories, logs, screenshots, traces, caches, temporary files, dependency installations, or virtual environments.

Safe source categories are application source, tests, fixtures, scripts, documentation, extension source, dependency definitions, configuration schemas, `README.md`, `AGENTS.md`, `.env.example`, and the PII-free pilot manifest. The URL-bearing `5site-candidates-v1.json` and all other operational `data` content are excluded.

## Profile Boundary

The production encrypted profile is stored outside Git at:

`C:\Users\goo10\AppData\Local\kensho_assistant\profile.enc`

The application resolves the path from `KENSHO_PROFILE_PATH`. If the variable is absent, the same local application-data path is used. Tests use a temporary fictional encrypted profile and never read the production file. The old profile is not copied. The user registers the real profile only after the standalone baseline passes.

## Assisted Session Architecture

`assisted_session` is the authoritative workflow state. It owns the session ID, candidate lock, candidate state, confirmed mapping reference, form fingerprint, manual-submission acknowledgement, and non-PII audit record.

The Chrome extension is a thin browser adapter. Its service worker owns only ephemeral browser state and a `chrome.storage.session` profile fragment. Content scripts receive values only for the explicit fill operation and discard references after fill, rollback, navigation, candidate change, or session clear.

The bridge binds only to `127.0.0.1` on a port separate from the management UI. It accepts POST requests from the service worker, consumes one-time capability tokens with a maximum 60-second TTL, and binds each token to `session_id`, `candidate_id`, `origin`, and `form_fingerprint`. It rejects replay, expiry, and binding mismatches before returning the minimum confirmed profile fields. URLs, query strings, logs, caches, and exceptions do not persist PII.

## Extension Installation Boundary

The unpacked extension from the standalone path is treated as a separate installation. The old installation is not removed automatically. The runbook records the new `chrome.runtime.id`, requires site permissions to be granted again, and verifies that only one kensho panel and one submit guard are active. If both old and new extensions are active on the same page, the trial is blocked until the user disables one manually.

## Safety Gates

The gates are sequential:

1. `SOURCE_CANONICAL_VERIFIED`
2. `STANDALONE_COPY_VERIFIED`
3. `STANDALONE_BASELINE_PASS`
4. `ASSISTED_SESSION_INTEGRATION_PASS`
5. `FIELD_MAPPING_SAFETY_PASS`
6. `REAL_SITE_NON_SUBMIT_PASS`
7. `SINGLE_ASSISTED_SUBMISSION_PASS`

A failed or unverified gate blocks all later gates. Automatic final submission, confirmation-button automation, consent automation, CAPTCHA handling, login automation, and Git push remain forbidden. `submitted_count_auto` remains zero.

## Real-Site Phases

Phase A uses a fictional test profile in a separate session. It analyzes one site, requires mapping review, fills only confirmed safe fields, verifies the post-fill state, rolls back every extension change, confirms zero persistence, and exits without submission.

Phase B starts only after Phase A passes. It uses the user-registered profile in a fresh session. The assistant may prepare fields up to human review. The user alone handles consent, CAPTCHA, and final submission, then explicitly records `送信済み・次へ`. Phase A and Phase B have separate run IDs and evidence.

## Failure Policy

Any uncertainty about source provenance, copied content, profile location, extension duplication, bridge binding, field mapping, post-fill verification, rollback completeness, PII persistence, candidate mutation, or submit activity fails closed. No result is reported as complete without an artifact or test result proving it.
