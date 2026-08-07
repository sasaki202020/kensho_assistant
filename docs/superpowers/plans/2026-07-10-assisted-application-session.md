# Assisted Application Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 承認済みの案件を1件ずつChromeで開き、安全に入力できる項目だけを埋めて、人間の手動送信後に次の案件へ進めるセッション機能を追加する。

**Architecture:** `app/assisted_session.py` にセッション状態・完了判定・runner をまとめ、既存の `AutoApplyEngine` と `fill_campaign_page` を再利用する。CLI は `prepare-session` で runner を起動し、Web UI は session state JSON を読み書きして開始・送信済み・保留・停止を制御する。

**Tech Stack:** Python 3.12, Playwright sync API, FastAPI, Jinja2, pytest.

## Global Constraints

- 外部サイトの送信ボタン、確認ボタン、完了ボタンはコードからクリックしない
- `submitted_count_auto` は常に `0` を維持する
- CAPTCHA 回避、Cloudflare 回避、webdriver 隠し、User-Agent 回転は追加しない
- `profile.enc` は読まない、復号情報はログに出さない
- 個人情報は状態ファイル・ログ・UI に平文で残さない
- 既存の `prepare`、`prepare-all`、`dry-run`、`later-queue` の入口は壊さない

---

### Task 1: Shared session state and completion classifier

**Files:**
- Create: `kensho_assistant/app/assisted_session.py`
- Modify: `kensho_assistant/app/paths.py`
- Test: `kensho_assistant/tests/test_assisted_session.py`

**Interfaces:**
- Produces:
  - `load_assisted_session_state() -> dict[str, object]`
  - `save_assisted_session_state(payload: dict[str, object]) -> Path`
  - `request_assisted_session_action(action: str, queue_id: str = "", note: str = "") -> Path`
  - `clear_assisted_session_action() -> Path`
  - `classify_completion_snapshot(current_url: str, title: str, body_text: str, baseline_url: str = "") -> dict[str, object]`

- [ ] **Step 1: Write the failing tests**

```python
def test_assisted_session_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    path = save_assisted_session_state({
        "status": "AWAITING_USER_SUBMIT",
        "current_campaign_id": "abc",
        "submitted_count_auto": 0,
    })
    data = load_assisted_session_state()
    assert path.exists()
    assert data["status"] == "AWAITING_USER_SUBMIT"
    assert data["submitted_count_auto"] == 0

def test_completion_classifier_distinguishes_complete_confirm_and_uncertain():
    complete = classify_completion_snapshot("https://example.com/thanks", "受付完了", "応募を受け付けました")
    confirm = classify_completion_snapshot("https://example.com/confirm", "確認画面", "内容を確認してください")
    uncertain = classify_completion_snapshot("https://example.com/next", "移動しました", "ありがとうございました")
    assert complete["state"] == "COMPLETED"
    assert confirm["state"] == "AWAITING_USER_SUBMIT"
    assert uncertain["state"] == "AWAITING_USER_NEXT"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:
`py -3 -m pytest kensho_assistant/tests/test_assisted_session.py -q`

Expected: fail because the module and helpers do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

```python
ASSISTED_SESSION_DIR = DATA_DIR / "assisted_session"
ASSISTED_SESSION_STATE_JSON = ASSISTED_SESSION_DIR / "session.json"

def classify_completion_snapshot(current_url: str, title: str, body_text: str, baseline_url: str = "") -> dict[str, object]:
    return {"state": "AWAITING_USER_SUBMIT", "manual_submit_observed": False, "completion_confirmed": False, "reason": ""}

def load_assisted_session_state() -> dict[str, object]:
    return default_assisted_session_state()

def save_assisted_session_state(payload: dict[str, object]) -> Path:
    return ASSISTED_SESSION_STATE_JSON
