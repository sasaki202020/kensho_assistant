"""Isolation seam for the fake-profile, single-candidate, non-submit pilot.

Every test runs against temporary "normal" stores so that a regression cannot
touch real data, and the hashes of those stores are compared before/after.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import socket
import string
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from kensho_assistant.app import assisted_session as session
from kensho_assistant.app import paths
from kensho_assistant.app import profile_manager
from kensho_assistant.app.extension_bridge import ALLOWED_PAYLOAD_KEYS, CapabilityBridge


pilot = importlib.import_module("kensho_assistant.app.pilot_nonsubmit")
web = importlib.import_module("kensho_assistant.web.app")
main_module = importlib.import_module("kensho_assistant.main")

TODAY = date(2026, 9, 20)
ORIGIN = "https://www.example-campaign.test"
URL = ORIGIN + "/present/entry"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normal_store_hashes(root: Path) -> dict[str, str]:
    files = [root / "apply_queue.csv", root / "assisted_session" / "session.json"]
    files += sorted((root / "entries").rglob("*"))
    return {str(path.relative_to(root)): _sha256(path) for path in files if path.is_file()}


def _forbidden(name: str, calls: list[str]):
    def _fail(*_args, **_kwargs):
        calls.append(name)
        raise AssertionError(f"{name} must not be called in pilot mode")
    return _fail


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Temporary normal stores + a temporary PILOT_DIR; all module globals restored after."""
    data = tmp_path / "data"
    (data / "entries").mkdir(parents=True)
    (data / "assisted_session").mkdir(parents=True)
    (data / "apply_queue.csv").write_text(
        "campaign_id,queue_status,approved_by_user\nnormal-1,APPROVED,true\n", encoding="utf-8"
    )
    (data / "entries" / "entry_history.jsonl").write_text('{"id":"normal-entry"}\n', encoding="utf-8")
    (data / "entries" / "entry_history.csv").write_text("id\nnormal-entry\n", encoding="utf-8")
    normal_state = data / "assisted_session" / "session.json"
    normal_state.write_text(json.dumps({"session_id": "normal-session", "workflow_state": "IDLE"}), encoding="utf-8")
    pilot_dir = data / "pilot"
    (pilot_dir / "runs").mkdir(parents=True)
    config = tmp_path / "config" / "approved_origins.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"schema_version": 1, "origins": [ORIGIN]}), encoding="utf-8")

    monkeypatch.setattr(paths, "PILOT_DIR", pilot_dir)
    monkeypatch.setattr(session, "ASSISTED_SESSION_DIR", normal_state.parent)
    monkeypatch.setattr(session, "ASSISTED_SESSION_STATE_JSON", normal_state)
    monkeypatch.setattr(session, "REAL_SITE_TRIALS_JSONL", data / "real_site_trials" / "trials.jsonl")
    monkeypatch.setattr(session, "REAL_SITE_TRIAL_STEPS_JSONL", data / "real_site_trials" / "steps.jsonl")
    monkeypatch.setattr(session, "_PILOT_STORAGE", None)
    monkeypatch.setattr(session, "_PILOT_CANDIDATE", None)
    monkeypatch.setattr(session, "_EXTENSION_BRIDGE", CapabilityBridge(ttl_seconds=60))
    monkeypatch.setattr(session, "_EXTENSION_CONTROL_TOKENS", {})
    monkeypatch.setattr(session, "_EXTENSION_PROGRESS_RESPONSES", {})

    # Underlying normal-queue writers: if a regression reaches them, they
    # mutate the temporary normal queue so the hash comparison catches it.
    writes: list[str] = []
    def queue_writer(name):
        def _write(campaign_id, *_args, **_kwargs):
            writes.append(name)
            with (data / "apply_queue.csv").open("a", encoding="utf-8") as handle:
                handle.write(f"{campaign_id},{name},true\n")
            return True
        return _write
    monkeypatch.setattr(session, "_apply_queue_mark_hold", queue_writer("HOLD"))
    monkeypatch.setattr(session, "_apply_queue_mark_skipped", queue_writer("SKIPPED"))
    monkeypatch.setattr(session, "_apply_queue_mark_manual_submitted", queue_writer("SUBMITTED"))

    # Real profile loaders: any call is a failure.
    loader_calls: list[str] = []
    monkeypatch.setattr(profile_manager, "load_profile", _forbidden("profile_manager.load_profile", loader_calls))
    monkeypatch.setattr(web, "load_profile", _forbidden("web.app.load_profile", loader_calls))
    monkeypatch.setattr(main_module, "_load_profile_or_fail", _forbidden("main._load_profile_or_fail", loader_calls))
    monkeypatch.setattr(session, "load_profile", _forbidden("assisted_session.load_profile", loader_calls))
    # The pilot never reads the saved apply queue for candidates.
    queue_reads: list[str] = []
    monkeypatch.setattr(session, "load_apply_queue", _forbidden("load_apply_queue", queue_reads))
    monkeypatch.setattr(session, "approved_queue_rows", _forbidden("approved_queue_rows", queue_reads))

    manifest = {
        "candidate_id": "pilot-candidate-1",
        "url": URL,
        "origin": ORIGIN,
        "campaign_period_start": "2026-09-01",
        "campaign_period_end": "2026-09-30",
        "human_verified_at": "2026-09-19T10:00:00+09:00",
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "tmp": tmp_path, "data": data, "pilot_dir": pilot_dir, "config": config,
        "normal_state": normal_state, "manifest": manifest, "manifest_path": manifest_path,
        "writes": writes, "loader_calls": loader_calls, "queue_reads": queue_reads,
    }


