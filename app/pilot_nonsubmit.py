"""Fake-profile, single-candidate, non-submit pilot runner (Phase 5A, step 1).

Safety contract:

- The only profile source is an in-memory fake profile with a per-run nonce.
  The nonce is never written to disk or logs; it is exposed only in memory to
  the browser/monitor stage through ``PilotRunContext``.
- The assisted session is switched to pilot storage under
  ``PILOT_DIR/runs/<run>`` before anything is locked; normal queue/history
  writers refuse and the saved apply queue is never read.
- The extension talks to ``127.0.0.1:8787``.  The runner binds that port
  exclusively first; if a resident app owns it, the pilot refuses to start.
  It then verifies that the server answering on the port is this run's pilot
  app (``pilot_run_id``) before any capability could be issued.
- ``run_pilot_nonsubmit(..., phase5a=Phase5AConfig(...))`` (the CLI path)
  first verifies a clean git worktree and the dedicated extension build
  against its source, then runs the browser stage in
  ``app/pilot_browser_stage.py`` and writes a value-free
  ``data/pilot/runs/<run>/result.json``.  Without ``phase5a`` the legacy
  default hook ``pilot_browser_and_monitor_stage`` stops before the browser.
  No final-submit path exists here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import socket
import string
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Mapping

from . import assisted_session
from .origin_policy import policy_fingerprint
from . import paths
from .extension_bridge import ALLOWED_PAYLOAD_KEYS
from ..web.app import create_app


PILOT_WEB_HOST = "127.0.0.1"
PILOT_WEB_PORT = 8787  # hardcoded in the Chrome extension service worker

MANIFEST_REQUIRED_KEYS = frozenset(
    {
        "candidate_id",
        "campaign_period_start",
        "campaign_period_end",
        "human_verified_at",
    }
)
MANIFEST_OPTIONAL_KEYS = frozenset({"expected_fingerprint", "url", "origin", "knshow_link"})
_CANDIDATE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_NONCE_ALPHABET = string.ascii_lowercase + string.digits
NONCE_LENGTH = 16

# Keys that carry the per-run nonce (uniquely detectable in traffic/storage).
_NONCE_FIELDS = {
    "last_name": "ln",
    "first_name": "fn",
    "last_name_kana": "lk",
    "first_name_kana": "fk",
    "city": "ct",
    "street": "st",
    "building": "bd",
}
# Digits-only keys: fixed, obviously fake values that cannot carry the nonce.
_UNDETECTABLE_FIELDS = {
    "phone": "09000000000",
    "postal_code": "0000000",
}


class PilotError(RuntimeError):
    """Base class for pilot runner refusals."""


class PilotManifestError(PilotError, ValueError):
    """The pilot manifest is invalid or out of its campaign period."""


class PilotPortInUseError(PilotError):
    """The extension port is already bound (e.g. the resident web app)."""


class PilotServerMismatchError(PilotError):
    """The server answering on the pilot port is not this run's pilot app."""


class PilotPreconditionError(PilotError):
    """Phase 5A preconditions (clean commit, verified build) are not met."""


@dataclass(frozen=True)
class PilotNonsubmitManifest:
    candidate_id: str
    url: str
    origin: str
    campaign_period_start: date
    campaign_period_end: date
    human_verified_at: str
    expected_fingerprint: str = ""
    knshow_link: str = ""


@dataclass
class FakeProfile:
    """In-memory fake profile. ``repr`` never shows the nonce or values."""

    nonce: str = field(repr=False)
    values: dict[str, str] = field(repr=False)
    undetectable_keys: tuple[str, ...] = ()

    def clear(self) -> None:
        self.values.clear()
        self.values = {}
        self.nonce = ""


@dataclass
class PilotRunContext:
    """Handed to the browser/monitor stage. Holds the nonce in memory only."""

    pilot_run_id: str
    base_url: str
    manifest: PilotNonsubmitManifest
    storage: assisted_session.PilotStorageHandle
    fake_profile: FakeProfile = field(repr=False)
    app: object = field(repr=False)


# ------------------------------------------------------------------ manifest

