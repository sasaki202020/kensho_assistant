import json
from datetime import datetime, timedelta, timezone

import pytest

from kensho_assistant.app import paths, form_template_store as store


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "FORM_TEMPLATES_JSON", tmp_path / "form_templates.json")
    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path / "config")
    paths.CONFIG_DIR.mkdir()
    (paths.CONFIG_DIR / "approved_origins.json").write_text(
        json.dumps({"schema_version": 1, "origins": ["http://127.0.0.1:9999"]}), encoding="utf-8")
    return paths.FORM_TEMPLATES_JSON


def template():
    return {
        "origin": "http://127.0.0.1:9999", "pathname": "/form",
        "fingerprint": "1234abcd", "structureFingerprint": "5678abcd",
        "extensionVersion": "0.2.0", "humanConfirmedAt": datetime.now(timezone.utc).isoformat(),
        "fields": [{"path": "html[0]/body[0]/form[0]/input[0]", "approvedProfileKey": "email"}],
    }


def test_save_load_without_values(storage):
    assert store.save_template(template(), build_sha256="a" * 64) == "saved"
    records = store.get_templates_for_origin("http://127.0.0.1:9999", extension_version="0.2.0", build_sha256="a" * 64)
    assert len(records) == 1
    assert records[0]["fields"] == template()["fields"]
    assert records[0]["extension_build_sha256"] == "a" * 64
    assert store.get_templates_for_origin("http://127.0.0.1:9999", extension_version="0.0.0", build_sha256="a" * 64) == []
    assert store.get_templates_for_origin("http://127.0.0.1:9999", extension_version="0.2.0", build_sha256="b" * 64) == []


@pytest.mark.parametrize("change", [
    {"value": "INPUT-SENTINEL"}, {"origin": "https://unapproved.invalid"},
    {"fields": [{"path": "html[0]/input[0]", "approvedProfileKey": "password"}]},
    {"fields": [{"path": "INPUT-SENTINEL", "approvedProfileKey": "email"}]},
    {"fields": [{"path": "html[0]/input[0]", "approvedProfileKey": "email", "value": "INPUT-SENTINEL"}]},
    {"pathname": "/person@example.invalid"}, {"pathname": "/123456789"},
    {"humanConfirmedAt": ""}, {"fingerprint": "INPUT-SENTINEL"},
    {"fields": [{"path": "html[0]/input[0]", "approvedProfileKey": "email", "disabled": True}]},
])
def test_reject_unsafe_schema(storage, change):
    with pytest.raises(ValueError):
        store.save_template({**template(), **change}, build_sha256="a" * 64)
    assert not storage.exists()


def test_expiry_conflict_and_revoke(storage):
    t = template()
    store.save_template(t, build_sha256="a" * 64)
    before = storage.read_bytes()
    assert store.save_template({**t, "fingerprint": "ffffffff"}, build_sha256="a" * 64) == "conflict"
    assert storage.read_bytes() == before
    assert store.save_template(t, build_sha256="a" * 64) == "unchanged"
    assert storage.read_bytes() == before
    assert set(store.list_summaries()[0]) == {"origin", "pathname", "field_count", "humanConfirmedAt"}
    assert store.revoke(origin=t["origin"], pathname="/other") == 0
    assert store.revoke(origin=t["origin"], pathname=t["pathname"]) == 1
    assert store.load_templates() == []
    t["humanConfirmedAt"] = (datetime.now(timezone.utc) - timedelta(days=181)).isoformat()
    store.save_template(t, build_sha256="a" * 64)
    assert store.load_templates() == []
    assert store.revoke() == 1


def test_atomic_failure_preserves_previous(storage, monkeypatch):
    store.save_template(template(), build_sha256="a" * 64)
    before = storage.read_bytes()
    def interrupted(*args):
        raise OSError("fixture interruption")
    monkeypatch.setattr(store.os, "replace", interrupted)
    with pytest.raises(OSError):
        store.save_template({**template(), "pathname": "/second"}, build_sha256="a" * 64)
    assert storage.read_bytes() == before
    assert list(storage.parent.glob(".form-templates-*")) == []


def test_pilot_isolation(storage, tmp_path, monkeypatch):
    from kensho_assistant.app import assisted_session as session
    monkeypatch.setattr(paths, "PILOT_DIR", tmp_path / "pilot")
    for name in ("ASSISTED_SESSION_DIR", "ASSISTED_SESSION_STATE_JSON", "REAL_SITE_TRIALS_JSONL",
        "REAL_SITE_TRIAL_STEPS_JSONL", "_EXTENSION_BRIDGE", "_EXTENSION_CONTROL_TOKENS",
        "_EXTENSION_PROGRESS_RESPONSES", "_PILOT_STORAGE", "_PILOT_CANDIDATE"):
        monkeypatch.setattr(session, name, getattr(session, name))
    session.use_pilot_storage(tmp_path / "pilot" / "runs" / "fixture")
    for action in (store.load_templates, store.list_summaries, store.revoke,
        lambda: store.save_template(template(), build_sha256="a" * 64),
        lambda: store.get_templates_for_origin(template()["origin"], extension_version="0.2.0", build_sha256="a" * 64)):
        with pytest.raises(session.PilotIsolationError):
            action()
    assert not storage.exists()


def test_cli_summary_and_explicit_revoke(storage, capsys):
    from kensho_assistant.main import build_parser
    store.save_template(template(), build_sha256="a" * 64)
    parser = build_parser()
    args = parser.parse_args(["form-templates", "list"])
    assert args.func(args) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["count"] == 1
    assert "fields" not in summary["templates"][0]
    assert "html[0]" not in json.dumps(summary)
    with pytest.raises(SystemExit):
        parser.parse_args(["form-templates", "revoke"])
    args = parser.parse_args(["form-templates", "revoke", "--origin", template()["origin"], "--pathname", "/form"])
    assert args.func(args) == 0
    assert json.loads(capsys.readouterr().out)["revoked_count"] == 1
    store.save_template(template(), build_sha256="a" * 64)
    args = parser.parse_args(["form-templates", "revoke", "--all"])
    assert args.func(args) == 0
    assert json.loads(capsys.readouterr().out)["revoked_count"] == 1


def test_saved_at_type_is_validated(storage):
    with pytest.raises(ValueError):
        store.save_template({**template(), "savedAt": []}, build_sha256="a" * 64)


@pytest.mark.parametrize("field", [
    {"path": 123, "approvedProfileKey": "email"},
    {"path": "html[0]/input[0]", "approvedProfileKey": []},
    {"path": "html[0]/input[0]", "approvedProfileKey": "email", "confidenceBand": []},
    {"path": "html[0]/input[0]", "approvedProfileKey": "email", "disabled": 0},
])
def test_field_type_checks(storage, field):
    with pytest.raises(ValueError):
        store.save_template({**template(), "fields": [field]}, build_sha256="a" * 64)
