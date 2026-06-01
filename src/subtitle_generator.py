from __future__ import annotations

from pathlib import Path

from .script_generator import SlidePlan


def _format_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_subtitles(
    slides: list[SlidePlan],
    durations: list[float],
    output_path: Path,
) -> Path:
    lines: list[str] = []
    current = 0.0
    for index, (slide, duration) in enumerate(zip(slides, durations), start=1):
        start = current
        end = current + max(duration, 1.0)
        current = end
        text = slide.narration.replace("\n", " ").strip()
        lines.extend(
            [
                str(index),
                f"{_format_timestamp(start)} --> {_format_timestamp(end)}",
                text,
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