def _parse_date(value: object, name: str) -> date:
    if not isinstance(value, str):
        raise PilotManifestError(f"manifest_invalid_{name}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise PilotManifestError(f"manifest_invalid_{name}") from None


def _origin_of(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    default_port = 443 if parsed.scheme == "https" else 80
    port = f":{parsed.port}" if parsed.port and parsed.port != default_port else ""
    return f"{parsed.scheme}://{host}{port}"


def validate_pilot_nonsubmit_manifest(
    data: object,
    *,
    today: date | None = None,
    approved_origins_path: Path | None = None,
    allow_loopback_http: bool = False,
    knshow_url_classifier_for_tests: Callable[[str], bool] | None = None,
) -> PilotNonsubmitManifest:
    """Strictly validate a single-candidate manifest. Error messages carry no values.

    ``allow_loopback_http`` is an in-process test seam for local fixtures: it
    admits loopback ``http://127.0.0.1`` / ``http://localhost`` only.  The CLI never sets it.
    """
    from .origin_policy import is_origin_allowed

    if not isinstance(data, dict):
        raise PilotManifestError("manifest_not_object")
    keys = set(data)
    unknown = keys - MANIFEST_REQUIRED_KEYS - MANIFEST_OPTIONAL_KEYS
    if unknown:
        raise PilotManifestError("manifest_unknown_keys:" + ",".join(sorted(unknown)))
    missing = MANIFEST_REQUIRED_KEYS - keys
    if missing:
        raise PilotManifestError("manifest_missing_keys:" + ",".join(sorted(missing)))

    candidate_id = data["candidate_id"]
    if not isinstance(candidate_id, str) or not _CANDIDATE_ID_RE.fullmatch(candidate_id):
        raise PilotManifestError("manifest_invalid_candidate_id")

    if ("url" in keys) == ("knshow_link" in keys):
        raise PilotManifestError("manifest_target_exclusive")
    human_navigation = "knshow_link" in keys
    if human_navigation and "origin" in keys:
        raise PilotManifestError("manifest_origin_with_knshow_link")
    if not human_navigation and "origin" not in keys:
        raise PilotManifestError("manifest_missing_keys:origin")
    url = data["knshow_link"] if human_navigation else data["url"]
    if not isinstance(url, str) or "?" in url or "#" in url:
        raise PilotManifestError("manifest_invalid_url")
    try:
        parsed = urllib.parse.urlsplit(url)
        parsed.port  # noqa: B018 - raises on an invalid port
    except ValueError:
        raise PilotManifestError("manifest_invalid_url") from None
    loopback_fixture = (
        allow_loopback_http is True
        and parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost"}
    )
    if (
        (parsed.scheme != "https" and not loopback_fixture)
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or any(ch.isspace() for ch in url)
    ):
        raise PilotManifestError("manifest_invalid_url")
    if human_navigation:
        fixture_source = (loopback_fixture and knshow_url_classifier_for_tests is not None
                          and knshow_url_classifier_for_tests(url))
        if (not fixture_source and (parsed.hostname != "www.knshow.com" or parsed.port not in {None, 443})
                or not re.fullmatch(r"/(?:rd|detail)/[^/?#]+(?:/[^/?#]+)*/?", parsed.path)
                or parsed.username is not None or parsed.password is not None
                or any(segment in {".", ".."} for segment in parsed.path.split("/"))
                or "\\" in url or any(ord(ch) < 32 for ch in url)):
            raise PilotManifestError("manifest_invalid_knshow_link")
        origin = ""
        knshow_link, url = url, ""
    else:
        knshow_link = ""
        origin = data["origin"]
        if not isinstance(origin, str) or origin != _origin_of(url):
            raise PilotManifestError("manifest_origin_mismatch")
        if not is_origin_allowed(origin, allow_loopback_http=allow_loopback_http)[0]:
            raise PilotManifestError("manifest_origin_not_approved")

    start = _parse_date(data["campaign_period_start"], "campaign_period_start")
    end = _parse_date(data["campaign_period_end"], "campaign_period_end")
    if start > end:
        raise PilotManifestError("manifest_invalid_campaign_period")
    current = today or datetime.now().astimezone().date()
    if not start <= current <= end:
        raise PilotManifestError("manifest_outside_campaign_period")

    verified = data["human_verified_at"]
    if not isinstance(verified, str):
        raise PilotManifestError("manifest_invalid_human_verified_at")
    try:
        datetime.fromisoformat(verified)
    except ValueError:
        raise PilotManifestError("manifest_invalid_human_verified_at") from None

    fingerprint = data.get("expected_fingerprint", "")
    if "expected_fingerprint" in data and (not isinstance(fingerprint, str) or not fingerprint.strip()):
        raise PilotManifestError("manifest_invalid_expected_fingerprint")

    return PilotNonsubmitManifest(
        candidate_id=candidate_id,
        url=url,
        origin=origin,
        campaign_period_start=start,
        campaign_period_end=end,
        human_verified_at=verified,
        expected_fingerprint=str(fingerprint or "").strip(),
        knshow_link=knshow_link,
    )


def load_pilot_nonsubmit_manifest(
    path: Path,
    *,
    today: date | None = None,
    approved_origins_path: Path | None = None,
    allow_loopback_http: bool = False,
    knshow_url_classifier_for_tests: Callable[[str], bool] | None = None,
) -> PilotNonsubmitManifest:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise PilotManifestError("manifest_unreadable") from None
    return validate_pilot_nonsubmit_manifest(
        data,
        today=today,
        approved_origins_path=approved_origins_path,
        allow_loopback_http=allow_loopback_http,
        knshow_url_classifier_for_tests=knshow_url_classifier_for_tests,
    )


# -------------------------------------------------------------- fake profile

def build_fake_profile() -> FakeProfile:
    """Build a fake profile whose every string field contains a fresh nonce."""
    nonce = "".join(secrets.choice(_NONCE_ALPHABET) for _ in range(NONCE_LENGTH))
    values = {key: f"{tag}{nonce}" for key, tag in _NONCE_FIELDS.items()}
    values["email"] = f"p{nonce}@example.com"
    values.update(_UNDETECTABLE_FIELDS)
    if not set(values) <= ALLOWED_PAYLOAD_KEYS:  # pragma: no cover - static guard
        raise PilotError("fake_profile_key_not_allowed")
    return FakeProfile(
        nonce=nonce,
        values=values,
        undetectable_keys=tuple(sorted(_UNDETECTABLE_FIELDS)),
    )


# --------------------------------------------------------------- port/server

def reserve_pilot_socket(host: str = PILOT_WEB_HOST, port: int = PILOT_WEB_PORT) -> socket.socket:
    """Bind ``host:port`` exclusively or refuse; never share the port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((host, int(port)))
        sock.listen(64)
    except OSError:
        sock.close()
        raise PilotPortInUseError(
            f"{host}:{port} is already in use. Stop the resident web app before the pilot."
        ) from None
    return sock


@contextmanager
def _serve(app, sock: socket.socket) -> Iterator[str]:
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, name="kensho-pilot-web", daemon=True
    )
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not server.started:
            raise PilotError("pilot_server_not_started")
        host, port = sock.getsockname()[:2]
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def fetch_session_status(base_url: str, *, timeout: float = 5.0) -> dict:
    # Never route loopback traffic through a system proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base_url + "/api/session/status", timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise PilotServerMismatchError("pilot_status_invalid")
    return payload


def verify_pilot_status(
    status: Mapping[str, object], expected_run_id: str, candidate_id: str | None = None
) -> None:
    supplied = status.get("pilot_run_id")
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, str(expected_run_id)):
        raise PilotServerMismatchError("pilot_run_id_mismatch")
    if candidate_id is not None and status.get("active_candidate_id") != candidate_id:
        raise PilotServerMismatchError("pilot_candidate_mismatch")


# ------------------------------------------------------------ browser stage

def pilot_browser_and_monitor_stage(context: PilotRunContext) -> dict[str, object]:
    """Integration point for dedicated-browser launch + network monitor.

    Not integrated yet (``app/pilot_network_monitor.py`` is built separately).
    It must return only non-PII fields; only ``browser_stage`` is kept.
    """
    return {"browser_stage": "NOT_INTEGRATED"}


def _cleared_profile_loader() -> Mapping[str, object]:
    raise assisted_session.PilotIsolationError("fake_profile_cleared")


# ------------------------------------------------------------------ Phase 5A

_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
PASS_LABELS = {
    "real_site": "REAL_SITE_NON_SUBMIT_PASS",
    "loopback_fixture": "LOCAL_FIXTURE_NON_SUBMIT_PASS",
}


@dataclass(frozen=True)
class Phase5AConfig:
    """Browser-stage settings for one Phase 5A run.

    The CLI sets only ``confirmer`` (interactive, per field) and
    ``allow_undetectable``.  ``browser_args``, ``allow_loopback_http_for_tests``,
    ``git_root``/``project_root`` overrides and short quiet periods are
    in-process test seams for local fixtures.
    """

    confirmer: Callable[[Mapping[str, object]], bool] | None = None
    allow_undetectable: bool = False
    project_root: Path = paths.PACKAGE_ROOT
    git_root: Path | None = None
    runtime_profiles_root: Path | None = None
    headless: bool = False
    quiet_min_seconds: float = 30.0
    quiet_seconds: float = 2.0
    browser_args: tuple[str, ...] = ()
    allow_loopback_http_for_tests: bool = False
    knshow_url_classifier_for_tests: Callable[[str], bool] | None = None
    human_navigation_timeout_for_tests: float | None = None
    output: Callable[..., None] | None = None


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        raise PilotPreconditionError("precondition_file_unreadable") from None


def git_worktree_state(root: Path) -> dict[str, object]:
    """HEAD and cleanliness (tracked and untracked, ignoring .gitignore'd files)."""

    def git(*args: str) -> str:
        try:
            done = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True, text=True, timeout=60, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            raise PilotPreconditionError("git_unavailable") from None
        if done.returncode != 0:
            raise PilotPreconditionError("git_state_unreadable")
        return done.stdout

    head = git("rev-parse", "HEAD").strip()
    if not _COMMIT_RE.fullmatch(head):
        raise PilotPreconditionError("git_head_unreadable")
    dirty = bool(git("status", "--porcelain", "--untracked-files=all").strip())
    return {"commit": head, "worktree_clean": not dirty}


def verify_phase5a_preconditions(
    config: Phase5AConfig, manifest_path: Path, approved_origins_path: Path
) -> dict[str, object]:
    """Clean worktree + dedicated build verified against its source (no rebuild)."""
    from .browser_manager import verify_dedicated_extension_build

    git_state = git_worktree_state(Path(config.git_root or config.project_root))
    if not git_state["worktree_clean"]:
        raise PilotPreconditionError("worktree_not_clean")
    try:
        verified = verify_dedicated_extension_build(
            project_root=Path(config.project_root),
            approved_origins_path=Path(approved_origins_path),
        )
    except Exception:
        raise PilotPreconditionError("dedicated_extension_build_unverified") from None
    return {
        "commit": git_state["commit"],
        "worktree_clean": True,
        "extension_build_sha256": str(verified["build_sha256"]),
        "extension_version": str(verified["version"]),
        "config_sha256": policy_fingerprint(),
        "manifest_sha256": _file_sha256(manifest_path),
    }


def _post_run_invariants(
    config: Phase5AConfig, pre: Mapping[str, object], approved_origins_path: Path, manifest_path: Path
) -> dict[str, bool]:
    from .browser_manager import verify_dedicated_extension_build

    result = {
        "commit_unchanged": False,
        "worktree_clean": False,
        "extension_build_unchanged": False,
        "config_unchanged": False,
        "manifest_unchanged": False,
    }
    try:
        git_state = git_worktree_state(Path(config.git_root or config.project_root))
        result["commit_unchanged"] = git_state["commit"] == pre["commit"]
        result["worktree_clean"] = bool(git_state["worktree_clean"])
    except PilotError:
        pass
    try:
        verified = verify_dedicated_extension_build(
            project_root=Path(config.project_root),
            approved_origins_path=Path(approved_origins_path),
        )
        result["extension_build_unchanged"] = verified["build_sha256"] == pre["extension_build_sha256"]
    except Exception:
        pass
    try:
        result["config_unchanged"] = policy_fingerprint() == pre["config_sha256"]
        result["manifest_unchanged"] = _file_sha256(manifest_path) == pre["manifest_sha256"]
    except (PilotError, ValueError, OSError):
        pass
    return result


def normal_store_paths() -> list[Path]:
    """Normal (non-pilot) stores; read before the pilot storage switch."""
    return [
        Path(paths.APPLY_QUEUE_CSV),
        Path(paths.ENTRY_HISTORY_DIR),
        Path(assisted_session.ASSISTED_SESSION_STATE_JSON),
        Path(assisted_session.REAL_SITE_TRIALS_JSONL),
        Path(assisted_session.REAL_SITE_TRIAL_STEPS_JSONL),
    ]


def phase5a_overall(evidence: Mapping[str, object]) -> str:
    """PASS only when every metric is exactly PASS/0; UNVERIFIED never passes."""
    steps = dict(evidence.get("steps", {}) or {})
    statuses = list(steps.values())
    monitor = evidence.get("monitor", {}) or {}
    residue = evidence.get("residue", {}) or {}
    hashes = evidence.get("normal_store_hashes", {}) or {}
    post = evidence.get("post_fill", {}) or {}
    if (
        "FAIL" in statuses
        or monitor.get("status") == "FAIL"
        or (isinstance(monitor.get("blocked_sentinel_attempts"), int)
            and monitor["blocked_sentinel_attempts"] > 0)
        or residue.get("status") == "FAIL"
        or hashes.get("identical") is not True
    ):
        return "FAIL"
    if "STOPPED" in statuses or evidence.get("stop_reason"):
        return "STOPPED"
    exact = (
        bool(statuses)
        and all(status == "PASS" for status in statuses)
        and not evidence.get("failure_reasons")
        and monitor.get("status") == "PASS"
        and monitor.get("sentinel_network_leak") == 0
        and monitor.get("blocked_sentinel_attempts") == 0
        and monitor.get("pre_send_blocking_enabled") is True
        and monitor.get("extension_non_loopback_requests") == 0
        and monitor.get("undetectable_fields_count") == 0
        and residue.get("status") == "PASS"
        and residue.get("total") == 0
        and post.get("submitted_count_auto") == 0
        and post.get("auto_submit_detected") == 0
        and evidence.get("submitted_count_auto") == 0
        and all((evidence.get("invariants_after") or {"_": False}).values())
    )
    if exact:
        return PASS_LABELS.get(str(evidence.get("target_kind")), "UNVERIFIED")
    return "UNVERIFIED"


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def run_pilot_nonsubmit(
    manifest_path: Path,
    *,
    port: int = PILOT_WEB_PORT,
    today: date | None = None,
    approved_origins_path: Path | None = None,
    browser_hook: Callable[[PilotRunContext], Mapping[str, object] | None] | None = None,
    phase5a: Phase5AConfig | None = None,
) -> dict[str, object]:
    """Run the isolated pilot. Returns a non-PII summary.

    With ``phase5a`` (the CLI path) the run verifies preconditions before
    binding anything, performs the browser stage and writes a value-free
    ``result.json`` into the run directory.
    """
    if phase5a is not None:
        if browser_hook is not None:
            raise PilotError("browser_hook_and_phase5a_are_exclusive")
        if approved_origins_path is None:
            approved_origins_path = Path(phase5a.project_root) / "config" / "approved_origins.json"
    manifest = load_pilot_nonsubmit_manifest(
        manifest_path,
        today=today,
        approved_origins_path=approved_origins_path,
        allow_loopback_http=bool(phase5a is not None and phase5a.allow_loopback_http_for_tests),
        knshow_url_classifier_for_tests=(phase5a.knshow_url_classifier_for_tests
            if phase5a is not None and phase5a.allow_loopback_http_for_tests else None),
    )
    pre: dict[str, object] = {}
    normal_paths: list[Path] = []
    normal_before: dict[str, str] = {}
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if phase5a is not None:
        from .pilot_residue import snapshot_sha256

        if assisted_session.pilot_storage_active() is not None:
            raise PilotPreconditionError("pilot_storage_already_active")
        pre = verify_phase5a_preconditions(phase5a, Path(manifest_path), Path(approved_origins_path))
        normal_paths = normal_store_paths()
        normal_before = snapshot_sha256(normal_paths)
    sock = reserve_pilot_socket(PILOT_WEB_HOST, port)
    fake: FakeProfile | None = None
    app = None
    stage_evidence: dict[str, object] = {}
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_name = f"nonsubmit-{stamp}-{secrets.token_hex(4)}"
        storage = assisted_session.use_pilot_storage(Path(paths.PILOT_DIR) / "runs" / run_name)
        assisted_session.lock_pilot_candidate(
            candidate_id=manifest.candidate_id,
            url=manifest.url,
            origin=manifest.origin,
            period_end=manifest.campaign_period_end,
        )
        fake = build_fake_profile()
        profile = fake

        def fake_profile_loader() -> Mapping[str, object]:
            if not profile.values:
                raise assisted_session.PilotIsolationError("fake_profile_cleared")
            return dict(profile.values)

        pilot_run_id = secrets.token_hex(16)
        app = create_app(profile_loader=fake_profile_loader, pilot_run_id=pilot_run_id)
        with _serve(app, sock) as base_url:
            verify_pilot_status(fetch_session_status(base_url), pilot_run_id, manifest.candidate_id)
            context = PilotRunContext(
                pilot_run_id=pilot_run_id,
                base_url=base_url,
                manifest=manifest,
                storage=storage,
                fake_profile=fake,
                app=app,
            )
            if phase5a is not None:
                from .pilot_browser_stage import run_browser_stage

                stage_evidence = run_browser_stage(
                    context, phase5a, pre, approved_origins_path=Path(approved_origins_path)
                )
                stage = {"browser_stage": "PHASE5A"}
            else:
                stage = (browser_hook or pilot_browser_and_monitor_stage)(context) or {}
        browser_stage = str(stage.get("browser_stage", "") or "UNKNOWN")
        summary: dict[str, object] = {
            "status": "STOPPED_BEFORE_BROWSER" if browser_stage == "NOT_INTEGRATED" else "STAGE_RETURNED",
            "run_dir": str(storage.run_dir),
            "pilot_run_id": pilot_run_id,
            "candidate_id": manifest.candidate_id,
            "origin": manifest.origin,
            "server_verified": True,
            "browser_stage": browser_stage,
            "undetectable_keys": list(fake.undetectable_keys),
            "sentinel_network_leak": "UNVERIFIED",
            "submitted_count_auto": 0,
        }
    finally:
        if fake is not None:
            fake.clear()
        if app is not None:
            app.state.profile_loader = _cleared_profile_loader
        if assisted_session.pilot_storage_active() is not None:
            assisted_session.end_pilot_session()
        sock.close()
    if phase5a is None:
        return summary
    return _finalize_phase5a(
        summary=summary,
        stage_evidence=stage_evidence,
        pre=pre,
        config=phase5a,
        manifest=manifest,
        manifest_path=Path(manifest_path),
        approved_origins_path=Path(approved_origins_path),
        normal_paths=normal_paths,
        normal_before=normal_before,
        run_dir=Path(storage.run_dir),
        run_name=run_name,
        started_at=started_at,
    )


def _finalize_phase5a(
    *, summary, stage_evidence, pre, config, manifest, manifest_path, approved_origins_path,
    normal_paths, normal_before, run_dir, run_name, started_at,
) -> dict[str, object]:
    from .pilot_residue import compare_sha256_snapshots, snapshot_sha256

    hashes = compare_sha256_snapshots(normal_before, snapshot_sha256(normal_paths))
    invariants = _post_run_invariants(config, pre, approved_origins_path, manifest_path)
    steps = {"preconditions": "PASS", **dict(stage_evidence.get("steps", {}) or {})}
    steps["normal_store_hashes"] = "PASS" if hashes["identical"] else "FAIL"
    steps["invariants"] = "PASS" if all(invariants.values()) else "FAIL"
    target_url = str(stage_evidence.get("url", manifest.url))
    target_origin = str(stage_evidence.get("origin", manifest.origin))
    host = urllib.parse.urlsplit(target_url).hostname or ""
    evidence: dict[str, object] = {
        "schema_version": 1,
        "kind": "pilot_nonsubmit_phase5a",
        "run_name": run_name,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target_kind": "loopback_fixture" if host in {"127.0.0.1", "localhost"} else "real_site",
        "candidate_id": manifest.candidate_id,
        "origin": target_origin,
        "url": target_url,
        "commit": pre["commit"],
        "worktree_clean": pre["worktree_clean"],
        "extension_build_sha256": pre["extension_build_sha256"],
        "extension_version": pre["extension_version"],
        "config_sha256": pre["config_sha256"],
        "manifest_sha256": pre["manifest_sha256"],
        "invariants_after": invariants,
        "allow_undetectable": bool(config.allow_undetectable),
        **{key: value for key, value in stage_evidence.items() if key != "steps"},
        "steps": steps,
        "normal_store_hashes": hashes,
        "submitted_count_auto": 0,
    }
    evidence["overall"] = phase5a_overall(evidence)
    result_path = run_dir / "result.json"
    _write_json_atomic(result_path, evidence)
    summary.update(
        origin=target_origin,
        status="PHASE5A_COMPLETED",
        overall=evidence["overall"],
        stop_reason=evidence.get("stop_reason", ""),
        result_path=str(result_path),
        commit=pre["commit"],
        extension_build_sha256=pre["extension_build_sha256"],
        form_fingerprint=evidence.get("form_fingerprint", ""),
        sentinel_network_leak=(evidence.get("monitor") or {}).get("sentinel_network_leak", "UNVERIFIED"),
    )
    return summary