```

- [ ] **Step 4: Run the tests and verify they pass**

Run:
`py -3 -m pytest kensho_assistant/tests/test_assisted_session.py -q`

Expected: PASS.

---

### Task 2: Session runner and queue progression

**Files:**
- Modify: `kensho_assistant/app/assisted_session.py`
- Modify: `kensho_assistant/app/apply_queue.py` only if a shared helper is required
- Test: `kensho_assistant/tests/test_assisted_session.py`

**Interfaces:**
- Consumes:
  - `AutoApplyEngine("dry_run").run(page, campaign, profile)`
  - `approved_queue_rows(load_apply_queue())`
  - `mark_manual_submitted`, `mark_hold`, `mark_skipped`
  - `target_url_for_campaign`
- Produces:
  - `run_assisted_application_session(*, status_filter: str = "APPROVED,PREPARED", limit: int = 12, browser: str = "chrome", keep_open: bool = False) -> dict[str, object]`
  - session state transitions: `IDLE`, `OPENING`, `FILLING`, `AWAITING_USER_SUBMIT`, `VERIFYING_COMPLETION`, `AWAITING_USER_NEXT`, `ADVANCING`, `COMPLETED`, `STOPPED`

- [ ] **Step 1: Write the failing tests**

```python
def test_session_runner_processes_only_approved_prepared_rows(monkeypatch):
    calls = []
    class FakeEngine:
        def __init__(self, mode: str) -> None:
            self.mode = mode
        def run(self, page, campaign, profile):
            calls.append({"campaign_id": campaign["campaign_id"], "mode": self.mode})
            return {
                "record": {"campaign_id": campaign["campaign_id"], "status": "AWAITING_USER_SUBMIT", "submitted_count_auto": 0},
                "analysis": {},
                "pre_submit_check": {},
                "filled_fields": [],
                "missing_fields": [],
                "submit_result": {"status": "DRY_RUN_COMPLETED"},
            }
    monkeypatch.setattr("kensho_assistant.app.assisted_session.approved_queue_rows", lambda rows=None: [
        {"campaign_id": "a", "queue_status": "APPROVED", "approved_by_user": "true"},
        {"campaign_id": "b", "queue_status": "PREPARED", "approved_by_user": "true"},
        {"campaign_id": "c", "queue_status": "QUEUED", "approved_by_user": "false"},
    ])
    monkeypatch.setattr("kensho_assistant.app.assisted_session.AutoApplyEngine", lambda mode: FakeEngine(mode))
    result = run_assisted_application_session(status_filter="APPROVED,PREPARED", limit=2, browser="chrome")
    assert result["processed"] == 2
    assert [call["campaign_id"] for call in calls] == ["a", "b"]
    assert result["submitted_count_auto"] == 0

def test_session_runner_honors_manual_next_hold_and_stop(monkeypatch):
    state_updates = []
    monkeypatch.setattr("kensho_assistant.app.assisted_session.request_assisted_session_action", lambda action, queue_id="", note="": state_updates.append((action, queue_id, note)) or Path("session.json"))
    monkeypatch.setattr("kensho_assistant.app.assisted_session.classify_completion_snapshot", lambda current_url, title, body_text, baseline_url="": {"state": "COMPLETED", "manual_submit_observed": True, "completion_confirmed": True, "reason": "完了"})
    result = run_assisted_application_session(status_filter="APPROVED", limit=1, browser="chrome")
    assert result["status"] in {"completed", "stopped"}
    assert any(action == "submitted_next" for action, _, _ in state_updates)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:
`py -3 -m pytest kensho_assistant/tests/test_assisted_session.py -q`

Expected: fail because the runner does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

```python
class AssistedSessionRunner:
    def __init__(
        self,
        *,
        status_filter: str = "APPROVED,PREPARED",
        limit: int = 12,
        browser: str = "chrome",
        keep_open: bool = False,
    ) -> None:
        self.status_filter = status_filter
        self.limit = limit
        self.browser = browser
        self.keep_open = keep_open

    def run(self) -> dict[str, object]:
        return {"status": "completed", "processed": 0, "submitted_count_auto": 0}

def run_assisted_application_session(
    *,
    status_filter: str = "APPROVED,PREPARED",
    limit: int = 12,
    browser: str = "chrome",
    keep_open: bool = False,
) -> dict[str, object]:
    return AssistedSessionRunner(
        status_filter=status_filter,
        limit=limit,
        browser=browser,
        keep_open=keep_open,
    ).run()
```

