from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_ISOLATED_FILES = [
    "shared/messages.js",
    "shared/config.js",
    "shared/field-types.js",
    "shared/redaction.js",
    "shared/normalization.js",
    "shared/form-fingerprint.js",
    "shared/audit-log.js",
    "content/isolated-guard.js",
    "content/field-matcher.js",
    "content/form-detector.js",
    "content/form-filler.js",
    "content/overlay.js",
]
EXCLUDED_PARTS = {
    "tests",
    "__pycache__",
    "node_modules",
    "profile.enc",
    ".env",
}


@dataclass(frozen=True)
class BuildResult:
    output_dir: Path
    origins: tuple[str, ...]
    build_sha256: str


def _normalize_origin(value: object) -> str:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid_approved_origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("invalid_approved_origin")
    if parsed.path not in {"", "/"}:
        raise ValueError("invalid_approved_origin")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    default_port = 443 if parsed.scheme == "https" else 80
    port = f":{parsed.port}" if parsed.port and parsed.port != default_port else ""
    return f"{parsed.scheme}://{host}{port}"


def load_approved_origins(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("origins"), list):
        raise ValueError("invalid_approved_origins_config")
    return sorted({_normalize_origin(item) for item in payload["origins"]})


def _copy_source(source_dir: Path, destination: Path) -> None:
    for source in sorted(source_dir.rglob("*")):
        relative = source.relative_to(source_dir)
        if source.is_dir() or any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if relative.name == "manifest.json":
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _build_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def build_dedicated_extension(
    *,
    source_dir: Path,
    output_dir: Path,
    approved_origins_path: Path,
    isolated_files: list[str] | None = None,
) -> BuildResult:
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    origins = load_approved_origins(approved_origins_path)
    if not origins:
        raise ValueError("approved_origins_empty")
    matches = [f"{origin}/*" for origin in origins]
    source_manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest = dict(source_manifest)
    manifest["permissions"] = [
        permission
        for permission in source_manifest.get("permissions", [])
        if permission != "activeTab"
    ]
    manifest.pop("optional_host_permissions", None)
    manifest["host_permissions"] = matches
    manifest["content_scripts"] = [
        {
            "matches": matches,
            "js": ["content/submit-guard.js"],
            "run_at": "document_start",
            "all_frames": False,
            "world": "MAIN",
        },
        {
            "matches": matches,
            "js": list(isolated_files or DEFAULT_ISOLATED_FILES),
            "run_at": "document_idle",
            "all_frames": False,
            "world": "ISOLATED",
        },
    ]

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kensho-extension-build-", dir=output_dir.parent) as temp:
        staging = Path(temp) / "extension"
        staging.mkdir()
        _copy_source(source_dir, staging)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for required in ["content/submit-guard.js", *(isolated_files or DEFAULT_ISOLATED_FILES)]:
            if not (staging / required).is_file():
                raise ValueError(f"extension_build_input_missing:{required}")
        build_sha256 = _build_hash(staging)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(staging, output_dir)
    return BuildResult(output_dir, tuple(origins), build_sha256)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the exact-origin dedicated Chrome extension")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).parents[1])
    args = parser.parse_args()
    root = args.project_root.resolve()
    result = build_dedicated_extension(
        source_dir=root / "extension",
        output_dir=root / "build" / "extension",
        approved_origins_path=root / "config" / "approved_origins.json",
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "output_dir": str(result.output_dir),
                "approved_origins": list(result.origins),
                "build_sha256": result.build_sha256,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
