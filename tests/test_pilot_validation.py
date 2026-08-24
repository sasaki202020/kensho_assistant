from __future__ import annotations

import json
from argparse import Namespace
from copy import deepcopy
from pathlib import Path

import pytest

from kensho_assistant.app.pilot_validation import (
    PilotTrialStore,
    build_pilot_plan,
    create_pilot_manifest,
    git_commit_sha,
    pilot_candidate_preflight,
    pilot_structure_summary,
    pilot_build_preflight,
    run_pilot_manifest,
    validate_pilot_manifest,
)
from kensho_assistant.app.pilot_safety import (
    build_pilot_test_pii,
    compare_storage_snapshots,
    scan_for_forbidden_values,
    snapshot_storage,
)
from kensho_assistant.app.real_site_trials import TrialStore
from kensho_assistant.main import build_parser, cmd_pilot_run, cmd_trial_report


def test_git_commit_sha_is_resolved_from_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    class _Result:
        stdout = "pilot-commit-sha\n"

    def fake_run(*args, **kwargs):
        observed.update(kwargs)
        return _Result()

    monkeypatch.setattr("kensho_assistant.app.pilot_validation.subprocess.run", fake_run)

    assert git_commit_sha() == "pilot-commit-sha"
    assert observed["cwd"].name == "kensho_assistant"


def test_pilot_build_preflight_rejects_dirty_or_unattested_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kensho_assistant.app.pilot_validation.git_worktree_status", lambda: " M app/form_detector.py")
    monkeypatch.setattr("kensho_assistant.app.pilot_validation.git_branch_name", lambda: "codex/high-value-kensho-v1")
    monkeypatch.setattr("kensho_assistant.app.pilot_validation.git_commit_sha", lambda: "head-sha")

    result = pilot_build_preflight(
        {
            "git_branch": "codex/high-value-kensho-v1",
            "pilot_commit": "head-sha",
            "build_fingerprint_sha256": "fingerprint-sha",
        }
    )

    assert result["valid"] is False
    assert "worktree_dirty" in result["errors"]
    assert result["worktree_clean"] is False


def test_pilot_build_preflight_requires_fingerprint_inputs_when_paths_are_used() -> None:
    result = pilot_build_preflight(
        {
            "git_branch": "codex/high-value-kensho-v1",
            "pilot_commit": "head-sha",
            "build_fingerprint_sha256": "fingerprint-sha",
        },
        manifest_path=Path("pilot.json"),
    )

    assert result["valid"] is False
    assert "fingerprint_inputs_missing" in result["errors"]


def test_pilot_run_cli_blocks_before_profile_or_browser(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = create_pilot_manifest(_candidates(), limit_sites=5)
    monkeypatch.setattr("kensho_assistant.main.load_pilot_manifest", lambda _path: manifest)
    monkeypatch.setattr(
        "kensho_assistant.main.pilot_build_preflight",
        lambda _manifest, **_kwargs: {
            "valid": False,
            "errors": ["worktree_dirty"],
            "current_branch": "codex/high-value-kensho-v1",
            "current_head": "head-sha",
            "worktree_clean": False,
            "fingerprint_matches": None,
        },
    )
    monkeypatch.setattr("kensho_assistant.main.ensure_runtime_dirs", lambda: (_ for _ in ()).throw(AssertionError("must block before runtime setup")))
    monkeypatch.setattr("kensho_assistant.main._load_profile_or_fail", lambda: (_ for _ in ()).throw(AssertionError("must not load profile")))

    result = cmd_pilot_run(Namespace(manifest="pilot.json", candidates="candidates.json", browser="chrome"))

    assert result == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED_PILOT_BUILD"


def _candidates(count: int = 5) -> list[dict[str, str]]:
    return [
        {
            "campaign_id": f"candidate-{index}",
            "resolved_entry_url": f"https://site-{index}.example/form?email=secret@example.com",
            "site_category": "standard_form",
            "queue_status": "APPROVED",
        }
        for index in range(count)
    ]


def test_manifest_plans_five_sites_three_attempts_without_urls() -> None:
    manifest = create_pilot_manifest(_candidates(), limit_sites=5)
    assert manifest["mode"] == "pilot"
    assert manifest["attempts_per_site"] == 3
    assert len(manifest["entries"]) == 5
    assert validate_pilot_manifest(manifest)["valid"] is True

    plan = build_pilot_plan(manifest)
    assert len(plan) == 15
    assert {item["attempt_no"] for item in plan} == {1, 2, 3}
    assert all(len([item for item in plan if item["site_id"] == entry["site_id"]]) == 3 for entry in manifest["entries"])

    text = json.dumps(manifest, ensure_ascii=False)
    assert "https://" not in text
    assert "secret@example.com" not in text


def test_pilot_candidate_preflight_rejects_stale_manifest_bindings() -> None:
    manifest = create_pilot_manifest(_candidates(), limit_sites=5)
    current_candidates = _candidates(1)

    result = pilot_candidate_preflight(manifest, current_candidates)

    assert result["valid"] is False
    assert result["missing_count"] == 4
    assert "candidate_ref_missing" in result["errors"]


class _Page:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.scripts: list[str] = []

    def goto(self, url: str, **kwargs) -> None:
        self.url = url

    def evaluate(self, script: str):
        self.scripts.append(script)
        return {"blockedAttempts": 0, "reasons": []}


class _Context:
    def __init__(self) -> None:
        self.page = _Page()
        self.closed = False
        self.init_scripts: list[str] = []

    def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)

    def new_page(self) -> _Page:
        for script in self.init_scripts:
            self.page.evaluate(script)
        return self.page

    def close(self) -> None:
        self.closed = True