def _free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _run(env, **kwargs):
    kwargs.setdefault("port", _free_port())
    kwargs.setdefault("today", TODAY)
    kwargs.setdefault("approved_origins_path", env["config"])
    return pilot.run_pilot_nonsubmit(env["manifest_path"], **kwargs)


def _get_json(url: str) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


# ---------------------------------------------------------------- storage seam

def test_run_dir_outside_pilot_runs_is_rejected(env):
    for bad in (
        env["tmp"] / "elsewhere",
        env["pilot_dir"],
        env["pilot_dir"] / "runs",
        env["pilot_dir"] / "runs_evil" / "x",
        env["pilot_dir"] / "runs" / ".." / "manifests",
        env["data"] / "assisted_session",
    ):
        with pytest.raises(ValueError):
            session.use_pilot_storage(bad)
    assert session._PILOT_STORAGE is None
    assert session.ASSISTED_SESSION_STATE_JSON == env["normal_state"]


def test_pilot_storage_redirects_state_and_trial_logs(env):
    before = _normal_store_hashes(env["data"])
    run_dir = env["pilot_dir"] / "runs" / "r1"
    handle = session.use_pilot_storage(run_dir)
    assert handle.run_dir == run_dir.resolve()
    assert session.ASSISTED_SESSION_STATE_JSON == run_dir.resolve() / "session.json"
    assert session.REAL_SITE_TRIALS_JSONL.parent == run_dir.resolve()
    assert session.REAL_SITE_TRIAL_STEPS_JSONL.parent == run_dir.resolve()
    session.save_assisted_session_state({"session_id": "pilot"})
    assert (run_dir / "session.json").exists()
    assert session.load_assisted_session_state()["session_id"] == "pilot"
    assert _normal_store_hashes(env["data"]) == before


def test_second_activation_with_different_dir_raises(env):
    first = session.use_pilot_storage(env["pilot_dir"] / "runs" / "a")
    assert session.use_pilot_storage(env["pilot_dir"] / "runs" / "a") is first
    with pytest.raises(session.PilotIsolationError):
        session.use_pilot_storage(env["pilot_dir"] / "runs" / "b")
    assert session.ASSISTED_SESSION_STATE_JSON.parent == first.run_dir


def test_activation_resets_bridge_and_tokens(env):
    old_bridge = session._EXTENSION_BRIDGE
    session.register_extension_control_token("stale-session")
    session._EXTENSION_PROGRESS_RESPONSES[("stale-session", "op")] = "tok"
    session.use_pilot_storage(env["pilot_dir"] / "runs" / "fresh")
    assert session._EXTENSION_BRIDGE is not old_bridge
    assert session._EXTENSION_CONTROL_TOKENS == {}
    assert session._EXTENSION_PROGRESS_RESPONSES == {}
    with pytest.raises(ValueError):
        session.validate_extension_control_token("stale-session", "anything")


def test_hold_skip_manual_submitted_unchanged_when_not_activated(env):
    assert session.mark_hold("normal-1") is True
    assert session.mark_skipped("normal-1") is True
    assert session.mark_manual_submitted("normal-1") is True
    assert env["writes"] == ["HOLD", "SKIPPED", "SUBMITTED"]