The runner must:
- open one persistent Chrome context
- fill safe fields through the existing auto fill path
- save analysis, pre-submit check, screenshot, and HTML snapshot through existing engine output
- wait for a manual submit or a control action before advancing
- treat `submitted_next` as a manual submission acknowledgment
- treat `hold` as a hold transition without recording auto submission
- treat `stop` as a stop transition and leave `submitted_count_auto` at `0`
- use clear completion evidence only when page URL/title/body indicate a final completion state

- [ ] **Step 4: Run the tests and verify they pass**

Run:
`py -3 -m pytest kensho_assistant/tests/test_assisted_session.py -q`

Expected: PASS.

---

### Task 3: CLI command for session start

**Files:**
- Modify: `kensho_assistant/main.py`
- Test: `kensho_assistant/tests/test_web_app.py`

**Interfaces:**
- Produces:
  - `cmd_prepare_session(args: argparse.Namespace) -> int`
  - parser command: `py -3 main.py prepare-session --status APPROVED,PREPARED --limit 12 --browser chrome`

- [ ] **Step 1: Write the failing tests**

```python
def test_prepare_session_command_calls_runner(monkeypatch, capsys):
    calls = {}
    monkeypatch.setattr(main_cli, "run_assisted_application_session", lambda **kwargs: calls.update(kwargs) or {"status": "completed", "processed": 2, "submitted_count_auto": 0})
    result = main_cli.cmd_prepare_session(argparse.Namespace(status="APPROVED,PREPARED", limit=12, browser="chrome", keep_open=False))
    assert result == 0
    assert calls["status_filter"] == "APPROVED,PREPARED"
    assert calls["limit"] == 12
    assert calls["browser"] == "chrome"
    assert "submitted_count_auto: 0" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:
`py -3 -m pytest kensho_assistant/tests/test_web_app.py -q`

Expected: fail because the command and parser entry do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

```python
prepare_session = subparsers.add_parser("prepare-session", help="run assisted manual-submit session")
prepare_session.add_argument("--status", default="APPROVED,PREPARED", help="queue_status to process")
prepare_session.add_argument("--limit", type=int, default=12, help="max campaigns")
prepare_session.add_argument("--browser", choices=("chrome", "chromium"), default="chrome", help="headed browser to use")
prepare_session.add_argument("--keep-open", action="store_true", help="keep browser open after stop")
prepare_session.set_defaults(func=cmd_prepare_session)
```

- [ ] **Step 4: Run the tests and verify they pass**

Run:
`py -3 -m pytest kensho_assistant/tests/test_web_app.py -q`

Expected: PASS.

---

### Task 4: Web UI start/control/status wiring

**Files:**
- Modify: `kensho_assistant/web/app.py`
- Modify: `kensho_assistant/web/templates/dashboard.html`
- Modify: `kensho_assistant/web/templates/approved_session.html`
- Modify: `kensho_assistant/web/static/style.css` only if a small layout fix is required
- Test: `kensho_assistant/tests/test_web_app.py`

**Interfaces:**
- Produces:
  - `@app.post("/queue/session/start")`
  - `@app.get("/api/session/status")`
  - `@app.post("/queue/session/{queue_id}/submitted-next")`
  - `@app.post("/queue/session/{queue_id}/hold")`
  - `@app.post("/queue/session/{queue_id}/stop")`
  - dashboard button text: `今日の応募を始める`
  - session controls: `送信済み・次へ`, `保留`, `停止`

- [ ] **Step 1: Write the failing tests**

```python
def test_session_start_route_spawns_prepare_session(monkeypatch):
    calls = {}
    monkeypatch.setattr("kensho_assistant.web.app.subprocess.Popen", fake_popen)
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/queue/session/start", follow_redirects=False)
    assert response.status_code == 303
    assert "prepare-session" in " ".join(calls["args"])

