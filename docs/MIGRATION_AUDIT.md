# Standalone Migration Audit

## Gate

`STANDALONE_COPY_VERIFIED`

## Source

- Source Git root: `archive/retired_kensho_assistant_20260801/kensho_assistant`
- Source branch: `codex/extension-mvp`
- Source HEAD: `7ce150bae87839859e69271ecf1b76007e120fad`
- Extension version: `0.2.0`

The source path above is intentionally repository-relative in this report. The migration inventory contains no absolute source path.

## Canonical Evidence

- Current legacy working directory: implementation files absent; rejected.
- Existing standalone candidate: absent before migration.
- Verified source Python tests: `394 passed`.
- Verified extension unit tests: `24 passed`.
- Verified extension local smoke: PASS.
- Verified Web smoke: `WEB_SMOKE_TEST_OK`.
- Required features found: assisted session, automatic injection, combined Japanese-name mapping, session profile reuse, form fingerprint, loopback bridge, state machine, and submit guard.

## Copy Evidence

- Allowlisted source files copied: `294`.
- Missing copied files: `0`.
- Source SHA-256 mismatches: `0`.
- Destination SHA-256 mismatches: `0`.
- Forbidden destination paths: `0`.
- Absolute source path in inventory: `false`.
- Safe data copied: `data/pilot/manifests/5site-pilot-v1.json` only.

Excluded content includes `.git`, `.env`, `profile.enc`, cookies, browser profiles, operational CSV/JSONL data, normal history, logs, reports, screenshots, traces, caches, temporary files, `node_modules`, and `.venv`.

## Source Integrity

The source Git status and major source SHA-256 values were unchanged after tests and migration. The source was not deleted, restored, staged, or committed.