def test_hold_skip_manual_submitted_rejected_in_pilot_mode(env):
    before = _normal_store_hashes(env["data"])
    session.use_pilot_storage(env["pilot_dir"] / "runs" / "r1")
    for writer in (session.mark_hold, session.mark_skipped, session.mark_manual_submitted):
        with pytest.raises(session.PilotIsolationError):
            writer("pilot-candidate-1")
    assert env["writes"] == []
    assert _normal_store_hashes(env["data"]) == before


def test_second_candidate_rejected(env):
    session.use_pilot_storage(env["pilot_dir"] / "runs" / "r1")
    state = session.lock_pilot_candidate(
        candidate_id="pilot-candidate-1", url=URL, origin=ORIGIN, period_end=date(2026, 9, 30)
    )
    assert state["active_candidate_id"] == "pilot-candidate-1"
    assert state["workflow_state"] == "CANDIDATE_LOCKED"
    assert state["candidate_ids"] == ["pilot-candidate-1"]
    with pytest.raises(session.PilotIsolationError):
        session.lock_pilot_candidate(
            candidate_id="pilot-candidate-2", url=URL, origin=ORIGIN, period_end=date(2026, 9, 30)
        )
    assert session.load_assisted_session_state()["active_candidate_id"] == "pilot-candidate-1"


def test_lock_requires_active_pilot_storage(env):
    with pytest.raises(session.PilotIsolationError):
        session.lock_pilot_candidate(
            candidate_id="pilot-candidate-1", url=URL, origin=ORIGIN, period_end=date(2026, 9, 30)
        )


def test_pilot_candidate_validation_never_reads_queue(env):
    session.use_pilot_storage(env["pilot_dir"] / "runs" / "r1")
    session.lock_pilot_candidate(
        candidate_id="pilot-candidate-1", url=URL, origin=ORIGIN, period_end=date(2099, 9, 30)
    )
    session.validate_extension_candidate("pilot-candidate-1")
    with pytest.raises(ValueError):
        session.validate_extension_candidate("normal-1")
    with pytest.raises(session.PilotIsolationError):
        session._load_session_candidates("APPROVED,PREPARED", 12)
    assert env["queue_reads"] == []


def test_pilot_candidate_validation_rejects_after_period(env):
    session.use_pilot_storage(env["pilot_dir"] / "runs" / "r1")
    session.lock_pilot_candidate(
        candidate_id="pilot-candidate-1", url=URL, origin=ORIGIN, period_end=date(2000, 1, 1)
    )
    with pytest.raises(ValueError):
        session.validate_extension_candidate("pilot-candidate-1")


def test_end_pilot_session_clears_tokens_and_bridge(env):
    session.use_pilot_storage(env["pilot_dir"] / "runs" / "r1")
    session.register_extension_control_token("s1")
    session._EXTENSION_BRIDGE.start()
    session.end_pilot_session()
    assert session._EXTENSION_CONTROL_TOKENS == {}
    assert session._EXTENSION_PROGRESS_RESPONSES == {}
    assert session.extension_bridge_status()["running"] is False


# ------------------------------------------------------------------- manifest

def _validate(env, **changes):
    data = dict(env["manifest"])
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return pilot.validate_pilot_nonsubmit_manifest(
        data, today=TODAY, approved_origins_path=env["config"]
    )


def test_manifest_accepts_single_valid_candidate(env):
    manifest = _validate(env, expected_fingerprint="fp-123")
    assert manifest.candidate_id == "pilot-candidate-1"
    assert manifest.origin == ORIGIN
    assert manifest.expected_fingerprint == "fp-123"


def test_manifest_approval_is_independent_of_static_origin_config(env):
    env['config'].unlink()
    manifest = _validate(env, url='https://new-campaign.test/form', origin='https://new-campaign.test')
    assert manifest.origin == 'https://new-campaign.test'


@pytest.mark.parametrize(
    "changes",
    [
        {"extra": "x"},
        {"candidates": [{"candidate_id": "a"}, {"candidate_id": "b"}]},
        {"candidate_id": ["a", "b"]},
        {"candidate_id": ""},
        {"candidate_id": None},
        {"url": "http://www.example-campaign.test/present/entry"},
        {"url": URL + "?q=1"},
        {"url": URL + "#frag"},
        {"url": "https://user:pw@www.example-campaign.test/present/entry"},
        {"origin": "https://other.example-campaign.test"},
        {"url": "https://login.yahoo.co.jp/entry", "origin": "https://login.yahoo.co.jp"},
        {"campaign_period_start": "not-a-date"},
        {"campaign_period_end": "2026-08-31"},
        {"campaign_period_start": "2026-09-25"},
        {"human_verified_at": "yesterday"},
        {"human_verified_at": None},
        {"expected_fingerprint": 123},
    ],
)
def test_manifest_rejects_invalid(env, changes):
    with pytest.raises(pilot.PilotManifestError):
        _validate(env, **changes)


