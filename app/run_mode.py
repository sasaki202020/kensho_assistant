from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import CONFIG_DIR


RUN_MODES = {"mock", "dry_run", "review"}
RUN_MODE_CONFIG_JSON = CONFIG_DIR / "run_mode.json"


def normalize_run_mode(value: str | None, default: str = "dry_run") -> str:
    mode = (value or default).strip().lower()
    if mode not in RUN_MODES:
        raise ValueError(f"unsupported KENSHO_RUN_MODE: {mode}")
    return mode


def get_run_mode(config_path: str | Path | None = None) -> str:
    env_mode = os.environ.get("KENSHO_RUN_MODE")
    if env_mode:
        return normalize_run_mode(env_mode)
    path = Path(config_path) if config_path else RUN_MODE_CONFIG_JSON
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return normalize_run_mode(str(data.get("run_mode", "")))
    return "dry_run"