class _Browser:
    version = "test-browser-1"

    def __init__(self) -> None:
        self.contexts: list[_Context] = []
        self.closed = False

    def new_context(self) -> _Context:
        context = _Context()
        self.contexts.append(context)
        return context

    def close(self) -> None:
        self.closed = True


class _Engine:
    def __init__(self) -> None:
        self.run_mode = "dry_run"
        self.persist_flags: list[bool] = []
        self.keep_guard_flags: list[bool] = []

    def run(self, page, campaign, profile, *, persist_artifacts=True, keep_submission_guard=False):
        self.persist_flags.append(persist_artifacts)
        self.keep_guard_flags.append(keep_submission_guard)
        return {
            "record": {
                "status": "PRE_SUBMIT_READY",
                "total_fields_count": 4,
                "filled_fields_count": 4,
                "unresolved_required_fields_count": 0,
                "submit_button_detected": True,
                "submit_clicked": False,
                "auto_submitted": False,
            },
            "missing_fields": [],
            "pre_submit_check": {},
        }


class _GuardTriggeredEngine(_Engine):
    def run(self, page, campaign, profile, *, persist_artifacts=True, keep_submission_guard=False):
        result = super().run(
            page,
            campaign,
            profile,
            persist_artifacts=persist_artifacts,
            keep_submission_guard=keep_submission_guard,
        )
        result["record"]["submit_guard_blocked_attempts"] = 1
        result["record"]["submit_guard_reasons"] = ["form.submit"]
        return result


class _UnsafeArtifactEngine(_Engine):
    def run(self, page, campaign, profile, *, persist_artifacts=True, keep_submission_guard=False):
        result = super().run(page, campaign, profile, persist_artifacts=persist_artifacts, keep_submission_guard=keep_submission_guard)
        result["record"]["html_snapshot_path"] = "unsafe.html"
        return result


class _SubmitAttemptedEngine(_Engine):
    def run(self, page, campaign, profile, *, persist_artifacts=True, keep_submission_guard=False):
        result = super().run(page, campaign, profile, persist_artifacts=persist_artifacts, keep_submission_guard=keep_submission_guard)
        result["record"]["submit_attempted"] = True
        return result


