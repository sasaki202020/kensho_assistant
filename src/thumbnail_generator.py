from __future__ import annotations

from pathlib import Path

from .config import AppConfig
from .slide_generator import generate_thumbnail, generate_thumbnail_variants


def create_thumbnail(
    topic: str,
    first_slide_path: Path,
    output_dir: Path,
    config: AppConfig,
) -> Path:
    output_path = output_dir / "thumbnail.png"
    return generate_thumbnail(topic, first_slide_path, output_path, config)


def create_thumbnail_variants(topic: str, output_dir: Path, config: AppConfig) -> list[Path]:
    return generate_thumbnail_variants(topic, output_dir, config)
