from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection

import pytest

from kensho_assistant.app.extension_bridge import CapabilityBridge


def _bridge() -> CapabilityBridge:
    return CapabilityBridge(ttl_seconds=60)


def test_capability_is_bound_and_consumed_once() -> None:
    bridge = _bridge()
    issued = bridge.issue(
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.test",
        fingerprint="fp-1",
        payload={"email": "PII must remain in memory only"},
    )

    consumed = bridge.consume(
        token=issued["token"],
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.test",
        fingerprint="fp-1",
    )
    assert consumed["payload"]["email"]

    with pytest.raises(ValueError, match="invalid_capability"):
        bridge.consume(
            token=issued["token"],
            session_id="session-1",
            candidate_id="candidate-1",
            origin="https://example.test",
            fingerprint="fp-1",
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "other-session"),
        ("candidate_id", "other-candidate"),
        ("origin", "https://other.test"),
        ("fingerprint", "other-fingerprint"),
    ],
)
def test_capability_binding_rejects_mismatch(field: str, value: str) -> None:
    bridge = _bridge()
    issued = bridge.issue(
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.test",
        fingerprint="fp-1",
        payload={"email": "memory-only"},
    )
    values = {
        "session_id": "session-1",
        "candidate_id": "candidate-1",
        "origin": "https://example.test",
        "fingerprint": "fp-1",
    }
    values[field] = value
    with pytest.raises(ValueError, match="invalid_capability"):
        bridge.consume(token=issued["token"], **values)


def test_origin_must_not_have_path_query_or_fragment() -> None:
    bridge = _bridge()
    for origin in (
        "https://example.test/path",
        "https://example.test/?email=pii@example.invalid",
        "https://example.test/#fragment",
    ):
        with pytest.raises(ValueError, match="invalid_origin"):
            bridge.issue(
                session_id="session-1",
                candidate_id="candidate-1",
                origin=origin,
                fingerprint="fp-1",
                payload={},
            )


def test_ttl_expiry_is_fail_closed() -> None:
    bridge = CapabilityBridge(ttl_seconds=1)
    issued = bridge.issue(
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.test",
        fingerprint="fp-1",
        payload={},
    )
    bridge._issued[issued["token"]]["expires_at"] = time.monotonic() - 1
    with pytest.raises(ValueError, match="invalid_capability"):
        bridge.consume(
            token=issued["token"],
            session_id="session-1",
            candidate_id="candidate-1",
            origin="https://example.test",
            fingerprint="fp-1",
        )


def test_payload_is_limited_to_confirmed_profile_fields() -> None:
    bridge = _bridge()
    with pytest.raises(ValueError, match="invalid_capability_payload"):
        bridge.issue(
            session_id="session-1",
            candidate_id="candidate-1",
            origin="https://example.test",
            fingerprint="fp-1",
            payload={"unknown_field": "value"},
        )


def test_loopback_http_endpoint_returns_payload_without_logging() -> None:
    bridge = _bridge()
    host, port = bridge.start()
    try:
        issued = bridge.issue(
            session_id="session-1",
            candidate_id="candidate-1",
            origin="http://127.0.0.1:8787",
            fingerprint="fp-1",
            payload={"email": "memory-only"},
        )
        connection = HTTPConnection(host, port, timeout=2)
        connection.request(
            "POST",
            "/v1/capability/consume",
            body=json.dumps(
                {
                    "token": issued["token"],
                    "session_id": "session-1",
                    "candidate_id": "candidate-1",
                    "origin": "http://127.0.0.1:8787",
                    "fingerprint": "fp-1",
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["payload"]["email"] == "memory-only"
        connection.close()
        assert bridge.host == "127.0.0.1"
    finally:
        bridge.stop()


def test_loopback_http_endpoint_supports_extension_preflight() -> None:
    bridge = _bridge()
    host, port = bridge.start()
    try:
        connection = HTTPConnection(host, port, timeout=2)
        connection.request(
            "OPTIONS",
            "/v1/capability/consume",
            headers={"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"},
        )
        response = connection.getresponse()
        assert response.status == 204
        assert response.getheader("Access-Control-Allow-Origin") == "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
        connection.close()
    finally:
        bridge.stop()