def test_manifest_must_be_object(env):
    with pytest.raises(pilot.PilotManifestError):
        pilot.validate_pilot_nonsubmit_manifest([env["manifest"]], today=TODAY, approved_origins_path=env["config"])


# --------------------------------------------------------------- fake profile

def test_fake_profile_embeds_unique_nonce(env):
    first = pilot.build_fake_profile()
    second = pilot.build_fake_profile()
    assert first.nonce != second.nonce
    assert len(first.nonce) >= 10
    assert set(first.nonce) <= set(string.ascii_lowercase + string.digits)
    assert set(first.values) <= ALLOWED_PAYLOAD_KEYS
    assert set(first.undetectable_keys) == {"phone", "postal_code"}
    for key, value in first.values.items():
        assert isinstance(value, str) and value
        if key in first.undetectable_keys:
            assert value.isdigit() and first.nonce not in value
        else:
            assert first.nonce in value, key
    assert first.values["email"] == f"p{first.nonce}@example.com"
    assert "nonce" not in repr(first).lower() or first.nonce not in repr(first)
    first.clear()
    assert first.values == {} and first.nonce == ""


# -------------------------------------------------------------------- runner

def test_port_in_use_refuses_to_start(env):
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    try:
        with pytest.raises(pilot.PilotPortInUseError):
            _run(env, port=blocker.getsockname()[1])
    finally:
        blocker.close()
    assert session._PILOT_STORAGE is None
    assert not any((env["pilot_dir"] / "runs").iterdir())


def test_outside_period_refuses_before_anything(env):
    with pytest.raises(pilot.PilotManifestError):
        _run(env, today=date(2026, 10, 1))
    assert session._PILOT_STORAGE is None


def test_full_run_isolated_from_real_profile_and_normal_stores(env):
    before = _normal_store_hashes(env["data"])
    seen = {}

    def hook(context):
        seen["nonce"] = context.fake_profile.nonce
        seen["values"] = dict(context.fake_profile.values)
        status = _get_json(context.base_url + "/api/session/status")
        seen["status"] = status
        # Only the extension/session endpoints exist in pilot mode.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with pytest.raises(urllib.error.HTTPError) as blocked:
            opener.open(context.base_url + "/", timeout=5)
        seen["dashboard_status"] = blocked.value.code
        # The only profile source reachable from the app is the fake one.
        seen["loaded"] = context.app.state.profile_loader()
        seen["context"] = context
        return {"browser_stage": "TEST_HOOK"}

    result = _run(env, browser_hook=hook)

    assert env["loader_calls"] == []
    assert env["queue_reads"] == []
    assert env["writes"] == []
    assert _normal_store_hashes(env["data"]) == before
    assert result["server_verified"] is True
    assert result["submitted_count_auto"] == 0
    assert result["candidate_id"] == "pilot-candidate-1"
    assert seen["status"]["pilot_run_id"] == result["pilot_run_id"]
    assert seen["status"]["active_candidate_id"] == "pilot-candidate-1"
    assert seen["status"]["workflow_state"] == "CANDIDATE_LOCKED"
    assert seen["dashboard_status"] == 404
    assert seen["loaded"] == seen["values"]

    nonce = seen["nonce"]
    assert nonce and nonce not in json.dumps(result)
    run_dir = Path(result["run_dir"])
    assert run_dir.is_relative_to(env["pilot_dir"] / "runs")
    files = [path for path in run_dir.rglob("*") if path.is_file()]
    assert files, "candidate lock must be persisted in pilot storage"
    for path in env["tmp"].rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert nonce.encode() not in content, path.name
            assert nonce.encode("utf-16-le") not in content, path.name

    # Session end: fake profile references and tokens are gone.
    context = seen["context"]
    assert context.fake_profile.values == {} and context.fake_profile.nonce == ""
    with pytest.raises(Exception):
        context.app.state.profile_loader()
    assert session._EXTENSION_CONTROL_TOKENS == {}
    assert session.extension_bridge_status()["running"] is False


