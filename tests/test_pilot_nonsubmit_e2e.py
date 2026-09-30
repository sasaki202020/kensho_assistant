"""Phase 5A browser stage of ``pilot-nonsubmit`` against local fixtures only.

Real headless Chromium, the real dedicated extension build (built into a
temporary project root), the real pilot web app on a test-injected loopback
port and the real SentinelNetworkMonitor/residue checker.  Nothing here may
reach the internet: Chromium gets host-resolver rules that make every
non-loopback hostname unresolvable.

The extension hardcodes ``http://127.0.0.1:8787``.  Like
tests/test_assisted_extension_integration.py, the temporary extension source
rewrites that origin to the test port before the dedicated build is produced,
so the build fingerprint check still compares build output with its source.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import socket
import subprocess
import threading
from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from kensho_assistant.app import assisted_session as session
from kensho_assistant.app import paths
from kensho_assistant.app import form_template_store
from kensho_assistant.app import profile_manager
from kensho_assistant.app.extension_bridge import CapabilityBridge
from kensho_assistant.app.pilot_network_monitor import SW_NETWORK_EVENTS_ENV
from kensho_assistant.scripts.build_dedicated_extension import build_dedicated_extension
from kensho_assistant.scripts.run_extension_local_smoke import _build_smoke_extension


pilot = importlib.import_module("kensho_assistant.app.pilot_nonsubmit")
stage = importlib.import_module("kensho_assistant.app.pilot_browser_stage")
web = importlib.import_module("kensho_assistant.web.app")
main_module = importlib.import_module("kensho_assistant.main")

TESTS_ROOT = Path(__file__).resolve().parent
NO_INTERNET = (
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"
)
CAPABILITY_PATH = "/api/session/extension-capability"


class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/pilot_e2e_fixtures/epinard_like_leak.html":
            body = (TESTS_ROOT / "pilot_e2e_fixtures" / "epinard_like.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self) -> None:  # autosave sink; body is read and discarded
        self.server.received_posts += 1
        if self.path == "/sink":
            self.server.received_sink_posts += 1
        length = int(self.headers.get("content-length") or 0)
        if length:
            self.rfile.read(length)
        self.send_response(204)
        self.end_headers()


@contextmanager
def _fixture_server() -> Iterator[str]:
    handler = lambda *a, **k: _Handler(*a, directory=str(TESTS_ROOT), **k)  # noqa: E731
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.received_posts = 0
    server.received_sink_posts = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=pilot-test",
         "-c", "user.email=pilot-test@example.invalid", *args],
        check=True, capture_output=True, text=True,
    )


def _make_clean_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    (root / "tracked.txt").write_text("fixture\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _forbidden(name: str, calls: list[str]):
    def _fail(*_args, **_kwargs):
        calls.append(name)
        raise AssertionError(f"{name} must not be called in pilot mode")
    return _fail


@pytest.fixture
def e2e(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "entries").mkdir(parents=True)
    (data / "assisted_session").mkdir(parents=True)
    queue = data / "apply_queue.csv"
    queue.write_text("campaign_id,queue_status,approved_by_user\nnormal-1,APPROVED,true\n", encoding="utf-8")
    (data / "entries" / "entry_history.jsonl").write_text('{"id":"normal-entry"}\n', encoding="utf-8")
    normal_state = data / "assisted_session" / "session.json"
    normal_state.write_text(json.dumps({"session_id": "normal", "workflow_state": "IDLE"}), encoding="utf-8")
    template_path = data / "form_templates.json"
    template_path.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(paths, "FORM_TEMPLATES_JSON", template_path)
    template_calls: list[str] = []
    for name in ("load_templates", "get_templates_for_origin", "save_template", "list_summaries", "revoke"):
        monkeypatch.setattr(form_template_store, name, _forbidden("form_template_store." + name, template_calls))
    pilot_dir = data / "pilot"
    (pilot_dir / "runs").mkdir(parents=True)

    monkeypatch.setattr(paths, "PILOT_DIR", pilot_dir)
    monkeypatch.setattr(paths, "APPLY_QUEUE_CSV", queue)
    monkeypatch.setattr(paths, "ENTRY_HISTORY_DIR", data / "entries")
    monkeypatch.setattr(session, "ASSISTED_SESSION_DIR", normal_state.parent)
    monkeypatch.setattr(session, "ASSISTED_SESSION_STATE_JSON", normal_state)
    monkeypatch.setattr(session, "REAL_SITE_TRIALS_JSONL", data / "real_site_trials" / "trials.jsonl")
    monkeypatch.setattr(session, "REAL_SITE_TRIAL_STEPS_JSONL", data / "real_site_trials" / "steps.jsonl")
    monkeypatch.setattr(session, "_PILOT_STORAGE", None)
    monkeypatch.setattr(session, "_PILOT_CANDIDATE", None)
    monkeypatch.setattr(session, "_EXTENSION_BRIDGE", CapabilityBridge(ttl_seconds=60))
    monkeypatch.setattr(session, "_EXTENSION_CONTROL_TOKENS", {})
    monkeypatch.setattr(session, "_EXTENSION_PROGRESS_RESPONSES", {})
    monkeypatch.delenv(SW_NETWORK_EVENTS_ENV, raising=False)

    loader_calls: list[str] = []
    monkeypatch.setattr(profile_manager, "load_profile", _forbidden("profile_manager.load_profile", loader_calls))
    monkeypatch.setattr(web, "load_profile", _forbidden("web.app.load_profile", loader_calls))
    monkeypatch.setattr(main_module, "_load_profile_or_fail", _forbidden("main._load_profile_or_fail", loader_calls))
    monkeypatch.setattr(session, "load_profile", _forbidden("assisted_session.load_profile", loader_calls))
    queue_reads: list[str] = []
    monkeypatch.setattr(session, "load_apply_queue", _forbidden("load_apply_queue", queue_reads))
    monkeypatch.setattr(session, "approved_queue_rows", _forbidden("approved_queue_rows", queue_reads))
    writes: list[str] = []
    for name in ("_apply_queue_mark_hold", "_apply_queue_mark_skipped", "_apply_queue_mark_manual_submitted"):
        monkeypatch.setattr(session, name, _forbidden(name, writes))

    # Capture the nonce (tests only) and every API path hit on the pilot app.
    profiles: list[object] = []
    nonces: list[str] = []
    real_build = pilot.build_fake_profile

    def capturing_build():
        profile = real_build()
        profiles.append(profile)
        nonces.append(str(profile.nonce))
        return profile
    monkeypatch.setattr(pilot, "build_fake_profile", capturing_build)
    api_paths: list[str] = []
    capability_keys: list[list[str]] = []
    real_issue = session.issue_extension_capability
    def observed_issue(**kwargs):
        capability_keys.append(list(kwargs["profile_keys"]))
        return real_issue(**kwargs)
    monkeypatch.setattr(web, "issue_extension_capability", observed_issue)
    real_create_app = pilot.create_app

    def observed_create_app(**kwargs):
        app = real_create_app(**kwargs)

        @app.middleware("http")
        async def record(request, call_next):
            api_paths.append(request.url.path)
            return await call_next(request)
        return app
    monkeypatch.setattr(pilot, "create_app", observed_create_app)

    repo = _make_clean_repo(tmp_path / "repo")
    api_port = _free_port()
    with _fixture_server() as (origin, fixture_server):
        project = tmp_path / "project"
        project.mkdir()
        extension_dir = _build_smoke_extension(project, origin)
        manifest_json = extension_dir / "manifest.json"
        ext_manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
        ext_manifest.pop("version_name")  # No fixture-bridge bypass.
        manifest_json.write_text(json.dumps(ext_manifest), encoding="utf-8")
        worker_js = extension_dir / "service-worker.js"
        worker_js.write_text(
            worker_js.read_text(encoding="utf-8").replace(
                "http://127.0.0.1:8787", f"http://127.0.0.1:{api_port}"
            ),
            encoding="utf-8",
        )
        config = project / "config" / "approved_origins.json"
        config.parent.mkdir()
        config.write_text(json.dumps({"schema_version": 1, "origins": [origin]}), encoding="utf-8")
        build_dedicated_extension(
            source_dir=extension_dir, output_dir=project / "build" / "extension",
            approved_origins_path=config,
        )
        today = datetime.now().astimezone().date()

        def write_manifest(page: str, **extra) -> Path:
            payload = {
                "candidate_id": "fixture-candidate-1",
                "url": f"{origin}/pilot_e2e_fixtures/{page}",
                "origin": origin,
                "campaign_period_start": (today - timedelta(days=1)).isoformat(),
                "campaign_period_end": (today + timedelta(days=1)).isoformat(),
                "human_verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                **extra,
            }
            path = tmp_path / f"manifest-{page}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return path

        asked: list[dict] = []

        def confirmer_for(keys: set[str]):
            def confirm(field):
                asked.append(dict(field))
                return field["proposed_profile_key"] in keys
            return confirm

        def run(page: str = "form.html", *, approve=frozenset({"last_name", "first_name", "email"}),
                allow_undetectable: bool = False, quiet: float = 0.5,
                browser_args=(NO_INTERNET,), **manifest_extra):
            config_obj = pilot.Phase5AConfig(
                confirmer=confirmer_for(set(approve)),
                allow_undetectable=allow_undetectable,
                project_root=project,
                git_root=repo,
                runtime_profiles_root=tmp_path / "runtime",
                headless=True,
                quiet_min_seconds=quiet,
                quiet_seconds=0.5,
                browser_args=browser_args,
                allow_loopback_http_for_tests=True,
                output=lambda *_a, **_k: None,
            )
            return pilot.run_pilot_nonsubmit(
                write_manifest(page, **manifest_extra),
                port=api_port,
                approved_origins_path=config,
                phase5a=config_obj,
            )

        yield {
            "tmp": tmp_path, "data": data, "pilot_dir": pilot_dir, "run": run, "asked": asked,
            "nonces": nonces, "profiles": profiles, "api_paths": api_paths,
            "loader_calls": loader_calls, "queue_reads": queue_reads, "writes": writes,
            "normal": [queue, data / "entries" / "entry_history.jsonl", normal_state, template_path],
            "project": project, "repo": repo, "config": config, "write_manifest": write_manifest,
            "api_port": api_port,
            "capability_keys": capability_keys,
            "origin": origin, "fixture_server": fixture_server,
        }
        assert template_calls == []


def _evidence(result) -> dict:
    path = Path(result["result_path"])
    assert path.name == "result.json" and path.parent == Path(result["run_dir"])
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_nonce_nowhere(e2e, result, capfd) -> None:
    assert e2e["nonces"], "fake profile was not built"
    nonce = e2e["nonces"][-1]
    run_dir = Path(result["run_dir"])
    assert run_dir.is_dir() and any(run_dir.iterdir())
    for path in e2e["tmp"].rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert nonce.encode() not in content, path.name
            assert nonce.upper().encode() not in content, path.name
            assert nonce.encode("utf-16-le") not in content, path.name
    captured = capfd.readouterr()
    assert nonce not in captured.out and nonce not in captured.err
    assert nonce not in json.dumps(result)
    # The in-memory fake profile is dropped at the end of the run.
    assert e2e["profiles"][-1].values == {} and e2e["profiles"][-1].nonce == ""


def _assert_common_isolation(e2e) -> None:
    assert e2e["loader_calls"] == []
    assert e2e["queue_reads"] == []
    assert e2e["writes"] == []
    assert session.pilot_storage_active() is not None  # never falls back to normal storage
    assert session._PILOT_CANDIDATE is None  # lock released
    assert session._EXTENSION_CONTROL_TOKENS == {}
    assert session.extension_bridge_status()["running"] is False
    assert not list((e2e["tmp"] / "runtime").iterdir())  # temp Chromium profile removed


# ---------------------------------------------------------------- happy path

def test_happy_path_name_email_only_passes(e2e, capfd):
    before = {str(p): _sha256(p) for p in e2e["normal"]}
    result = e2e["run"]()
    evidence = _evidence(result)

    assert result["overall"] == "LOCAL_FIXTURE_NON_SUBMIT_PASS", (evidence["steps"], evidence["stop_reason"])
    assert evidence["overall"] == "LOCAL_FIXTURE_NON_SUBMIT_PASS"
    assert evidence["target_kind"] == "loopback_fixture"
    assert all(status == "PASS" for status in evidence["steps"].values()), evidence["steps"]
    assert evidence["approved_profile_keys"] == ["email", "first_name", "last_name"]
    by_key = {row["proposed_profile_key"]: row for row in evidence["mapping"]}
    assert by_key["phone"]["approved"] is False
    assert by_key["phone"]["decision"] == "forced_skip_undetectable"
    assert {row["proposed_profile_key"] for row in e2e["asked"]} == {"last_name", "first_name", "email"}
    for row in evidence["mapping"]:
        assert set(row) == {"field_id", "label", "field_type", "input_type", "proposed_profile_key",
                            "human_mappable", "approved", "decision"}

    post = evidence["post_fill"]
    assert post["filled_count"] == 3 and post["target_matched_count"] == 3
    assert post["unrelated_changed_count"] == 0 and post["unapproved_value_count"] == 0
    assert post["navigation_count"] == 0 and post["url_unchanged"] is True
    assert post["submitted_count_auto"] == 0 and post["auto_submit_detected"] == 0
    assert evidence["rollback"]["rollback_complete"] is True
    assert evidence["rollback"]["restored_matches_snapshot"] is True
    assert evidence["session_clear"]["sensitive_extension_keys_remaining"] == 0

    monitor = evidence["monitor"]
    assert monitor["status"] == "PASS", monitor["unverified_reasons"]
    assert monitor["sentinel_network_leak"] == 0
    assert monitor["extension_non_loopback_requests"] == 0
    assert monitor["non_loopback_requests_total"] == 0
    assert monitor["sw_network_events_observable"] is True
    assert evidence["residue"]["status"] == "PASS" and evidence["residue"]["total"] == 0
    assert evidence["normal_store_hashes"]["identical"] is True
    assert evidence["submitted_count_auto"] == 0
    assert evidence["commit"] and len(evidence["extension_build_sha256"]) == 64
    assert len(evidence["config_sha256"]) == 64 and len(evidence["form_fingerprint"]) > 0
    assert all(evidence["invariants_after"].values())
    assert CAPABILITY_PATH in e2e["api_paths"]

    assert {str(p): _sha256(p) for p in e2e["normal"]} == before
    _assert_common_isolation(e2e)
    _assert_nonce_nowhere(e2e, result, capfd)


@pytest.mark.parametrize("mode", ["opaque", "leak"])
def test_epinard_like_approved_subset_is_restored_and_egress_blocked(e2e, capfd, mode):
    before = {str(p): _sha256(p) for p in e2e["normal"]}
    # Only this controlled hostname maps to the loopback fixture. All other
    # non-loopback names remain unresolvable and no Internet host is contacted.
    resolver = (
        "--host-resolver-rules=MAP external.test 127.0.0.1, "
        "MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"
    )
    result = e2e["run"](
        "epinard_like_leak.html" if mode == "leak" else "epinard_like.html",
        browser_args=(resolver,), quiet=1.0,
        approve=frozenset({"full_name", "full_name_kana", "email", "street"}),
    )
    evidence = _evidence(result)
    assert evidence["approved_profile_keys"] == [
        "email", "first_name", "first_name_kana", "last_name", "last_name_kana", "street"
    ]
    assert e2e["capability_keys"] == [[
        "last_name", "first_name", "last_name_kana", "first_name_kana", "street", "email"
    ]]
    assert evidence["steps"]["mapping_confirmed"] == "PASS", evidence
    assert evidence["steps"]["fill"] == "PASS", (evidence["steps"], evidence["failure_reasons"], evidence["monitor"])
    assert evidence["post_fill"]["filled_count"] == 4
    assert evidence["post_fill"]["unrelated_changed_count"] == 0
    assert evidence["post_fill"]["unapproved_value_count"] == 0
    assert evidence["post_fill"]["submitted_count_auto"] == 0
    assert evidence["steps"]["rollback"] == "PASS"
    assert evidence["steps"]["session_clear"] == "PASS"
    assert evidence["residue"]["status"] == "PASS" and evidence["residue"]["total"] == 0
    monitor = evidence["monitor"]
    assert monitor["pre_send_blocking_enabled"] is True
    assert monitor["blocked_sentinel_attempts"] + monitor["blocked_opaque_requests"] > 0
    assert monitor["sentinel_network_leak"] in (0, "UNVERIFIED")
    assert e2e["fixture_server"].received_sink_posts == 0
    assert monitor["unload_network_blocking_enabled"] is True
    assert evidence["overall"] == ("FAIL" if monitor["blocked_sentinel_attempts"] else "UNVERIFIED")
    assert {str(p): _sha256(p) for p in e2e["normal"]} == before
    _assert_common_isolation(e2e)
    _assert_nonce_nowhere(e2e, result, capfd)


def test_stopped_extension_worker_during_cleanup_does_not_skip_later_steps(e2e, capfd, monkeypatch):
    evaluate_worker = stage.evaluate_worker
    def stopped_during_clear(worker, expression, arg=None, **kwargs):
        if "chrome.storage.session.remove(keys)" in expression:
            raise TimeoutError("stopped_worker")
        return evaluate_worker(worker, expression, arg, **kwargs)
    monkeypatch.setattr(stage, "evaluate_worker", stopped_during_clear)
    result = e2e["run"]()
    evidence = _evidence(result)
    assert evidence["steps"]["fill"] == "PASS"
    assert evidence["steps"]["rollback"] == "PASS"
    assert evidence["steps"]["session_clear"] == "FAIL"
    assert evidence["session_clear"]["end_pilot_session"] is True
    assert evidence["steps"]["quiet_period"] == "PASS"
    assert evidence["steps"]["lock_release"] == "PASS"
    assert evidence["steps"]["context_close"] == "PASS"
    _assert_common_isolation(e2e)
    _assert_nonce_nowhere(e2e, result, capfd)


def test_mapping_not_approved_fills_nothing(e2e, capfd):
    result = e2e["run"](approve=frozenset())
    evidence = _evidence(result)
    assert result["overall"] != "LOCAL_FIXTURE_NON_SUBMIT_PASS"
    assert evidence["overall"] == "STOPPED"
    assert evidence["stop_reason"] == "MAPPING_NOT_APPROVED"
    assert evidence["steps"]["fill"] == "NOT_RUN"
    assert evidence["approved_profile_keys"] == []
    assert all(row["approved"] is False for row in evidence["mapping"])
    assert CAPABILITY_PATH not in e2e["api_paths"]
    assert evidence["monitor"]["status"] != "PASS"
    _assert_common_isolation(e2e)
    _assert_nonce_nowhere(e2e, result, capfd)


def test_phone_approved_without_flag_is_refused(e2e, capfd):
    result = e2e["run"](approve=frozenset({"phone", "email"}))
    evidence = _evidence(result)
    by_key = {row["proposed_profile_key"]: row for row in evidence["mapping"]}
    assert by_key["phone"]["approved"] is False
    assert by_key["phone"]["decision"] == "forced_skip_undetectable"
    assert "phone" not in {row["proposed_profile_key"] for row in e2e["asked"]}
    assert "phone" not in evidence["approved_profile_keys"]
    assert evidence["monitor"]["undetectable_fields_count"] == 0
    _assert_common_isolation(e2e)
    _assert_nonce_nowhere(e2e, result, capfd)


def test_phone_with_allow_undetectable_is_unverified_never_pass(e2e, capfd):
    result = e2e["run"](approve=frozenset({"phone", "email"}), allow_undetectable=True)
    evidence = _evidence(result)
    assert evidence["approved_profile_keys"] == ["email", "phone"]
    assert evidence["allow_undetectable"] is True
    assert evidence["post_fill"]["filled_count"] == 2
    assert evidence["monitor"]["undetectable_fields_count"] == 1
    assert evidence["monitor"]["status"] == "UNVERIFIED"
    assert evidence["overall"] == "UNVERIFIED"
    assert result["overall"] == "UNVERIFIED"
    _assert_common_isolation(e2e)
    _assert_nonce_nowhere(e2e, result, capfd)


def test_autosave_after_input_is_leak_and_cleanup_still_runs(e2e, capfd):
    result = e2e["run"]("autosave_form.html", quiet=5.0)
    evidence = _evidence(result)
    assert evidence["monitor"]["sentinel_network_leak"] >= 1
    assert evidence["monitor"]["requests_after_clear"] >= 1
    assert evidence["monitor"]["status"] == "FAIL"
    assert evidence["overall"] == "FAIL"
    assert evidence["steps"]["rollback"] == "PASS"
    assert evidence["steps"]["session_clear"] == "PASS"
    assert evidence["rollback"]["rollback_complete"] is True
    _assert_common_isolation(e2e)
    _assert_nonce_nowhere(e2e, result, capfd)


@pytest.mark.parametrize(
    "page, reason",
    [
        ("sw_form.html", "page_service_worker_registered"),
        ("iframe_form.html", "cross_origin_iframe_present"),
    ],
)
def test_prefill_blockers_stop_before_capability(e2e, capfd, page, reason):
    result = e2e["run"](page)
    evidence = _evidence(result)
    assert evidence["stop_reason"] == "PREFILL_BLOCKED"
    assert reason in evidence["prefill_blocking_reasons"]
    assert evidence["overall"] == "STOPPED"
    assert evidence["steps"]["mapping_human_confirmation"] == "NOT_RUN"
    assert e2e["asked"] == []
    assert CAPABILITY_PATH not in e2e["api_paths"]
    _assert_common_isolation(e2e)
    _assert_nonce_nowhere(e2e, result, capfd)


def test_expected_fingerprint_mismatch_stops_form_changed(e2e, capfd):
    result = e2e["run"](expected_fingerprint="0" * 64)
    evidence = _evidence(result)
    assert evidence["stop_reason"] == "FORM_CHANGED_REVIEW_REQUIRED"
    assert evidence["overall"] == "STOPPED"
    assert evidence["steps"]["fill"] == "NOT_RUN"
    assert e2e["asked"] == []
    assert CAPABILITY_PATH not in e2e["api_paths"]
    _assert_common_isolation(e2e)
    _assert_nonce_nowhere(e2e, result, capfd)


def test_without_service_worker_network_events_prefill_is_blocked(e2e, capfd, monkeypatch):
    monkeypatch.setattr(stage, "service_worker_network_events", nullcontext)
    result = e2e["run"]()
    evidence = _evidence(result)
    assert evidence["stop_reason"] == "PREFILL_BLOCKED"
    assert "service_worker_network_unobservable" in evidence["prefill_blocking_reasons"]
    assert evidence["monitor"]["extension_non_loopback_requests"] == "UNVERIFIED"
    assert CAPABILITY_PATH not in e2e["api_paths"]
    _assert_common_isolation(e2e)
    _assert_nonce_nowhere(e2e, result, capfd)


# ------------------------------------------------------------ preconditions

def _refuse(e2e, **changes):
    config_obj = pilot.Phase5AConfig(
        confirmer=lambda _f: True, project_root=e2e["project"], git_root=e2e["repo"],
        runtime_profiles_root=e2e["tmp"] / "runtime", headless=True,
        allow_loopback_http_for_tests=True, output=lambda *_a, **_k: None, **changes,
    )
    with pytest.raises(pilot.PilotPreconditionError):
        pilot.run_pilot_nonsubmit(
            e2e["write_manifest"]("form.html"), port=e2e["api_port"],
            approved_origins_path=e2e["config"], phase5a=config_obj,
        )
    assert session.pilot_storage_active() is None
    assert not any((e2e["pilot_dir"] / "runs").iterdir())
    # The port was never bound.
    probe = socket.socket()
    probe.bind(("127.0.0.1", e2e["api_port"]))
    probe.close()


def test_dirty_worktree_refuses_before_binding(e2e):
    (e2e["repo"] / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    _refuse(e2e)


def test_stale_extension_build_refuses_before_binding(e2e):
    target = e2e["project"] / "build" / "extension" / "content" / "overlay.js"
    target.write_text(target.read_text(encoding="utf-8") + "\n// tampered\n", encoding="utf-8")
    _refuse(e2e)


def test_http_manifest_is_rejected_without_test_flag(e2e):
    config_obj = pilot.Phase5AConfig(
        confirmer=lambda _f: True, project_root=e2e["project"], git_root=e2e["repo"],
        output=lambda *_a, **_k: None,
    )
    with pytest.raises(pilot.PilotManifestError):
        pilot.run_pilot_nonsubmit(
            e2e["write_manifest"]("form.html"), port=e2e["api_port"],
            approved_origins_path=e2e["config"], phase5a=config_obj,
        )
    assert session.pilot_storage_active() is None


def test_cli_confirmer_is_per_field_default_no(monkeypatch, capsys):
    answers = iter(["", "y", "Y", "yes", "all"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    field = {"index": 1, "total": 5, "label": "姓", "field_type": "last_name",
             "input_type": "text", "proposed_profile_key": "last_name"}
    decisions = [stage.interactive_mapping_confirmer(field) for _ in range(5)]
    assert decisions == [False, True, True, False, False]

    def eof(_prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    assert stage.interactive_mapping_confirmer(field) is False


def test_cli_passes_allow_undetectable_and_keeps_port(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        pilot, "run_pilot_nonsubmit",
        lambda path, **kwargs: calls.append((path, kwargs)) or {"status": "ok", "overall": "STOPPED", "submitted_count_auto": 0},
    )
    parser = main_module.build_parser()
    args = parser.parse_args(["pilot-nonsubmit", "--manifest", "m.json", "--allow-undetectable"])
    assert args.func(args) == 3  # completed, but not a PASS
    kwargs = calls[0][1]
    assert kwargs["port"] == 8787
    config_obj = kwargs["phase5a"]
    assert config_obj.allow_undetectable is True
    assert config_obj.allow_loopback_http_for_tests is False
    assert config_obj.browser_args == ()
    assert config_obj.confirmer is stage.interactive_mapping_confirmer
    args = parser.parse_args(["pilot-nonsubmit", "--manifest", "m.json"])
    args.func(args)
    assert calls[1][1]["phase5a"].allow_undetectable is False


# ------------------------------------------------- pilot mapping seam (unit)

def test_confirm_pilot_mapping_requires_locked_pilot_candidate(e2e):
    with pytest.raises(session.PilotIsolationError):
        session.confirm_pilot_mapping(
            None, None, extension_id="x" * 32, expected_url="http://127.0.0.1:1/f",
            approved_profile_keys=["email"],
        )
    assert session._EXTENSION_CONTROL_TOKENS == {}


def test_confirm_pilot_mapping_rejects_keys_not_human_approved(e2e, monkeypatch):
    url = "http://127.0.0.1:1/pilot_e2e_fixtures/form.html"
    session.use_pilot_storage(e2e["pilot_dir"] / "runs" / "unit")
    session.lock_pilot_candidate(
        candidate_id="unit-1", url=url, origin="http://127.0.0.1:1",
        period_end=date.today() + timedelta(days=1),
    )
    # The extension template binds more keys than the human approved.
    monkeypatch.setattr(
        session, "confirmed_extension_mapping",
        lambda *_a, **_k: {"tab_id": 1, "document_id": "d", "fingerprint": "fp",
                           "profile_keys": ["email", "phone"]},
    )
    provisioned = []
    monkeypatch.setattr(session, "provision_extension_control_token", lambda *a, **k: provisioned.append(1))
    with pytest.raises(session.PilotIsolationError):
        session.confirm_pilot_mapping(
            None, None, extension_id="x" * 32, expected_url=url, approved_profile_keys=["email"],
        )
    with pytest.raises(session.PilotIsolationError):
        session.confirm_pilot_mapping(
            None, None, extension_id="x" * 32, expected_url=url,
            approved_profile_keys=["email", "password"],
        )
    state = session.load_assisted_session_state()
    assert state["workflow_state"] == "CANDIDATE_LOCKED"
    assert "confirmed_profile_keys" not in state
    assert provisioned == [] and session._EXTENSION_CONTROL_TOKENS == {}
    released = session.release_pilot_candidate()
    assert released["workflow_state"] == "FAILED_SAFE"
    assert released["active_candidate_id"] == ""
    assert session._PILOT_CANDIDATE is None
    assert e2e["queue_reads"] == [] and e2e["writes"] == []
