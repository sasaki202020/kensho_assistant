from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable


DISALLOWED_ARTIFACT_SUFFIXES = {".html", ".htm", ".png", ".jpg", ".jpeg", ".webp", ".zip", ".trace"}
SENSITIVE_PROFILE_KEYS = {
    "name", "first_name", "last_name", "full_name", "email", "phone", "tel",
    "address", "address1", "address2", "city", "postal_code", "zip",
}


def build_pilot_test_pii() -> dict[str, str]:
    marker = "927" + "41"
    return {
        "name": "PII_TEST_" + "山田太郎_" + marker,
        "email": "pii-test-" + marker + "@example.invalid",
        "phone": "090-" + "0000-" + "2741",
        "address": "PII_TEST_" + "ADDRESS_" + marker,
        "postal_code": "000-" + "2741",
    }


def ensure_pilot_storage(root: Path) -> None:
    root = Path(root)
    try:
        for name in ("runs", "evidence", "reports"):
            (root / name).mkdir(parents=True, exist_ok=True)
        probe = root / "runs" / ".write-probe"
        probe.write_bytes(b"pilot-storage-probe")
        probe.unlink()
    except OSError as exc:
        raise RuntimeError("pilot_storage_unavailable") from exc


def snapshot_storage(root: Path, *, excluded_root: Path | None = None) -> dict[str, str]:
    root = Path(root)
    if not root.exists():
        return {}
    excluded = Path(excluded_root).resolve() if excluded_root else None
    snapshot: dict[str, str] = {}
    try:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if excluded and (resolved == excluded or excluded in resolved.parents):
                continue
            relative = path.relative_to(root).as_posix()
            snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError) as exc:
        raise RuntimeError("candidate_state_snapshot_failed") from exc
    return snapshot


def compare_storage_snapshots(before: dict[str, str], after: dict[str, str]) -> dict[str, object]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(key for key in set(before) & set(after) if before[key] != after[key])
    return {"identical": not (added or removed or changed), "added": added, "removed": removed, "changed": changed}


def scan_for_forbidden_values(root: Path, values: Iterable[object]) -> dict[str, object]:
    root = Path(root)
    needles: list[bytes] = []
    for value in values:
        text = str(value or "")
        if text:
            needles.extend((text.encode("utf-8"), text.encode("utf-16-le")))
    hits: list[str] = []
    unsafe_artifacts: list[str] = []
    try:
        if root.exists():
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
                if path.suffix.casefold() in DISALLOWED_ARTIFACT_SUFFIXES:
                    unsafe_artifacts.append(relative)
                content = path.read_bytes()
                if any(needle in content for needle in needles):
                    hits.append(relative)
    except (OSError, ValueError) as exc:
        raise RuntimeError("pii_persistence_check_failed") from exc
    return {"clean": not hits and not unsafe_artifacts, "hits": hits, "unsafe_artifacts": unsafe_artifacts}


def sensitive_profile_values(profile: dict[str, object] | object) -> list[object]:
    if not isinstance(profile, dict):
        try:
            items = profile.items()  # type: ignore[union-attr]
        except AttributeError:
            return []
    else:
        items = profile.items()
    return [value for key, value in items if str(key).casefold() in SENSITIVE_PROFILE_KEYS and str(value or "")]


def auto_submit_guard_contract() -> bool:
    from .submission_guard import INSTALL_SCRIPT

    required = (
        "preventDefault",
        "button[type=submit]",
        "keydown",
        "Enter",
        "HTMLFormElement.prototype.submit",
        "requestSubmit",
    )
    return all(term in INSTALL_SCRIPT for term in required)
