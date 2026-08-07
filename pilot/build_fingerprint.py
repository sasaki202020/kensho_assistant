from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ATTESTATION_FIELDS = {"pilot_commit", "build_fingerprint_sha256"}
ROOT_FILES = (
    "__init__.py",
    "desktop_app.py",
    "main.py",
    "mail_importer.py",
    "requirements.txt",
    "run_web.py",
)
SOURCE_DIRS = ("app", "config", "pilot", "scripts", "ui", "web")
RELATED_TESTS = (
    "tests/test_pilot_build_fingerprint.py",
    "tests/test_pilot_preflight.py",
    "tests/test_pilot_validation.py",
    "tests/test_privacy_guard.py",
    "tests/test_submission_guard.py",
)


def _manifest_bytes(path: Path) -> bytes:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = dict(payload)
        for field in ATTESTATION_FIELDS:
            if field in payload:
                payload[field] = ""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _label(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def build_fingerprint(source_files: Iterable[Path], manifest_path: Path, candidates_path: Path) -> str:
    entries: list[tuple[str, bytes]] = []
    for path in source_files:
        entries.append((_label(path), path.read_bytes()))
    entries.append(("pilot-manifest.json", _manifest_bytes(manifest_path)))
    entries.append(("pilot-candidates.json", _manifest_bytes(candidates_path)))

    digest = hashlib.sha256()
    for label, content in sorted(entries, key=lambda item: item[0]):
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def default_pilot_files() -> list[Path]:
    files = [PROJECT_ROOT / name for name in ROOT_FILES]
    for directory in SOURCE_DIRS:
        files.extend(path for path in (PROJECT_ROOT / directory).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    files.extend(PROJECT_ROOT / name for name in RELATED_TESTS)
    return sorted({path.resolve() for path in files if path.is_file()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a reproducible five-site pilot build fingerprint")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    args = parser.parse_args(argv)
    print(build_fingerprint(default_pilot_files(), args.manifest, args.candidates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
