from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import kensho_assistant.main as cli
from kensho_assistant.app import profile_manager
from kensho_assistant.app.entry_logger import log_event
from kensho_assistant.app.paths import CONFIG_DIR, resolve_profile_path


def _write_env(path: Path, key: str) -> None:
    path.write_text(f"KENSHO_PROFILE_KEY={key}\n", encoding="utf-8")


def test_resolve_profile_path_prefers_explicit_environment_override(tmp_path: Path) -> None:
    configured = tmp_path / "private" / "profile.enc"

    resolved = resolve_profile_path(
        {
            "KENSHO_PROFILE_PATH": str(configured),
            "LOCALAPPDATA": str(tmp_path / "ignored"),
        }
    )

    assert resolved == configured.resolve()


def test_resolve_profile_path_defaults_to_local_app_data(tmp_path: Path) -> None:
    resolved = resolve_profile_path({"LOCALAPPDATA": str(tmp_path)})

    assert resolved == (tmp_path / "kensho_assistant" / "profile.enc").resolve()


def test_resolve_profile_path_fails_closed_without_local_app_data() -> None:
    with pytest.raises(RuntimeError, match="profile storage is not configured"):
        resolve_profile_path({})


def test_resolve_profile_path_rejects_repository_storage() -> None:
    with pytest.raises(RuntimeError, match="outside the repository"):
        resolve_profile_path({"KENSHO_PROFILE_PATH": str(CONFIG_DIR / "profile.enc")})


def test_default_profile_source_never_falls_back_to_repository_plaintext(
    tmp_path: Path,
    monkeypatch,
) -> None:
    external_profile = tmp_path / "local-app-data" / "profile.enc"
    repository_plaintext = tmp_path / "repository" / "config" / "profile.json"
    repository_plaintext.parent.mkdir(parents=True)
    repository_plaintext.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(profile_manager, "PROFILE_ENC", external_profile)
    monkeypatch.setattr(profile_manager, "PROFILE_JSON", repository_plaintext)

    assert profile_manager.profile_source_path() == external_profile


def test_profile_cli_never_reports_repository_plaintext_fallback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(cli, "PROFILE_ENC", tmp_path / "external" / "profile.enc")
    monkeypatch.setattr(cli, "PROFILE_JSON", tmp_path / "repository" / "profile.json")
    monkeypatch.setattr(cli, "profile_check", lambda encrypted=False: ({}, ["email"]))

    cli.cmd_profile_check(type("Args", (), {"encrypted": False})())

    output = capsys.readouterr().out
    assert "profile store: external profile.enc" in output
    assert "profile.json" not in output


def test_missing_default_profile_error_does_not_report_plaintext_path(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_profile", lambda: {})

    with pytest.raises(SystemExit, match="encrypted profile is missing") as error:
        cli._load_profile_or_fail()

    assert "profile.json" not in str(error.value)


def test_default_encryption_writes_only_to_external_profile_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    key = Fernet.generate_key().decode("utf-8")
    env_path = tmp_path / ".env"
    plain = tmp_path / "fictional-profile.json"
    external_profile = tmp_path / "local-app-data" / "profile.enc"
    plain.write_text('{"last_name": "FICTIONAL_TEST_USER"}', encoding="utf-8")
    _write_env(env_path, key)
    monkeypatch.setattr(profile_manager, "DOTENV_PATH", env_path)
    monkeypatch.setattr(profile_manager, "PROFILE_ENC", external_profile)

    target = profile_manager.encrypt_profile(source_path=plain)

    assert target == external_profile
    assert external_profile.exists()
    assert profile_manager.load_profile(external_profile, encrypted=True) == {
        "last_name": "FICTIONAL_TEST_USER"
    }


def test_profile_encrypt_and_load_round_trip(tmp_path: Path, monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    env_path = tmp_path / ".env"
    plain = tmp_path / "profile.json"
    enc = tmp_path / "profile.enc"
    profile = {
        "last_name": "山田",
        "first_name": "太郎",
        "last_name_kana": "ヤマダ",
        "first_name_kana": "タロウ",
        "postal_code": "100-0001",
        "prefecture": "東京都",
        "city": "千代田区",
        "address1": "千代田1-1",
        "address2": "テストマンション101",
        "phone": "09000001234",
        "email": "kensho-test@example.com",
        "gender": "男性",
        "birth_year": "1980",
        "birth_month": "1",
        "birth_day": "1",
    }
    plain.write_text(__import__("json").dumps(profile, ensure_ascii=False), encoding="utf-8")
    _write_env(env_path, key)
    monkeypatch.setattr(profile_manager, "DOTENV_PATH", env_path)
    target = profile_manager.encrypt_profile(source_path=plain, target_path=enc)
    assert target == enc
    loaded = profile_manager.load_profile(enc, encrypted=True)
    assert loaded == profile


def test_encrypted_profile_does_not_leak_to_logs(tmp_path: Path, monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    env_path = tmp_path / ".env"
    plain = tmp_path / "profile.json"
    enc = tmp_path / "profile.enc"
    log_path = tmp_path / "run.jsonl"
    profile = {
        "last_name": "山田",
        "first_name": "太郎",
        "last_name_kana": "ヤマダ",
        "first_name_kana": "タロウ",
        "postal_code": "100-0001",
        "prefecture": "東京都",
        "city": "千代田区",
        "address1": "千代田1-1",
        "address2": "テストマンション101",
        "phone": "09000001234",
        "email": "kensho-test@example.com",
        "gender": "男性",
        "birth_year": "1980",
        "birth_month": "1",
        "birth_day": "1",
    }
    plain.write_text(__import__("json").dumps(profile, ensure_ascii=False), encoding="utf-8")
    _write_env(env_path, key)
    monkeypatch.setattr(profile_manager, "DOTENV_PATH", env_path)
    profile_manager.encrypt_profile(source_path=plain, target_path=enc)
    log_event("profile", profile, path=log_path)
    text = log_path.read_text(encoding="utf-8")
    assert "山田" not in text
    assert "09000001234" not in text
    assert "kensho-test@example.com" not in text


def test_save_profile_encrypts_from_memory_without_plaintext_file(tmp_path: Path, monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    env_path = tmp_path / ".env"
    external_profile = tmp_path / "local-app-data" / "profile.enc"
    repository_plaintext = tmp_path / "repository" / "profile.json"
    _write_env(env_path, key)
    monkeypatch.setattr(profile_manager, "DOTENV_PATH", env_path)
    monkeypatch.setattr(profile_manager, "PROFILE_ENC", external_profile)
    monkeypatch.setattr(profile_manager, "PROFILE_JSON", repository_plaintext)
    profile = {
        "last_name": "PII_TEST_LAST",
        "first_name": "PII_TEST_FIRST",
        "last_name_kana": "テストセイ",
        "first_name_kana": "テストメイ",
        "postal_code": "000-0000",
        "prefecture": "東京都",
        "city": "テスト区",
        "address1": "テスト1-1",
        "address2": "テスト101",
        "phone": "00000000000",
        "email": "pii-test@example.invalid",
        "gender": "未回答",
        "birth_year": "1980",
        "birth_month": "1",
        "birth_day": "1",
    }

    target = profile_manager.save_profile(profile)

    assert target == external_profile
    assert target.exists()
    assert not repository_plaintext.exists()
    assert profile_manager.load_profile(target, encrypted=True) == profile
