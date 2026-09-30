from __future__ import annotations

import json
from pathlib import Path

import pytest

from kensho_assistant.app.browser_manager import (
    close_browser_safely,
    create_dedicated_runtime_profile,
    launch_dedicated_kensho_context,
    validate_dedicated_target_url,
    verify_dedicated_extension_build,
)
from kensho_assistant.scripts.build_dedicated_extension import (
    build_dedicated_extension,
    build_hash,
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


def test_build_has_fixed_permissions_and_runtime_scripts_only(tmp_path: Path) -> None:
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

    assert manifest["host_permissions"] == ["https://*/*", "http://127.0.0.1/*", "http://localhost/*"]
    assert "optional_host_permissions" not in manifest
    assert "<all_urls>" not in json.dumps(manifest)
    assert manifest["version_name"] == "dedicated-runtime-origin"
    assert "content_scripts" not in manifest


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


def test_build_is_independent_of_origin_config(tmp_path: Path) -> None:
    source = _source_extension(tmp_path)
    config = tmp_path / 'approved.json'
    kwargs = dict(source_dir=source, output_dir=tmp_path / 'build' / 'extension',
                  approved_origins_path=config,
                  isolated_files=['shared/messages.js', 'content/isolated-guard.js', 'content/overlay.js'])
    config.write_text(json.dumps({'schema_version': 1, 'origins': ['https://first.test']}))
    first = build_dedicated_extension(**kwargs)
    config.write_text(json.dumps({'schema_version': 1, 'origins': ['https://second.test']}))
    assert build_dedicated_extension(**kwargs).build_sha256 == first.build_sha256
    config.unlink()
    assert build_dedicated_extension(**kwargs).build_sha256 == first.build_sha256
    assert verify_dedicated_extension_build(project_root=tmp_path,
        isolated_files=kwargs['isolated_files'])['build_sha256'] == first.build_sha256


def test_dedicated_target_rejects_url_data_outside_exact_origin(tmp_path: Path) -> None:
    config = tmp_path / "approved.json"
    config.write_text(
        json.dumps({"schema_version": 1, "origins": ["https://www.epinard.jp"]}),
        encoding="utf-8",
    )

    assert validate_dedicated_target_url(
        "https://www.epinard.jp/presentquiz/", approved_candidate_origin="https://www.epinard.jp"
    ) == "https://www.epinard.jp/presentquiz/"
    for rejected in (
        "https://example.com/presentquiz/",
        "https://www.epinard.jp/presentquiz/?email=test@example.invalid",
        "https://www.epinard.jp/presentquiz/#member-id",
        "https://user@example.com/presentquiz/",
    ):
        with pytest.raises(ValueError, match="dedicated_target_not_allowed"):
            validate_dedicated_target_url(rejected, approved_candidate_origin="https://www.epinard.jp")


def test_build_canonicalizes_text_newlines_and_preserves_binary(tmp_path: Path) -> None:
    source = _source_extension(tmp_path)
    config = tmp_path / "approved.json"
    config.write_text(json.dumps({"schema_version": 1, "origins": ["http://127.0.0.1"]}))
    scripts = ["shared/messages.js", "content/isolated-guard.js", "content/overlay.js"]
    binary = b"\x00\xff\r\n\x01"
    (source / "asset.bin").write_bytes(binary)
    for suffix in ("js", "json", "html", "css", "md", "txt"):
        (source / f"sample.{suffix}").write_bytes(b"first\nsecond\n")
    kwargs = dict(source_dir=source, approved_origins_path=config, isolated_files=scripts)
    first = build_dedicated_extension(output_dir=tmp_path / "build" / "extension", **kwargs)
    source_hash = build_hash(source)
    for path in source.rglob("*"):
        if path.is_file() and path.suffix != ".bin":
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert build_hash(source) == source_hash
    second = build_dedicated_extension(output_dir=tmp_path / "crlf-build", **kwargs)
    assert first.build_sha256 == second.build_sha256
    for path in second.output_dir.rglob("*"):
        if path.is_file() and path.suffix != ".bin":
            assert b"\r\n" not in path.read_bytes()
    assert (second.output_dir / "asset.bin").read_bytes() == binary
    verified = verify_dedicated_extension_build(
        project_root=tmp_path, approved_origins_path=config, isolated_files=scripts,
    )
    assert verified["build_sha256"] == first.build_sha256
    # Verification must also accept a CRLF checkout of the existing build.
    for path in first.output_dir.rglob("*"):
        if path.is_file() and path.suffix != ".bin":
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert verify_dedicated_extension_build(
        project_root=tmp_path, approved_origins_path=config, isolated_files=scripts,
    )["build_sha256"] == first.build_sha256
    (source / "sample.txt").write_bytes(b"First\nsecond\n")
    assert build_hash(source) != source_hash
    changed = build_dedicated_extension(output_dir=tmp_path / "changed-build", **kwargs)
    assert changed.build_sha256 != first.build_sha256
    with pytest.raises(RuntimeError, match="dedicated_extension_build_stale"):
        verify_dedicated_extension_build(
            project_root=tmp_path, approved_origins_path=config, isolated_files=scripts,
        )
    (source / "sample.txt").write_bytes(b"first\nsecond\n")
    (source / "asset.bin").write_bytes(binary.replace(b"\r\n", b"\n"))
    assert build_hash(source) != source_hash
    binary_changed = build_dedicated_extension(output_dir=tmp_path / "binary-build", **kwargs)
    assert binary_changed.build_sha256 != first.build_sha256


def test_dedicated_build_verification_detects_stale_source(tmp_path: Path) -> None:
    source = _source_extension(tmp_path)
    config = tmp_path / "approved.json"
    config.write_text(
        json.dumps({"schema_version": 1, "origins": ["https://www.epinard.jp"]}),
        encoding="utf-8",
    )
    output = tmp_path / "build" / "extension"
    build_dedicated_extension(
        source_dir=source,
        output_dir=output,
        approved_origins_path=config,
        isolated_files=["shared/messages.js", "content/isolated-guard.js", "content/overlay.js"],
    )

    verified = verify_dedicated_extension_build(
        project_root=tmp_path,
        approved_origins_path=config,
        isolated_files=["shared/messages.js", "content/isolated-guard.js", "content/overlay.js"],
    )
    assert verified["version"] == "0.2.0"
    assert len(verified["build_sha256"]) == 64

    (source / "content" / "overlay.js").write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="dedicated_extension_build_stale"):
        verify_dedicated_extension_build(
            project_root=tmp_path,
            approved_origins_path=config,
            isolated_files=["shared/messages.js", "content/isolated-guard.js", "content/overlay.js"],
        )


