from __future__ import annotations

import subprocess
from pathlib import Path


def _render_animated_slide_segment(slide_path: Path, duration: float, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filter_expr = (
        "fps=30,"
        "scale=2000:1125,"
        "crop=1920:1080:"
        "x='40+22*sin(2*PI*t/7)':"
        "y='22+14*cos(2*PI*t/6)',"
        "format=yuv420p"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-t",
            f"{max(duration, 1.0):.3f}",
            "-i",
            slide_path.resolve().as_posix(),
            "-vf",
            filter_expr,
            "-an",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            output_path.name,
        ],
        check=True,
        capture_output=True,
        text=False,
        cwd=output_path.parent,
    )
    return output_path


def render_video(
    slide_paths: list[Path],
    audio_path: Path,
    subtitles_path: Path,
    output_path: Path,
    durations: list[float],
) -> Path:
    if len(slide_paths) != len(durations):
        raise ValueError("slide_paths and durations length mismatch")

    segment_dir = output_path.parent / "animated_segments"
    segment_paths: list[Path] = []
    for index, (slide_path, duration) in enumerate(zip(slide_paths, durations), start=1):
        segment_path = segment_dir / f"segment_{index:02d}.mp4"
        segment_paths.append(_render_animated_slide_segment(slide_path, duration, segment_path))

    list_file = output_path.parent / "slides_concat.txt"
    with list_file.open("w", encoding="utf-8") as handle:
        for segment_path in segment_paths:
            handle.write(f"file '{segment_path.resolve().as_posix()}'\n")

    subtitle_path = subtitles_path.resolve().as_posix().replace(":", r"\:")
    subtitle_filter = (
        f"subtitles='{subtitle_path}'"
        f":force_style='FontName=Meiryo,FontSize=28,Alignment=2,MarginV=42'"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file.name,
            "-i",
            audio_path.resolve().as_posix(),
            "-vf",
            subtitle_filter,
            "-r",
            "30",
            "-fps_mode",
            "cfr",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-shortest",
            output_path.name,
        ],
        check=True,
        capture_output=True,
        text=False,
        cwd=output_path.parent,
    )
    return output_path