def test_pilot_run_is_read_only_uses_fresh_contexts_and_is_idempotent(tmp_path) -> None:
    candidates = _candidates()
    original = deepcopy(candidates)
    manifest = create_pilot_manifest(candidates, limit_sites=5)
    store = PilotTrialStore(tmp_path / "pilot" / "runs" / "trials.jsonl")
    browser = _Browser()
    engine = _Engine()
    history: list[dict[str, str]] = []

    first = run_pilot_manifest(
        manifest,
        candidates=candidates,
        store=store,
        browser=browser,
        actual_browser="chromium",
        engine=engine,
        profile={"first_name": "TEST"},
        review_callback=lambda page, trial: None,
        protected_storage_root=tmp_path / "normal",
        pilot_storage_root=tmp_path / "pilot",
    )
    second = run_pilot_manifest(
        manifest,
        candidates=candidates,
        store=store,
        browser=browser,
        actual_browser="chromium",
        engine=engine,
        profile={"first_name": "TEST"},
        review_callback=lambda page, trial: None,
        protected_storage_root=tmp_path / "normal",
        pilot_storage_root=tmp_path / "pilot",
    )

    records = store.load(manifest_id=manifest["manifest_id"])
    assert first["recorded"] == 15
    assert second["recorded"] == 0
    assert second["already_recorded"] == 15
    assert len(records) == 15
    assert len({record.trial_id for record in records}) == 15
    assert {record.attempt_no for record in records} == {1, 2, 3}
    assert all(record.manifest_id == manifest["manifest_id"] for record in records)
    assert all(record.git_commit_sha for record in records)
    assert all(record.config_fingerprint for record in records)
    assert all(record.execution_status == "COMPLETED" for record in records)
    assert candidates == original
    assert history == []
    assert len(browser.contexts) == 15
    assert len({id(context) for context in browser.contexts}) == 15
    assert all(context.closed for context in browser.contexts)
    assert all(any("__kenshoSubmitGuard" in script for script in context.init_scripts) for context in browser.contexts)
    assert all(any("__kenshoSubmitGuard" in script for script in context.page.scripts) for context in browser.contexts)
    assert engine.persist_flags == [False] * 15
    assert engine.keep_guard_flags == [True] * 15
    assert "https://" not in store.path.read_text(encoding="utf-8")
    assert "secret@example.com" not in store.path.read_text(encoding="utf-8")


def test_pilot_rejects_non_dry_run_engine_before_creating_context(tmp_path) -> None:
    manifest = create_pilot_manifest(_candidates(), limit_sites=5)
    browser = _Browser()
    engine = _Engine()
    engine.run_mode = "mock"
    with pytest.raises(ValueError, match="dry_run"):
        run_pilot_manifest(
            manifest,
            candidates=_candidates(),
            store=PilotTrialStore(tmp_path / "pilot" / "runs" / "trials.jsonl"),
            browser=browser,
            actual_browser="chromium",
            engine=engine,
            profile={},
            review_callback=lambda page, trial: None,
            protected_storage_root=tmp_path / "normal",
            pilot_storage_root=tmp_path / "pilot",
        )
    assert browser.contexts == []


def test_pilot_halts_manifest_after_submission_guard_trigger(tmp_path) -> None:
    manifest = create_pilot_manifest(_candidates(), limit_sites=5)
    browser = _Browser()
    store = PilotTrialStore(tmp_path / "pilot" / "runs" / "trials.jsonl")
    result = run_pilot_manifest(
        manifest,
        candidates=_candidates(),
        store=store,
        browser=browser,
        actual_browser="chromium",
        engine=_GuardTriggeredEngine(),
        profile={},
        review_callback=lambda page, trial: None,
        protected_storage_root=tmp_path / "normal",
        pilot_storage_root=tmp_path / "pilot",
    )
    assert result["halted"] is True
    assert result["halt_reason"] == "SUBMIT_GUARD_TRIGGERED"
    assert result["recorded"] == 1
    assert len(browser.contexts) == 1
    records = store.load(manifest_id=manifest["manifest_id"])
    assert len(records) == 1
    assert records[0].error_category == "SUBMIT_GUARD_TRIGGERED"


@pytest.mark.parametrize(
    ("engine", "reason"),
    [(_UnsafeArtifactEngine(), "UNSAFE_ARTIFACT_POLICY"), (_SubmitAttemptedEngine(), "UNINTENDED_SUBMISSION")],
)
def test_pilot_halts_on_unsafe_artifact_or_submit_attempt(tmp_path, engine, reason) -> None:
    result = run_pilot_manifest(
        create_pilot_manifest(_candidates(), limit_sites=5),
        candidates=_candidates(),
        store=PilotTrialStore(tmp_path / "pilot" / "runs" / "trials.jsonl"),
        browser=_Browser(),
        actual_browser="chromium",
        engine=engine,
        profile={},
        review_callback=lambda page, trial: None,
        protected_storage_root=tmp_path / "normal",
        pilot_storage_root=tmp_path / "pilot",
    )
    assert result["halted"] is True
    assert result["halt_reason"] == reason
    assert result["recorded"] == 1


