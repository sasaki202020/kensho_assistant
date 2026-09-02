from __future__ import annotations

import hmac
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit


MAX_REQUEST_BYTES = 64 * 1024
BRIDGE_PATH = "/v1/capability/consume"
ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "last_name",
        "first_name",
        "last_name_kana",
        "first_name_kana",
        "email",
        "phone",
        "postal_code",
        "prefecture",
        "city",
        "street",
        "building",
        "birth_date",
        "gender",
    }
)


def _validate_origin(value: str) -> str:
    origin = str(value or "").strip()
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid_origin")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("invalid_origin")
    return f"{parsed.scheme}://{parsed.netloc}"


def _validate_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("invalid_capability_payload")
    result: dict[str, str] = {}
    for key, item in value.items():
        name = str(key or "").strip()
        if name not in ALLOWED_PAYLOAD_KEYS:
            raise ValueError("invalid_capability_payload")
        if not isinstance(item, str):
            raise ValueError("invalid_capability_payload")
        result[name] = item
    return result


class CapabilityBridge:
    """Loopback-only, one-shot capability handoff for the extension adapter."""

    host = "127.0.0.1"

    def __init__(self, *, ttl_seconds: int = 60) -> None:
        if not 1 <= int(ttl_seconds) <= 60:
            raise ValueError("invalid_ttl")
        self.ttl_seconds = int(ttl_seconds)
        self._issued: dict[str, dict[str, Any]] = {}
        self._progress: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _purge_expired_locked(self) -> None:
        now = time.monotonic()
        self._issued = {
            token: record
            for token, record in self._issued.items()
            if now < float(record["expires_at"])
        }
        self._progress = {
            token: record
            for token, record in self._progress.items()
            if now < float(record["expires_at"])
        }

    def issue(
        self,
        *,
        session_id: str,
        candidate_id: str,
        origin: str,
        fingerprint: str,
        payload: dict[str, Any],
    ) -> dict[str, object]:
        session = str(session_id or "").strip()
        candidate = str(candidate_id or "").strip()
        fp = str(fingerprint or "").strip()
        safe_origin = _validate_origin(origin)
        if not session or not candidate or not fp:
            raise ValueError("invalid_capability_binding")
        safe_payload = _validate_payload(payload)
        token = secrets.token_urlsafe(32)
        progress_token = secrets.token_urlsafe(32)
        with self._lock:
            self._purge_expired_locked()
            self._issued[token] = {
                "session_id": session,
                "candidate_id": candidate,
                "origin": safe_origin,
                "fingerprint": fp,
                "payload": safe_payload,
                "progress_token": progress_token,
                "expires_at": time.monotonic() + self.ttl_seconds,
            }
        return {
            "token": token,
            "expires_in_seconds": self.ttl_seconds,
            "origin": safe_origin,
            "candidate_id": candidate,
            "session_id": session,
            "fingerprint": fp,
        }

    def consume(
        self,
        *,
        token: str,
        session_id: str,
        candidate_id: str,
        origin: str,
        fingerprint: str,
    ) -> dict[str, object]:
        supplied = str(token or "")
        safe_origin = _validate_origin(origin)
        with self._lock:
            self._purge_expired_locked()
            record = self._issued.pop(supplied, None)
        if not record:
            raise ValueError("invalid_capability")
        if time.monotonic() >= float(record["expires_at"]):
            raise ValueError("invalid_capability")
        if not hmac.compare_digest(str(record["session_id"]), str(session_id or "")):
            raise ValueError("invalid_capability")
        if not hmac.compare_digest(str(record["candidate_id"]), str(candidate_id or "")):
            raise ValueError("invalid_capability")
        if not hmac.compare_digest(str(record["origin"]), safe_origin):
            raise ValueError("invalid_capability")
        if not hmac.compare_digest(str(record["fingerprint"]), str(fingerprint or "")):
            raise ValueError("invalid_capability")
        progress_token = str(record["progress_token"])
        with self._lock:
            self._progress[progress_token] = {
                "session_id": record["session_id"],
                "candidate_id": record["candidate_id"],
                "origin": record["origin"],
                "fingerprint": record["fingerprint"],
                "expires_at": record["expires_at"],
            }
        return {"payload": record["payload"], "progress_token": progress_token}

    def validate_progress(
        self,
        *,
        token: str,
        session_id: str,
        candidate_id: str,
        origin: str,
        fingerprint: str,
        consume: bool,
    ) -> None:
        supplied = str(token or "")
        safe_origin = _validate_origin(origin)
        with self._lock:
            self._purge_expired_locked()
            record = self._progress.get(supplied)
        if not record or time.monotonic() >= float(record["expires_at"]):
            raise ValueError("invalid_progress_capability")
        checks = (
            (str(record["session_id"]), str(session_id or "")),
            (str(record["candidate_id"]), str(candidate_id or "")),
            (str(record["origin"]), safe_origin),
            (str(record["fingerprint"]), str(fingerprint or "")),
        )
        if any(not hmac.compare_digest(expected, actual) for expected, actual in checks):
            raise ValueError("invalid_progress_capability")
        if consume:
            with self._lock:
                if self._progress.pop(supplied, None) is None:
                    raise ValueError("invalid_progress_capability")

    def issue_progress(
        self,
        *,
        session_id: str,
        candidate_id: str,
        origin: str,
        fingerprint: str,
    ) -> str:
        safe_origin = _validate_origin(origin)
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._purge_expired_locked()
            self._progress[token] = {
                "session_id": str(session_id or ""),
                "candidate_id": str(candidate_id or ""),
                "origin": safe_origin,
                "fingerprint": str(fingerprint or ""),
                "expires_at": time.monotonic() + self.ttl_seconds,
            }
        return token

    def revoke_session(self, session_id: str) -> int:
        session = str(session_id or "").strip()
        if not session:
            return 0
        removed = 0
        with self._lock:
            for registry in (self._issued, self._progress):
                for token in [
                    token
                    for token, record in registry.items()
                    if hmac.compare_digest(str(record["session_id"]), session)
                ]:
                    registry.pop(token, None)
                    removed += 1
        return removed

    def start(self) -> tuple[str, int]:
        with self._lock:
            if self._server is not None:
                return self.host, int(self._server.server_port)
            bridge = self

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, _format: str, *_args: object) -> None:
                    return

                def _write_cors_headers(self) -> None:
                    request_origin = str(self.headers.get("Origin", ""))
                    if request_origin.startswith("chrome-extension://"):
                        self.send_header("Access-Control-Allow-Origin", request_origin)
                        self.send_header("Vary", "Origin")

                def do_OPTIONS(self) -> None:  # noqa: N802
                    if self.path != BRIDGE_PATH:
                        self.send_error(404)
                        return
                    self.send_response(204)
                    self._write_cors_headers()
                    self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type")
                    self.end_headers()

                def do_GET(self) -> None:  # noqa: N802
                    encoded = b'{"ok":false,"error":"method_not_allowed"}'
                    self.send_response(405)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(encoded)

                def do_POST(self) -> None:  # noqa: N802
                    if self.path != BRIDGE_PATH:
                        self.send_error(404)
                        return
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        size = 0
                    if size <= 0 or size > MAX_REQUEST_BYTES:
                        self.send_error(400)
                        return
                    try:
                        raw = self.rfile.read(size)
                        body = json.loads(raw.decode("utf-8"))
                        if not isinstance(body, dict):
                            raise ValueError("invalid_request")
                        result = bridge.consume(
                            token=body.get("token", ""),
                            session_id=body.get("session_id", ""),
                            candidate_id=body.get("candidate_id", ""),
                            origin=body.get("origin", ""),
                            fingerprint=body.get("fingerprint", ""),
                        )
                        encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
                        self.send_response(200)
                    except Exception:
                        encoded = b'{"ok":false,"error":"invalid_capability"}'
                        self.send_response(403)
                    self._write_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(encoded)

            self._server = ThreadingHTTPServer((self.host, 0), Handler)
            self._server.daemon_threads = True
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="kensho-extension-bridge",
                daemon=True,
            )
            self._thread.start()
            return self.host, int(self._server.server_port)

    def stop(self) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
            self._issued.clear()
            self._progress.clear()
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)


__all__ = ["ALLOWED_PAYLOAD_KEYS", "BRIDGE_PATH", "CapabilityBridge"]