def test_runtime_profile_is_unique_per_launch_and_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    first = create_dedicated_runtime_profile("session-1")
    second = create_dedicated_runtime_profile("session-1")

    assert first != second
    assert first.parent == local_app_data / "kensho_assistant" / "chrome-runs"
    assert second.parent == first.parent


def test_launch_uses_verified_runtime_snapshot_and_cleans_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source_extension(tmp_path)
    config = tmp_path / "approved.json"
    config.write_text(
        json.dumps({"schema_version": 1, "origins": ["https://www.epinard.jp"]}),
        encoding="utf-8",
    )
    output = tmp_path / "build" / "extension"
    built = build_dedicated_extension(
        source_dir=source,
        output_dir=output,
        approved_origins_path=config,
        isolated_files=["shared/messages.js", "content/isolated-guard.js", "content/overlay.js"],
    )
    captured: dict[str, object] = {}

    class FakeContext:
        def close(self) -> None:
            captured["closed"] = True

    class FakeChromium:
        def launch_persistent_context(self, user_data_dir, **kwargs):
            captured["user_data_dir"] = Path(user_data_dir)
            captured["args"] = kwargs["args"]
            return FakeContext()

    monkeypatch.setattr(
        "kensho_assistant.app.browser_manager.verify_dedicated_extension_build",
        lambda **_kwargs: {
            "build_sha256": built.build_sha256,
            "version": "0.2.0",
            "approved_origins": ["https://www.epinard.jp"],
            "extension_dir": output,
        },
    )
    runtime_root = tmp_path / "runtime"
    context, _browser, _verified = launch_dedicated_kensho_context(
        type("Playwright", (), {"chromium": FakeChromium()})(),
        run_id="run-1",
        project_root=tmp_path,
        runtime_profiles_root=runtime_root,
    )
    run_root = Path(captured["user_data_dir"]).parent
    extension_args = [arg for arg in captured["args"] if "load-extension" in arg]

    assert run_root.parent == runtime_root
    assert extension_args == [f"--load-extension={run_root / 'extension'}"]
    assert run_root / "extension" != output
    close_browser_safely(context)
    assert captured["closed"] is True
    assert not run_root.exists()


def test_start_script_uses_fresh_dedicated_profile_and_fixed_build_path() -> None:
    script = (Path(__file__).parents[1] / "scripts" / "start_kensho_chrome.ps1").read_text(
        encoding="utf-8"
    )
    browser_manager = (Path(__file__).parents[1] / "app" / "browser_manager.py").read_text(
        encoding="utf-8"
    )

    assert "chrome-runs" in script
    assert "--disable-extensions-except" in browser_manager
    assert "--load-extension" in browser_manager
    assert "build_dedicated_extension.py" not in script
    assert '"--verify-only"' in script
    assert "diagnostic_runner_requires_verify_only" in (
        Path(__file__).parents[1] / "scripts" / "run_dedicated_chrome.py"
    ).read_text(encoding="utf-8")
    assert "Stop-Process" not in script
    assert "Remove-Item" not in script
