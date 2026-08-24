from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.pilot.build_fingerprint import build_fingerprint, default_pilot_files


def test_build_fingerprint_is_repeatable_and_ignores_attestation_fields(tmp_path) -> None:
    manifest = tmp_path / "5site-pilot-v1.json"
    candidates = tmp_path / "5site-candidates-v1.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "pilot_id": "5site-pilot-v1",
                "pilot_commit": "",
                "build_fingerprint_sha256": "",
            }
        ),
        encoding="utf-8",
    )
    candidates.write_text(json.dumps({"sites": [{"site_id": "site-1"}]}), encoding="utf-8")
    source = tmp_path / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")

    first = build_fingerprint([source], manifest, candidates)
    second = build_fingerprint([source], manifest, candidates)
    assert first == second

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["pilot_commit"] = "commit-sha"
    payload["build_fingerprint_sha256"] = first
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert build_fingerprint([source], manifest, candidates) == first


def test_build_fingerprint_changes_when_candidate_manifest_changes(tmp_path) -> None:
    manifest = tmp_path / "pilot.json"
    candidates = tmp_path / "candidates.json"
    source = tmp_path / "source.py"
    manifest.write_text(json.dumps({"pilot_commit": "", "build_fingerprint_sha256": ""}), encoding="utf-8")
    candidates.write_text(json.dumps({"sites": [{"site_id": "site-1"}]}), encoding="utf-8")
    source.write_text("VALUE = 1\n", encoding="utf-8")
    first = build_fingerprint([source], manifest, candidates)

    candidates.write_text(json.dumps({"sites": [{"site_id": "site-2"}]}), encoding="utf-8")
    assert build_fingerprint([source], manifest, candidates) != first


def test_default_pilot_files_include_extension_and_form_safety_inputs() -> None:
    labels = {path.relative_to(Path(__file__).resolve().parents[1]).as_posix() for path in default_pilot_files()}

    assert "extension/content/form-filler.js" in labels
    assert "extension/manifest.json" in labels
    assert "tests/test_field_mapping_safety.py" in labels
    assert "tests/test_form_scope.py" in labels
