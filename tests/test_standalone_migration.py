import hashlib
import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_SCRIPT = PROJECT_ROOT / "scripts" / "migrate_standalone_allowlist.ps1"


def _write(root: Path, relative: str, content: str = "safe") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_migration(source: Path, destination: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(MIGRATION_SCRIPT),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _source_fixture(root: Path) -> None:
    for relative in (
        "app/main.py",
        "tests/test_safe.py",
        "tests/extension_fixtures/form.html",
        "scripts/tool.ps1",
        "docs/guide.md",
        "extension/manifest.json",
        "pilot/__init__.py",
        "ui/page.py",
        "web/app.py",
        "samples/mail/sample.txt",
        "config/rules.yaml",
        "config/profile.example.json",
        "README.md",
        "AGENTS.md",
        ".env.example",
        "requirements.txt",
        "main.py",
        "MIGRATION_PROVENANCE.md",
        "data/pilot/manifests/5site-pilot-v1.json",
    ):
        _write(root, relative, f"safe:{relative}")

    for relative in (
        ".git/config",
        ".env",
        "config/profile.enc",
        "browser_profile/Default/Cookies",
        "data/campaigns.csv",
        "data/pilot/manifests/5site-candidates-v1.json",
        "logs/app.log",
        "screenshots/form.png",
        "traces/trace.zip",
        "cache/item.bin",
        "tmp/item.txt",
        "node_modules/package/index.js",
        ".venv/pyvenv.cfg",
        "extension/node_modules/package/index.js",
    ):
        _write(root, relative, f"secret:{relative}")


def test_migration_copies_only_allowlisted_source_and_safe_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    _source_fixture(source)
    _write(
        destination,
        "docs/superpowers/specs/2026-08-08-kensho-standalone-completion-design.md",
        "approved design",
    )
    _write(
        destination,
        "docs/superpowers/plans/2026-08-08-kensho-standalone-completion.md",
        "approved plan",
    )

    result = _run_migration(source, destination)

    assert result.returncode == 0, result.stderr
    assert (destination / "app/main.py").read_text(encoding="utf-8") == "safe:app/main.py"
    assert (destination / "data/pilot/manifests/5site-pilot-v1.json").exists()
    assert not (destination / "config/profile.enc").exists()
    assert not (destination / "data/campaigns.csv").exists()
    assert not (destination / "data/pilot/manifests/5site-candidates-v1.json").exists()
    assert not (destination / "extension/node_modules").exists()
    assert not (destination / ".git").exists()

    inventory_path = destination / "migration_inventory.json"
    inventory_raw = inventory_path.read_text(encoding="utf-8")
    inventory = json.loads(inventory_raw)
    assert str(source) not in inventory_raw
    rows = {row["relative_path"]: row["sha256"] for row in inventory["files"]}
    assert rows["app/main.py"] == hashlib.sha256(b"safe:app/main.py").hexdigest().upper()
    assert "config/profile.enc" not in rows


def test_migration_fails_closed_for_unexpected_existing_destination_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    _source_fixture(source)
    _write(destination, "unexpected.txt", "do not overwrite")

    result = _run_migration(source, destination)

    assert result.returncode != 0
    assert "DESTINATION_NOT_EMPTY" in (result.stdout + result.stderr)
    assert not (destination / "app/main.py").exists()
    assert (destination / "unexpected.txt").read_text(encoding="utf-8") == "do not overwrite"