def test_pilot_structure_requires_exactly_five_sites_with_three_attempts(tmp_path) -> None:
    candidates = _candidates()
    manifest = create_pilot_manifest(candidates, limit_sites=5)
    store = PilotTrialStore(tmp_path / "pilot" / "runs" / "trials.jsonl")
    browser = _Browser()
    run_pilot_manifest(
        manifest,
        candidates=candidates,
        store=store,
        browser=browser,
        actual_browser="chromium",
        engine=_Engine(),
        profile={},
        review_callback=lambda page, trial: None,
        protected_storage_root=tmp_path / "normal",
        pilot_storage_root=tmp_path / "pilot",
    )
    records = store.load(manifest_id=manifest["manifest_id"])
    assert pilot_structure_summary(records[:-1], manifest["manifest_id"])["structural_pass"] is False
    summary = pilot_structure_summary(records, manifest["manifest_id"])
    assert summary["structural_pass"] is True
    assert set(summary["per_site_trial_counts"].values()) == {3}


def test_pilot_run_cli_rejects_keep_open() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["pilot-run", "--manifest", "pilot.json", "--keep-open"])


def test_trial_report_cli_requires_complete_pilot_structure(tmp_path, monkeypatch) -> None:
    candidates = _candidates()
    manifest = create_pilot_manifest(candidates, limit_sites=5)
    trial_path = tmp_path / "trials.jsonl"
    store = PilotTrialStore(trial_path)
    run_pilot_manifest(
        manifest,
        candidates=candidates,
        store=store,
        browser=_Browser(),
        actual_browser="chromium",
        engine=_Engine(),
        profile={},
        review_callback=lambda page, trial: None,
        protected_storage_root=tmp_path / "normal",
        pilot_storage_root=tmp_path,
    )
    lines = trial_path.read_text(encoding="utf-8").splitlines()
    monkeypatch.setattr("kensho_assistant.main.PILOT_TRIALS_JSONL", trial_path)
    args = Namespace(
        manifest_id=manifest["manifest_id"],
        output=str(tmp_path / "report"),
        require_trials=15,
        require_sites=5,
    )

    trial_path.write_text("\n".join(lines[:14]) + "\n", encoding="utf-8")
    assert cmd_trial_report(args) == 2
    trial_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert cmd_trial_report(args) == 0


def test_pilot_rejects_normal_trial_store_before_browser_access(tmp_path) -> None:
    browser = _Browser()
    with pytest.raises(ValueError, match="pilot_store_required"):
        run_pilot_manifest(
            create_pilot_manifest(_candidates(), limit_sites=5),
            candidates=_candidates(),
            store=TrialStore(tmp_path / "normal-trials.jsonl"),
            browser=browser,
            actual_browser="chromium",
            engine=_Engine(),
            profile={},
            review_callback=lambda page, trial: None,
            protected_storage_root=tmp_path / "normal",
            pilot_storage_root=tmp_path / "pilot",
        )
    assert browser.contexts == []


def test_pilot_keeps_real_candidate_storage_and_history_unchanged(tmp_path) -> None:
    normal = tmp_path / "normal"
    normal.mkdir()
    (normal / "apply_queue.csv").write_text("campaign_id,queue_status,updated_at\nc1,PREPARED,original\n", encoding="utf-8")
    (normal / "history.jsonl").write_text('{"campaign_id":"c1","status":"PREPARED"}\n', encoding="utf-8")
    before = snapshot_storage(normal)
    manifest = create_pilot_manifest(_candidates(), limit_sites=5)
    result = run_pilot_manifest(
        manifest,
        candidates=_candidates(),
        store=PilotTrialStore(tmp_path / "pilot" / "runs" / "trials.jsonl"),
        browser=_Browser(),
        actual_browser="chromium",
        engine=_Engine(),
        profile={},
        review_callback=lambda page, trial: None,
        protected_storage_root=normal,
        pilot_storage_root=tmp_path / "pilot",
    )
    after = snapshot_storage(normal)
    assert compare_storage_snapshots(before, after)["identical"] is True
    assert result["candidate_state_changed"] is False
    assert result["submitted_count_auto"] == 0


def test_pilot_storage_contains_no_fake_pii_or_artifacts(tmp_path) -> None:
    manifest = create_pilot_manifest(_candidates(), limit_sites=5)
    pilot_root = tmp_path / "pilot"
    fake_pii = build_pilot_test_pii()
    result = run_pilot_manifest(
        manifest,
        candidates=_candidates(),
        store=PilotTrialStore(pilot_root / "runs" / "trials.jsonl"),
        browser=_Browser(),
        actual_browser="chromium",
        engine=_Engine(),
        profile=fake_pii,
        review_callback=lambda page, trial: None,
        protected_storage_root=tmp_path / "normal",
        pilot_storage_root=pilot_root,
    )
    scan = scan_for_forbidden_values(pilot_root, fake_pii.values())
    assert scan["clean"] is True
    assert result["pii_persisted"] is False
    assert not list(pilot_root.rglob("*.html"))
    assert not list(pilot_root.rglob("*.png"))
    assert not list(pilot_root.rglob("*.zip"))


