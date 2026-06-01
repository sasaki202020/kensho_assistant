from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

from .paths import CONFIG_DIR, PROFILE_EXAMPLE_JSON, PROFILE_JSON

try:
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover - handled by runtime checks
    Fernet = None


PROFILE_ENC = CONFIG_DIR / "profile.enc"
DOTENV_PATH = Path.cwd() / ".env"

REQUIRED_PROFILE_KEYS = [
    "last_name",
    "first_name",
    "last_name_kana",
    "first_name_kana",
    "postal_code",
    "prefecture",
    "city",
    "address1",
    "address2",
    "phone",
    "email",
    "gender",
    "birth_year",
    "birth_month",
    "birth_day",
]


def _load_env_values() -> dict[str, str]:
    values = {key: value for key, value in dotenv_values(DOTENV_PATH).items() if value is not None} if DOTENV_PATH.exists() else {}
    values.update({key: value for key, value in os.environ.items() if value is not None})
    return values


def _require_env_key() -> bytes:
    values = _load_env_values()
    key = values.get("KENSHO_PROFILE_KEY", "").strip()
    if not key:
        raise SystemExit("KENSHO_PROFILE_KEY is missing in .env")
    if Fernet is None:
        raise SystemExit("cryptography is required for profile encryption")
    return key.encode("utf-8")


def _fernet() -> Fernet:
    return Fernet(_require_env_key())


def _read_json_file(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {str(key): str(value) for key, value in data.items()}


def _write_json_file(path: Path, data: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _encrypt_bytes(payload: bytes) -> bytes:
    return _fernet().encrypt(payload)


def _decrypt_bytes(payload: bytes) -> bytes:
    return _fernet().decrypt(payload)


def profile_source_path(encrypted: bool | None = None) -> Path:
    if encrypted is True:
        return PROFILE_ENC
    if encrypted is False:
        return PROFILE_JSON
    if PROFILE_ENC.exists():
        return PROFILE_ENC
    return PROFILE_JSON


def load_profile(path: str | Path | None = None, encrypted: bool | None = None) -> dict[str, str]:
    profile_path = Path(path) if path else profile_source_path(encrypted=encrypted)
    if not profile_path.exists():
        return {}
    if profile_path.suffix == ".enc" or encrypted is True:
        payload = _decrypt_bytes(profile_path.read_bytes())
        return {str(key): str(value) for key, value in json.loads(payload.decode("utf-8")).items()}
    return _read_json_file(profile_path)


def profile_missing_fields(profile: Mapping[str, str]) -> list[str]:
    return [key for key in REQUIRED_PROFILE_KEYS if not str(profile.get(key, "")).strip()]


def profile_is_complete(profile: Mapping[str, str]) -> bool:
    return not profile_missing_fields(profile)


def load_example_profile() -> dict[str, str]:
    if PROFILE_EXAMPLE_JSON.exists():
        return _read_json_file(PROFILE_EXAMPLE_JSON)
    return {}


def encrypt_profile(
    source_path: str | Path | None = None,
    target_path: str | Path | None = None,
    delete_plain: bool = False,
) -> Path:
    source = Path(source_path) if source_path else PROFILE_JSON
    target = Path(target_path) if target_path else PROFILE_ENC
    if not source.exists():
        raise SystemExit(f"{source} is missing")
    profile = _read_json_file(source)
    encrypted = _encrypt_bytes(json.dumps(profile, ensure_ascii=False).encode("utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encrypted)
    if delete_plain and source.suffix == ".json":
        source.unlink()
    return target


def decrypt_profile(
    source_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, str]:
    if output_path is None:
        raise SystemExit("decrypt requires --output")
    source = Path(source_path) if source_path else PROFILE_ENC
    if not source.exists():
        raise SystemExit(f"{source} is missing")
    profile = load_profile(source, encrypted=True)
    _write_json_file(Path(output_path), profile)
    return profile


def rotate_profile_key(delete_plain: bool = False) -> Path:
    if not DOTENV_PATH.exists():
        raise SystemExit(".env is missing")
    profile = load_profile(encrypted=None)
    if not profile:
        raise SystemExit("profile data is missing")
    new_key = Fernet.generate_key() if Fernet else None
    if new_key is None:
        raise SystemExit("cryptography is required for profile encryption")
    encrypted = Fernet(new_key).encrypt(json.dumps(profile, ensure_ascii=False).encode("utf-8"))
    PROFILE_ENC.write_bytes(encrypted)
    _write_env_key(new_key.decode("utf-8"))
    if delete_plain and PROFILE_JSON.exists():
        PROFILE_JSON.unlink()
    return PROFILE_ENC


def _write_env_key(new_key: str) -> None:
    lines: list[str] = []
    found = False
    if DOTENV_PATH.exists():
        lines = DOTENV_PATH.read_text(encoding="utf-8").splitlines()
        updated: list[str] = []
        for line in lines:
            if line.startswith("KENSHO_PROFILE_KEY="):
                updated.append(f"KENSHO_PROFILE_KEY={new_key}")
                found = True
            else:
                updated.append(line)
        lines = updated
    if not found:
        lines.append(f"KENSHO_PROFILE_KEY={new_key}")
    DOTENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def profile_check(encrypted: bool = False) -> tuple[dict[str, str], list[str]]:
    profile = load_profile(encrypted=encrypted if encrypted else None)
    return profile, profile_missing_fields(profile)

