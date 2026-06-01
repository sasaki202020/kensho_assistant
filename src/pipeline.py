from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path

from .config import AppConfig, load_config
from .fact_checker import write_fact_check
from .review import write_review_report
from .publish_package import assemble_publish_package
from .safety_checker import build_warnings, scan_risky_phrases, write_warnings
from .script_generator import generate_script
from .slide_generator import generate_slides
from .source_fetcher import fetch_source_document
from .subtitle_generator import write_subtitles
from .thumbnail_generator import create_thumbnail, create_thumbnail_variants
from .tts_generator import concat_audio_files, synthesize_slide_audio
from .video_renderer import render_video
from .youtube_meta_generator import write_youtube_meta


def _slugify(topic: str, official_url: str | None) -> str:
    digest_src = topic + "|" + (official_url or "")
    digest = hashlib.sha1(digest_src.encode("utf-8")).hexdigest()[:10]
    base = re.sub(r"[^A-Za-z0-9]+", "-", topic).strip("-").lower()
    if not base:
        base = f"topic-{digest}"
    elif base.isdigit() or len(base) < 4:
        base = f"{base}-{digest}"
    return base[:60]


def _write_text(output_dir: Path, filename: str, content: str) -> Path:
    path = output_dir / filename
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path


def run_pipeline(
    topic: str,
    official_url: str | None,
    config_path: Path,
    output_suffix: str | None = None,
) -> dict[str, object]:
    config = load_config(config_path) if config_path.exists() else AppConfig()
    slug = _slugify(topic, official_url)
    if output_suffix:
        slug = f"{slug}-{output_suffix.strip('-')}"
    output_dir = Path(config.output_root) / slug
    output_dir.mkdir(parents=True, exist_ok=True)

    source = fetch_source_document(topic, official_url, output_dir)
    package = generate_script(topic, source, config)
    scenes_json_path = output_dir / "scenes.json"
    scenes_json_path.write_text(json.dumps(package.scenes_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    script_path = _write_text(output_dir, "script.md", package.script_markdown)
    narration_path = _write_text(output_dir, "narration.txt", package.narration_text)

    slide_paths = generate_slides(package.scenes, output_dir, config)

    audio_paths: list[Path] = []
    durations: list[float] = []
    for index, scene in enumerate(package.scenes, start=1):
        audio_path, duration = synthesize_slide_audio(scene, output_dir, config, index)
        audio_paths.append(audio_path)
        durations.append(duration)

    narration_audio = concat_audio_files(audio_paths, output_dir / "narration.wav")
    subtitles_path = write_subtitles(package.scenes, durations, output_dir / "subtitles.srt")
    video_path = render_video(
        slide_paths=slide_paths,
        audio_path=narration_audio,
        subtitles_path=subtitles_path,
        output_path=output_dir / "video.mp4",
        durations=durations,
    )
    thumbnail_path = create_thumbnail(topic, slide_paths[0], output_dir, config)
    thumbnail_variants = create_thumbnail_variants(topic, output_dir, config)
    youtube_meta_path = write_youtube_meta(output_dir, topic, source, package)
    facts_path = write_fact_check(output_dir, source, package)
    warnings = build_warnings(source, package) + scan_risky_phrases(youtube_meta_path.read_text(encoding="utf-8")) + package.warnings
    warnings_path = write_warnings(output_dir, warnings)
    review_path = write_review_report(output_dir)
    publish_artifacts = assemble_publish_package(output_dir, source, package)

    return {
        "output_dir": str(output_dir),
        "files": {
            "video": str(video_path),
            "thumbnail": str(thumbnail_path),
            "thumbnail_A": str(thumbnail_variants[0]),
            "thumbnail_B": str(thumbnail_variants[1]),
            "thumbnail_C": str(thumbnail_variants[2]),
            "youtube_meta": str(youtube_meta_path),
            "script": str(script_path),
            "narration": str(narration_path),
            "slides": str(output_dir / "slides"),
            "subtitles": str(subtitles_path),
            "sources": str(output_dir / "sources.txt"),
            "sources_summary": str(output_dir / "sources_summary.md"),
            "scenes": str(scenes_json_path),
            "facts_check": str(facts_path),
            "warnings": str(warnings_path),
            "review_report": str(review_path),
            "final_video_check": str(publish_artifacts["final_video_check"]),
            "publish_checklist": str(publish_artifacts["publish_checklist"]),
            "thumbnails_review": str(publish_artifacts["thumbnails_review"]),
            "publish_ready_report": str(publish_artifacts["publish_ready_report"]),
            "publish_package": str(publish_artifacts["publish_dir"]),
            "filmora_not_used_reason": str(publish_artifacts["filmora_not_used_reason"]),
        },
    }