def test_pilot_fails_closed_when_storage_snapshot_or_evidence_write_fails(tmp_path, monkeypatch) -> None:
    manifest = create_pilot_manifest(_candidates(), limit_sites=5)
    browser = _Browser()
    monkeypatch.setattr("kensho_assistant.app.pilot_validation.snapshot_storage", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("blocked")))
    with pytest.raises(RuntimeError, match="candidate_state_snapshot_failed"):
        run_pilot_manifest(
            manifest,
            candidates=_candidates(),
            store=PilotTrialStore(tmp_path / "pilot" / "runs" / "trials.jsonl"),
            browser=browser,
            actual_browser="chromium",
            engine=_Engine(),
            profile={},
            review_callback=lambda page, trial: None,
            protected_storage_root=tmp_path / "normal",
            pilot_storage_root=tmp_path / "pilot",
        )
    assert browser.contexts == []


def test_pilot_halts_when_candidate_storage_changes(tmp_path) -> None:
    normal = tmp_path / "normal"
    normal.mkdir()
    state = normal / "apply_queue.csv"
    state.write_text("campaign_id,queue_status\nc1,PREPARED\n", encoding="utf-8")
    browser = _Browser()
    result = run_pilot_manifest(
        create_pilot_manifest(_candidates(), limit_sites=5),
        candidates=_candidates(),
        store=PilotTrialStore(tmp_path / "pilot" / "runs" / "trials.jsonl"),
        browser=browser,
        actual_browser="chromium",
        engine=_Engine(),
        profile={},
        review_callback=lambda page, trial: state.write_text("campaign_id,queue_status\nc1,SUBMITTED\n", encoding="utf-8"),
        protected_storage_root=normal,
        pilot_storage_root=tmp_path / "pilot",
    )
    assert result["halted"] is True
    assert result["halt_reason"] == "CANDIDATE_STATE_CHANGED"
    assert result["candidate_state_changed"] is True
    assert len(browser.contexts) == 1


def test_pilot_evidence_write_failure_is_terminal(tmp_path, monkeypatch) -> None:
    store = PilotTrialStore(tmp_path / "pilot" / "runs" / "trials.jsonl")
    monkeypatch.setattr(store, "append", lambda record: (_ for _ in ()).throw(OSError("read-only")))
    with pytest.raises(RuntimeError, match="pilot_evidence_write_failed"):
        run_pilot_manifest(
            create_pilot_manifest(_candidates(), limit_sites=5),
            candidates=_candidates(),
            store=store,
            browser=_Browser(),
            actual_browser="chromium",
            engine=_Engine(),
            profile={},
            review_callback=lambda page, trial: None,
            protected_storage_root=tmp_path / "normal",
            pilot_storage_root=tmp_path / "pilot",
        )


def test_trial_report_keeps_pilot_and_normal_history_separate(tmp_path, monkeypatch) -> None:
    candidates = _candidates()
    manifest = create_pilot_manifest(candidates, limit_sites=5)
    pilot_path = tmp_path / "pilot" / "runs" / "trials.jsonl"
    run_pilot_manifest(
        manifest,
        candidates=candidates,
        store=PilotTrialStore(pilot_path),
        browser=_Browser(),
        actual_browser="chromium",
        engine=_Engine(),
        profile={},
        review_callback=lambda page, trial: None,
        protected_storage_root=tmp_path / "normal",
        pilot_storage_root=tmp_path / "pilot",
    )
    normal_path = tmp_path / "normal-trials.jsonl"
    normal_path.write_text("", encoding="utf-8")
    monkeypatch.setattr("kensho_assistant.main.PILOT_TRIALS_JSONL", pilot_path)
    monkeypatch.setattr("kensho_assistant.main.REAL_SITE_TRIALS_JSONL", normal_path)
    normal_args = Namespace(manifest_id="", output=str(tmp_path / "normal-report"), require_trials=0, require_sites=0)
    assert cmd_trial_report(normal_args) == 0
    assert json.loads((tmp_path / "normal-report" / "trial_results.json").read_text(encoding="utf-8")) == []