def test_default_hook_is_not_integrated(env):
    result = _run(env)
    assert result["browser_stage"] == "NOT_INTEGRATED"
    assert result["submitted_count_auto"] == 0
    assert env["loader_calls"] == []


def test_pilot_run_id_mismatch_aborts_before_capability(env, monkeypatch):
    real_create_app = pilot.create_app
    monkeypatch.setattr(
        pilot, "create_app",
        lambda **kwargs: real_create_app(**{**kwargs, "pilot_run_id": "impostor-run-id"}),
    )
    issued = []
    monkeypatch.setattr(session, "issue_extension_capability", _forbidden("issue", issued))
    monkeypatch.setattr(web, "issue_extension_capability", _forbidden("issue", issued))
    hook_calls = []
    with pytest.raises(pilot.PilotServerMismatchError):
        _run(env, browser_hook=lambda context: hook_calls.append(context))
    assert hook_calls == [] and issued == []
    assert env["loader_calls"] == []
    assert session.extension_bridge_status()["running"] is False


def test_verify_rejects_status_without_pilot_run_id(env):
    """A normal resident app (no pilot_run_id) on the port must be rejected."""
    with pytest.raises(pilot.PilotServerMismatchError):
        pilot.verify_pilot_status({"session_id": "x"}, "expected")
    with pytest.raises(pilot.PilotServerMismatchError):
        pilot.verify_pilot_status({"pilot_run_id": "other"}, "expected")
    pilot.verify_pilot_status({"pilot_run_id": "expected"}, "expected")


# --------------------------------------------------------- web app pilot mode

def test_normal_app_status_has_no_pilot_run_id(env):
    from fastapi.testclient import TestClient
    with TestClient(web.create_app()) as client:
        body = client.get("/api/session/status", params={"pilot_run_id": "x"}).json()
    assert "pilot_run_id" not in body


def test_pilot_app_requires_fake_loader_and_active_storage(env):
    with pytest.raises(ValueError):
        web.create_app(pilot_run_id="abc", profile_loader=None)
    with pytest.raises(ValueError):
        web.create_app(pilot_run_id="abc", profile_loader=lambda: {})
    session.use_pilot_storage(env["pilot_dir"] / "runs" / "r1")
    app = web.create_app(pilot_run_id="abc", profile_loader=lambda: {})
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        assert client.get("/api/session/status").json()["pilot_run_id"] == "abc"
        assert client.get("/").status_code == 404
        assert client.post("/queue/session/start").status_code == 404


# ------------------------------------------------------------------------ CLI

def test_cli_hardcodes_port_8787(env, monkeypatch):
    calls = []
    monkeypatch.setattr(pilot, "run_pilot_nonsubmit", lambda path, **kwargs: calls.append((path, kwargs)) or {"status": "ok", "submitted_count_auto": 0})
    parser = main_module.build_parser()
    args = parser.parse_args(["pilot-nonsubmit", "--manifest", str(env["manifest_path"])])
    assert not hasattr(args, "port")
    with pytest.raises(SystemExit):
        parser.parse_args(["pilot-nonsubmit", "--manifest", "m.json", "--port", "9999"])
    assert args.func(args) == 0
    assert calls[0][0] == Path(env["manifest_path"])
    assert calls[0][1]["port"] == 8787
    assert pilot.PILOT_WEB_PORT == 8787


def test_blocked_sentinel_attempt_prevents_phase5a_pass_even_if_monitor_misreports_pass():
    evidence = {
        "target_kind": "loopback_fixture",
        "steps": {"fill": "PASS"},
        "monitor": {"status": "PASS", "sentinel_network_leak": 0,
                    "blocked_sentinel_attempts": 0, "pre_send_blocking_enabled": True,
                    "extension_non_loopback_requests": 0, "undetectable_fields_count": 0},
        "residue": {"status": "PASS", "total": 0},
        "normal_store_hashes": {"identical": True},
        "post_fill": {"submitted_count_auto": 0, "auto_submit_detected": 0},
        "submitted_count_auto": 0,
        "invariants_after": {"commit": True},
    }
    assert pilot.phase5a_overall(evidence) == "LOCAL_FIXTURE_NON_SUBMIT_PASS"
    evidence["monitor"]["blocked_sentinel_attempts"] = 1
    assert pilot.phase5a_overall(evidence) == "FAIL"
