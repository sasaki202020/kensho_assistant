from pathlib import Path

from cryptography.fernet import Fernet

from kensho_assistant.app import profile_manager
from kensho_assistant.app.entry_logger import log_event


def _write_env(path: Path, key: str) -> None:
    path.write_text(f"KENSHO_PROFILE_KEY={key}\n", encoding="utf-8")


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
