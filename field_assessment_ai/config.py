from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _parse_cors_origins(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ("*",)
    values = [value.strip() for value in raw.split(",")]
    filtered = [value for value in values if value]
    return tuple(filtered) if filtered else ("*",)


def _to_path(raw: str | None, default: Path) -> Path:
    if not raw:
        return default
    return Path(raw).expanduser()


@dataclass(slots=True)
class AppSettings:
    app_name: str = "現場査定AI v0.1"
    version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8001
    api_prefix: str = "/api/v0"
    runtime_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "runtime")
    cors_origins: tuple[str, ...] = ("*",)

    @property
    def database_path(self) -> Path:
        return self.runtime_root / "field_assessment_ai.sqlite3"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.resolve().as_posix()}"

    @property
    def upload_dir(self) -> Path:
        return self.runtime_root / "uploads"

    def ensure_directories(self) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


def load_settings() -> AppSettings:
    base_runtime = Path(__file__).resolve().parent / "runtime"
    runtime_root = _to_path(os.getenv("FIELD_ASSESSMENT_AI_RUNTIME_ROOT"), base_runtime)
    host = os.getenv("FIELD_ASSESSMENT_AI_HOST", "127.0.0.1")
    port = int(os.getenv("FIELD_ASSESSMENT_AI_PORT", "8001"))
    api_prefix = os.getenv("FIELD_ASSESSMENT_AI_API_PREFIX", "/api/v0")
    cors_origins = _parse_cors_origins(os.getenv("FIELD_ASSESSMENT_AI_CORS_ORIGINS"))
    return AppSettings(
        host=host,
        port=port,
        api_prefix=api_prefix,
        runtime_root=runtime_root,
        cors_origins=cors_origins,
    )