def test_session_status_api_returns_safe_state(monkeypatch):
    monkeypatch.setattr("kensho_assistant.web.app.load_assisted_session_state", lambda: {"status": "AWAITING_USER_SUBMIT", "submitted_count_auto": 0})
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/session/status")
    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "AWAITING_USER_SUBMIT"
    assert data["submitted_count_auto"] == 0
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:
`py -3 -m pytest kensho_assistant/tests/test_web_app.py -q`

Expected: fail because the routes and template bindings do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

```python
def _start_prepare_session(status: str = "APPROVED,PREPARED", limit: int = 12, browser: str = "chrome", keep_open: bool = False) -> str:
    command = [sys.executable, str(PACKAGE_ROOT.parent / "main.py"), "prepare-session", "--status", status, "--limit", str(limit), "--browser", browser]
    if keep_open:
        command.append("--keep-open")
    subprocess.Popen(command, cwd=str(PACKAGE_ROOT.parent), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return "started"
```

Web UI must:
- show current session status without internal implementation names
- show current campaign, progress, unresolved items, and next action
- keep `submitted_count_auto=0` visible
- avoid showing `READY_FOR_FILL`, `REVIEW_ONLY`, or other developer-only labels in the default view
- leave the existing `prepare`, `prepare-all`, `dry-run`, and `later-queue` pages intact

- [ ] **Step 4: Run the tests and verify they pass**

Run:
`py -3 -m pytest kensho_assistant/tests/test_web_app.py -q`

Expected: PASS.

---

### Task 5: Verification and docs

**Files:**
- Modify: `kensho_assistant/docs/CODEX_HANDOFF.md` only if it needs a one-line pointer update
- Modify: `kensho_assistant/docs/kensho_harness.md` only if the new session flow needs a short note
- Test: all tests touched by the session feature

**Interfaces:**
- Produces:
  - passing focused tests
  - `py -3 -m compileall kensho_assistant/app/assisted_session.py kensho_assistant/main.py kensho_assistant/web/app.py`
  - `py -3 -m pytest kensho_assistant/tests/test_assisted_session.py kensho_assistant/tests/test_web_app.py -q`

- [ ] **Step 1: Run focused verification**

Run:
`py -3 -m pytest kensho_assistant/tests/test_assisted_session.py kensho_assistant/tests/test_web_app.py -q`

- [ ] **Step 2: Run compile verification**

Run:
`py -3 -m compileall kensho_assistant/app/assisted_session.py kensho_assistant/main.py kensho_assistant/web/app.py`

- [ ] **Step 3: Run the smoke check**

Run:
`py -3 web_app.py --smoke-test`

- [ ] **Step 4: Commit when green**

```bash
git add kensho_assistant/app/assisted_session.py kensho_assistant/app/paths.py kensho_assistant/main.py kensho_assistant/web/app.py kensho_assistant/web/templates/dashboard.html kensho_assistant/web/templates/approved_session.html kensho_assistant/tests/test_assisted_session.py kensho_assistant/tests/test_web_app.py
git commit -m "feat: add assisted application session"
```

## Self-Review

1. Spec coverage:
- 送信前停止: Task 2, Task 4
- 単一 Chrome セッション: Task 2
- 手動送信後の次案件遷移: Task 2, Task 4
- `submitted_count_auto = 0`: Task 1, Task 2, Task 3, Task 4
- 既存入口保持: Task 3, Task 4
- 個人情報非表示: Task 1, Task 2, Task 4

2. Placeholder scan:
- `TODO`、`TBD`、未定の API 名は使っていない
- 既存関数名と新規関数名は Task 間で一致している

3. Type consistency:
- `classify_completion_snapshot(...)` の戻り値は dict で統一
- `run_assisted_application_session(...)` の戻り値は dict で統一
- `request_assisted_session_action(...)` は CLI と Web UI の両方で同じ制御ファイルを更新する
