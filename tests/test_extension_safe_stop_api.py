from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kensho_assistant.app.assisted_session import (
    load_assisted_session_state,
    save_assisted_session_state,
)
from kensho_assistant.web.app import create_app


@pytest.fixture
def active_session(monkeypatch, tmp_path):
    path = tmp_path / "session.json"
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", path
    )
    revoked = []
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.revoke_extension_capabilities",
        lambda session: revoked.append(session),
    )
    save_assisted_session_state({
        "workflow_state": "HUMAN_ACTION_REQUIRED",
        "session_id": "session-1",
        "active_candidate_id": "candidate-1",
        "candidate_id": "candidate-1",
        "current_url": "https://example.invalid/apply",
        "form_fingerprint": "fingerprint-1",
        "extension_id": "a" * 32,
        "submitted_count_auto": 0,
    })
    return path, revoked


def request_body():
    return {
        "session_id": "session-1",
        "candidate_id": "candidate-1",
        "origin": "https://example.invalid",
        "fingerprint": "fingerprint-1",
    }


def test_extension_safe_stop_reaches_canonical_state(active_session):
    _, revoked = active_session
    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/api/session/extension-safe-stop",
            headers={"origin": "chrome-extension://" + "a" * 32},
            json=request_body(),
        )
    assert response.status_code == 200
    state = load_assisted_session_state()
    assert state["workflow_state"] == "FAILED_SAFE"
    assert state["candidate_marked_submitted"] is False
    assert state["submitted_count_auto"] == 0
    assert revoked == ["session-1"]


@pytest.mark.parametrize("field", ["session_id", "candidate_id", "origin", "fingerprint"])
def test_extension_safe_stop_rejects_wrong_binding(active_session, field):
    path, revoked = active_session
    before = path.read_bytes()
    body = request_body()
    body[field] = "https://other.invalid" if field == "origin" else "wrong"
    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/api/session/extension-safe-stop",
            headers={"origin": "chrome-extension://" + "a" * 32},
            json=body,
        )
    assert response.status_code == 409
    assert path.read_bytes() == before
    assert revoked == []


@pytest.mark.parametrize("host,origin", [
    ("127.0.0.1", "chrome-extension://" + "b" * 32),
    ("127.0.0.1", "https://other.invalid"),
    ("127.0.0.1", ""),
    ("192.0.2.1", "chrome-extension://" + "a" * 32),
])
def test_extension_safe_stop_rejects_untrusted_caller(active_session, host, origin):
    path, revoked = active_session
    before = path.read_bytes()
    with TestClient(create_app(), client=(host, 50000)) as client:
        response = client.post(
            "/api/session/extension-safe-stop",
            headers={"origin": origin},
            json=request_body(),
        )
    assert response.status_code == 403
    assert path.read_bytes() == before
    assert revoked == []
