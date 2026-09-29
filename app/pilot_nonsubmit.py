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
- Browser launch and network monitoring are not integrated yet; see
  ``pilot_browser_and_monitor_stage``.  No final-submit path exists here.
"""
from __future__ import annotations

import hmac
import json
import re
import secrets
import socket
import string
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
from . import paths
from .extension_bridge import ALLOWED_PAYLOAD_KEYS
from ..web.app import create_app


PILOT_WEB_HOST = "127.0.0.1"
PILOT_WEB_PORT = 8787  # hardcoded in the Chrome extension service worker

MANIFEST_REQUIRED_KEYS = frozenset(
    {
        "candidate_id",
        "url",
        "origin",
        "campaign_period_start",
        "campaign_period_end",
        "human_verified_at",
    }
)
MANIFEST_OPTIONAL_KEYS = frozenset({"expected_fingerprint"})
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


@dataclass(frozen=True)
class PilotNonsubmitManifest:
    candidate_id: str
    url: str
    origin: str
    campaign_period_start: date
    campaign_period_end: date
    human_verified_at: str
    expected_fingerprint: str = ""


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
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    return f"{parsed.scheme}://{host}{port}"


def validate_pilot_nonsubmit_manifest(
    data: object,
    *,
    today: date | None = None,
    approved_origins_path: Path | None = None,
) -> PilotNonsubmitManifest:
    """Strictly validate a single-candidate manifest. Error messages carry no values."""
    from ..scripts.build_dedicated_extension import load_approved_origins

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

    url = data["url"]
    if not isinstance(url, str) or "?" in url or "#" in url:
        raise PilotManifestError("manifest_invalid_url")
    try:
        parsed = urllib.parse.urlsplit(url)
        parsed.port  # noqa: B018 - raises on an invalid port
    except ValueError:
        raise PilotManifestError("manifest_invalid_url") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or any(ch.isspace() for ch in url)
    ):
        raise PilotManifestError("manifest_invalid_url")
    origin = data["origin"]
    if not isinstance(origin, str) or origin != _origin_of(url):
        raise PilotManifestError("manifest_origin_mismatch")
    origins_path = approved_origins_path or paths.CONFIG_DIR / "approved_origins.json"
    try:
        approved = load_approved_origins(origins_path)
    except (OSError, ValueError):
        raise PilotManifestError("approved_origins_unavailable") from None
    if origin not in approved:
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
    )


def load_pilot_nonsubmit_manifest(
    path: Path,
    *,
    today: date | None = None,
    approved_origins_path: Path | None = None,
) -> PilotNonsubmitManifest:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise PilotManifestError("manifest_unreadable") from None
    return validate_pilot_nonsubmit_manifest(
        data, today=today, approved_origins_path=approved_origins_path
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


def run_pilot_nonsubmit(
    manifest_path: Path,
    *,
    port: int = PILOT_WEB_PORT,
    today: date | None = None,
    approved_origins_path: Path | None = None,
    browser_hook: Callable[[PilotRunContext], Mapping[str, object] | None] | None = None,
) -> dict[str, object]:
    """Run the isolated pilot up to the browser stage. Returns a non-PII summary."""
    manifest = load_pilot_nonsubmit_manifest(
        manifest_path, today=today, approved_origins_path=approved_origins_path
    )
    sock = reserve_pilot_socket(PILOT_WEB_HOST, port)
    fake: FakeProfile | None = None
    app = None
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
            stage = (browser_hook or pilot_browser_and_monitor_stage)(context) or {}
        browser_stage = str(stage.get("browser_stage", "") or "UNKNOWN")
        return {
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
