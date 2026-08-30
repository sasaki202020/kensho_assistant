from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_dedicated_extension import (
    build_dedicated_extension,
    load_approved_origins,
)


def _source_extension(root: Path) -> Path:
    extension = root / "extension"
    (extension / "content").mkdir(parents=True)
    (extension / "shared").mkdir()
    (extension / "content" / "submit-guard.js").write_text("guard", encoding="utf-8")
    (extension / "content" / "isolated-guard.js").write_text("isolated", encoding="utf-8")
    (extension / "content" / "overlay.js").write_text("overlay", encoding="utf-8")
    (extension / "shared" / "messages.js").write_text("messages", encoding="utf-8")
    (extension / "service-worker.js").write_text("worker", encoding="utf-8")
    (extension / "manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": 3,
                "name": "test",
                "version": "0.2.0",
                "permissions": ["activeTab", "scripting", "storage"],
                "optional_host_permissions": ["http://*/*", "https://*/*"],
                "background": {"service_worker": "service-worker.js"},
            }
        ),
        encoding="utf-8",
    )
    return extension


def test_load_approved_origins_normalizes_and_rejects_non_origin_values(tmp_path: Path) -> None:
    config = tmp_path / "approved.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "origins": ["https://www.epinard.jp", "https://www.epinard.jp/"],
            }
        ),
        encoding="utf-8",
    )

    assert load_approved_origins(config) == ["https://www.epinard.jp"]

    config.write_text(
        json.dumps({"schema_version": 1, "origins": ["https://www.epinard.jp/path"]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid_approved_origin"):
        load_approved_origins(config)


def test_build_has_exact_permissions_and_static_main_and_isolated_scripts(tmp_path: Path) -> None:
    source = _source_extension(tmp_path)
    config = tmp_path / "approved.json"
    config.write_text(
        json.dumps({"schema_version": 1, "origins": ["https://www.epinard.jp"]}),
        encoding="utf-8",
    )

    result = build_dedicated_extension(
        source_dir=source,
        output_dir=tmp_path / "build" / "extension",
        approved_origins_path=config,
        isolated_files=["shared/messages.js", "content/isolated-guard.js", "content/overlay.js"],
    )
    manifest = json.loads((result.output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["host_permissions"] == ["https://www.epinard.jp/*"]
    assert "optional_host_permissions" not in manifest
    assert "<all_urls>" not in json.dumps(manifest)
    assert "https://*/*" not in manifest["host_permissions"]
    assert manifest["content_scripts"] == [
        {
            "matches": ["https://www.epinard.jp/*"],
            "js": ["content/submit-guard.js"],
            "run_at": "document_start",
            "all_frames": False,
            "world": "MAIN",
        },
        {
            "matches": ["https://www.epinard.jp/*"],
            "js": ["shared/messages.js", "content/isolated-guard.js", "content/overlay.js"],
            "run_at": "document_idle",
            "all_frames": False,
            "world": "ISOLATED",
        },
    ]


def test_build_is_deterministic_and_does_not_copy_runtime_data(tmp_path: Path) -> None:
    source = _source_extension(tmp_path)
    (source / "tests").mkdir()
    (source / "tests" / "ignored.js").write_text("ignored", encoding="utf-8")
    (source / "profile.enc").write_text("secret", encoding="utf-8")
    config = tmp_path / "approved.json"
    config.write_text(
        json.dumps({"schema_version": 1, "origins": ["https://www.epinard.jp"]}),
        encoding="utf-8",
    )
    output = tmp_path / "build" / "extension"

    first = build_dedicated_extension(
        source_dir=source,
        output_dir=output,
        approved_origins_path=config,
        isolated_files=["shared/messages.js", "content/isolated-guard.js", "content/overlay.js"],
    )
    second = build_dedicated_extension(
        source_dir=source,
        output_dir=output,
        approved_origins_path=config,
        isolated_files=["shared/messages.js", "content/isolated-guard.js", "content/overlay.js"],
    )

    assert first.build_sha256 == second.build_sha256
    assert not (output / "tests").exists()
    assert not (output / "profile.enc").exists()


def test_start_script_uses_only_dedicated_profile_and_fixed_build_path() -> None:
    script = (Path(__file__).parents[1] / "scripts" / "start_kensho_chrome.ps1").read_text(
        encoding="utf-8"
    )

    assert "AppData\\Local\\kensho_assistant\\chrome-profile" in script
    assert "--disable-extensions-except" in script
    assert "--load-extension" in script
    assert "build\\extension" in script
    assert "Stop-Process" not in script
    assert "Remove-Item" not in script
